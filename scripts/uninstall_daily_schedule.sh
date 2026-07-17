#!/bin/zsh

set -euo pipefail

LABEL="com.asti.daily-monitor"
PLIST_PATH="$HOME/Library/LaunchAgents/$LABEL.plist"

if [[ -f "$PLIST_PATH" ]]; then
  launchctl bootout "gui/$UID" "$PLIST_PATH" 2>/dev/null || true
  rm "$PLIST_PATH"
fi

echo "ASTI daily monitoring removed."

