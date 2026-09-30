"""Stage 4: turn VLM verdicts into one best screenshot per screen appearance.

A frame qualifies if it holds at least one screen that is on, that the crop check
confirms is a real display, and whose content is readable (foreground or
background); see frame_screens. Frames of recurring footage (titles, credits) are
skipped. Qualifying frames are grouped into appearances (runs separated by more
than APPEARANCE_GAP_S or by a visual change below APPEARANCE_MIN_SIM) and the
best frame of each run is chosen.

Writes work/SxxEyy/appearances.json.
"""

import argparse
import json

import numpy as np
import pandas as pd

from .config import Episode, episodes, fmt_ts
from .refine import load_refined
from .shared import shared_ms
from .verify import load_done, margins

APPEARANCE_GAP_S = 20.0
APPEARANCE_MIN_SIM = 0.80  # consecutive qualifying frames less alike than this start a new appearance
PROMINENCE_WEIGHT = {"fills_frame": 1.0, "main": 1.0, "background": 0.5}


def frame_screens(rec: dict, refined: dict | None = None) -> list[dict]:
    """Screens in a frame that are switched on and readable.

    Without `refined` (first-pass only) a screen needs content_visible. With `refined` (crop-check
    verdicts) a screen qualifies if the crop check says it is a real screen and either check judged
    it readable. Deliberately lenient: an extra frame is cheaper to delete by hand than a missed one.
    """
    out = []
    for i, s in enumerate(rec["screens"]):
        if not s["on"]:
            continue
        if refined is None:
            if not s["content_visible"]:
                continue
        else:
            r = refined.get((rec["ms"], i))
            if not (r and r["is_screen"] and (s["content_visible"] or r["legible"])):
                continue
            s = {**s, "what": r["what"], "type": r["kind"] if r["kind"] != "other" else s["type"]}
        out.append(s)
    return out


def best_screen(rec: dict, refined: dict | None = None) -> dict:
    return max(frame_screens(rec, refined), key=lambda s: PROMINENCE_WEIGHT[s["prominence"]])


def select_episode(ep: Episode, gap_s: float = APPEARANCE_GAP_S) -> list[dict]:
    z = np.load(ep.work / "siglip.npz")
    m = dict(zip(z["ms"].tolist(), margins(z["logits"]).tolist()))
    frames = pd.read_parquet(ep.work / "frames.parquet").set_index("ms")
    sharp_rank = frames["sharpness"].rank(pct=True).to_dict()

    refined = load_refined(ep)
    recurring = shared_ms(ep)
    recs = sorted(
        (r for r in load_done(ep.work / "vlm.jsonl").values() if r["ms"] not in recurring and frame_screens(r, refined)),
        key=lambda r: r["ms"],
    )

    pos = {int(t): i for i, t in enumerate(z["ms"])}
    emb = z["emb"]

    runs: list[list[dict]] = []
    for r in recs:
        prev = runs[-1][-1] if runs else None
        if prev and r["ms"] - prev["ms"] <= gap_s * 1000 and emb[pos[r["ms"]]] @ emb[pos[prev["ms"]]] >= APPEARANCE_MIN_SIM:
            runs[-1].append(r)
        else:
            runs.append([r])

    def score(r: dict) -> float:
        s = best_screen(r, refined)
        return (
            2.0 * PROMINENCE_WEIGHT[s["prominence"]]
            + 1.5 * bool(r["sharp"])
            + 1.0 * sharp_rank[r["ms"]]
            + 0.1 * m[r["ms"]]
        )

    out = []
    for run in runs:
        best = max(run, key=score)
        s = best_screen(best, refined)
        out.append(
            {
                "ms": best["ms"],
                "start_ms": run[0]["ms"],
                "end_ms": run[-1]["ms"],
                "n_frames": len(run),
                "type": s["type"],
                "prominence": s["prominence"],
                "what": s["what"],
                "box": s["box"],
            }
        )
    (ep.work / "appearances.json").write_text(json.dumps(out, indent=1))
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("episodes", nargs="*", type=int)
    ap.add_argument("--gap", type=float, default=APPEARANCE_GAP_S)
    args = ap.parse_args()
    for ep in episodes(args.episodes):
        apps = select_episode(ep, args.gap)
        print(f"{ep.code}: {len(apps)} appearances")
        for a in apps:
            print(f"  {fmt_ts(a['ms'])}  {a['type']:9s} {a['prominence']:11s} {a['what']}  ({a['n_frames']} frames)")


if __name__ == "__main__":
    main()
