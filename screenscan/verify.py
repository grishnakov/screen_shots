"""Stage 3: send SigLIP candidates to the VLM.

Candidates are frames with a high screen-vs-non-screen margin. Consecutive
near-identical candidates are clustered so the VLM sees only a few frames per
cluster. A random sample of low-scoring frames is also sent (--audit) to
estimate what the first pass is missing.

Results are appended to work/SxxEyy/vlm.jsonl (one line per frame, resumable).
"""

import argparse
import asyncio
import json

import numpy as np
import pandas as pd
from tqdm import tqdm

from .config import Episode, episodes
from .shared import shared_ms
from .siglip import NEGATIVE, POSITIVE
from .vlm import inspect_many

MARGIN_THRESHOLD = -3.0
OWL_THRESHOLD = 0.20
CLUSTER_GAP_MS = 3000
CLUSTER_MIN_SIM = 0.90
FRAMES_PER_CLUSTER = 3


def margins(logits: np.ndarray) -> np.ndarray:
    p = len(POSITIVE)
    return logits[:, :p].max(1) - logits[:, p:].max(1)


def clusters(ep: Episode, threshold: float = MARGIN_THRESHOLD) -> list[list[int]]:
    """Indices (into the frames arrays) of candidate frames, grouped into runs."""
    z = np.load(ep.work / "siglip.npz")
    m = margins(z["logits"])
    idx = np.flatnonzero(m > threshold)
    runs: list[list[int]] = []
    for i in idx:
        if runs and z["ms"][i] - z["ms"][runs[-1][-1]] <= CLUSTER_GAP_MS and z["emb"][i] @ z["emb"][runs[-1][-1]] >= CLUSTER_MIN_SIM:
            runs[-1].append(i)
        else:
            runs.append([i])
    return runs


def pick_representatives(ep: Episode, run: list[int]) -> list[int]:
    z = np.load(ep.work / "siglip.npz")
    m = margins(z["logits"])
    sharp = pd.read_parquet(ep.work / "frames.parquet")["sharpness"].to_numpy()
    picks = {max(run, key=lambda i: m[i]), max(run, key=lambda i: sharp[i]), run[len(run) // 2]}
    return sorted(picks)[:FRAMES_PER_CLUSTER]


def load_done(path) -> dict[int, dict]:
    done = {}
    if path.exists():
        for line in path.read_text().splitlines():
            r = json.loads(line)
            done[r["ms"]] = r
    return done


def verify_episode(ep: Episode, audit: int = 0, threshold: float = MARGIN_THRESHOLD) -> str:
    z = np.load(ep.work / "siglip.npz")
    ms = z["ms"]
    out = ep.work / "vlm.jsonl"
    done = load_done(out)

    wanted: dict[int, str] = {}
    runs = clusters(ep, threshold)
    for run in runs:
        for i in pick_representatives(ep, run):
            wanted[int(ms[i])] = "candidate"
    owl_path = ep.work / "owl.json"
    if owl_path.exists():
        # Small / background screens the whole-frame scorer misses: any shot frame OWLv2 fired on.
        for k, dets in json.loads(owl_path.read_text()).items():
            if any(d["score"] >= OWL_THRESHOLD for d in dets):
                wanted.setdefault(int(k), "owl")
    if audit:
        m = margins(z["logits"])
        low = np.flatnonzero(m <= threshold)
        rng = np.random.default_rng(0)
        for i in rng.choice(low, min(audit, len(low)), replace=False):
            wanted.setdefault(int(ms[i]), "audit")

    recurring = shared_ms(ep)
    wanted = {t: src for t, src in wanted.items() if t not in recurring}
    todo = [t for t in wanted if t not in done]
    if todo:
        bar = tqdm(total=len(todo), desc=ep.code, mininterval=10)
        # Append each verdict as it arrives so an interrupted run resumes where it stopped.
        with out.open("a") as f:

            def save(i: int, result: dict | None) -> None:
                if result is not None:
                    f.write(json.dumps({"ms": todo[i], "source": wanted[todo[i]], **result}) + "\n")
                    f.flush()
                bar.update()

            asyncio.run(inspect_many([ep.work / "frames" / f"{t:07d}.jpg" for t in todo], on_done=save))
        bar.close()
    return f"{ep.code}: {len(runs)} clusters, {len(todo)} frames sent to VLM ({len(wanted) - len(todo)} cached)"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("episodes", nargs="*", type=int)
    ap.add_argument("--audit", type=int, default=0, help="also send N random low-scoring frames")
    ap.add_argument("--threshold", type=float, default=MARGIN_THRESHOLD)
    args = ap.parse_args()
    for ep in episodes(args.episodes):
        print(verify_episode(ep, args.audit, args.threshold), flush=True)


if __name__ == "__main__":
    main()
