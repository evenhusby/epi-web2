# epiport.org (v2)

Institutional site for EPI AS — static Astro frontend + nightly-generated
public data. See `epiport-handoff.md` for the full brief (architecture,
design tokens, content, and open TODOs) and `epiport-prototype.html` for
the original self-contained visual reference this was ported from.

## Structure

- `src/pages/index.astro`, `src/pages/en/index.astro` — the two locales
  (`no` at `/`, `en` at `/en/`), via Astro's built-in i18n routing.
- `src/components/` — Hero, MapApp (stat band + interactive map + port
  panel), About, Roles.
- `src/lib/map-app.ts` — the interactive map/panel, ported from the
  prototype's inline script (D3, click-to-select a port, aggregate view).
- `src/lib/i18n.ts` — the NO/EN string dictionary.
- `public/api/summary.json`, `public/api/ports.geojson` — placeholder data
  matching the documented contract; baked into the static build. Replace
  with real output from `tools/generate_public_json.py` once wired up.

## Develop

```
npm install
npm run dev
```

## Deploy (Railway)

Mirrors the `evenhusby/epi-pilot` repo's Railway config-as-code pattern:

- `railway.toml` + `Dockerfile` — the static site service (build with
  `npm run build`, serve `dist/` via `serve`).
- `railway.cron.toml` + `Dockerfile.cron` + `tools/generate_public_json.py`
  — a nightly job scaffold for the epi_v2 export. **Not wired end-to-end
  yet** — see the docstring in `generate_public_json.py` for what's left
  (real epi_v2 queries, and a decision on how the generated files reach
  the live site: shared Volume + small read API, or a data-only commit
  that triggers a rebuild).

No hardcoded Railway tokens or project/service IDs in this repo — set
`RAILWAY_API_TOKEN` etc. as Railway environment variables if/when the
redeploy-trigger path is wired up, not in source.

## Known gaps (from epiport-handoff.md)

1. DNV wording needs revisiting at the 2027 handover.
2. Which per-port fields are public (esp. `avg_score`) isn't settled.
3. `tools/generate_public_json.py` has placeholder SQL — needs the real
   epi_v2 schema.
4. Coastlines are a hand-drawn illustrative placeholder — swap for
   Natural Earth 1:50m (via MapLibre, or keep D3).
5. No redirect map from the old Squarespace URLs yet.
6. Full port list/coordinates should come from the database/WPI, not the
   17-port placeholder set carried over from the prototype.
