#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

APP_NAME="Chedan Image2"
SPEC_FILE="chedan-image2-gui-macos.spec"
DMG_NAME="Chedan-Image2-macOS.dmg"
PKG_NAME="Chedan-Image2-macOS.pkg"
ZIP_NAME="Chedan-Image2-macOS-app.zip"
PNG_ICON="chedankj-cd-egg-solid-logo.png"
ICNS_ICON="chedankj-cd-egg-solid-logo.icns"
ICONSET_DIR="chedankj-cd-egg-solid-logo.iconset"

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 is required. Install Python 3 first."
  exit 1
fi

python3 -m pip install --upgrade pip
python3 -m pip install pyinstaller httpx pillow

if [ -f "$PNG_ICON" ] && command -v sips >/dev/null 2>&1 && command -v iconutil >/dev/null 2>&1; then
  rm -rf "$ICONSET_DIR"
  mkdir -p "$ICONSET_DIR"
  sips -z 16 16     "$PNG_ICON" --out "$ICONSET_DIR/icon_16x16.png" >/dev/null
  sips -z 32 32     "$PNG_ICON" --out "$ICONSET_DIR/icon_16x16@2x.png" >/dev/null
  sips -z 32 32     "$PNG_ICON" --out "$ICONSET_DIR/icon_32x32.png" >/dev/null
  sips -z 64 64     "$PNG_ICON" --out "$ICONSET_DIR/icon_32x32@2x.png" >/dev/null
  sips -z 128 128   "$PNG_ICON" --out "$ICONSET_DIR/icon_128x128.png" >/dev/null
  sips -z 256 256   "$PNG_ICON" --out "$ICONSET_DIR/icon_128x128@2x.png" >/dev/null
  sips -z 256 256   "$PNG_ICON" --out "$ICONSET_DIR/icon_256x256.png" >/dev/null
  sips -z 512 512   "$PNG_ICON" --out "$ICONSET_DIR/icon_256x256@2x.png" >/dev/null
  sips -z 512 512   "$PNG_ICON" --out "$ICONSET_DIR/icon_512x512.png" >/dev/null
  sips -z 1024 1024 "$PNG_ICON" --out "$ICONSET_DIR/icon_512x512@2x.png" >/dev/null
  iconutil -c icns "$ICONSET_DIR" -o "$ICNS_ICON"
  rm -rf "$ICONSET_DIR"
  echo "Built icon: $ICNS_ICON"
fi

rm -rf build dist "$DMG_NAME" "$PKG_NAME" "$ZIP_NAME"
python3 -m PyInstaller --clean "$SPEC_FILE"

if [ ! -d "dist/${APP_NAME}.app" ]; then
  echo "Build failed: dist/${APP_NAME}.app was not created."
  exit 1
fi

echo "Built app: dist/${APP_NAME}.app"

if command -v ditto >/dev/null 2>&1; then
  ditto -c -k --keepParent "dist/${APP_NAME}.app" "dist/${ZIP_NAME}"
  echo "Built app zip: dist/${ZIP_NAME}"
fi

if command -v hdiutil >/dev/null 2>&1; then
  mkdir -p "dist/dmg-root"
  rm -rf "dist/dmg-root/${APP_NAME}.app"
  cp -R "dist/${APP_NAME}.app" "dist/dmg-root/"
  ln -s /Applications "dist/dmg-root/Applications"
  hdiutil create -volname "${APP_NAME}" -srcfolder "dist/dmg-root" -ov -format UDZO "dist/${DMG_NAME}"
  rm -rf "dist/dmg-root"
  echo "Built dmg: dist/${DMG_NAME}"
fi

if command -v pkgbuild >/dev/null 2>&1; then
  pkgbuild \
    --component "dist/${APP_NAME}.app" \
    --install-location "/Applications" \
    "dist/${PKG_NAME}"
  echo "Built pkg installer: dist/${PKG_NAME}"
fi
