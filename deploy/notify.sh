#!/usr/bin/env bash
# Put a message somewhere a person will actually see it.
#
# This runs inside WSL, where nothing is looking at stdout. A Windows toast is
# the one channel that reaches the human sitting at the machine, so the check
# script hands its message here rather than deciding for itself.
#
# Falls back to writing a line, because an alert that fails silently is worse
# than an alert that is merely ugly.
set -uo pipefail
MESSAGE="${1:-}"
[ -z "$MESSAGE" ] && exit 0

LOG="${NOTIFY_LOG:-$HOME/.cache/cramschool-alerts.log}"
mkdir -p "$(dirname "$LOG")"
echo "$(date '+%Y-%m-%d %H:%M:%S')  $MESSAGE" >> "$LOG"

command -v powershell.exe >/dev/null 2>&1 || exit 0
powershell.exe -NoProfile -Command "
\$ErrorActionPreference = 'Stop'
[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] | Out-Null
\$xml = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent(
    [Windows.UI.Notifications.ToastTemplateType]::ToastText02)
\$t = \$xml.GetElementsByTagName('text')
\$t.Item(0).AppendChild(\$xml.CreateTextNode('浮島 批改伺服器')) | Out-Null
\$t.Item(1).AppendChild(\$xml.CreateTextNode('$MESSAGE')) | Out-Null
[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('浮島').Show(
    [Windows.UI.Notifications.ToastNotification]::new(\$xml))
" >/dev/null 2>&1 || true
