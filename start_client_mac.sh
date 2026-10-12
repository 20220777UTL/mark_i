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
if [ ! -f "$PROJECT_DIR/Client.exe" ]; then
    echo "Missing client executable: $PROJECT_DIR/Client.exe" >&2
    exit 1
fi
if [ ! -f "$PROJECT_DIR/zss.ini" ]; then
    echo "Missing runtime config: $PROJECT_DIR/zss.ini" >&2
    exit 1
fi

cd "$PROJECT_DIR"
QSG_RHI_BACKEND=opengl WINEPREFIX="$HOME/.wine" WINEDEBUG=-all \
    "$WINE_BIN" "$PROJECT_DIR/Client.exe" 2>&1 \
    | tee "$PROJECT_DIR/../wine_log_opengl.txt"
