#!/usr/bin/env python3
"""Nightly export from epi_v2 -> summary.json + ports.geojson.

Per epiport-handoff.md's data contract. Intended to run on a Railway cron
service (see railway.cron.toml).

The SOx/NOx actual-vs-baseline logic mirrors epi-pilot-repo's
backend/epi_pilot/api/routers/stats.py::_compute_dashboard() (scrubber-aware
SOx variant, chosen over leaderboard.py's simpler ×2-only formula since the
two disagree and stats.py's is the more complete one). "Reduced tonnes"
extends the pattern epi-pilot only applies to NOx today (its
/stats/debug/nox endpoint) to both pollutants: reduced = max(0, baseline -
actual). There is no "member_since" field anywhere in epi_v2 -- dropped
from the public contract rather than publishing a fabricated date.

NOT WIRED END-TO-END YET. This container's filesystem is ephemeral and not
shared with the site service, so writing to a local path and redeploying
does nothing by itself -- the site's Dockerfile rebuilds `public/api/*`
from git, it won't pick up files written by a separate container. Before
this is production-ready, pick one:
  (a) Mount a Railway Volume at PUBLIC_DATA_DIR on *both* this service and
      a small read API service that serves it directly (the "lite lesende
      API" option in the handoff doc), instead of baking into the static
      build; or
  (b) Have this script commit the generated files back to the repo (or an
      object store) and let that commit trigger the site's rebuild.
Redeploy-trigger below is left in as a building block for option (a)/(b),
not as a complete solution.

Required env vars:
  DATABASE_URL          epi_v2 Postgres connection string
Optional:
  PUBLIC_DATA_DIR        where to write the two files (default: public/api
                          next to this repo, for local testing)
  RAILWAY_API_TOKEN, RAILWAY_SITE_SERVICE_ID, RAILWAY_ENVIRONMENT_ID
                          if set, trigger a redeploy after writing
"""
import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import psycopg2
import psycopg2.extras

OUT_DIR = Path(os.environ.get("PUBLIC_DATA_DIR") or Path(__file__).resolve().parent.parent / "public" / "api")

# Public site's score bands, on the 0-100 display scale (epi_score is stored
# 0-1 in the DB -- see epi_calculations.epi_score, NUMERIC(6,4)).
SCORE_BAND_EDGES = (30, 50, 70)

PORTS_SQL = """
select id, name, lat, lon
from epi_v2.ports
where is_test = false and is_pilot = false
order by name;
"""

STAYS_SQL = """
select id, port_id, shore_power_mwh
from epi_v2.port_stays
where port_id = any(%(port_ids)s)
  and arrival >= date_trunc('year', now());
"""

ENGINES_SQL = """
select stay_id, fuel_consumption_kg, sulphur_content, sox_scrubber_hours,
       running_hours, sox_co2_avg_ratio, power_prod_kwh, average_load_kw,
       rpm, nox_avg_emission_g_kwh, nox_rating_g_kwh
from epi_v2.engines
where stay_id = any(%(stay_ids)s);
"""

BOILERS_SQL = """
select stay_id, fuel_consumption_kg, sulphur_content, sox_scrubber_hours,
       sox_co2_avg_ratio
from epi_v2.boilers
where stay_id = any(%(stay_ids)s);
"""

# Latest epi_calculations row per stay (a stay can be recalculated).
EPI_SCORES_SQL = """
select distinct on (stay_id) stay_id, epi_score
from epi_v2.epi_calculations
where stay_id = any(%(stay_ids)s)
order by stay_id, id desc;
"""


def tier1_nox_g_kwh(rpm):
    """MARPOL Annex VI Tier I NOx limit in g/kWh. Mirrors stats.py."""
    if rpm is None:
        return None
    if rpm < 130:
        return 17.0
    if rpm >= 2000:
        return 9.8
    return 45.0 * (rpm ** -0.2)


def score_band_index(score_pct):
    for i, edge in enumerate(SCORE_BAND_EDGES):
        if score_pct < edge:
            return i
    return len(SCORE_BAND_EDGES)


