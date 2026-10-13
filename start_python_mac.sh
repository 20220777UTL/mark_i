#!/bin/bash
set -euo pipefail

PROJECT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)
WINE_BIN="/Applications/Wine Staging.app/Contents/Resources/wine/bin/wine"
if [ ! -x "$WINE_BIN" ]; then
    WINE_BIN=$(command -v wine || true)
fi
if [ -z "$WINE_BIN" ]; then
    echo "Wine was not found. Add Wine to PATH or install Wine Staging in /Applications." >&2
    exit 127
fi
if [ ! -f "$PROJECT_DIR/PythonScripts/main.py" ]; then
    echo "Missing Python entry point: $PROJECT_DIR/PythonScripts/main.py" >&2
    exit 1
fi
if [ ! -f "$HOME/.wine/drive_c/Python312/python.exe" ]; then
    echo "Missing Windows Python: $HOME/.wine/drive_c/Python312/python.exe" >&2
    exit 1
fi
if [ ! -f "$PROJECT_DIR/zss.ini" ]; then
    echo "Missing runtime config: $PROJECT_DIR/zss.ini" >&2
    exit 1
fi

cd "$PROJECT_DIR"
if [ "$#" -eq 0 ]; then
    set -- --team blue --side left --sim
fi

exec env WINEPREFIX="$HOME/.wine" WINEDEBUG=-all \
    "$WINE_BIN" 'C:\Python312\python.exe' -X utf8 -B \
    "$PROJECT_DIR/PythonScripts/main.py" "$@"
