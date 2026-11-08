// Cloudflare Pages Function: forwards the app's data lookups to the open public APIs.

const DEFAULT_AGENT = "Sykkelturen/1.0 (+https://github.com/steinwulvik/Sykkelturen)";

function json(status, body, cache = "no-store") {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json; charset=utf-8", "Cache-Control": cache },
  });
}

function coords(params) {
  const lat = Number.parseFloat(params.get("lat") ?? "");
  const lon = Number.parseFloat(params.get("lon") ?? "");
  if (!Number.isFinite(lat) || !Number.isFinite(lon) || lat < -90 || lat > 90 || lon < -180 || lon > 180) {
    throw new Error("Ugyldige koordinater");
  }
  return { lat, lon };
}

async function proxy(url, headers, contentType, timeoutMs = 25000) {
  try {
    const res = await fetch(url, { headers, signal: AbortSignal.timeout(timeoutMs) });
    if (!res.ok) return json(502, { error: `Tjenesten svarte med status ${res.status}` });
    return new Response(res.body, {
      status: 200,
      headers: { "Content-Type": contentType, "Cache-Control": "public, max-age=300" },
    });
  } catch (err) {
    return json(502, { error: String(err?.message || err) });
  }
}

async function postJson(url, body, headers, timeoutMs = 25000) {
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...headers },
    body: JSON.stringify(body),
    signal: AbortSignal.timeout(timeoutMs),
  });
  if (!res.ok) throw new Error(`status ${res.status}`);
  return res.json();
}

async function geocode(params, agent) {
  const q = (params.get("q") || "").trim();
  if (!q || q.length > 160) return json(400, { error: "Skriv inn et startsted eller reisemål." });
  const url = "https://nominatim.openstreetmap.org/search?" +
    new URLSearchParams({ q, format: "jsonv2", limit: "1", countrycodes: "no" });
  try {
    const res = await fetch(url, { headers: { "User-Agent": agent }, signal: AbortSignal.timeout(20000) });
    if (!res.ok) throw new Error(`status ${res.status}`);
    const result = await res.json();
    if (!result.length) {
      return json(404, { error: `Fant ikke «${q}» i Norge. Prøv et mer presist stedsnavn eller en adresse.` });
    }
    const place = result[0];
    return json(200, { lat: Number(place.lat), lon: Number(place.lon), name: place.display_name || q }, "public, max-age=86400");
  } catch (err) {
    return json(502, { error: `Kunne ikke slå opp stedet: ${err?.message || err}` });
  }
}

function elevation(params, agent) {
  let query;
  try {
    const raw = params.get("points");
    if (raw) {
      const points = JSON.parse(raw);
      if (!Array.isArray(points) || points.length < 1 || points.length > 30) {
        throw new Error("Oppgi mellom 1 og 30 koordinatpunkter.");
      }
      const normalized = points.map((p) => {
        if (!Array.isArray(p) || p.length < 2) throw new Error("Hvert punkt må inneholde lengdegrad og breddegrad.");
        const lon = Number(p[0]);
        const lat = Number(p[1]);
        if (!Number.isFinite(lat) || !Number.isFinite(lon) || lat < -90 || lat > 90 || lon < -180 || lon > 180) {
          throw new Error("Ugyldige koordinater");
        }
        return [lon, lat];
      });
      query = { koordsys: "4326", punkter: JSON.stringify(normalized) };
    } else {
      const { lat, lon } = coords(params);
      query = { koordsys: "4326", nord: String(lat), ost: String(lon) };
    }
  } catch (err) {
    return json(400, { error: `Høydeoppslag: ${err.message}` });
  }
  const url = "https://ws.geonorge.no/hoydedata/v1/punkt?" + new URLSearchParams(query);
  return proxy(url, { "User-Agent": agent }, "application/json; charset=utf-8", 60000);
}

function airquality(params, agent) {
  let c;
  try { c = coords(params); } catch (err) { return json(400, { error: `Luftkvalitetsvarsel: ${err.message}` }); }
  const url = "https://api.met.no/weatherapi/airqualityforecast/0.1/?" +
    new URLSearchParams({ lat: String(c.lat), lon: String(c.lon), areaclass: "grunnkrets" });
  return proxy(url, { "User-Agent": agent }, "application/json; charset=utf-8");
}

async function transit(params) {
  let c;
  try { c = coords(params); } catch (err) { return json(400, { error: `Holdeplasser: ${err.message}` }); }
  const query = `{ nearest(latitude: ${c.lat}, longitude: ${c.lon}, maximumDistance: 3000, maximumResults: 12, filterByPlaceTypes: [stopPlace], filterByInUse: true) { edges { node { place { ... on StopPlace { id name latitude longitude } } } } } }`;
  try {
    const result = await postJson("https://api.entur.io/journey-planner/v3/graphql", { query },
      { "ET-Client-Name": "steinwulvik-sykkelturen" });
    if (result.errors?.length) throw new Error(result.errors[0].message || "Entur GraphQL-feil");
    return json(200, result.data?.nearest || {}, "public, max-age=300");
  } catch (err) {
    return json(502, { error: `Entur kunne ikke hente stopp i nærheten: ${err?.message || err}` });
  }
}

function weather(params, agent) {
  let c;
  try { c = coords(params); } catch (err) { return json(400, { error: `Værvarsel: ${err.message}` }); }
  const url = "https://api.met.no/weatherapi/locationforecast/2.0/compact?" +
    new URLSearchParams({ lat: c.lat.toFixed(4), lon: c.lon.toFixed(4) });
  return proxy(url, { "User-Agent": agent }, "application/json; charset=utf-8");
}

function route(params, agent) {
  const nums = ["lon1", "lat1", "lon2", "lat2"].map((k) => Number.parseFloat(params.get(k) ?? ""));
  if (!nums.every(Number.isFinite)) return json(400, { error: "Ugyldige koordinater" });
  const [lon1, lat1, lon2, lat2] = nums;
  const url = "https://brouter.de/brouter?" + new URLSearchParams({
    lonlats: `${lon1},${lat1}|${lon2},${lat2}`, profile: "trekking", alternativeidx: "0", format: "geojson",
  });
  return proxy(url, { "User-Agent": agent }, "application/geo+json; charset=utf-8", 45000);
}

export async function onRequestGet({ request, env }) {
  const url = new URL(request.url);
  const params = url.searchParams;
  const agent = env.MET_USER_AGENT || DEFAULT_AGENT;
  switch (url.pathname) {
    case "/api/geocode": return geocode(params, agent);
    case "/api/elevation": return elevation(params, agent);
    case "/api/airquality": return airquality(params, agent);
    case "/api/transit": return transit(params);
    case "/api/weather": return weather(params, agent);
    case "/api/cycle/route": return route(params, agent);
    default: return json(404, { error: "Ukjent adresse" });
  }
}
