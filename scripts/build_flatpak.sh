#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY_DIST="$ROOT_DIR/dist/linux-flatpak"
PY_WORK="$ROOT_DIR/build/pylinux-flatpak"
MANIFEST="$ROOT_DIR/com.chleved.Cursepante.yml"

cd "$ROOT_DIR"

if ! command -v flatpak-builder >/dev/null 2>&1; then
  echo "[flatpak] Installing flatpak-builder in WSL..."
  sudo apt-get update
  sudo apt-get install -y flatpak-builder
fi

if ! flatpak --user remotes --columns=name | grep -qx "flathub"; then
  echo "[flatpak] Adding Flathub remote..."
  flatpak --user remote-add --if-not-exists flathub https://flathub.org/repo/flathub.flatpakrepo
fi

if ! flatpak --user info org.freedesktop.Sdk//24.08 >/dev/null 2>&1; then
  echo "[flatpak] Installing org.freedesktop SDK and Platform 24.08..."
  flatpak --user install -y flathub org.freedesktop.Sdk//24.08 org.freedesktop.Platform//24.08
fi

source venv/bin/activate

echo "[flatpak] Building Linux binary with PyInstaller..."
pyinstaller --clean --noconfirm --distpath "$PY_DIST" --workpath "$PY_WORK" cursepante.spec

if [[ ! -d "$ROOT_DIR/repo" ]]; then
  ostree --repo="$ROOT_DIR/repo" init --mode=archive-z2
fi
ostree --repo="$ROOT_DIR/repo" config set core.min-free-space-percent 0

echo "[flatpak] Building Flatpak repo..."
flatpak-builder --user --disable-rofiles-fuse --force-clean --repo=repo build-dir "$MANIFEST"

echo "[flatpak] Bundling artifact..."
flatpak build-bundle repo dist/cursepante.flatpak com.chleved.Cursepante

echo "[flatpak] Created: $ROOT_DIR/dist/cursepante.flatpak"
