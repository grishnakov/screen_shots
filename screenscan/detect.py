"""Stage 2b: OWLv2 open-vocabulary detection of small / background screens.

Whole-frame SigLIP misses screens that occupy a small part of the frame, so
this runs a detector on one sharp frame per shot. Shots are runs of consecutive
sampled frames with near-identical SigLIP embeddings.

Writes work/SxxEyy/owl.json: {ms: [{"label", "score", "box": [x1,y1,x2,y2] (0-1)}]}
"""

import argparse
import json

import numpy as np
import pandas as pd
import torch
from PIL import Image
from transformers import Owlv2ForObjectDetection, Owlv2Processor

from .config import Episode, episodes
from .device import DEVICE, half

DTYPE = half(torch.float16)

MODEL = "google/owlv2-base-patch16-ensemble"
QUERIES = [
    "a computer monitor",
    "a laptop computer",
    "a television",
    "a smartphone",
    "a projector screen",
    "a tablet",
]
SCORE_THRESHOLD = 0.15
SHOT_MIN_SIM = 0.90
LONG_SHOT_STEP_MS = 5000


def shot_representatives(ep: Episode) -> list[int]:
    """One sharp frame per shot, plus one every LONG_SHOT_STEP_MS inside long shots."""
    z = np.load(ep.work / "siglip.npz")
    ms, emb = z["ms"], z["emb"]
    sharp = pd.read_parquet(ep.work / "frames.parquet")["sharpness"].to_numpy()
    starts = [0] + [i for i in range(1, len(ms)) if emb[i] @ emb[i - 1] < SHOT_MIN_SIM]
    ends = starts[1:] + [len(ms)]
    reps: list[int] = []
    for a, b in zip(starts, ends):
        step = max(1, round(LONG_SHOT_STEP_MS / (ms[1] - ms[0])))
        for c in range(a, b, step):
            reps.append(int(ms[max(range(c, min(c + step, b)), key=lambda i: sharp[i])]))
    return reps


def load():
    proc = Owlv2Processor.from_pretrained(MODEL)
    model = Owlv2ForObjectDetection.from_pretrained(MODEL, dtype=DTYPE).to(DEVICE).eval()
    return model, proc


@torch.inference_mode()
def detect_episode(ep: Episode, model, proc, force: bool = False, batch: int = 8) -> str:
    out = ep.work / "owl.json"
    if out.exists() and not force:
        return f"{ep.code}: cached"
    reps = shot_representatives(ep)
    result: dict[str, list[dict]] = {}
    for i in range(0, len(reps), batch):
        chunk = reps[i : i + batch]
        imgs = [Image.open(ep.work / "frames" / f"{m:07d}.jpg").convert("RGB") for m in chunk]
        inputs = proc(text=[QUERIES] * len(imgs), images=imgs, return_tensors="pt").to(DEVICE)
        inputs["pixel_values"] = inputs["pixel_values"].to(DTYPE)
        outputs = model(**inputs)
        # OWLv2 pads to a square, so boxes are relative to the padded square side.
        side = max(imgs[0].size)
        dets = proc.post_process_grounded_object_detection(
            outputs, threshold=SCORE_THRESHOLD, target_sizes=[(side, side)] * len(imgs), text_labels=[QUERIES] * len(imgs)
        )
        for m, img, d in zip(chunk, imgs, dets):
            w, h = img.size
            boxes = []
            for box, score, label in zip(d["boxes"].tolist(), d["scores"].tolist(), d["text_labels"]):
                x1, y1, x2, y2 = box
                boxes.append(
                    {
                        "label": label,
                        "score": round(score, 3),
                        "box": [max(0, x1 / w), max(0, y1 / h), min(1, x2 / w), min(1, y2 / h)],
                    }
                )
            result[str(m)] = boxes
    out.write_text(json.dumps(result))
    hits = sum(1 for v in result.values() if v)
    return f"{ep.code}: {len(reps)} shot frames, {hits} with detections"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("episodes", nargs="*", type=int)
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()
    model, proc = load()
    for ep in episodes(args.episodes):
        print(detect_episode(ep, model, proc, args.force), flush=True)


if __name__ == "__main__":
    main()