def accumulate_engine(agg, eng):
    fk = float(eng["fuel_consumption_kg"] or 0)

    # SOx -- sulphur mass (no x2), scrubber-corrected when hours/ratio available.
    sulphur_frac = float(eng["sulphur_content"] or 0)
    scrubber_h = float(eng["sox_scrubber_hours"] or 0)
    running_h = float(eng["running_hours"] or 0)
    if scrubber_h > 0 and running_h > 0:
        scrubber_frac = min(1.0, scrubber_h / running_h)
        ratio = float(eng["sox_co2_avg_ratio"]) if eng["sox_co2_avg_ratio"] is not None else None
        if ratio is not None and ratio > 0:
            agg["sox_kg"] += fk * ((1 - scrubber_frac) * sulphur_frac + scrubber_frac * ratio / 4300)
        else:
            agg["sox_kg"] += fk * sulphur_frac
    else:
        agg["sox_kg"] += fk * sulphur_frac
    agg["sox_kg_baseline"] += fk * 0.001  # 0.1% S ECA limit, sulphur mass

    # NOx -- measured, else certified rating, else Tier I; baseline is Tier I.
    power_kwh = float(eng["power_prod_kwh"] or 0) or (
        float(eng["average_load_kw"] or 0) * running_h
    )
    tier1 = tier1_nox_g_kwh(eng["rpm"])
    if tier1 is not None:
        agg["nox_kg_baseline"] += tier1 * power_kwh / 1_000
    if eng["nox_avg_emission_g_kwh"] is not None:
        nox_g = float(eng["nox_avg_emission_g_kwh"])
    elif eng["nox_rating_g_kwh"] is not None:
        nox_g = float(eng["nox_rating_g_kwh"])
    else:
        nox_g = tier1 or 0.0
    agg["nox_kg"] += nox_g * power_kwh / 1_000


def accumulate_boiler(agg, boil):
    # Boilers only support SOx (see epiport handoff / methodology doc).
    fk = float(boil["fuel_consumption_kg"] or 0)
    sulphur_frac = float(boil["sulphur_content"] or 0)
    ratio = float(boil["sox_co2_avg_ratio"]) if boil["sox_co2_avg_ratio"] is not None else None
    if float(boil["sox_scrubber_hours"] or 0) > 0 and ratio is not None and ratio > 0:
        agg["sox_kg"] += fk * ratio / 4300
    else:
        agg["sox_kg"] += fk * sulphur_frac
    agg["sox_kg_baseline"] += fk * 0.001


def new_agg():
    return {"sox_kg": 0.0, "sox_kg_baseline": 0.0, "nox_kg": 0.0, "nox_kg_baseline": 0.0}


