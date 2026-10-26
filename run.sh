#!/usr/bin/env bash
# Kept for existing macOS/Linux habits; the pipeline itself lives in screenscan/__main__.py.
#   SEASON=1 ./run.sh       same as: uv run -m screenscan --season 1
#   SEASON=7 ./run.sh 1 2 3 same as: uv run -m screenscan --season 7 1 2 3
set -euo pipefail
cd "$(dirname "$0")"
exec uv run -m screenscan "$@"
