#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APPDIR="$ROOT_DIR/AppDir"
PY_DIST="$ROOT_DIR/dist/linux-appimage"
PY_WORK="$ROOT_DIR/build/pylinux-appimage"
OUTPUT="$ROOT_DIR/dist/cursepante-x86_64.AppImage"
APPIMAGE_TOOL_DIR="$HOME/.local/appimagetool"
APPIMAGE_TOOL="$APPIMAGE_TOOL_DIR/appimagetool-x86_64.AppImage"
DESKTOP_FILE="$ROOT_DIR/packaging/linux/com.chleved.Cursepante.desktop"
ICON_FILE="$ROOT_DIR/packaging/linux/com.chleved.Cursepante.svg"
APPDIR_DESKTOP="$APPDIR/com.chleved.Cursepante.desktop"

cd "$ROOT_DIR"
source venv/bin/activate

echo "[appimage] Building Linux binary with PyInstaller..."
pyinstaller --clean --noconfirm --distpath "$PY_DIST" --workpath "$PY_WORK" cursepante.spec

if [[ ! -x "$APPIMAGE_TOOL" ]]; then
  echo "[appimage] Downloading appimagetool (first run only)..."
  mkdir -p "$APPIMAGE_TOOL_DIR"
  curl -L "https://github.com/AppImage/AppImageKit/releases/download/continuous/appimagetool-x86_64.AppImage" -o "$APPIMAGE_TOOL"
  chmod +x "$APPIMAGE_TOOL"
fi

echo "[appimage] Preparing AppDir structure..."
rm -rf "$APPDIR"
mkdir -p "$APPDIR/usr/bin"
mkdir -p "$APPDIR/usr/share/applications"
mkdir -p "$APPDIR/usr/share/icons/hicolor/scalable/apps"

install -Dm755 "$PY_DIST/cursepante" "$APPDIR/usr/bin/cursepante"
install -Dm644 "$ICON_FILE" "$APPDIR/usr/share/icons/hicolor/scalable/apps/com.chleved.Cursepante.svg"

# appimagetool rejects desktop files with CRLF, so normalize line endings.
tr -d '\r' < "$DESKTOP_FILE" > "$APPDIR_DESKTOP"
install -Dm644 "$APPDIR_DESKTOP" "$APPDIR/usr/share/applications/com.chleved.Cursepante.desktop"

cp "$ICON_FILE" "$APPDIR/com.chleved.Cursepante.svg"

cat > "$APPDIR/AppRun" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export APPIMAGE_EXTRACT_AND_RUN=1
exec "$HERE/usr/bin/cursepante" "$@"
EOF
chmod +x "$APPDIR/AppRun"

echo "[appimage] Building AppImage..."
ARCH=x86_64 APPIMAGE_EXTRACT_AND_RUN=1 "$APPIMAGE_TOOL" "$APPDIR" "$OUTPUT"

echo "[appimage] Created: $OUTPUT"
