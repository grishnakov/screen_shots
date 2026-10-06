"""Stage 3b: strict second look at each screen the VLM found, on a crop of just that screen.

The full-frame pass is deliberately generous. This pass asks one narrow question about the
cropped region so printed signs, banners, posters and title graphics that looked like screens
in context get rejected. Results are appended to work/SxxEyy/refine.jsonl:
  {"ms": ..., "idx": <index into that frame's screens list>, "is_screen", "kind", "legible", "what"}
"""

import argparse
import asyncio
import json

import cv2

from .config import Episode, episodes
from .verify import load_done
from .vlm import encode_image, run_jobs, ask

CROP_PAD = 0.10
FULL_FRAME_AREA = 0.6  # boxes covering more than this fraction of the frame use the whole frame

PROMPT = """You are given two images from one frame of a TV show. Image 1 is the whole frame with a red rectangle around a candidate object. Image 2 is a magnified crop of the region inside the red rectangle.

Decide whether the object in the red rectangle is an electronic screen that is switched on and displaying content: a computer monitor or laptop display, a television, a phone or tablet display, a projector image, or a video game screen.

It is NOT a screen if it is: a printed poster, banner, billboard or advertisement (including ones on buses, vans, walls or shelters), a sign, a menu board, a vending machine or fridge, a painting, a photograph, a window, a mirror, a whiteboard, a title or credit graphic, or a device that is off, blank or black.
If the crop is filled with software, web-page, email, chat or phone-UI content it IS a screen even though no device edge is visible.

First describe what the object physically is and how you can tell whether it emits light like a display (observation). Then answer:
- is_screen: true only if it is a powered-on electronic display
- kind: computer, laptop, tv, phone, tablet, projector, or other
- legible: true only if you can tell what is being shown on it (read text, recognise the app, site or picture)
- what: a few words describing what is on the screen

When in doubt, answer is_screen true. A lit rectangle that is blurry, dim, small or shows only a solid colour (blue or green screens, logos, blank desktops) still counts as a screen if it looks powered on. Only answer false when you are fairly sure it is NOT an electronic display (a printed poster or sign, a window, an object that is clearly off) or it is not a display at all.
Answer legible true if you can make out any of the content (text, a picture, a UI), even at low resolution."""

SCHEMA = {
    "type": "object",
    "properties": {
        "observation": {"type": "string"},
        "is_screen": {"type": "boolean"},
        "kind": {"enum": ["computer", "laptop", "tv", "phone", "tablet", "projector", "other"]},
        "legible": {"type": "boolean"},
        "what": {"type": "string"},
    },
    "required": ["observation", "is_screen", "kind", "legible", "what"],
}


def normalise_box(box: list[float]) -> list[float]:
    """Qwen sometimes answers in 0-1000 units instead of 0-1 fractions."""
    if max(box) > 1.5:
        box = [v / 1000 for v in box]
    x1, y1, x2, y2 = (min(max(v, 0.0), 1.0) for v in box)
    return [min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2)]


def crop_for(frame, box: list[float]):
    x1, y1, x2, y2 = normalise_box(box)
    if (x2 - x1) * (y2 - y1) > FULL_FRAME_AREA or x2 - x1 < 0.01 or y2 - y1 < 0.01:
        return frame
    h, w = frame.shape[:2]
    px, py = (x2 - x1) * CROP_PAD, (y2 - y1) * CROP_PAD
    return frame[
        int(max(0, y1 - py) * h) : int(min(1, y2 + py) * h), int(max(0, x1 - px) * w) : int(min(1, x2 + px) * w)
    ]


def marked_frame(frame, box: list[float]):
    x1, y1, x2, y2 = normalise_box(box)
    h, w = frame.shape[:2]
    out = frame.copy()
    cv2.rectangle(out, (int(x1 * w), int(y1 * h)), (int(x2 * w), int(y2 * h)), (0, 0, 255), 5)
    return out


def magnified(crop, min_side: int = 512):
    h, w = crop.shape[:2]
    s = min_side / min(h, w)
    return cv2.resize(crop, (round(w * s), round(h * s)), interpolation=cv2.INTER_CUBIC) if s > 1 else crop


def screen_jobs(ep: Episode, ms: int, screens: list[dict]) -> list:
    frame = cv2.imread(str(ep.work / "frames" / f"{ms:07d}.jpg"))
    jobs = []
    for s in screens:
        urls = [encode_image(marked_frame(frame, s["box"]), 1024), encode_image(magnified(crop_for(frame, s["box"])), 768)]
        jobs.append(lambda cl, urls=urls: ask(cl, urls, PROMPT, SCHEMA, max_tokens=350))
    return jobs


def refine_episode(ep: Episode) -> str:
    vlm = load_done(ep.work / "vlm.jsonl")
    out = ep.work / "refine.jsonl"
    done = {(r["ms"], r["idx"]) for r in map(json.loads, out.read_text().splitlines())} if out.exists() else set()

    keys, jobs = [], []
    for ms, rec in sorted(vlm.items()):
        todo = [(i, s) for i, s in enumerate(rec["screens"]) if s["on"] and (ms, i) not in done]
        if not todo:
            continue
        jobs += screen_jobs(ep, ms, [s for _, s in todo])
        keys += [(ms, i) for i, _ in todo]

    if jobs:
        with out.open("a") as f:

            def save(j: int, result: dict | None) -> None:
                if result is not None:
                    f.write(json.dumps({"ms": keys[j][0], "idx": keys[j][1], **result}) + "\n")
                    f.flush()

            asyncio.run(run_jobs(jobs, on_done=save))
    return f"{ep.code}: {len(jobs)} screen crops checked ({len(done)} cached)"


def load_refined(ep: Episode) -> dict[tuple[int, int], dict]:
    path = ep.work / "refine.jsonl"
    return {(r["ms"], r["idx"]): r for r in map(json.loads, path.read_text().splitlines())} if path.exists() else {}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("episodes", nargs="*", type=int)
    args = ap.parse_args()
    for ep in episodes(args.episodes):
        print(refine_episode(ep), flush=True)


if __name__ == "__main__":
    main()
