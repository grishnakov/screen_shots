"""Stage 2c: flag footage that recurs across episodes (opening titles, logos, credits, recaps).

A frame is "shared" if near-identical frames (SigLIP cosine >= MIN_SIM) exist in at least
MIN_EPISODE_FRACTION of the other episodes. Writes work/SxxEyy/shared.npy (bool per sampled frame).
Screens shown in a single scene almost never recur that widely, so verify/select skip shared frames.
Only long stretches count (see flag_shared): recurring close-ups of regular characters must not be dropped.
"""

import argparse

import numpy as np
import torch

from .config import Episode, episodes
from .device import DEVICE, half

MIN_SIM = 0.96
MIN_EPISODE_FRACTION = 0.35
DILATE_FRAMES = 3  # widen flagged stretches by this many samples each side to bridge stray unflagged frames
MIN_BLOCK_FRAMES = 40  # only stretches this long (titles, credits: ~45 s) are flagged at all


def recurrence(all_emb: dict[int, np.ndarray]) -> dict[int, np.ndarray]:
    """For each episode, per-frame count of other episodes that contain a near-identical frame."""
    dev = DEVICE
    emb = {k: torch.from_numpy(v).to(dev, half(torch.float16)) for k, v in all_emb.items()}
    out = {}
    for k, a in emb.items():
        count = torch.zeros(len(a), device=dev)
        for j, b in emb.items():
            if j == k:
                continue
            best = torch.cat([(a[i : i + 1024] @ b.T).max(1).values for i in range(0, len(a), 1024)])
            count += (best >= MIN_SIM).float()
        out[k] = count.cpu().numpy()
    return out


def flag_shared(raw: np.ndarray) -> np.ndarray:
    """Keep only long stretches of recurring frames (title sequence, credits) and widen them so stray
    unflagged frames inside or at their edges are covered.

    Short stretches are dropped entirely: a few recurring frames in the middle of an episode are
    close-ups of a regular character, act-break fades or similar, and may hold a real screen, so they
    must never be discarded.
    """
    wide = np.convolve(raw, np.ones(2 * DILATE_FRAMES + 1), "same") > 0
    out = np.zeros_like(raw, dtype=bool)
    edges = np.flatnonzero(np.diff(np.r_[0, wide, 0]))
    for a, b in zip(edges[::2], edges[1::2]):
        if b - a >= MIN_BLOCK_FRAMES:
            out[a:b] = True
    return out


def shared_ms(ep: Episode) -> set[int]:
    """Timestamps (ms) of sampled frames flagged as recurring footage; empty if not computed yet."""
    path = ep.work / "shared.npy"
    if not path.exists():
        return set()
    return set(np.load(ep.work / "siglip.npz")["ms"][np.load(path)].tolist())


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.parse_args()
    eps = [ep for ep in episodes() if (ep.work / "siglip.npz").exists()]
    counts = recurrence({ep.number: np.load(ep.work / "siglip.npz")["emb"] for ep in eps})
    need = max(2, MIN_EPISODE_FRACTION * (len(eps) - 1))
    for ep in eps:
        flag = flag_shared(counts[ep.number] >= need)
        np.save(ep.work / "shared.npy", flag)
        print(f"{ep.code}: {int(flag.sum())} of {len(flag)} frames flagged shared (need >= {need:.1f} other episodes)")


if __name__ == "__main__":
    main()
