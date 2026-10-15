#!/bin/bash
# Daily pipeline: scrape newswire.lk -> build site -> deploy to Netlify.
# Manual local run. The scheduled 10:00 run happens in GitHub Actions (.github/workflows/daily.yml).
set -uo pipefail
export PATH="/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin:$PATH"
cd "$(dirname "$0")" || exit 1

mkdir -p logs
LOG="logs/$(date +%Y-%m-%d).log"
exec >>"$LOG" 2>&1
echo "===== $(date '+%Y-%m-%d %H:%M:%S') daily run ====="

notify() {  # macOS notification so failures don't go unnoticed
  osascript -e "display notification \"$1\" with title \"Lanka Daily Digest\"" >/dev/null 2>&1 || true
}
fail() { echo "FAILED: $1"; notify "Daily update failed: $1 (see $LOG)"; exit 1; }

.venv/bin/python scraper.py      || fail "scraping"
.venv/bin/python build_site.py   || fail "building the site"
./deploy.sh                      || fail "deploying to Netlify"

echo "===== done $(date '+%H:%M:%S') ====="
find logs -name '*.log' -mtime +30 -delete 2>/dev/null
