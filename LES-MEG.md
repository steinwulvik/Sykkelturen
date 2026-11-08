# Rutevær og terreng

En webapp som viser en sykkelrute mellom to steder, terrenghøyde langs ruta, vær ved start, midtveis og mål, luftkvalitetsvarsel for området ved rutemidtpunktet og kollektivholdeplasser nær ruta.

## Oppbygning

- `public/index.html`: hele nettsiden (kart, skjema og kort).
- `functions/api/[[path]].js`: Cloudflare Pages Function som henter data fra de åpne tjenestene under `/api/…`, slik at nettleseren bare snakker med appens eget domene.

| Adresse | Henter fra |
|---|---|
| `/api/geocode?q=` | OpenStreetMap Nominatim |
| `/api/cycle/route?lon1=&lat1=&lon2=&lat2=` | BRouter (profil «trekking») |
| `/api/elevation?points=` | Kartverket høydedata |
| `/api/weather?lat=&lon=` | MET Locationforecast |
| `/api/airquality?lat=&lon=` | MET Air Quality Forecast |
| `/api/transit?lat=&lon=` | Entur Journey Planner |

## Kjør lokalt

Installer Node.js og kjør fra denne mappen:

```bash
npx wrangler pages dev public
```

Åpne adressen Wrangler skriver ut (vanligvis http://localhost:8788).

## Publisering

Appen publiseres med Cloudflare Pages fra dette repoet: ingen byggkommando og utdatamappe `public`. Mappen `functions` blir publisert som Pages Functions. Miljøvariabelen `MET_USER_AGENT` kan settes for å identifisere appen overfor MET og Nominatim; ellers brukes en standardverdi med lenke til repoet.

## Datakilder

- **Kartverket:** topografisk kart og høydedata.
- **MET:** værvarsel og modellert luftkvalitetsvarsel. Luftkvalitet vises som varsel, ikke som sanntidsmålinger fra en lokal sensor.
- **Entur:** aktive kollektivholdeplasser innenfor 3 km rundt utvalgte punkter langs ruta. Nettsiden viser dem når de ligger inntil 1,2 km fra rutelinjen.
- **BRouter:** sykkelrute.
- **OpenStreetMap Nominatim:** oppslag av stedsnavn. Tjenesten er felles og har bruksregler, så oppslagene holdes få.

## Begrensninger

- Luftkvalitetsvarselet forenkles til Bra, Moderat eller Dårlig basert på METs samlede AQI-varsel.
- Høydeprofilen bruker ni punkter jevnt fordelt langs ruta og viser meter over havet mot kilometer. Den gir en forenklet profil, ikke en detaljert veianalyse.
- Vær og luftkvalitet gjelder prognoseområder og punkter og kan avvike lokalt.
- Appen viser ikke trafikkmengde eller trafikkmeldinger, og ingen av kortene er en full vurdering av sykkelsikkerhet.
