#!/bin/bash
# Daily ingest wrapper for cron. Cron has a near-empty PATH and no shell
# init, so everything is set explicitly here.

set -u
set -o pipefail

export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"
export LANG="en_US.UTF-8"
export LC_ALL="en_US.UTF-8"

REPO="/Users/Ade/Projects/Thailand10"
PYTHON="/usr/local/bin/python3"
TS="$(date +%Y%m%d-%H%M%S)"
LOG="$REPO/logs/ingest-cron-$TS.log"

mkdir -p "$REPO/logs"

cd "$REPO" || { echo "cd $REPO failed" >&2; exit 1; }

{
  echo "=== cron ingest start: $(date) ==="
  echo "PATH=$PATH"
  echo "PWD=$(pwd)"
  "$PYTHON" ingest_runner.py
  rc=$?
  echo "=== cron ingest end: $(date) (exit=$rc) ==="
  exit $rc
} 2>&1 | tee "$LOG"

exit "${PIPESTATUS[0]}"
