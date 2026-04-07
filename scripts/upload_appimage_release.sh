#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 <release-tag>"
  exit 1
fi

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TAG="$1"
ASSET="$ROOT_DIR/dist/cursepante-x86_64.AppImage"

if [[ ! -f "$ASSET" ]]; then
  echo "AppImage not found: $ASSET"
  exit 1
fi

cd "$ROOT_DIR"
gh release upload "$TAG" "$ASSET" --clobber

echo "Uploaded $ASSET to release $TAG"
