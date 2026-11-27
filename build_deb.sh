#!/bin/bash
set -e

PACKAGE_NAME="py-autoclicker_1.0.0-1_all"
BUILD_DIR="./build_root"

echo "[*] Preparing build directory structure..."
rm -rf "$BUILD_DIR"
mkdir -p "$BUILD_DIR"

# Copy package layout from the working tree into build_root
cp -r DEBIAN lib usr etc "$BUILD_DIR/"

# Strip local Python bytecode caches before packaging
find "$BUILD_DIR" -name "__pycache__" -type d -exec rm -rf {} +

echo "[*] Setting proper file and directory permissions..."
chmod 0755 "$BUILD_DIR/DEBIAN"
chmod 0644 "$BUILD_DIR/DEBIAN/control"
chmod 0755 "$BUILD_DIR/DEBIAN/postinst"
chmod 0755 "$BUILD_DIR/DEBIAN/postrm"

# Executable wrapper
chmod 0755 "$BUILD_DIR/usr/bin/py-autoclicker"

# Configuration, udev rules, kernel module loader, and desktop entry
chmod 0644 "$BUILD_DIR/lib/udev/rules.d/60-py-autoclicker.rules"
chmod 0644 "$BUILD_DIR/usr/lib/modules-load.d/py-autoclicker.conf"
chmod 0644 "$BUILD_DIR/usr/share/applications/py-autoclicker.desktop"
chmod 0644 "$BUILD_DIR/etc/py-autoclicker/config.toml"

# Python package source files
find "$BUILD_DIR/usr/share/py-autoclicker" -type f -exec chmod 0644 {} \;
find "$BUILD_DIR/usr/share/py-autoclicker" -type d -exec chmod 0755 {} \;

echo "[*] Building .deb package with dpkg-deb..."
dpkg-deb --build --root-owner-group "$BUILD_DIR" "${PACKAGE_NAME}.deb"

# Clean up temporary staging directory
rm -rf "$BUILD_DIR"

echo "[+] Build completed successfully: ${PACKAGE_NAME}.deb"
echo "Install with: sudo apt install ./${PACKAGE_NAME}.deb"

