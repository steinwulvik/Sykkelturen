# Rutevær og terreng

En lokal læringsapp som viser en sykkelrute mellom to steder, terrenghøyde langs ruta, vær ved start/midtveis/mål og luftkvalitetsvarsel for området ved rutemidtpunktet.

## Start lokalt

Installer Python 3. Installer avhengighetene og start serveren fra denne mappen:

```powershell
python -m pip install -r requirements.txt
python server.py
```

Åpne http://127.0.0.1:8002. Hold terminalvinduet åpent mens appen kjører. Stopp serveren med Ctrl+C.

## Datakilder

- **Kartverket:** topografisk kart og høydedata.
- **MET:** værvarsel og modellert luftkvalitetsvarsel. Luftkvalitet vises som varsel, ikke som sanntidsmålinger fra en lokal sensor.
- **Entur:** aktive kollektivholdeplasser nær utvalgte punkter langs ruta. Oppslaget bruker `ET-Client-Name` og spør etter holdeplasser innenfor 3 km rundt hvert punkt; nettsiden viser dem når de ligger inntil 1,2 km fra rutelinjen.
- **BRouter:** sykkelrute.
- **OpenStreetMap Nominatim:** oppslag av stedsnavn. Bruk oppslag med måte; tjenesten er felles og har bruksregler.

Trafikkestimat og trafikkmeldinger er tatt ut av denne førsteversjonen. Luftkvalitetsvarselet forenkles til Bra, Moderat eller Dårlig basert på METs samlede AQI-varsel.

MET ber om en beskrivende `User-Agent`. Lokalt brukes `TryggSykkeltur/0.2 (lokalt læringsprosjekt)`. Før offentlig publisering bør denne settes til en identifiserende verdi med kontaktinformasjon, for eksempel ved å sette miljøvariabelen `MET_USER_AGENT` i driftsmiljøet.

Høydeprofilen bruker ni punkter jevnt fordelt langs ruta og viser meter over havet mot kilometer. Punktene gir en forenklet profil, ikke en detaljert veianalyse. Vær og luftkvalitet gjelder prognoseområder/punkter og kan avvike lokalt. Ingen av kortene er en full vurdering av sykkelsikkerhet.

## Publisering

Opprett en Web Service i Render fra repoet `steinwulvik/Sykkelturen`, med `pip install -r requirements.txt` som Build Command og `python server.py` som Start Command. Sett `MET_USER_AGENT` med kontaktinformasjon i Render-miljøet før offentlig bruk.
