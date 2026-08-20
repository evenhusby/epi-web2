# epiport.org – nytt nettsted: overlevering til Claude Code

## Bakgrunn og mål
Dagens epiport.org kjører på Squarespace med en skjør JS-integrasjon mot EPI-databasen
(nøkkeltallene på forsiden rendres i dag tomme). Fra 1/1-2027 overtar OceanScore
markedsføring og kommunikasjon for EPI, og nettstedets rolle reduseres til en
institusjonell faktaside for EPI AS: hva EPI er, hvem som står bak, kart over
deltakerhavner og noen nøkkeltall. Squarespace erstattes av en liten kodebasert
løsning deployet på Railway.

## Arkitektur (besluttet)
- **Statisk frontend** + **lite lesende API**. Det offentlige nettstedet snakker
  aldri direkte med produksjonsdatabasen.
- En **nattlig jobb** (Railway cron / GitHub Action) genererer to filer fra
  epi_v2-skjemaet (PostgreSQL): `summary.json` og `ports.geojson`.
  API-et serverer dem med lang cache – eller de bakes inn statisk ved rebuild.
- **Rammeverkvalg står åpent**: React/Vite (kjent stack, fletting klientside)
  eller Astro (fletting på byggetid, HTML først, kart som React-island,
  NO/EN som to innholdsmapper med markdown). Astro anbefalt for dette
  nettstedet; React/Vite fullt forsvarlig.
- Kart i produksjon: MapLibre med vektorfliser, eller behold D3 og bytt
  håndtegnede kystlinjer mot Natural Earth 1:50m.
- Redirects fra dagens Squarespace-URL-struktur (/about-the-epi, /ports,
  /news/...) må settes opp ved DNS-flytting.

## Prototype (foreligger)
`epiport-prototype.html` – selvstendig fil, ingen byggetrinn, D3 fra cdnjs.
Fungerer som både visuell fasit og datakontrakt. Funksjonalitet:
- Klikkbare havnepunkter i kartet
- Havnepanel som i utgangspunktet viser aggregat for ALLE havner
  (anløpsvektet snittscore/OPS-andel, summert fordeling); valg av havn gir
  detaljer + «← Alle havner»-lenke tilbake
- Fungerende NO/EN-veksling (i18n-ordbok i JS)
- Responsiv (bruddpunkter 900px og 560px)

## Datakontrakt (definert øverst i prototypens script)
I produksjon erstattes konstantene med:
```js
const SUMMARY = await (await fetch('/api/summary.json')).json();
const PORTS   = await (await fetch('/api/ports.geojson')).json();
```

`summary.json`:
```json
{
  "generated_at": "ISO-8601",
  "year": 2026,
  "active_ports": 27,
  "port_calls_ytd": 3412,
  "sox_reduced_tonnes_ytd": 184,
  "nox_reduced_tonnes_ytd": 1260
}
```

`ports.geojson`: FeatureCollection av Point-features med properties:
`name`, `calls_ytd`, `avg_score`, `ops_share_pct`,
`nox_reduced_ytd`, `score_distribution` (array[4]: band 0–30, 30–50,
50–70, 70–100). Per-havn-aggregater ligger i properties slik at panelet
ikke trenger eget API-kall. ALLE tall i prototypen er fiktive plassholdere.

## Design: retning B «Årsrapport» (valgt av tre skisserte retninger)
Redaksjonell/trykksak-estetikk. Signaliserer EPI AS' institusjonelle rolle
som metodikk-eier (ikke kommersielt produkt – det er OceanScores domene).

Tokens (fra prototypens :root):
- `--papir #FDFCF9` (bakgrunn), `--blekk #26332F` (tekst/linjaler),
  `--blekk-lys #55605B`, `--grafitt #6B7570` (sekundær),
  `--gronn #1E5C48` (måltall/aksent), `--linje #C9C4B4`,
  `--linje-lys #E5E1D6`, `--sjo #F4F2EA` (landflate i kart)
- Display/tall: Palatino-stakk (serif). Brødtekst: system-sans.
- Struktur: tynne linjaler over hvert element; 2px blekkstrek under
  header og over footer; prikkede skillelinjer i panelet.
- Kart: strekkart – land som konturomriss, prikket gradnett, grønne
  havnepunkter, kursiv serif-etiketter, kursiv billedtekst.
