#!/bin/bash

set -euo pipefail

# Required parameters:
# @raycast.schemaVersion 1
# @raycast.title Download YouTube Videos
# @raycast.mode fullOutput
# @raycast.packageName YouTube Downloader
# @raycast.description Download YouTube videos using yt-dlp
# @raycast.argument1 { "type": "text", "placeholder": "[Format] YouTube URLs (space separated)" }

CONFIG_DIR="$HOME/.config/yt-dlp"

prompt_for_format() {
    if ! command -v osascript >/dev/null 2>&1; then
        echo "Error: Format is required when osascript is unavailable" >&2
        exit 1
    fi

    local selection=""
    if ! selection=$(osascript <<'APPLESCRIPT'
set formats to {"Best", "720", "480", "Audio"}
set chosen to choose from list formats with prompt "Select download format" default items {"Best"}
if chosen is false then
    return ""
end if
return item 1 of chosen
APPLESCRIPT
    ); then
        selection=""
    fi

    if [[ -z "${selection}" ]]; then
        echo "Download cancelled by user"
        exit 0
    fi

    printf '%s\n' "${selection}"
}

normalize_format() {
    local raw="$1"
    printf '%s\n' "${raw}" | tr '[:upper:]' '[:lower:]'
}

# Check if yt-dlp is installed
if ! command -v yt-dlp >/dev/null 2>&1; then
    echo "Error: yt-dlp is not installed"
    echo "Install with: brew install yt-dlp"
    exit 1
fi

# Check if argument is provided
if [[ $# -eq 0 || -z "${1}" ]]; then
    echo "Error: No YouTube URLs provided"
    exit 1
fi

declare -a parts=()

if [[ $# -eq 1 ]]; then
    input=$(printf '%s\n' "$1")
    IFS=$' \t\n' read -r -a parts <<<"${input}"
else
    parts=("$@")
fi

if [[ ${#parts[@]} -eq 0 ]]; then
    echo "Error: No YouTube URLs provided"
    exit 1
fi

format_candidate="$(normalize_format "${parts[0]}")"
format_label=""
format=""
start_index=0

case "${format_candidate}" in
    best|720|480|audio)
        format="${format_candidate}"
        start_index=1
        ;;
esac

if [[ -z "${format}" ]]; then
    selection="$(prompt_for_format)"
    format="$(normalize_format "${selection}")"
fi

case "${format}" in
    best)
        format_label="Best"
        config_path="${CONFIG_DIR}/best"
        ;;
    720)
        format_label="720"
        config_path="${CONFIG_DIR}/720"
        ;;
    480)
        format_label="480"
        config_path="${CONFIG_DIR}/480"
        ;;
    audio)
        format_label="Audio"
        config_path="${CONFIG_DIR}/audio"
        ;;
    *)
        echo "Error: Unsupported format '${format}'"
        exit 1
        ;;
esac

if [[ ! -f "${config_path}" ]]; then
    echo "Error: Config file not found for format '${format_label}' at ${config_path}"
    exit 1
fi

if [[ ${#parts[@]} -le ${start_index} ]]; then
    echo "Error: No YouTube URLs provided"
    exit 1
fi

urls=("${parts[@]:${start_index}}")

echo "Using format: ${format_label}"

for url in "${urls[@]}"; do
    echo "Downloading: ${url}"
    yt-dlp --config-location "${config_path}" "${url}"
done

echo "Download completed!"
