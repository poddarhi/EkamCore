#!/bin/bash
# EkamCore Installer — double-click this file to install and launch.
# This removes the macOS quarantine flag and copies the app to Applications.

clear
echo ""
echo "  ╔══════════════════════════════════════╗"
echo "  ║    Installing EkamCore Manager...    ║"
echo "  ╚══════════════════════════════════════╝"
echo ""

# Find the .app in the same directory as this script
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
APP_NAME="EkamCore Manager.app"

# Check if we're running from a DMG volume
if [[ "$SCRIPT_DIR" == /Volumes/* ]]; then
    APP_PATH="$SCRIPT_DIR/$APP_NAME"
else
    APP_PATH="$SCRIPT_DIR/$APP_NAME"
fi

if [[ ! -d "$APP_PATH" ]]; then
    # Try the DMG volume
    for vol in /Volumes/EkamCore*; do
        if [[ -d "$vol/$APP_NAME" ]]; then
            APP_PATH="$vol/$APP_NAME"
            break
        fi
    done
fi

if [[ ! -d "$APP_PATH" ]]; then
    echo "  ERROR: Could not find EkamCore Manager.app"
    echo "  Please mount the DMG first and try again."
    echo ""
    read -p "  Press Enter to close..."
    exit 1
fi

echo "  Found: $APP_PATH"
echo ""

# Copy to Applications
echo "  Copying to /Applications..."
rm -rf "/Applications/$APP_NAME"
cp -R "$APP_PATH" "/Applications/$APP_NAME"

# Remove quarantine flag (this is what fixes the "damaged" error)
echo "  Removing quarantine flag..."
xattr -cr "/Applications/$APP_NAME"

echo ""
echo "  ✓ EkamCore Manager installed successfully!"
echo ""
echo "  Launching..."
echo ""

open "/Applications/$APP_NAME"

echo "  EkamCore Manager is starting."
echo "  You can close this window."
echo ""
