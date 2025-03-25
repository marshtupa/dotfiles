#!/bin/bash

# Required parameters:
# @raycast.schemaVersion 1
# @raycast.title Restart ChatGPT
# @raycast.mode compact

# Optional parameters:
# @raycast.icon ⏪
# @raycast.packageName Developer Utils
# @raycast.description Restart ChatGPT

# Restart ChatGPT
osascript -e 'tell application "ChatGPT" to quit'
osascript -e 'tell application "ChatGPT" to activate'

echo "ChatGPT restarted"

