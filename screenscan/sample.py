"""Stage 1: decode each episode and keep SAMPLE_FPS frames per second.

Writes work/SxxEyy/frames/<ms>.jpg plus frames.parquet with timestamp,
sharpness (variance of Laplacian) and mean brightness per sampled frame.
"""

import argparse
from concurrent.futures import ProcessPoolExecutor

import av
import cv2
import numpy as np
import pandas as pd

from .config import SAMPLE_FPS, Episode, episodes


def sharpness(gray: np.ndarray) -> float:
    return float(cv2.Laplacian(gray, cv2.CV_32F).var())


def sample_episode(ep: Episode, force: bool = False) -> str:
    out = ep.work / "frames.parquet"
    if out.exists() and not force:
        return f"{ep.code}: cached"
    frames_dir = ep.work / "frames"
    frames_dir.mkdir(parents=True, exist_ok=True)

    rows = []
    with av.open(str(ep.video)) as container:
        stream = container.streams.video[0]
        stream.thread_type = "AUTO"
        next_t = 0.0
        for frame in container.decode(stream):
            if frame.time is None or frame.time < next_t:
                continue
            next_t += 1.0 / SAMPLE_FPS
            bgr = frame.to_ndarray(format="bgr24")
            gray = cv2.cvtColor(cv2.resize(bgr, (960, 540), interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2GRAY)
            ms = round(frame.time * 1000)
            cv2.imwrite(str(frames_dir / f"{ms:07d}.jpg"), bgr, [cv2.IMWRITE_JPEG_QUALITY, 92])
            rows.append({"ms": ms, "sharpness": sharpness(gray), "brightness": float(gray.mean())})

    pd.DataFrame(rows).to_parquet(out)
    return f"{ep.code}: {len(rows)} frames"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("episodes", nargs="*", type=int)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--workers", type=int, default=6)
    args = ap.parse_args()
    eps = episodes(args.episodes)
    with ProcessPoolExecutor(args.workers) as pool:
        for msg in pool.map(sample_episode, eps, [args.force] * len(eps)):
            print(msg, flush=True)


if __name__ == "__main__":
    main()
