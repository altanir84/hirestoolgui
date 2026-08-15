#!/usr/bin/env bash

set -euo pipefail

# ------------------------------------------------------------
# HiResToolsGUI - AppImage build script
# ------------------------------------------------------------

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

APP_NAME="HiResToolsGUI"
APP_ID="hirestoolsgui"
VERSION="1.1.0"
ARCH="x86_64"

SPEC_FILE="$PROJECT_ROOT/HiResToolsGUI.spec"
DIST_DIR="$PROJECT_ROOT/dist/$APP_NAME"
APPDIR="$PROJECT_ROOT/$APP_NAME.AppDir"

APPIMAGE_TOOL="$PROJECT_ROOT/build_tools/appimagetool-x86_64.AppImage"
APPIMAGE_NAME="$APP_NAME-$VERSION-$ARCH.AppImage"
APPIMAGE_PATH="$PROJECT_ROOT/$APPIMAGE_NAME"
SHA256_FILE="$APPIMAGE_PATH.sha256"

echo "==> HiResToolsGUI AppImage build"
echo "==> Project root: $PROJECT_ROOT"
echo "==> Version: $VERSION"
echo "==> Architecture: $ARCH"

cd "$PROJECT_ROOT"

# ------------------------------------------------------------
# 1. Validate required files/tools
# ------------------------------------------------------------

if [[ ! -f "$SPEC_FILE" ]]; then
    echo "ERROR: PyInstaller spec file not found:"
    echo "  $SPEC_FILE"
    exit 1
fi

if ! command -v pyinstaller >/dev/null 2>&1; then
    echo "ERROR: pyinstaller not found in PATH."
    echo "Activate the project's virtual environment first."
    exit 1
fi

if [[ ! -x "$APPIMAGE_TOOL" ]]; then
    echo "ERROR: appimagetool not found or not executable:"
    echo "  $APPIMAGE_TOOL"
    exit 1
fi

if [[ ! -f "$PROJECT_ROOT/packaging/appimage/AppRun" ]]; then
    echo "ERROR: AppRun not found."
    exit 1
fi

if [[ ! -f "$PROJECT_ROOT/packaging/appimage/$APP_ID.desktop" ]]; then
    echo "ERROR: desktop file not found."
    exit 1
fi

if [[ ! -f "$PROJECT_ROOT/app/assets/hires_toolgui.svg" ]]; then
    echo "ERROR: application icon not found."
    exit 1
fi

# ------------------------------------------------------------
# 2. Clean previous builds
# ------------------------------------------------------------

echo "==> Cleaning previous build artifacts..."

rm -rf "$PROJECT_ROOT/build"
rm -rf "$PROJECT_ROOT/dist"
rm -rf "$APPDIR"
rm -f "$APPIMAGE_PATH"
rm -f "$SHA256_FILE"

# ------------------------------------------------------------
# 3. Build application with PyInstaller spec
# ------------------------------------------------------------

echo "==> Building application with PyInstaller..."

pyinstaller \
    --noconfirm \
    --clean \
    "$SPEC_FILE"

if [[ ! -x "$DIST_DIR/$APP_NAME" ]]; then
    echo "ERROR: PyInstaller executable was not generated:"
    echo "  $DIST_DIR/$APP_NAME"
    exit 1
fi

# ------------------------------------------------------------
# 4. Create AppDir structure
# ------------------------------------------------------------

echo "==> Creating AppDir..."

mkdir -p "$APPDIR/usr/bin"
mkdir -p "$APPDIR/usr/share/applications"
mkdir -p "$APPDIR/usr/share/icons/hicolor/scalable/apps"

# ------------------------------------------------------------
# 5. Copy PyInstaller bundle
# ------------------------------------------------------------

echo "==> Copying PyInstaller bundle..."

cp -a "$DIST_DIR" "$APPDIR/usr/bin/"

# ------------------------------------------------------------
# 6. Install AppRun
# ------------------------------------------------------------

echo "==> Installing AppRun..."

cp "$PROJECT_ROOT/packaging/appimage/AppRun" \
   "$APPDIR/AppRun"

chmod +x "$APPDIR/AppRun"

# ------------------------------------------------------------
# 7. Install desktop entry
# ------------------------------------------------------------

echo "==> Installing desktop entry..."

cp "$PROJECT_ROOT/packaging/appimage/$APP_ID.desktop" \
   "$APPDIR/$APP_ID.desktop"

cp "$PROJECT_ROOT/packaging/appimage/$APP_ID.desktop" \
   "$APPDIR/usr/share/applications/$APP_ID.desktop"

# ------------------------------------------------------------
# 8. Install application icon
# ------------------------------------------------------------

echo "==> Installing application icon..."

cp "$PROJECT_ROOT/app/assets/hires_toolgui.svg" \
   "$APPDIR/$APP_ID.svg"

cp "$PROJECT_ROOT/app/assets/hires_toolgui.svg" \
   "$APPDIR/usr/share/icons/hicolor/scalable/apps/$APP_ID.svg"

# ------------------------------------------------------------
# 9. Create .DirIcon
# ------------------------------------------------------------

echo "==> Creating .DirIcon..."

ln -sf "$APP_ID.svg" "$APPDIR/.DirIcon"

# ------------------------------------------------------------
# 10. Validate desktop entry
# ------------------------------------------------------------

if command -v desktop-file-validate >/dev/null 2>&1; then
    echo "==> Validating desktop entry..."
    desktop-file-validate "$APPDIR/$APP_ID.desktop"
else
    echo "WARNING: desktop-file-validate not installed."
    echo "Install with: sudo apt install desktop-file-utils"
fi

# ------------------------------------------------------------
# 11. Validate AppRun
# ------------------------------------------------------------

if [[ ! -x "$APPDIR/AppRun" ]]; then
    echo "ERROR: AppRun is not executable."
    exit 1
fi

# ------------------------------------------------------------
# 12. Build AppImage
# ------------------------------------------------------------

echo "==> Building AppImage..."

ARCH="$ARCH" \
"$APPIMAGE_TOOL" \
"$APPDIR" \
"$APPIMAGE_PATH"

# ------------------------------------------------------------
# 13. Validate generated AppImage
# ------------------------------------------------------------

if [[ ! -f "$APPIMAGE_PATH" ]]; then
    echo "ERROR: AppImage was not generated."
    exit 1
fi

chmod +x "$APPIMAGE_PATH"

# ------------------------------------------------------------
# 14. Generate SHA-256
# ------------------------------------------------------------

echo "==> Generating SHA-256..."

cd "$PROJECT_ROOT"
sha256sum "$APPIMAGE_NAME" > "$SHA256_FILE"

# ------------------------------------------------------------
# 15. Verify SHA-256
# ------------------------------------------------------------

echo "==> Verifying SHA-256..."

sha256sum --check "$SHA256_FILE"

# ------------------------------------------------------------
# Finished
# ------------------------------------------------------------

echo
echo "============================================================"
echo " HiResToolsGUI build completed successfully"
echo "============================================================"
echo
echo "AppImage:"
echo "  $APPIMAGE_PATH"
echo
echo "SHA-256:"
echo "  $SHA256_FILE"
echo
echo "Checksum:"
cat "$SHA256_FILE"
echo
echo "Run with:"
echo "  ./$APPIMAGE_NAME"
echo
