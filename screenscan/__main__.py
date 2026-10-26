"""Full pipeline, every stage resumable (cached results are skipped). Works the same on Windows, macOS and Linux.

  uv run -m screenscan --season 1           all episodes of season 1 (defaults to $SEASON, else 1)
  uv run -m screenscan --season 7 1 2 3     just those episodes of season 7
  uv run -m screenscan --season 7 --only verify,refine 3
  uv run -m screenscan --season 7 --list    show which video file each episode matched
"""

import argparse
import os
import re
import subprocess
import sys
import time

STAGES = ["sample", "siglip", "shared", "detect", "verify", "refine", "select", "export"]
EXTRA_ARGS = {"sample": ["--workers", "4"]}
ALL_EPISODES = {"shared"}  # always over every scored episode
NOISE = re.compile(r"warn|installed|Loading weights|it/s\]", re.IGNORECASE)


def run_stage(stage: str, episodes: list[str], env: dict[str, str]) -> None:
    print(f"=== {time.strftime('%H:%M:%S')} {stage}", flush=True)
    cmd = [sys.executable, "-m", f"screenscan.{stage}", *EXTRA_ARGS.get(stage, [])]
    if stage not in ALL_EPISODES:
        cmd += episodes
    # Text mode splits on "\r" as well, so each progress-bar redraw is its own line and gets filtered.
    with subprocess.Popen(
        cmd, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace"
    ) as proc:
        for line in proc.stdout:
            if not NOISE.search(line):
                print(line, end="", flush=True)
    if proc.returncode:
        print(f"({stage} exited with code {proc.returncode}; continuing)", flush=True)


def main() -> None:
    ap = argparse.ArgumentParser(prog="screenscan", description="Find every on-screen screen in a season's episodes.")
    ap.add_argument("episodes", nargs="*", type=int, help="episode numbers (default: all found for the season)")
    ap.add_argument("--season", type=int, default=int(os.environ.get("SEASON", "1")))
    ap.add_argument("--only", help=f"comma-separated subset of stages: {','.join(STAGES)}")
    ap.add_argument("--device", choices=["cuda", "mps", "cpu"], help="force the compute device for local models")
    ap.add_argument("--list", action="store_true", help="list the season's episodes and their video files, then exit")
    args = ap.parse_args()

    os.environ["SEASON"] = str(args.season)  # read by screenscan.config, here and in every stage
    if args.device:
        os.environ["SCREENSCAN_DEVICE"] = args.device

    if args.list:
        from .config import episodes

        for e in episodes(args.episodes):
            print(e.code, "|", e.title, "|", e.video.name)
        return

    stages = STAGES
    if args.only:
        chosen = {s.strip() for s in args.only.split(",")}
        if unknown := chosen - set(STAGES):
            ap.error(f"unknown stage(s) {', '.join(sorted(unknown))}; choose from {', '.join(STAGES)}")
        stages = [s for s in STAGES if s in chosen]  # always in pipeline order

    # UTF-8 everywhere, so model output with non-Latin text can't crash on a Windows code page.
    env = {**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"}
    sys.stdout.reconfigure(errors="replace")
    try:
        for stage in stages:
            run_stage(stage, [str(n) for n in args.episodes], env)
    except KeyboardInterrupt:
        sys.exit("\ninterrupted; run the same command again to resume")
    print(f"=== {time.strftime('%H:%M:%S')} done")


if __name__ == "__main__":
    main()
