#!/usr/bin/env bash
# Full pipeline, every stage resumable (cached results are skipped).
#   SEASON=1 ./run.sh   all episodes of season 1 (SEASON defaults to 1)
#   SEASON=7 ./run.sh 1 2 3   just those episodes of season 7
set -euo pipefail
cd "$(dirname "$0")"
eps="$*"
step() { echo "=== $(date +%T) $1"; shift; "$@" 2>&1 | grep -v -i 'warn\|installed\|Loading weights\|it/s\]' || true; }

step sample   uv run -m screenscan.sample --workers 4 $eps
step siglip   uv run -m screenscan.siglip $eps
step shared   uv run -m screenscan.shared          # always over every scored episode
step detect   uv run -m screenscan.detect $eps
step verify   uv run -m screenscan.verify $eps
step refine   uv run -m screenscan.refine $eps
step select   uv run -m screenscan.select $eps
step export   uv run -m screenscan.export $eps
echo "=== $(date +%T) done"
