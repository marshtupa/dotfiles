# dotfiles

## Installation
```bash
xcode-select --install
softwareupdate --install-rosetta --agree-to-license
git clone https://github.com/marshtupa/dotfiles.git
cd ~/dotfiles
sh ./setup
```

## Manual
- Open Automator
- Go to System Preferences → Users & Groups → Login Items and add this application
  - Select file from icloud drive (Automator → arc_mount.app)
- Raycast X (Beta) — homebrew cask'а нет, ставится вручную с сайта Raycast.
  Классическую версию (`cask "raycast"`) параллельно не ставить: обе клеймят URL-схему
  `raycast://`, и диплинки расширений (например OpenAI Translator → Query OCR) уходят
  в ту копию, где расширение не установлено.
