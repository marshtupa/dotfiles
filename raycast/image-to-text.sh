#!/bin/bash

# Required parameters:
# @raycast.schemaVersion 1
# @raycast.title OCR Selected to Markdown
# @raycast.mode fullOutput
# Optional parameters:
# @raycast.icon 📝
# @raycast.packageName Document AI
# @raycast.needsConfirmation false

# === НАСТРОЙКИ ===
PYTHON_SCRIPT="$HOME/dotfiles/raycast/docai_to_md.py"
PYTHON_BIN="$(command -v python3)"
NORMALIZER_SCRIPT="$HOME/dotfiles/raycast/normalize_md.py"

PROMPT_INPUT="$1"

if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "ERROR: python3 не найден."
  exit 1
fi
if [[ ! -f "$PYTHON_SCRIPT" ]]; then
  echo "ERROR: не найден $PYTHON_SCRIPT"
  exit 1
fi
if [[ ! -f "$NORMALIZER_SCRIPT" ]]; then
  echo "ERROR: не найден $NORMALIZER_SCRIPT"
  exit 1
fi

# Получаем выделенные элементы Finder (или текущую папку, если ничего не выделено)
paths=$(osascript <<'APPLESCRIPT'
try
  tell application "Finder"
    if front window exists then
      set theSel to selection as alias list
      if theSel is {} then set theSel to {target of front window as alias}
    else
      error "Открой окно Finder и выдели файл."
    end if
  end tell
  set text item delimiters to linefeed
  set outList to {}
  repeat with a in theSel
    set end of outList to POSIX path of a
  end repeat
  return (outList as text)
on error errMsg
  return "ERROR:" & errMsg
end try
APPLESCRIPT
)

if [[ "$paths" == ERROR:* ]]; then
  echo "$paths"
  exit 1
fi

echo "Document AI OCR → Markdown"
success=0; fail=0
while IFS= read -r filepath; do
  [[ -z "$filepath" ]] && continue
  if [[ -d "$filepath" ]]; then
    echo "⏭ Пропуск папки: $filepath"
    continue
  fi
  echo "→ $filepath"
   "$PYTHON_BIN" "$PYTHON_SCRIPT" \
     "$filepath" || { echo "  ❌ Ошибка"; ((fail++)); continue; }

  # После создания Markdown файла нормализуем его через OpenRouter
  md_path="${filepath%.*}.md"
  if [[ -f "$md_path" ]]; then
    "$PYTHON_BIN" "$NORMALIZER_SCRIPT" "$md_path" || echo "  ⚠️ Нормализация не выполнена"
  else
    echo "  ⚠️ Markdown файл не найден: $md_path"
  fi

  echo "! Файл обработан $filepath"
  ((success++))
done <<< "$paths"

echo "Готово. Успешно: $success, Ошибок: $fail"
