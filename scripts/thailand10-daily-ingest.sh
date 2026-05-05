#!/bin/bash
# Daily ingest wrapper. Invoked by launchd (com.thailand10.daily-ingest)
# every day at 09:30 local time. PATH/locale set explicitly here because
# launchd (and historically cron) gives the script a near-empty env.

set -u
set -o pipefail

export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"
export LANG="en_US.UTF-8"
export LC_ALL="en_US.UTF-8"

REPO="/Users/Ade/Projects/Thailand10"
PYTHON="/usr/local/bin/python3"
TS="$(date +%Y%m%d-%H%M%S)"
LOG="$REPO/logs/ingest-$TS.log"

mkdir -p "$REPO/logs"

cd "$REPO" || { echo "cd $REPO failed" >&2; exit 1; }

{
  echo "=== daily ingest start: $(date) ==="
  echo "PATH=$PATH"
  echo "PWD=$(pwd)"
  "$PYTHON" ingest_runner.py
  rc=$?
  echo "=== daily ingest end: $(date) (exit=$rc) ==="
  exit $rc
} 2>&1 | tee "$LOG"

exit "${PIPESTATUS[0]}"