def build_export(cur):
    cur.execute(PORTS_SQL)
    ports = cur.fetchall()
    port_ids = [p["id"] for p in ports]
    if not port_ids:
        return _empty_summary(), {"type": "FeatureCollection", "features": []}

    cur.execute(STAYS_SQL, {"port_ids": port_ids})
    stays = cur.fetchall()
    stay_ids = [s["id"] for s in stays]
    stay_port = {s["id"]: s["port_id"] for s in stays}

    engines, boilers, epi_scores = [], [], []
    if stay_ids:
        cur.execute(ENGINES_SQL, {"stay_ids": stay_ids})
        engines = cur.fetchall()
        cur.execute(BOILERS_SQL, {"stay_ids": stay_ids})
        boilers = cur.fetchall()
        cur.execute(EPI_SCORES_SQL, {"stay_ids": stay_ids})
        epi_scores = cur.fetchall()

    epi_by_stay = {r["stay_id"]: float(r["epi_score"]) for r in epi_scores}

    port_agg = defaultdict(new_agg)
    total_agg = new_agg()
    for eng in engines:
        port_id = stay_port.get(eng["stay_id"])
        if port_id is None:
            continue
        accumulate_engine(port_agg[port_id], eng)
        accumulate_engine(total_agg, eng)
    for boil in boilers:
        port_id = stay_port.get(boil["stay_id"])
        if port_id is None:
            continue
        accumulate_boiler(port_agg[port_id], boil)
        accumulate_boiler(total_agg, boil)

    calls_by_port = defaultdict(int)
    shore_power_calls_by_port = defaultdict(int)
    scores_by_port = defaultdict(list)
    for stay in stays:
        pid = stay["port_id"]
        calls_by_port[pid] += 1
        if float(stay["shore_power_mwh"] or 0) > 0:
            shore_power_calls_by_port[pid] += 1
        if stay["id"] in epi_by_stay:
            scores_by_port[pid].append(epi_by_stay[stay["id"]])

    features = []
    for port in ports:
        pid = port["id"]
        calls = calls_by_port.get(pid, 0)
        scores = scores_by_port.get(pid, [])
        avg_score = round(sum(scores) / len(scores) * 100, 1) if scores else None
        ops_share_pct = round(shore_power_calls_by_port.get(pid, 0) / calls * 100) if calls else 0

        distribution = [0, 0, 0, 0]
        if scores:
            for s in scores:
                distribution[score_band_index(s * 100)] += 1
            distribution = [round(c / len(scores) * 100) for c in distribution]

        agg = port_agg.get(pid, new_agg())
        nox_reduced_t = round(max(0.0, agg["nox_kg_baseline"] - agg["nox_kg"]) / 1_000)

        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [float(port["lon"]), float(port["lat"])]},
            "properties": {
                "name": port["name"],
                "calls_ytd": calls,
                "avg_score": avg_score,
                "ops_share_pct": ops_share_pct,
                "nox_reduced_ytd": nox_reduced_t,
                "score_distribution": distribution,
            },
        })

    summary = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "year": datetime.now(timezone.utc).year,
        "active_ports": len(ports),
        "port_calls_ytd": len(stays),
        "sox_reduced_tonnes_ytd": round(max(0.0, total_agg["sox_kg_baseline"] - total_agg["sox_kg"]) / 1_000),
        "nox_reduced_tonnes_ytd": round(max(0.0, total_agg["nox_kg_baseline"] - total_agg["nox_kg"]) / 1_000),
    }
    ports_geojson = {"type": "FeatureCollection", "features": features}
    return summary, ports_geojson


def _empty_summary():
    return {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "year": datetime.now(timezone.utc).year,
        "active_ports": 0,
        "port_calls_ytd": 0,
        "sox_reduced_tonnes_ytd": 0,
        "nox_reduced_tonnes_ytd": 0,
    }


def trigger_redeploy() -> None:
    token = os.environ.get("RAILWAY_API_TOKEN")
    service_id = os.environ.get("RAILWAY_SITE_SERVICE_ID")
    environment_id = os.environ.get("RAILWAY_ENVIRONMENT_ID")
    if not (token and service_id and environment_id):
        print("Skipping redeploy trigger: RAILWAY_API_TOKEN / "
              "RAILWAY_SITE_SERVICE_ID / RAILWAY_ENVIRONMENT_ID not all set.")
        return
    import requests
    resp = requests.post(
        "https://backboard.railway.app/graphql/v2",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json={
            "query": (
                "mutation($serviceId: String!, $environmentId: String!) {"
                " serviceInstanceDeploy(serviceId: $serviceId, environmentId: $environmentId)"
                " }"
            ),
            "variables": {"serviceId": service_id, "environmentId": environment_id},
        },
        timeout=30,
    )
    resp.raise_for_status()
    print("Redeploy triggered:", resp.json())


def main() -> int:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        print("DATABASE_URL is not set", file=sys.stderr)
        return 1

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    with psycopg2.connect(database_url) as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            summary, ports_geojson = build_export(cur)

    (OUT_DIR / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    (OUT_DIR / "ports.geojson").write_text(json.dumps(ports_geojson, indent=2), encoding="utf-8")
    print(f"Wrote {OUT_DIR/'summary.json'} and {OUT_DIR/'ports.geojson'}")

    trigger_redeploy()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
