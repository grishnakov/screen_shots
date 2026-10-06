"""Stage 5: write the deliverables.

output/<episode slug>/<slug>_<MM-SS>.png   lossless full-resolution frame of each appearance
output/screens.xlsx                        spreadsheet in the sample's layout (first four columns)
output/review.html                         contact sheet with the automatic labels, for weeding out mistakes
"""

import argparse
import html
import io
import json
from datetime import datetime

import av
import cv2
from openpyxl import Workbook
from openpyxl.drawing.image import Image as XlImage
from openpyxl.styles import Alignment, Font
from PIL import Image

from .config import OUTPUT_DIR, Episode, episodes, fmt_ts

THUMB = (480, 270)
HEADERS = [
    "Episode Number and Title",
    "Episode air date",
    "Time stamp when screen appears in episode (08:14) minutes:seconds",
    "Screenshot of interface/screen (labelled with name of episode, 1920 x 1080px)",
]


def grab_frames(ep: Episode, timestamps_ms: list[int]) -> dict[int, "av.VideoFrame"]:
    """Decode the exact frames at the given timestamps from the source video (full resolution)."""
    wanted = sorted(timestamps_ms)
    out = {}
    with av.open(str(ep.video)) as container:
        stream = container.streams.video[0]
        stream.thread_type = "AUTO"
        for target in wanted:
            container.seek(max(0, int(target / 1000 / stream.time_base) - 2 * round(1 / stream.time_base)), stream=stream)
            for frame in container.decode(stream):
                if frame.time * 1000 >= target - 1:
                    out[target] = frame.to_ndarray(format="bgr24")
                    break
    return out


def png_path(ep: Episode, ms: int):
    return OUTPUT_DIR / ep.slug / f"{ep.slug}_{fmt_ts(ms, '-')}.png"


def export_pngs(ep: Episode, apps: list[dict]) -> None:
    todo = [a["ms"] for a in apps if not png_path(ep, a["ms"]).exists()]
    if not todo:
        return
    (OUTPUT_DIR / ep.slug).mkdir(parents=True, exist_ok=True)
    for ms, bgr in grab_frames(ep, todo).items():
        cv2.imwrite(str(png_path(ep, ms)), bgr)


def build_xlsx(rows: list[tuple[Episode, dict]]) -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "Screens"
    ws.append(HEADERS)
    for c in ws[1]:
        c.font = Font(bold=True)
        c.alignment = Alignment(wrap_text=True, vertical="top")
    for col, width in zip("ABCD", (34, 16, 22, 70)):
        ws.column_dimensions[col].width = width

    for r, (ep, a) in enumerate(rows, start=2):
        ws.cell(r, 1, ep.label)
        if ep.air_date is not None:
            ws.cell(r, 2, datetime.combine(ep.air_date, datetime.min.time())).number_format = "mm/dd/yy"
        ts = ws.cell(r, 3, fmt_ts(a["ms"]))
        ts.number_format = "@"  # text, so Excel keeps 00:19 as minutes:seconds instead of a time of day
        for col in (1, 2, 3):
            ws.cell(r, col).alignment = Alignment(vertical="top", wrap_text=True)
        thumb = Image.open(png_path(ep, a["ms"])).convert("RGB")
        thumb.thumbnail(THUMB)
        buf = io.BytesIO()
        thumb.save(buf, "PNG")
        buf.seek(0)
        img = XlImage(buf)
        ws.add_image(img, f"D{r}")
        ws.row_dimensions[r].height = THUMB[1] * 0.75 + 4  # points
    ws.freeze_panes = "A2"
    wb.save(OUTPUT_DIR / "screens.xlsx")


def build_review(rows: list[tuple[Episode, dict]]) -> None:
    cards = []
    for ep, a in rows:
        rel = png_path(ep, a["ms"]).relative_to(OUTPUT_DIR)
        cards.append(
            f'<figure><a href="{html.escape(str(rel))}"><img loading="lazy" src="{html.escape(str(rel))}"></a>'
            f"<figcaption><b>{ep.code} {fmt_ts(a['ms'])}</b> &middot; {html.escape(a['type'])}, {html.escape(a['prominence'])}"
            f"<br>{html.escape(a['what'])}<br><small>{a['n_frames']} frames in appearance, "
            f"{fmt_ts(a['start_ms'])}&ndash;{fmt_ts(a['end_ms'])}</small></figcaption></figure>"
        )
    OUTPUT_DIR.joinpath("review.html").write_text(
        "<!doctype html><meta charset=utf-8><title>Screens review</title>"
        "<style>body{font:14px system-ui;background:#111;color:#ddd;margin:16px}"
        ".g{display:grid;grid-template-columns:repeat(auto-fill,minmax(420px,1fr));gap:12px}"
        "figure{margin:0;background:#1c1c1c;padding:8px;border-radius:6px}img{width:100%;display:block}"
        "figcaption{padding-top:6px}small{color:#888}a{color:inherit}</style>"
        f"<h2>{len(rows)} screen appearances</h2><div class=g>{''.join(cards)}</div>"
    )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("episodes", nargs="*", type=int)
    args = ap.parse_args()
    rows: list[tuple[Episode, dict]] = []
    for ep in episodes(args.episodes):
        path = ep.work / "appearances.json"
        if not path.exists():
            print(f"{ep.code}: no appearances.json, skipping")
            continue
        apps = json.loads(path.read_text())
        export_pngs(ep, apps)
        rows += [(ep, a) for a in apps]
        print(f"{ep.code}: {len(apps)} screenshots", flush=True)
    OUTPUT_DIR.mkdir(exist_ok=True)
    build_xlsx(rows)
    build_review(rows)
    print(f"wrote {OUTPUT_DIR}/screens.xlsx and review.html ({len(rows)} rows)")


if __name__ == "__main__":
    main()
