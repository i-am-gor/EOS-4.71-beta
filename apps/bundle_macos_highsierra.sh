#!/bin/bash
# Build EOS Flasher and EOS Pan Test for Intel Macs running macOS 10.13 High Sierra or later
# (x86_64 only, deployment target 10.13) in apps/dist/highsierra/. The universal builds
# (apps/bundle_macos.sh) need macOS 11. Same source, separate target directory.
# Needs: rustup target x86_64-apple-darwin.
set -euo pipefail
cd "$(dirname "$0")"
CARGO="${CARGO:-cargo}"
MIN=10.13
VERSION=$(grep -m1 '^version' Cargo.toml | cut -d'"' -f2)
OUT=dist/highsierra
mkdir -p "$OUT"
MACOSX_DEPLOYMENT_TARGET=$MIN "$CARGO" build --release --target x86_64-apple-darwin \
  --target-dir target-highsierra -p eos-flasher -p eos-pantest
bundle() {   # crate, app name, bundle id, extra plist keys
  local crate=$1 name=$2 id=$3 extra=$4
  local app="$OUT/$name.app"
  local bin="target-highsierra/x86_64-apple-darwin/release/$crate"
  # every load command must say 10.13 (a newer minimum would refuse to launch on High Sierra)
  local minos
  minos=$(otool -l "$bin" | awk '/LC_VERSION_MIN_MACOSX/{f=1} f&&/version/{print $2; exit}')
  [ "$minos" = "$MIN" ] || { echo "$crate: minimum macOS $minos, expected $MIN" >&2; exit 1; }
  rm -rf "$app"; mkdir -p "$app/Contents/MacOS" "$app/Contents/Resources"
  cp "$bin" "$app/Contents/MacOS/$crate"
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
  <key>LSMinimumSystemVersion</key><string>$MIN</string>
  <key>LSArchitecturePriority</key><array><string>x86_64</string></array>
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
cd "$OUT"
rm -f EOS-Flasher-macOS-HighSierra-Intel.zip EOS-PanTest-macOS-HighSierra-Intel.zip
ditto -c -k --keepParent "EOS Flasher.app" "EOS-Flasher-macOS-HighSierra-Intel.zip"
ditto -c -k --keepParent "EOS Pan Test.app" "EOS-PanTest-macOS-HighSierra-Intel.zip"
ls -la
