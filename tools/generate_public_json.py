#!/usr/bin/env python3
"""Nightly export from epi_v2 -> summary.json + ports.geojson.

Per epiport-handoff.md's data contract. Intended to run on a Railway cron
service (see railway.cron.toml).

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

TODO: the two queries below are placeholders. Replace them with the real
epi_v2 views/tables once the schema is confirmed (see handoff doc TODO #4).
"""
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import psycopg2
import psycopg2.extras

OUT_DIR = Path(os.environ.get("PUBLIC_DATA_DIR") or Path(__file__).resolve().parent.parent / "public" / "api")

SUMMARY_SQL = """
-- TODO: replace with the real epi_v2 aggregate view/query.
select
    count(distinct port_id)               as active_ports,
    sum(port_calls_ytd)                   as port_calls_ytd,
    sum(sox_reduced_tonnes_ytd)           as sox_reduced_tonnes_ytd,
    sum(nox_reduced_tonnes_ytd)           as nox_reduced_tonnes_ytd
from epi_v2.port_summary_ytd;
"""

PORTS_SQL = """
-- TODO: replace with the real epi_v2 per-port aggregate view/query.
select
    name, lon, lat, member_since, calls_ytd, avg_score,
    ops_share_pct, nox_reduced_ytd, score_distribution
from epi_v2.port_public_stats;
"""


def fetch_summary(cur) -> dict:
    cur.execute(SUMMARY_SQL)
    row = cur.fetchone()
    return {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "year": datetime.now(timezone.utc).year,
        "active_ports": row["active_ports"],
        "port_calls_ytd": row["port_calls_ytd"],
        "sox_reduced_tonnes_ytd": row["sox_reduced_tonnes_ytd"],
        "nox_reduced_tonnes_ytd": row["nox_reduced_tonnes_ytd"],
    }


def fetch_ports(cur) -> dict:
    cur.execute(PORTS_SQL)
    features = []
    for row in cur.fetchall():
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [row["lon"], row["lat"]]},
            "properties": {
                "name": row["name"],
                "member_since": row["member_since"],
                "calls_ytd": row["calls_ytd"],
                "avg_score": row["avg_score"],
                "ops_share_pct": row["ops_share_pct"],
                "nox_reduced_ytd": row["nox_reduced_ytd"],
                "score_distribution": row["score_distribution"],
            },
        })
    return {"type": "FeatureCollection", "features": features}


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
            summary = fetch_summary(cur)
            ports = fetch_ports(cur)

    (OUT_DIR / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    (OUT_DIR / "ports.geojson").write_text(json.dumps(ports, indent=2), encoding="utf-8")
    print(f"Wrote {OUT_DIR/'summary.json'} and {OUT_DIR/'ports.geojson'}")

    trigger_redeploy()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
