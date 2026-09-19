#!/usr/bin/env bash
# Tell me when the grading server stops answering.
#
# The failure that matters here is not a subtle one. It is the laptop in the
# cram school being asleep, rebooted, off the tailnet, or simply stopped — and
# the reason it matters more now is that teachers reaching it from outside the
# building cannot walk over and look. Silence is the whole problem: without
# this, the first report comes from a teacher who has already lost their
# afternoon.
#
# Deliberately small. A single developer will not read a dashboard; they will
# read one message that says the thing is down.
#
#   usage: deploy/healthcheck.sh
#   cron:  */10 * * * *  /path/to/deploy/healthcheck.sh
set -uo pipefail

URL="${HEALTH_URL:-http://100.107.235.123:8085/health}"
STATE="${HEALTH_STATE:-$HOME/.cache/cramschool-health}"
mkdir -p "$(dirname "$STATE")"

previous="$(cat "$STATE" 2>/dev/null || echo up)"
if curl -fsS --max-time 10 "$URL" | grep -q '"status":"ok"'; then
    current=up
else
    current=down
fi
echo "$current" > "$STATE"

# Only on a change. A check that shouts every ten minutes while the server is
# down is a check that gets muted, and a muted check is worse than none —
# it looks like coverage.
[ "$current" = "$previous" ] && exit 0

if [ "$current" = down ]; then
    message="⚠️ 批改伺服器沒有回應：$URL"
else
    message="✅ 批改伺服器恢復：$URL"
fi
echo "$(date '+%Y-%m-%d %H:%M:%S')  $message"

# Wired to whatever is at hand. Left as an explicit hook rather than guessing
# at a notification service: an alert that goes somewhere nobody looks is the
# same as no alert.
if [ -n "${HEALTH_NOTIFY_CMD:-}" ]; then
    "$HEALTH_NOTIFY_CMD" "$message" || true
fi
