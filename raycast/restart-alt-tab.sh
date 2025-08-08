#!/bin/bash

# Required parameters:
# @raycast.schemaVersion 1
# @raycast.title Restart AltTab
# @raycast.mode compact

# Optional parameters:
# @raycast.icon ⏪
# @raycast.packageName Developer Utils
# @raycast.description Restart AltTab

# Restart AltTab
osascript -e 'tell application "AltTab" to quit'
osascript -e 'tell application "AltTab" to activate'

echo "AltTab restarted"