- Semantikk: 2027-elementer har prikket linjal (fremtid = ennå ikke trykt);
  valgt havn markeres med tynn blekkring.

## Innhold (avstemt tekst, NO – EN speilet i prototypen)
- **Tittel:** Skipets miljøprestasjon i havn
- **Undertittel:** EPI beregner utslipp fra skip ved kai per anløp basert
  på detaljerte rapporter fra skipene.
- **Indikatorer:** Aktive havner · Anløp i år · SOx reduksjon · NOx reduksjon
- **Om EPI** («Målt, ikke sertifisert»): EPI tar utgangspunkt i faktiske
  forbrukstall og detaljert informasjon om skipets tekniske utrustning og
  operasjon ved kai. Energibruk og utslipp rapporteres per havneopphold.
  Dataene kvalitetskontrolleres av DNV.
- **Tidslinje:** 2019 etablert · 2023 Island/Orknøyene · 2026 «27 aktive
  havner» · 2027 metodikken videreføres i ESI (IKKE nevn EU MRV her)
- **Roller (4):** EPI AS (metodikk-eier) · DNV (2019–2026, drift av
  IT-løsning samt kvalitetskontroll) · OceanScore (tag «drift»,
  videreføring av DNVs arbeid samkjørt med ESI, fra 2027) · IAPH/ESI
  (rammeverk)
- **Ingen** metodikk-/PDF-seksjon inntil videre. Ingen nyhetsseksjon.
- Footer: info@epiport.org · Bergen Havn, Nøstegaten 30, 5006 Bergen ·
  © EPI AS · Drift og kommunikasjon: OceanScore

## Kjente forbehold / TODO
1. **DNV-formulering:** Om-teksten sier «kvalitetskontrolleres av DNV»
   (presens) mens rolleboksen sier 2019–2026. Korrekt frem til overgangen,
   men må oppdateres 1/1-27 – eller omformuleres nøytralt («uavhengig
   tredjepart») allerede nå.
2. **Publiseringsgrense:** Avstem med havnene/OceanScore hvilke
   per-havn-felter som skal være offentlige (særlig `avg_score`).
3. **Rolletekster:** Hold formuleringer om eierskap/struktur åpne til
   MOA er signert. «Metodikken videreføres i ESI» er valgt fordi den er
   sann uavhengig av utfall.
4. ~~SQL/jobb som genererer de to JSON-filene fra epi_v2 er ikke skrevet.~~
   Løst: `tools/generate_public_json.py` speiler nå epi-pilot-repos
   `stats.py`-logikk (scrubber-bevisst SOx, Tier I NOx-baseline, `reduced =
   max(0, baseline − actual)`). Ikke kjørt i produksjon ennå – se punkt 8
   under om dataleveranse til site-tjenesten.
5. Natural Earth-kystlinjer / MapLibre ikke implementert. (Kartet er siden
   byttet til Mapbox GL JS med ekte fliser – se README.)
6. Redirect-kart fra gamle URL-er ikke laget.
7. Havnelisten i prototypen (17 stk) er et utvalg – fullstendig liste og
   koordinater bør hentes fra databasen/WPI. `generate_public_json.py`
   henter nå faktisk alle `epi_v2.ports`-rader (filtrert på
   `is_test=false AND is_pilot=false`), så dette løses automatisk når
   jobben kjøres mot ekte data.
8. `member_since` er fjernet fra datakontrakten – epi_v2 har ikke noe
   medlemskaps-/innmeldingsdato-felt (`ports.created_at` er kun en
   synk-jobb-tidsstempel, ikke en kuratert dato), og heller ikke noe
   fungerte tredjepartskilde ble funnet. Legg til på nytt kun hvis noen
   leverer ekte data for dette.
9. Site- og cron-tjenesten kjører i separate Railway-containere med
   ephemeral filsystem – `generate_public_json.py` sine filer når ikke
   frem til den kjørende site-tjenesten før dette er koblet sammen
   (Volume + lese-API, eller commit-tilbake-til-repo). Se docstringen i
   scriptet.

## Forslag til første Claude Code-økter
1. Init repo (velg Astro eller Vite), porter prototypen inn i valgt struktur,
   behold `epiport-prototype.html` som referanse.
2. Skriv `generate_public_json.py` (eller SQL views) mot epi_v2 →
   `summary.json` + `ports.geojson` iht. kontrakten over.
3. Railway-oppsett: statisk site + cron; deretter DNS/redirects.
