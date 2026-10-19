#!/bin/bash
# Build EOS Flasher and EOS Pan Test as universal (arm64 + x86_64) macOS app bundles in apps/dist/.
# Needs: rustup targets aarch64-apple-darwin and x86_64-apple-darwin.
set -euo pipefail
cd "$(dirname "$0")"
CARGO="${CARGO:-cargo}"
VERSION=$(grep -m1 '^version' Cargo.toml | cut -d'"' -f2)
mkdir -p dist
for T in aarch64-apple-darwin x86_64-apple-darwin; do
  MACOSX_DEPLOYMENT_TARGET=11.0 "$CARGO" build --release --target "$T" -p eos-flasher -p eos-pantest
done
bundle() {   # crate, app name, bundle id, extra plist keys
  local crate=$1 name=$2 id=$3 extra=$4
  local app="dist/$name.app"
  rm -rf "$app"; mkdir -p "$app/Contents/MacOS" "$app/Contents/Resources"
  lipo -create -output "$app/Contents/MacOS/$crate" \
    "target/aarch64-apple-darwin/release/$crate" "target/x86_64-apple-darwin/release/$crate"
  cat > "$app/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>CFBundleName</key><string>$name</string>
  <key>CFBundleDisplayName</key><string>$name</string>
  <key>CFBundleIdentifier</key><string>$id</string>
  <key>CFBundleExecutable</key><string>$crate</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleShortVersionString</key><string>$VERSION</string>
  <key>CFBundleVersion</key><string>$VERSION</string>
  <key>LSMinimumSystemVersion</key><string>11.0</string>
  <key>NSHighResolutionCapable</key><true/>
  $extra
</dict></plist>
PLIST
  codesign --force --deep -s - "$app"
  lipo -info "$app/Contents/MacOS/$crate"
}
bundle eos-flasher "EOS Flasher" "com.github.rfidmusic.eos-flasher" ""
bundle eos-pantest "EOS Pan Test" "com.github.rfidmusic.eos-pantest" \
  "<key>NSMicrophoneUsageDescription</key><string>EOS Pan Test records the E4's outputs from your audio interface to measure pan.</string>"
cd dist && rm -f EOS-Apps-macOS-universal.zip
ditto -c -k --keepParent "EOS Flasher.app" "EOS-Flasher-macOS-universal.zip"
ditto -c -k --keepParent "EOS Pan Test.app" "EOS-PanTest-macOS-universal.zip"
ls -la
