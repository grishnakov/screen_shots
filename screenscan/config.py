"""Paths, episode metadata and tunable thresholds."""

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

# Titles and original air dates from https://en.wikipedia.org/wiki/Degrassi:_The_Next_Generation_season_N
# Season 1 lists episodes 1 and 2 as one two-part premiere, so there is no episode 2.
SEASON_1 = {
    1: ("Mother and Child Reunion", dt.date(2001, 10, 14)),
    3: ("Family Politics", dt.date(2001, 11, 4)),
    4: ("Eye of the Beholder", dt.date(2001, 11, 11)),
    5: ("Parents' Day", dt.date(2001, 11, 18)),
    6: ("The Mating Game", dt.date(2001, 11, 25)),
    7: ("Basketball Diaries", dt.date(2001, 12, 2)),
    8: ("Secrets & Lies", dt.date(2001, 12, 9)),
    9: ("Coming of Age", dt.date(2001, 12, 16)),
    10: ("Rumours and Reputations", dt.date(2002, 1, 6)),
    11: ("Friday Night", dt.date(2002, 1, 27)),
    12: ("Wannabe", dt.date(2002, 2, 3)),
    13: ("Cabaret", dt.date(2002, 2, 17)),
    14: ("Under Pressure", dt.date(2002, 2, 24)),
    15: ("Jagged Little Pill", dt.date(2002, 3, 3)),
}

SEASON_7 = {
    1: ("Standing in the Dark (Part 1)", dt.date(2008, 1, 14)),
    2: ("Standing in the Dark (Part 2)", dt.date(2008, 1, 21)),
    3: ("Love Is a Battlefield", dt.date(2008, 5, 19)),
    4: ("It's Tricky", dt.date(2008, 1, 28)),
    5: ("Death or Glory (Part 1)", dt.date(2008, 2, 4)),
    6: ("Death or Glory (Part 2)", dt.date(2008, 2, 11)),
    7: ("We Got the Beat", dt.date(2008, 2, 18)),
    8: ("Jessie's Girl", dt.date(2008, 2, 25)),
    9: ("Hungry Eyes", dt.date(2008, 3, 3)),
    10: ("Pass the Dutchie", dt.date(2008, 3, 10)),
    11: ("Owner of a Lonely Heart", dt.date(2008, 3, 17)),
    12: ("Live to Tell", dt.date(2008, 3, 24)),
    13: ("Bust a Move (Part 1)", dt.date(2008, 3, 31)),
    14: ("Bust a Move (Part 2)", dt.date(2008, 4, 7)),
    15: ("Got My Mind Set on You", dt.date(2008, 4, 14)),
    16: ("Sweet Child o' Mine", dt.date(2008, 4, 21)),
    17: ("Talking in Your Sleep", dt.date(2008, 4, 28)),
    18: ("Another Brick in the Wall", dt.date(2008, 5, 5)),
    19: ("Broken Wings", dt.date(2008, 5, 12)),
    20: ("Ladies' Night", dt.date(2008, 5, 26)),
    21: ("Everything She Wants", dt.date(2008, 6, 2)),
    22: ("Don't Stop Believin'", dt.date(2008, 6, 9)),
    23: ("If This Is It", dt.date(2008, 6, 16)),
    24: ("We Built This City", dt.date(2008, 6, 23)),
}


# Episode lists (title, air date) known to the program, keyed by season number.
TITLES = {1: SEASON_1, 7: SEASON_7}

# Videos are recognised by an "S01E03"-style tag anywhere in the file name (case-insensitive).
EPISODE_TAG = re.compile(r"(?<![A-Za-z0-9])[Ss](\d{1,2})[Ee](\d{1,3})(?!\d)")


def _legacy_identify(video: Path) -> tuple[int, int] | None:
    """Fallback for the original Degrassi download names, which carry no SxxEyy tag.

    Season 1 lives in video/full_episodes/ and is prefixed 01-14 in download order; the real episode is the
    production code (..._103_Degrassi... is episode 3). Season 7 lives in video/ prefixed with its number ("07 - ...").
    """
    try:
        if video.parent == VIDEO_ROOT / "full_episodes":
            return 1, int(re.search(r"_(1\d\d)_Degrassi", video.name).group(1)) - 100
        if video.parent == VIDEO_ROOT:
            return 7, int(video.name.split(" ", 1)[0])
    except (AttributeError, ValueError):
        pass
    return None


def identify(video: Path) -> tuple[int, int] | None:
    """(season, episode) for a video file, or None if the name carries no recognisable episode number."""
    if tag := EPISODE_TAG.search(video.name):
        return int(tag.group(1)), int(tag.group(2))
    return _legacy_identify(video)


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
    air_date: dt.date
    video: Path

    @property
    def code(self) -> str:
        return f"S{self.season:02d}E{self.number:02d}"

    @property
    def slug(self) -> str:
        return f"{self.code}_" + re.sub(r"[^A-Za-z0-9]+", "_", self.title).strip("_")

    @property
    def label(self) -> str:
        """Matches the sample sheet's 'S1 E3, Family Politics' style."""
        return f"S{self.season} E{self.number}, {self.title}"

    @property
    def work(self) -> Path:
        return WORK_DIR / self.code


def episodes(selection: list[int] | None = None) -> list[Episode]:
    """Episodes of the active season (SEASON env var) found under video/, ordered by episode number."""
    titles = TITLES.get(SEASON)
    out = []
    for (season, number), video in _scan_videos().items():
        if season != SEASON or (selection and number not in selection):
            continue
        if titles is None or number not in titles:
            raise SystemExit(f"{video.name}: no title/air date is known for S{season:02d}E{number:02d}")
        title, air = titles[number]
        out.append(Episode(season, number, title, air, video))
    return sorted(out, key=lambda e: e.number)


def fmt_ts(ms: int, sep: str = ":") -> str:
    """Timestamp as minutes:seconds (never decimal minutes), e.g. 754_000 -> '12:34'.

    Use sep="-" for filenames. Truncates to whole seconds, matching how a
    player displays the position.
    """
    s = int(ms) // 1000
    return f"{s // 60:02d}{sep}{s % 60:02d}"
