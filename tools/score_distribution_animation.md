# Score distribution animation

`animate_score_distribution.py` renders a video that cycles through the
"Score distribution per call" chart for every EPI port, for use in a
PowerPoint deck.

## Data source

- `public/api/ports.geojson` and `public/api/summary.json` in this repo --
  the exact static files the deployed site (epiport.org) fetches at
  runtime (see `src/lib/map-app.ts`). No live network call is made; the
  script reads these files directly.
- Data as of `summary.json`'s `generated_at`: **2026-08-20T08:21:35Z**
  (45 active ports, 2,989 port calls YTD at that point).
- To refresh: run `tools/generate_public_json.py` against `epi_v2` first
  (see that script's docstring for the `DATABASE_URL` it needs and the
  "not wired end-to-end yet" caveat about deploying the result), then rerun
  this script.

## Chart definition, copied from the site (not reinvented)

- 4 score bands, edges at 30/50/70 -- from `generate_public_json.py`'s
  `SCORE_BAND_EDGES`, labelled `0-30`, `30-50`, `50-70`, `70-100` to match
  `src/lib/map-app.ts`'s `.dist-axis` labels exactly.
- Bar colors from `src/styles/global.css`'s `.dist-bars` rules: bands 0-1 use
  `--linje-lys`, band 2 the site's `.mid` tint, band 3 `--gronn` (the site's
  `.hi`).
- Each port's `score_distribution` is already "% of that port's own calls in
  this band" (computed that way in `generate_public_json.py`), so the video
  plots it directly on a **fixed 0-100% axis** -- unlike the on-site panel,
  which rescales each port's own 4 bars to its own max purely so the bars
  visually fill the row. The fixed axis is what makes ports of different
  sizes comparable, per the brief.
- The "All ports" opening/closing view reproduces the exact same shape as
  the live site's own "Alle havner" panel (`aggregateAll()` in
  `map-app.ts`: an unweighted, element-wise sum of every port's own
  percentages), then rescales that sum to add up to 100 so it's a valid
  percentage on the fixed axis. This keeps it visually identical in shape to
  what's on epiport.org while making the number itself meaningful.
- A faint reference outline of the "All ports" distribution is drawn behind
  every individual port's bars, so deviation from the network average is
  visible at a glance.

## Ports excluded (default `--min-calls 10`)

10 of 45 ports have fewer than 10 port calls YTD in this data pull and are
left out of the animation (still counted in the "All ports" total):

| Port | calls_ytd |
|---|---|
| Akranes | 2 |
| Bodo | 9 |
| Froya | 2 |
| Hitra | 1 |
| Klaksvik | 2 |
| Lysekil | 8 |
| Mekjarvik | 1 |
| Namsos | 0 |
| Sandane | 2 |
| Stromness | 0 |

35 ports are included, sorted by `calls_ytd` descending by default.

## Fonts

epiport.org uses Palatino Linotype/Georgia (display) and the system sans
stack (body) -- both proprietary and unavailable on Linux. The script
substitutes **Liberation Serif** and **Liberation Sans** (metrically
compatible open clones of Times/Arial, `apt-get install fonts-liberation`),
falling back to generic serif/sans-serif with a warning if that package
isn't installed. Not pixel-identical to the site's fonts, but the same
proportions and character.

## Regenerating

```bash
pip install -r tools/requirements-animation.txt
python3 tools/animate_score_distribution.py --out-dir tools/score_distribution_output
```

Requires `ffmpeg` on PATH (`apt-get install ffmpeg fonts-liberation`) and
the packages in `tools/requirements-animation.txt` (kept separate from
`tools/requirements.txt`, which is scoped to `generate_public_json.py`'s
Postgres/Railway deps).

Key parameters (see `--help` for the full list):

| Flag | Default | Meaning |
|---|---|---|
| `--seconds-per-port` | 2.5 | time on screen per port, transition included |
| `--transition` | 0.6 | seconds of eased bar transition at the start of each segment |
| `--intro-seconds` / `--outro-seconds` | 3.0 / 2.0 | hold time on the "All ports" opening/closing view |
| `--min-calls` | 10 | ports below this many calls YTD are excluded |
| `--sort` | `calls_desc` | also: `alpha`, `score_desc` |
| `--lang` | `no` | also: `en` |
| `--poster-frame` | `first` | which frame `poster.png` is grabbed from; also: `last` |

Total duration ≈ `intro_seconds + n_ports * seconds_per_port +
outro_seconds`.

## Output

- `score_distribution_animasjon.mp4` -- H.264, yuv420p, no audio.
- `score_distribution_animasjon.gif` -- 960px wide, 15fps by default
  (`--skip-gif` to omit).
- `poster.png` -- full-resolution still, for use as the PowerPoint
  thumbnail.

Video files are generated output, not committed to this repo (only this
script and doc are). Rerun the script to regenerate them from the latest
data.
