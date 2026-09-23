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
#
# Checking the public path as well:
#
#   HEALTH_NAME=funnel HEALTH_PUBLIC_DNS=1 \
#   HEALTH_URL=https://commaserver.tail475cee.ts.net/health deploy/healthcheck.sh
#
# The two are separate checks on purpose. The server answering on the tailnet
# says the machine is up; it says nothing about the route teachers outside
# the building use, which runs through Tailscale's public relay and can break
# on its own — a lapsed Funnel config, an ACL edit, the relay itself.
set -uo pipefail

URL="${HEALTH_URL:-http://100.107.235.123:8085/health}"
NAME="${HEALTH_NAME:-}"
# One state file per check, or two checks would overwrite each other's
# memory and alert on every run as they disagreed.
STATE="${HEALTH_STATE:-$HOME/.cache/cramschool-health${NAME:+-$NAME}}"
mkdir -p "$(dirname "$STATE")"

# Resolve through public DNS when asked to.
#
# This is what makes the Funnel check a Funnel check. A machine that is
# itself on the tailnet resolves the public name to the PRIVATE address
# through MagicDNS, so a plain curl here would walk straight in over the
# tailnet and report the public route healthy while it was down. Asking a
# public resolver and pinning curl to the answer forces the request out
# through the relay, the way a teacher at home reaches it.
resolve=()
if [ "${HEALTH_PUBLIC_DNS:-0}" = 1 ]; then
    host="$(printf '%s' "$URL" | sed -E 's#^[a-z]+://([^/:]+).*#\1#')"
    ip="$(curl -s --max-time 10 -H 'accept: application/dns-json' \
            "https://cloudflare-dns.com/dns-query?name=$host&type=A" \
          | python3 -c 'import sys, json
try:
    answers = [a["data"] for a in json.load(sys.stdin).get("Answer", []) if a.get("type") == 1]
    print(answers[0] if answers else "")
except Exception:
    print("")')"
    # No answer is reported as down rather than skipped. A check that quietly
    # does nothing when it cannot run is indistinguishable from a passing one.
    [ -n "$ip" ] && resolve=(--resolve "$host:443:$ip")
fi

previous="$(cat "$STATE" 2>/dev/null || echo up)"
if { [ "${HEALTH_PUBLIC_DNS:-0}" != 1 ] || [ ${#resolve[@]} -gt 0 ]; } \
   && curl -fsS --max-time 15 "${resolve[@]}" "$URL" | grep -q '"status":"ok"'; then
    current=up
else
    current=down
fi
echo "$current" > "$STATE"

# Only on a change. A check that shouts every ten minutes while the server is
# down is a check that gets muted, and a muted check is worse than none —
# it looks like coverage.
[ "$current" = "$previous" ] && exit 0

label="${NAME:+（$NAME）}"
if [ "$current" = down ]; then
    message="⚠️ 批改伺服器沒有回應$label：$URL"
else
    message="✅ 批改伺服器恢復$label：$URL"
fi
echo "$(date '+%Y-%m-%d %H:%M:%S')  $message"

# Wired to whatever is at hand. Left as an explicit hook rather than guessing
# at a notification service: an alert that goes somewhere nobody looks is the
# same as no alert.
if [ -n "${HEALTH_NOTIFY_CMD:-}" ]; then
    "$HEALTH_NOTIFY_CMD" "$message" || true
fi
