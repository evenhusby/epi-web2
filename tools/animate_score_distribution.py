#!/usr/bin/env python3
"""Render an animated video of epiport.org's "Score distribution per call"
panel, cycling through one port at a time -- for use in a PowerPoint deck.

Data source: public/api/ports.geojson + public/api/summary.json in this repo.
These are the exact static files the deployed site fetches (see
src/lib/map-app.ts), so no live network call is made -- rerun
tools/generate_public_json.py first if you want a fresher export, then rerun
this script.

Chart shape mirrors src/lib/map-app.ts (distBars/panelRows) and
src/styles/global.css (.dist-bars/.dist-axis) exactly:
  - 4 score bands, edges at 30/50/70 (see generate_public_json.py's
    SCORE_BAND_EDGES), labelled "0-30", "30-50", "50-70", "70-100".
  - Bar colors: bands 0-1 = --linje-lys, band 2 = the site's ".mid" green
    tint, band 3 = --gronn (the site's ".hi" full green).
Unlike the on-site panel (which rescales each port's four bars to its own
max, purely for visual fill), this video plots score_distribution values
directly on a fixed 0-100% axis -- they are already "share of this port's
calls in this band" from generate_public_json.py, so this is what actually
lets ports of different sizes be compared, per the brief.

Usage:
  python3 tools/animate_score_distribution.py [options]

Run with --help for all parameters. Sensible defaults match the brief.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.font_manager as fm
import matplotlib.pyplot as plt
import numpy as np

REPO_ROOT = Path(__file__).resolve().parent.parent
PORTS_GEOJSON = REPO_ROOT / "public" / "api" / "ports.geojson"
SUMMARY_JSON = REPO_ROOT / "public" / "api" / "summary.json"

# ---- epiport.org design tokens, copied from src/styles/global.css ----
COLOR_PAPIR = "#FDFCF9"
COLOR_BLEKK = "#26332F"
COLOR_BLEKK_LYS = "#55605B"
COLOR_GRAFITT = "#6B7570"
COLOR_GRONN = "#1E5C48"
COLOR_LINJE = "#C9C4B4"
COLOR_LINJE_LYS = "#E5E1D6"
COLOR_MID = "#CDDCD2"
COLOR_MID_BORDER = "#9DBCA9"

BAND_LABELS = ["0–30", "30–50", "50–70", "70–100"]
# One color/edge pair per band, matching .dist-bars div / div.mid / div.hi.
BAR_FILL = [COLOR_LINJE_LYS, COLOR_LINJE_LYS, COLOR_MID, COLOR_GRONN]
BAR_EDGE = [COLOR_LINJE, COLOR_LINJE, COLOR_MID_BORDER, COLOR_GRONN]

# Font substitutes: epiport.org uses Palatino Linotype/Georgia (display) and
# system sans (body), both proprietary and unavailable on Linux. Liberation
# Serif/Sans are metrically compatible open substitutes (Times/Arial clones),
# installed via `apt-get install fonts-liberation`.
FONT_DISPLAY = "Liberation Serif"
FONT_BODY = "Liberation Sans"

LABELS = {
    "no": {
        "all_title": "Alle havner",
        "n": "n = {n} anløp",
        "score": "snittscore {s}",
        "source": "Kilde: Environmental Port Index (epiport.org), data per {date}",
    },
    "en": {
        "all_title": "All ports",
        "n": "n = {n} port calls",
        "score": "avg score {s}",
        "source": "Source: Environmental Port Index (epiport.org), data as of {date}",
    },
}


def load_data():
    ports = json.loads(PORTS_GEOJSON.read_text(encoding="utf-8"))["features"]
    summary = json.loads(SUMMARY_JSON.read_text(encoding="utf-8"))
    rows = [
        {
            "name": f["properties"]["name"],
            "calls_ytd": f["properties"]["calls_ytd"],
            "avg_score": f["properties"]["avg_score"],
            "dist": f["properties"]["score_distribution"],
        }
        for f in ports
    ]
    return rows, summary


def aggregate_all(rows):
    """All-ports reference distribution.

    Mirrors map-app.ts's aggregateAll(): element-wise sum of every port's own
    (already-percentage) score_distribution across ALL ports, unweighted by
    port size -- this reproduces the exact shape shown in the "Alle havner"
    panel on the live site. We then rescale that sum to add up to 100 so it
    reads as a valid percentage on the video's fixed 0-100% axis (rescaling
    preserves the relative bar shape, i.e. what's on the site, while making
    the numbers meaningful as "share of calls" for the animation's axis).
    """
    dist = [0.0, 0.0, 0.0, 0.0]
    for r in rows:
        if r["dist"]:
            for i, v in enumerate(r["dist"]):
                dist[i] += v
    total = sum(dist)
    if total > 0:
        dist = [v / total * 100 for v in dist]
    return dist


def select_and_sort(rows, min_calls: int, sort_by: str):
    kept = [r for r in rows if r["calls_ytd"] >= min_calls]
    excluded = [r for r in rows if r["calls_ytd"] < min_calls]
    if sort_by == "calls_desc":
        kept.sort(key=lambda r: (-r["calls_ytd"], r["name"]))
    elif sort_by == "alpha":
        kept.sort(key=lambda r: r["name"])
    elif sort_by == "score_desc":
        kept.sort(key=lambda r: (-(r["avg_score"] or -1), r["name"]))
    else:
        raise ValueError(f"unknown --sort {sort_by!r}")
    excluded.sort(key=lambda r: r["name"])
    return kept, excluded


def ease_smoothstep(t: np.ndarray) -> np.ndarray:
    t = np.clip(t, 0.0, 1.0)
    return t * t * (3 - 2 * t)


def build_timeline(all_rows, kept_rows, summary, args):
    """Returns a list of (dist, ref_dist, title, subtitle, show_ref) per frame."""
    fps = args.fps
    n_transition = max(1, round(args.transition * fps))
    n_port_hold = max(1, round((args.seconds_per_port - args.transition) * fps))
    n_intro = max(1, round(args.intro_seconds * fps))
    n_outro_hold = max(1, round((args.outro_seconds - args.transition) * fps))

    # The "All ports" reference/opening/closing view always aggregates over
    # every port (matching the website's own aggregateAll(), which is not
    # filtered by call volume) -- min-calls only controls which ports get
    # their own segment, per the brief.
    all_dist = np.array(aggregate_all(all_rows))
    lab = LABELS[args.lang]
    all_title = lab["all_title"]
    all_sub = lab["n"].format(n=f"{summary['port_calls_ytd']:,}".replace(",", " "))

    frames = []

    def hold(dist, title, subtitle, n, show_ref):
        for _ in range(n):
            frames.append((dist, all_dist, title, subtitle, show_ref))

    def transition(dist_from, dist_to, title, subtitle, n, show_ref):
        for i in range(n):
            t = ease_smoothstep(np.array((i + 1) / n))
            dist = dist_from + (dist_to - dist_from) * t
            frames.append((dist, all_dist, title, subtitle, show_ref))

    # Intro: hold "All ports".
    hold(all_dist, all_title, all_sub, n_intro, show_ref=False)

    prev_dist = all_dist
    for r in kept_rows:
        dist = np.array(r["dist"], dtype=float)
        title = r["name"]
        score_txt = f"{r['avg_score']:.1f}" if r["avg_score"] is not None else "–"
        subtitle = f"{lab['n'].format(n=r['calls_ytd'])} · {lab['score'].format(s=score_txt)}"
        transition(prev_dist, dist, title, subtitle, n_transition, show_ref=True)
        hold(dist, title, subtitle, n_port_hold, show_ref=True)
        prev_dist = dist

    # Outro: transition back to "All ports", then hold.
    transition(prev_dist, all_dist, all_title, all_sub, n_transition, show_ref=False)
    hold(all_dist, all_title, all_sub, n_outro_hold, show_ref=False)

    return frames


def setup_fonts():
    available = {f.name for f in fm.fontManager.ttflist}
    display = FONT_DISPLAY if FONT_DISPLAY in available else "serif"
    body = FONT_BODY if FONT_BODY in available else "sans-serif"
    if display == "serif":
        print(f"warning: {FONT_DISPLAY!r} not found, falling back to generic serif", file=sys.stderr)
    if body == "sans-serif":
        print(f"warning: {FONT_BODY!r} not found, falling back to generic sans-serif", file=sys.stderr)
    plt.rcParams["font.family"] = body
    return display, body


def draw_frame(fig, ax, frame, source_line, display_font, body_font):
    dist, ref_dist, title, subtitle, show_ref = frame
    ax.clear()
    ax.set_facecolor(COLOR_PAPIR)
    # fig.suptitle()/fig.text() add new artists on every call; ax.clear()
    # only clears the axes, so without this the title/subtitle/source lines
    # from every previous frame would stay on the figure and overlap.
    if fig._suptitle is not None:
        fig._suptitle.remove()
        fig._suptitle = None
    for txt in list(fig.texts):
        txt.remove()

    x = np.arange(4)
    if show_ref:
        ax.bar(x, ref_dist, width=0.62, color=COLOR_LINJE, alpha=0.35, zorder=1, linewidth=0)
    ax.bar(
        x, dist, width=0.46, color=BAR_FILL, edgecolor=BAR_EDGE, linewidth=2.2, zorder=2,
    )

    ax.set_xlim(-0.6, 3.6)
    ax.set_ylim(0, 100)
    ax.set_xticks(x)
    ax.set_xticklabels(BAND_LABELS, fontsize=22, color=COLOR_GRAFITT, fontfamily=body_font)
    ax.set_yticks([0, 20, 40, 60, 80, 100])
    ax.set_yticklabels([f"{v}%" for v in (0, 20, 40, 60, 80, 100)], fontsize=22, color=COLOR_GRAFITT, fontfamily=body_font)
    ax.yaxis.grid(True, color=COLOR_LINJE, linewidth=1, alpha=0.6, zorder=0)
    ax.set_axisbelow(True)
    for spine in ("top", "right", "left"):
        ax.spines[spine].set_visible(False)
    ax.spines["bottom"].set_color(COLOR_BLEKK)
    ax.tick_params(axis="both", length=0)

    fig.suptitle(
        title, x=0.09, y=0.94, ha="left", va="top", fontsize=40, color=COLOR_BLEKK,
        fontfamily=display_font, fontweight="normal",
    )
    fig.text(
        0.09, 0.845, subtitle, ha="left", va="top", fontsize=24, color=COLOR_BLEKK_LYS, fontfamily=body_font,
    )
    fig.text(
        0.09, 0.025, source_line, ha="left", va="bottom", fontsize=15, color=COLOR_GRAFITT, fontfamily=body_font,
    )


def render_frames(frames, out_dir: Path, args, source_line, display_font, body_font):
    out_dir.mkdir(parents=True, exist_ok=True)
    dpi = 100
    fig = plt.figure(figsize=(args.width / dpi, args.height / dpi), dpi=dpi)
    fig.patch.set_facecolor(COLOR_PAPIR)
    ax = fig.add_axes([0.09, 0.17, 0.87, 0.55])

    total = len(frames)
    digits = len(str(total))
    for i, frame in enumerate(frames):
        draw_frame(fig, ax, frame, source_line, display_font, body_font)
        fig.savefig(out_dir / f"frame_{i:0{digits}d}.png", facecolor=COLOR_PAPIR)
        if i % 100 == 0 or i == total - 1:
            print(f"  frame {i + 1}/{total}", file=sys.stderr)
    plt.close(fig)
    return digits


def encode_video(frame_dir: Path, digits: int, fps: int, out_path: Path):
    pattern = str(frame_dir / f"frame_%0{digits}d.png")
    cmd = [
        "ffmpeg", "-y", "-framerate", str(fps), "-i", pattern,
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18",
        "-movflags", "+faststart", str(out_path),
    ]
    subprocess.run(cmd, check=True)


def encode_gif(mp4_path: Path, out_path: Path, gif_width: int, gif_fps: int, tmp_dir: Path):
    palette = tmp_dir / "palette.png"
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(mp4_path), "-vf",
         f"fps={gif_fps},scale={gif_width}:-1:flags=lanczos,palettegen", str(palette)],
        check=True,
    )
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(mp4_path), "-i", str(palette), "-lavfi",
         f"fps={gif_fps},scale={gif_width}:-1:flags=lanczos[x];[x][1:v]paletteuse", str(out_path)],
        check=True,
    )


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--seconds-per-port", type=float, default=2.5)
    p.add_argument("--transition", type=float, default=0.6, help="seconds of bar transition at the start of each port/segment")
    p.add_argument("--intro-seconds", type=float, default=3.0)
    p.add_argument("--outro-seconds", type=float, default=2.0)
    p.add_argument("--min-calls", type=int, default=10, help="ports with calls_ytd below this are excluded")
    p.add_argument("--sort", choices=["calls_desc", "alpha", "score_desc"], default="calls_desc")
    p.add_argument("--lang", choices=["no", "en"], default="no")
    p.add_argument("--fps", type=int, default=30)
    p.add_argument("--width", type=int, default=1920)
    p.add_argument("--height", type=int, default=1080)
    p.add_argument("--gif-width", type=int, default=960)
    p.add_argument("--gif-fps", type=int, default=15)
    p.add_argument("--poster-frame", choices=["first", "last"], default="first")
    p.add_argument("--out-dir", type=Path, default=Path("score_distribution_output"))
    p.add_argument("--skip-gif", action="store_true")
    p.add_argument("--keep-frames", action="store_true", help="don't delete the intermediate PNG frame sequence")
    args = p.parse_args()

    if shutil.which("ffmpeg") is None:
        print("ffmpeg not found on PATH -- required to encode the video/gif.", file=sys.stderr)
        return 1

    rows, summary = load_data()
    kept, excluded = select_and_sort(rows, args.min_calls, args.sort)
    print(f"{len(kept)} ports included, {len(excluded)} excluded (calls_ytd < {args.min_calls}):")
    for r in excluded:
        print(f"  - {r['name']} (calls_ytd={r['calls_ytd']})")

    display_font, body_font = setup_fonts()
    lab = LABELS[args.lang]
    source_line = lab["source"].format(date=summary["generated_at"][:10])

    frames = build_timeline(rows, kept, summary, args)
    duration = len(frames) / args.fps
    print(f"{len(frames)} frames @ {args.fps}fps = {duration:.1f}s")

    args.out_dir.mkdir(parents=True, exist_ok=True)
    frame_dir = args.out_dir / "_frames"
    print("Rendering frames...", file=sys.stderr)
    digits = render_frames(frames, frame_dir, args, source_line, display_font, body_font)

    mp4_path = args.out_dir / "score_distribution_animasjon.mp4"
    print("Encoding MP4...", file=sys.stderr)
    encode_video(frame_dir, digits, args.fps, mp4_path)

    poster_idx = 0 if args.poster_frame == "first" else len(frames) - 1
    poster_src = frame_dir / f"frame_{poster_idx:0{digits}d}.png"
    poster_path = args.out_dir / "poster.png"
    shutil.copyfile(poster_src, poster_path)

    if not args.skip_gif:
        print("Encoding GIF...", file=sys.stderr)
        gif_path = args.out_dir / "score_distribution_animasjon.gif"
        encode_gif(mp4_path, gif_path, args.gif_width, args.gif_fps, args.out_dir)

    if not args.keep_frames:
        shutil.rmtree(frame_dir)

    print(f"Done. Output in {args.out_dir}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
