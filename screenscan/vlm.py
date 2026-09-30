"""VLM client: asks Qwen (served by vLLM) to inventory the screens visible in a frame."""

import asyncio
import base64
import json
from pathlib import Path

import cv2
from openai import AsyncOpenAI

from .config import VLM_API_KEY, VLM_BASE_URL, VLM_IS_LOCAL, VLM_MODEL

PROMPT = """You are helping catalogue every time a screen appears in a TV show.

Look at this frame and list every screen visible in it: computer monitors, laptops, TVs, projector screens, phones, tablets, game consoles, handheld devices, digital signs, etc.

IMPORTANT: many shots are extreme close-ups where the frame is filled by on-screen content (a web page, email, chat window, software dialog, phone display, TV picture) and no device edge or bezel is visible. These COUNT as a screen with prominence "fills_frame". Recognise them by user-interface elements, text rendered like software, scan lines, pixel structure or glare.

For each display report:
- type: one of computer, laptop, tv, phone, tablet, projector, other
- on: true only if the display is clearly powered on and showing content (false if black, blank, reflective or switched off)
- content_visible: true only if you can actually see what is on the display (text, a website, an image, a video, a UI). False if it is too small, too blurry, too dark, or turned away from the camera to make out.
- prominence: "fills_frame" if the display content takes up most of the frame (extreme close-up), "main" if it is a clear subject of the shot, "background" if it is visible but incidental
- box: [x1, y1, x2, y2] bounding box of the display's lit area as fractions of the image width/height (0-1)
- what: a few words describing the content (e.g. "email inbox", "news broadcast", "text message")

Also report:
- frame_is_credits_or_title: true if this is opening titles, end credits, a logo card or a black frame
- sharp: true if the frame is in focus and not motion blurred or mid-transition

Do not list things that are not screens: windows, mirrors, paintings, whiteboards, posters, framed photos, or printed pages. If there are no displays, return an empty list."""

SCHEMA = {
    "type": "object",
    "properties": {
        "screens": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "type": {"enum": ["computer", "laptop", "tv", "phone", "tablet", "projector", "other"]},
                    "on": {"type": "boolean"},
                    "content_visible": {"type": "boolean"},
                    "prominence": {"enum": ["fills_frame", "main", "background"]},
                    "box": {"type": "array", "items": {"type": "number"}, "minItems": 4, "maxItems": 4},
                    "what": {"type": "string"},
                },
                "required": ["type", "on", "content_visible", "prominence", "box", "what"],
            },
        },
        "frame_is_credits_or_title": {"type": "boolean"},
        "sharp": {"type": "boolean"},
    },
    "required": ["screens", "frame_is_credits_or_title", "sharp"],
}


# Backend-specific switches. Both turn off "thinking", which otherwise eats the token budget and truncates the JSON.
EXTRA_BODY = (
    {"chat_template_kwargs": {"enable_thinking": False}}  # local vLLM
    if VLM_IS_LOCAL
    else {"reasoning": {"enabled": False}, "provider": {"require_parameters": True}}  # OpenRouter
)


def encode_image(img, max_side: int = 1280) -> str:
    h, w = img.shape[:2]
    s = max_side / max(h, w)
    if s < 1:
        img = cv2.resize(img, (round(w * s), round(h * s)), interpolation=cv2.INTER_AREA)
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 90])
    return "data:image/jpeg;base64," + base64.b64encode(buf).decode()


def encode(path: Path, max_side: int = 1280) -> str:
    return encode_image(cv2.imread(str(path)), max_side)


def client() -> AsyncOpenAI:
    if not VLM_IS_LOCAL and not VLM_API_KEY:
        raise SystemExit("VLM_API_KEY is not set: copy .env.template to .env and add your key")
    return AsyncOpenAI(base_url=VLM_BASE_URL, api_key=VLM_API_KEY or "none", timeout=300)


async def ask(cl: AsyncOpenAI, image_url: str | list[str], prompt: str, schema: dict, max_tokens: int = 700) -> dict:
    urls = [image_url] if isinstance(image_url, str) else image_url
    resp = await cl.chat.completions.create(
        model=VLM_MODEL,
        messages=[
            {
                "role": "user",
                "content": [{"type": "image_url", "image_url": {"url": u}} for u in urls]
                + [{"type": "text", "text": prompt}],
            }
        ],
        temperature=0,
        max_tokens=max_tokens,
        response_format={"type": "json_schema", "json_schema": {"name": "answer", "schema": schema}},
        extra_body=EXTRA_BODY,
    )
    return json.loads(resp.choices[0].message.content)


async def inspect(cl: AsyncOpenAI, path: Path) -> dict:
    return await ask(cl, encode(path), PROMPT, SCHEMA)


async def run_jobs(jobs: list, concurrency: int = 8, on_done=None) -> list[dict | None]:
    """Run `jobs` (callables taking a client and returning an awaitable) with bounded concurrency."""
    cl = client()
    sem = asyncio.Semaphore(concurrency)
    out: list[dict | None] = [None] * len(jobs)

    async def one(i: int, job) -> None:
        async with sem:
            try:
                out[i] = await job(cl)
            except Exception as e:  # keep going; failures are retried on the next run
                out[i] = None
                print(f"VLM error on job {i}: {e!r}"[:200], flush=True)
        if on_done:
            on_done(i, out[i])

    await asyncio.gather(*(one(i, j) for i, j in enumerate(jobs)))
    return out


async def inspect_many(paths: list[Path], concurrency: int = 8, on_done=None) -> list[dict | None]:
    return await run_jobs([lambda cl, p=p: inspect(cl, p) for p in paths], concurrency, on_done)
