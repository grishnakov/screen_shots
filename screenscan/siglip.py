"""Stage 2: zero-shot SigLIP2 screen scoring of every sampled frame.

Writes work/SxxEyy/siglip.npz with
  ms        (N,)   frame timestamps
  emb       (N,D)  L2-normalised image embeddings (reused for scene grouping)
  logits    (N,P)  image-text logits for PROMPTS
"""

import argparse

import numpy as np
import pandas as pd
import torch
from PIL import Image
from transformers import AutoModel, AutoProcessor

from .config import Episode, episodes
from .device import DEVICE, half

DTYPE = half(torch.bfloat16)

MODEL = "google/siglip2-so400m-patch14-384"

POSITIVE = [
    "a photo of a computer monitor showing a screen that is turned on",
    "a close-up of a computer screen showing a website or email",
    "a photo of a laptop with its screen on",
    "a photo of a television screen that is turned on",
    "a close-up of a phone screen that is lit up",
    "a photo of a person looking at a cell phone display",
    "a projector screen showing an image",
    "a photo of a tablet screen turned on",
    "a photo of a video game on a screen",
    "a screenshot of a user interface with text and buttons",
]
NEGATIVE = [
    "a photo of people talking in a school hallway",
    "a photo of a classroom",
    "a photo of a bedroom",
    "a close-up of a person's face",
    "a photo of a kitchen",
    "a photo of a computer screen that is turned off and black",
    "a photo of a whiteboard or chalkboard",
    "a black frame",
    "a photo of people outdoors",
    "a photo of a window",
]
PROMPTS = POSITIVE + NEGATIVE


def load():
    model = AutoModel.from_pretrained(MODEL, dtype=DTYPE).to(DEVICE).eval()
    proc = AutoProcessor.from_pretrained(MODEL)
    return model, proc


@torch.inference_mode()
def score_episode(ep: Episode, model, proc, force: bool = False, batch: int = 64) -> str:
    out = ep.work / "siglip.npz"
    if out.exists() and not force:
        return f"{ep.code}: cached"
    ms = pd.read_parquet(ep.work / "frames.parquet")["ms"].to_numpy()

    text = proc(text=PROMPTS, padding="max_length", max_length=64, return_tensors="pt").to(DEVICE)
    tf = model.get_text_features(**text).pooler_output
    tf = torch.nn.functional.normalize(tf.float(), dim=-1)
    scale, bias = model.logit_scale.exp().float(), model.logit_bias.float()

    embs, logits = [], []
    for i in range(0, len(ms), batch):
        imgs = [Image.open(ep.work / "frames" / f"{m:07d}.jpg").convert("RGB") for m in ms[i : i + batch]]
        px = proc(images=imgs, return_tensors="pt").to(DEVICE, DTYPE)
        f = torch.nn.functional.normalize(model.get_image_features(**px).pooler_output.float(), dim=-1)
        embs.append(f.cpu().numpy())
        logits.append((f @ tf.T * scale + bias).cpu().numpy())
    np.savez(out, ms=ms, emb=np.concatenate(embs), logits=np.concatenate(logits))
    return f"{ep.code}: {len(ms)} frames scored"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("episodes", nargs="*", type=int)
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()
    model, proc = load()
    for ep in episodes(args.episodes):
        print(score_episode(ep, model, proc, args.force), flush=True)


if __name__ == "__main__":
    main()
