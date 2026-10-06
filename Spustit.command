#!/bin/zsh
set -e
cd "$(dirname "$0")"
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"
if ! command -v python3 >/dev/null; then
  echo "Chybí Python 3. Nainstalujte ho z https://www.python.org/downloads/"
  read -r "?Stiskněte Enter pro zavření."
  exit 1
fi
if ! command -v tesseract >/dev/null && ! command -v swiftc >/dev/null; then
  echo "Chybí lokální OCR. V Terminálu spusťte: brew install tesseract nebo xcode-select --install"
  read -r "?Stiskněte Enter pro zavření."
  exit 1
fi
if [ ! -x .venv/bin/python ]; then
  python3 -m venv .venv
fi
if ! .venv/bin/python -c 'from PIL import Image, ImageOps; import pillow_heif; import zxingcpp' >/dev/null 2>&1; then
  if ! .venv/bin/python -m pip install -r requirements.txt; then
    echo "Instalace se nezdařila. Ověřte připojení k internetu a spusťte aplikaci znovu."
    read -r "?Stiskněte Enter pro zavření."
    exit 1
  fi
fi
exec .venv/bin/python app.py
