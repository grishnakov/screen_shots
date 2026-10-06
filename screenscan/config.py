"""Paths, episode metadata and tunable thresholds."""

import csv
import datetime as dt
import functools
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SEASON = int(os.environ.get("SEASON", "1"))  # which season the stages operate on: SEASON=7 uv run -m ...
VIDEO_ROOT = ROOT / "video"
WORK_DIR = ROOT / "work"  # intermediate artifacts (sampled frames, features, VLM results), keyed by SxxEyy
OUTPUT_DIR = ROOT / "output" / f"season{SEASON:02d}"  # final screenshots, spreadsheet, review page

SAMPLE_FPS = 2.0

def _load_dotenv(path: Path) -> None:
    """Minimal .env reader (KEY=value lines); real environment variables win."""
    if not path.is_file():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


_load_dotenv(ROOT / ".env")

# Any OpenAI-compatible endpoint that accepts images; see .env.template.
VLM_BASE_URL = os.environ.get("VLM_BASE_URL", "https://openrouter.ai/api/v1")
VLM_MODEL = os.environ.get("VLM_MODEL", "deepseek/deepseek-v4.1-flash")
VLM_API_KEY = os.environ.get("VLM_API_KEY", "")
VLM_IS_LOCAL = "127.0.0.1" in VLM_BASE_URL or "localhost" in VLM_BASE_URL

# Optional local metadata, excluded from version control.
METADATA_PATH = ROOT / "episodes.csv"


def _load_metadata() -> dict[tuple[int, int], tuple[str, dt.date | None]]:
    if not METADATA_PATH.is_file():
        return {}
    with METADATA_PATH.open(newline="", encoding="utf-8-sig") as source:
        metadata = {}
        for row in csv.DictReader(source):
            key = int(row["season"]), int(row["episode"])
            if key in metadata:
                raise ValueError(f"Duplicate episode metadata: {key}")
            air = row["air_date"].strip()
            metadata[key] = row["title"].strip(), dt.date.fromisoformat(air) if air else None
        return metadata


# Videos are recognised by an "S01E03"-style tag anywhere in the file name (case-insensitive).
EPISODE_TAG = re.compile(r"(?<![A-Za-z0-9])[Ss](\d{1,2})[Ee](\d{1,3})(?!\d)")


def identify(video: Path) -> tuple[int, int] | None:
    """(season, episode) for a video file, or None if the name carries no recognisable episode number."""
    if tag := EPISODE_TAG.search(video.name):
        return int(tag.group(1)), int(tag.group(2))
    return None


@functools.cache
def _scan_videos() -> dict[tuple[int, int], Path]:
    found: dict[tuple[int, int], Path] = {}
    for video in sorted(VIDEO_ROOT.rglob("*.mkv")):
        key = identify(video)
        if key is None:
            print(f"warning: ignoring {video.relative_to(ROOT)}: no SxxEyy tag in the file name", file=sys.stderr)
        elif key in found:
            raise SystemExit(f"S{key[0]:02d}E{key[1]:02d} matches two files:\n  {found[key]}\n  {video}")
        else:
            found[key] = video
    return found


@dataclass(frozen=True)
class Episode:
    season: int
    number: int
    title: str
    air_date: dt.date | None
    video: Path

    @property
    def code(self) -> str:
        return f"S{self.season:02d}E{self.number:02d}"

    @property
    def slug(self) -> str:
        return f"{self.code}_" + re.sub(r"[^A-Za-z0-9]+", "_", self.title).strip("_")

    @property
    def label(self) -> str:
        """Season and episode number followed by the title."""
        return f"S{self.season} E{self.number}, {self.title}"

    @property
    def work(self) -> Path:
        return WORK_DIR / self.code


def episodes(selection: list[int] | None = None) -> list[Episode]:
    """Episodes of the active season (SEASON env var) found under video/, ordered by episode number."""
    metadata = _load_metadata()
    out = []
    for (season, number), video in _scan_videos().items():
        if season != SEASON or (selection and number not in selection):
            continue
        title, air = metadata.get((season, number), (f"Episode {number}", None))
        title = title or f"Episode {number}"
        out.append(Episode(season, number, title, air, video))
    return sorted(out, key=lambda e: e.number)


def fmt_ts(ms: int, sep: str = ":") -> str:
    """Timestamp as minutes:seconds (never decimal minutes), e.g. 754_000 -> '12:34'.

    Use sep="-" for filenames. Truncates to whole seconds, matching how a
    player displays the position.
    """
    s = int(ms) // 1000
    return f"{s // 60:02d}{sep}{s % 60:02d}"
