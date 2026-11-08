from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs, urlencode
from urllib.request import Request, urlopen
import json
import ssl
import certifi
import os
import urllib.error
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from concurrent.futures import ThreadPoolExecutor

ROOT = Path(__file__).resolve().parent
TLS = ssl.create_default_context(cafile=certifi.where())
POINT_CACHE = {"expires": 0, "data": None}
ESTIMATE_CACHE = {}
TRAFFIC_API = "https://trafikkdata-api.atlas.vegvesen.no/"
MET_USER_AGENT = os.environ.get("MET_USER_AGENT", "TryggSykkeltur/0.2 (lokalt læringsprosjekt)")


def fetch_json(url, method="GET", body=None, headers=None, timeout=30):
    request_headers = {"User-Agent": "TryggSykkeltur/0.1 (learning project)"}
    if headers:
        request_headers.update(headers)
    data = json.dumps(body).encode("utf-8") if body is not None else None
    if data is not None:
        request_headers.setdefault("Content-Type", "application/json")
    req = Request(url, data=data, headers=request_headers, method=method)
    with urlopen(req, timeout=timeout, context=TLS) as response:
        return json.loads(response.read().decode("utf-8"))


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        if parsed.path == "/api/geocode":
            query = params.get("q", [""])[0].strip()
            if not query or len(query) > 160:
                self.send_json(400, {"error": "Skriv inn et startsted eller reisemål."})
            else:
                url = "https://nominatim.openstreetmap.org/search?" + urlencode({"q": query, "format": "jsonv2", "limit": "1", "countrycodes": "no"})
                try:
                    result = fetch_json(url, headers={"User-Agent": "TryggSykkeltur/0.1 (learning project)"}, timeout=20)
                    if not result:
                        self.send_json(404, {"error": f"Fant ikke «{query}» i Norge. Prøv et mer presist stedsnavn eller en adresse."})
                    else:
                        place = result[0]
                        self.send_json(200, {"lat": float(place["lat"]), "lon": float(place["lon"]), "name": place.get("display_name", query)})
                except Exception as exc:
                    self.send_json(502, {"error": f"Kunne ikke slå opp stedet: {exc}"})
        elif parsed.path == "/api/elevation":
            try:
                if params.get("points"):
                    points = json.loads(params["points"][0])
                    if not isinstance(points, list) or not 1 <= len(points) <= 30:
                        raise ValueError("Oppgi mellom 1 og 30 koordinatpunkter.")
                    normalized = []
                    for point in points:
                        if not isinstance(point, list) or len(point) < 2:
                            raise ValueError("Hvert punkt må inneholde lengdegrad og breddegrad.")
                        lon, lat = map(float, point[:2])
                        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                            raise ValueError("Ugyldige koordinater")
                        normalized.append([lon, lat])
                    query = {"koordsys": 4326, "punkter": json.dumps(normalized, separators=(",", ":"))}
                else:
                    lat = float(params.get("lat", [""])[0]); lon = float(params.get("lon", [""])[0])
                    if not (-90 <= lat <= 90 and -180 <= lon <= 180): raise ValueError("Ugyldige koordinater")
                    query = {"koordsys": 4326, "nord": lat, "ost": lon}
                url = "https://ws.geonorge.no/hoydedata/v1/punkt?" + urlencode(query)
                self.proxy(url, {"User-Agent": "TryggSykkeltur/0.1 (learning project)"}, "application/json; charset=utf-8", timeout=60)
            except Exception as exc:
                self.send_json(400, {"error": f"Høydeoppslag: {exc}"})
        elif parsed.path == "/api/airquality":
            try:
                lat = float(params.get("lat", [""])[0]); lon = float(params.get("lon", [""])[0])
                if not (-90 <= lat <= 90 and -180 <= lon <= 180): raise ValueError("Ugyldige koordinater")
                url = "https://api.met.no/weatherapi/airqualityforecast/0.1/?" + urlencode({"lat": lat, "lon": lon, "areaclass": "grunnkrets"})
                self.proxy(url, {"User-Agent": MET_USER_AGENT}, "application/json; charset=utf-8")
            except Exception as exc:
                self.send_json(400, {"error": f"Luftkvalitetsvarsel: {exc}"})
        elif parsed.path == "/api/air":
            try:
                lat = float(params.get("lat", [""])[0]); lon = float(params.get("lon", [""])[0])
                if not (-90 <= lat <= 90 and -180 <= lon <= 180): raise ValueError("Ugyldige koordinater")
                url = f"https://api.nilu.no/aq/utd/{lat}/{lon}/10?" + urlencode({"method": "within"})
                self.proxy(url, {"User-Agent": "TryggSykkeltur/0.1 (learning project)"}, "application/json; charset=utf-8", timeout=60)
            except Exception as exc:
                self.send_json(400, {"error": f"Luftkvalitetsoppslag: {exc}"})
        elif parsed.path == "/api/transit":
            try:
                lat = float(params.get("lat", [""])[0]); lon = float(params.get("lon", [""])[0])
                if not (-90 <= lat <= 90 and -180 <= lon <= 180): raise ValueError("Ugyldige koordinater")
                query = """{ nearest(latitude: %s, longitude: %s, maximumDistance: 3000, maximumResults: 12, filterByPlaceTypes: [stopPlace], filterByInUse: true) { edges { node { place { ... on StopPlace { id name latitude longitude } } } } } }""" % (lat, lon)
                result = fetch_json("https://api.entur.io/journey-planner/v3/graphql", "POST", {"query": query}, {"ET-Client-Name": "tryggsykkeltur-laeringsapp"}, timeout=25)
                if result.get("errors"):
                    raise RuntimeError(str(result["errors"][0].get("message", "Entur GraphQL-feil")))
                self.send_json(200, result.get("data", {}).get("nearest", {}), "public, max-age=300")
            except Exception as exc:
                self.send_json(502, {"error": f"Entur kunne ikke hente stopp i nærheten: {exc}"})
        elif parsed.path == "/api/weather":
            lat = params.get("lat", ["59.9086"])[0]
            lon = params.get("lon", ["10.7345"])[0]
            url = "https://api.met.no/weatherapi/locationforecast/2.0/compact?" + urlencode({"lat": lat, "lon": lon})
            self.proxy(url, {"User-Agent": MET_USER_AGENT}, "application/json; charset=utf-8")
        elif parsed.path == "/api/cycle/route":
            lon1 = params.get("lon1", ["7.9956"])[0]
            lat1 = params.get("lat1", ["58.1467"])[0]
            lon2 = params.get("lon2", ["8.7669"])[0]
            lat2 = params.get("lat2", ["58.4617"])[0]
            route_url = "https://brouter.de/brouter?" + urlencode({"lonlats": f"{lon1},{lat1}|{lon2},{lat2}", "profile": "trekking", "alternativeidx": "0", "format": "geojson"})
            self.proxy(route_url, {"User-Agent": "TryggSykkeltur/0.1 (learning project)"}, "application/geo+json; charset=utf-8", timeout=45)
        elif parsed.path == "/api/cycle/traffic-points":
            self.traffic_points()
        elif parsed.path == "/api/cycle/history":
            point_id = params.get("id", [""])[0]
            if not point_id or len(point_id) > 80:
                self.send_json(400, {"error": "Ugyldig målepunkt-ID"})
            else:
                self.traffic_history(point_id)
        elif parsed.path == "/api/cycle/traffic-estimate":
            point_id = params.get("id", [""])[0]
            if not point_id or len(point_id) > 80:
                self.send_json(400, {"error": "Ugyldig målepunkt-ID"})
            else:
                self.traffic_estimate(point_id)
        elif parsed.path == "/":
            self.send_file("sykkelturen-dynamisk.html")
        elif parsed.path in ("/sykkelturen", "/sykkelturen.html"):
            self.send_file("sykkelturen-dynamisk.html")
        else:
            self.send_error(404)

    def send_file(self, name):
        try:
            body = (ROOT / name).read_bytes()
            content_type = "text/html; charset=utf-8"
            if name.endswith(".js"):
                content_type = "application/javascript; charset=utf-8"
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except FileNotFoundError:
            self.send_error(404)

    def send_json(self, status, body, cache="no-store"):
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", cache)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def traffic_points(self):
        now = time.time()
        if POINT_CACHE["data"] is not None and now < POINT_CACHE["expires"]:
            self.send_json(200, POINT_CACHE["data"], "public, max-age=21600")
            return
        query = """{ trafficRegistrationPoints(searchQuery: { roadCategoryIds: [E, R, F] }) { id name location { coordinates { latLon { lat lon } } } } }"""
        try:
            result = fetch_json(TRAFFIC_API, "POST", {"query": query}, timeout=45)
            if result.get("errors"):
                raise RuntimeError(str(result["errors"][0].get("message", "GraphQL-feil")))
            points = result.get("data", {}).get("trafficRegistrationPoints", [])
            POINT_CACHE["data"] = points
            POINT_CACHE["expires"] = now + 21600
            self.send_json(200, points, "public, max-age=21600")
        except Exception as exc:
            self.send_json(502, {"error": f"Trafikkdata-punkter: {exc}"})

    def traffic_history(self, point_id):
        safe_id = json.dumps(point_id)
        query = f"""{{ trafficData(trafficRegistrationPointId: {safe_id}) {{ volume {{ average {{ daily {{ byYear {{ year total {{ volume {{ average confidenceInterval {{ lowerBound upperBound }} }} coverage {{ percentage }} }} }} }} }} }} }} }}"""
        try:
            result = fetch_json(TRAFFIC_API, "POST", {"query": query})
            if result.get("errors"):
                raise RuntimeError(str(result["errors"][0].get("message", "GraphQL-feil")))
            rows = result.get("data", {}).get("trafficData", {}).get("volume", {}).get("average", {}).get("daily", {}).get("byYear", [])
            self.send_json(200, rows, "public, max-age=21600")
        except Exception as exc:
            self.send_json(502, {"error": f"Historiske trafikkdata: {exc}"})

    def traffic_estimate(self, point_id):
        cached = ESTIMATE_CACHE.get(point_id)
        if cached and time.time() < cached[0]:
            self.send_json(200, cached[1], "public, max-age=900")
            return
        now = datetime.now(ZoneInfo("Europe/Oslo")).replace(minute=0, second=0, microsecond=0)
        target = now - timedelta(days=7)
        periods = [target - timedelta(days=7 * i) for i in range(7, -1, -1)]

        def fetch_hour(start):
            end = start + timedelta(hours=1)
            start_text = start.isoformat(timespec="seconds")
            end_text = end.isoformat(timespec="seconds")
            safe_id = json.dumps(point_id)
            safe_from = json.dumps(start_text)
            safe_to = json.dumps(end_text)
            query = f"""{{ trafficData(trafficRegistrationPointId: {safe_id}) {{ volume {{ byHour(from: {safe_from}, to: {safe_to}) {{ edges {{ node {{ from total {{ volumeNumbers {{ volume }} coverage {{ percentage }} }} }} }} }} }} }} }}"""
            result = fetch_json(TRAFFIC_API, "POST", {"query": query}, timeout=30)
            if result.get("errors"):
                raise RuntimeError(str(result["errors"][0].get("message", "GraphQL-feil")))
            edges = result.get("data", {}).get("trafficData", {}).get("volume", {}).get("byHour", {}).get("edges", [])
            if not edges:
                return None
            node = edges[0].get("node", {})
            total = node.get("total", {})
            volume = total.get("volumeNumbers", {}).get("volume")
            coverage = total.get("coverage", {}).get("percentage")
            if volume is None:
                return None
            return {"year": start.strftime("%d.%m"), "date": start.date().isoformat(), "hour": start.hour, "total": {"volume": {"average": float(volume)}}, "coverage": coverage}

        try:
            with ThreadPoolExecutor(max_workers=2) as pool:
                results = list(pool.map(fetch_hour, periods))
            rows = [row for row in results if row is not None]
            ESTIMATE_CACHE[point_id] = (time.time() + 900, rows)
            self.send_json(200, rows, "public, max-age=900")
        except Exception as exc:
            self.send_json(200, [{"error": f"Kunne ikke beregne estimat for trafikkmengde: {exc}"}], "no-store")

    def proxy(self, url, headers, content_type, timeout=25):
        try:
            req = Request(url, headers=headers)
            with urlopen(req, timeout=timeout, context=TLS) as response:
                data = response.read()
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Cache-Control", "public, max-age=300")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        except Exception as exc:
            self.send_json(502, {"error": str(exc)})

    def log_message(self, fmt, *args):
        print("%s - %s" % (self.log_date_time_string(), fmt % args))

if __name__ == "__main__":
    host = "0.0.0.0"
    port = int(os.environ.get("PORT", "8002"))
    server = ThreadingHTTPServer((host, port), Handler)
    print(f"Den trygge sykkelturen kjører på port {port}")
    print("Stopp serveren med Ctrl+C")
    server.serve_forever()
