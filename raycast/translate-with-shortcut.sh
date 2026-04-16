#!/bin/bash

set -euo pipefail

# Required parameters:
# @raycast.schemaVersion 1
# @raycast.title Translate with Shortcut
# @raycast.mode fullOutput
# @raycast.packageName Shortcuts
# @raycast.description Translate selected text via a macOS Shortcut and show output in Raycast
# @raycast.argument1 { "type": "text", "placeholder": "Text to translate", "optional": true }
# Optional parameters:
# @raycast.icon 🌍
# @raycast.needsConfirmation false

# Set your shortcut name in Raycast env var RAYCAST_SHORTCUT_NAME.
# Fallback default if env var is not set:
SHORTCUT_NAME="${RAYCAST_SHORTCUT_NAME:-Translate Text}"

if [[ "${SHORTCUT_NAME}" == "SET_SHORTCUT_NAME" ]]; then
  echo "Error: shortcut name is not configured."
  echo "Set env var RAYCAST_SHORTCUT_NAME in Raycast command settings."
  echo "Example: RAYCAST_SHORTCUT_NAME=Translate Text"
  exit 1
fi

input_text=""
if [[ $# -ge 1 && -n "${1//[[:space:]]/}" ]]; then
  input_text="$1"
else
  # Fallback for cases where Raycast argument wasn't passed.
  clipboard_text="$(pbpaste || true)"
  if [[ -n "${clipboard_text//[[:space:]]/}" ]]; then
    input_text="${clipboard_text}"
  fi
fi

if [[ -z "${input_text//[[:space:]]/}" ]]; then
  echo "Error: no text was provided."
  echo "Tip: select text and run this command from Raycast, or pass text manually."
  exit 1
fi

input_file="$(mktemp "${TMPDIR:-/tmp}/raycast-translate-input.XXXXXX.txt")"
output_file="$(mktemp "${TMPDIR:-/tmp}/raycast-translate-output.XXXXXX.txt")"
cleanup() {
  rm -f "${input_file}" "${output_file}"
}
trap cleanup EXIT

printf '%s' "${input_text}" > "${input_file}"

run_output=""
if ! command -v shortcuts >/dev/null 2>&1; then
  echo "Error: 'shortcuts' CLI is unavailable on this macOS installation."
  exit 1
fi

if ! run_output="$(
  shortcuts run "${SHORTCUT_NAME}" \
    --input-path "${input_file}" \
    --output-path "${output_file}" \
    --output-type public.plain-text 2>&1
)"; then
  echo "Error: failed to run shortcut '${SHORTCUT_NAME}'."
  echo ""
  printf '%s\n' "${run_output}"
  echo ""
  echo "Check the shortcut name and ensure it accepts text input and returns text output."
  exit 1
fi

if [[ -s "${output_file}" ]]; then
  cat "${output_file}"
elif [[ -n "${run_output}" ]]; then
  printf '%s\n' "${run_output}"
else
  echo "Shortcut finished without text output."
fi
