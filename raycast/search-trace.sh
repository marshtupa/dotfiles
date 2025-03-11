#!/bin/bash

# Required parameters:
# @raycast.schemaVersion 1
# @raycast.title Search TSUM Trace
# @raycast.mode compact

# Optional parameters:
# @raycast.icon 🔍
# @raycast.argument1 { "type": "text", "placeholder": "Trace ID" }
# @raycast.packageName Developer Utils
# @raycast.description Open trace by ID in tsum.yandex-team.ru

# Construct the URL
URL="https://tsum.yandex-team.ru/trace/$1"

# Open in default browser
open "$URL"
