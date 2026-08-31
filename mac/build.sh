#!/usr/bin/env bash
# Build the Mac app and drop it in /Applications.
#
# Ad-hoc signed, because this is a personal build and a real certificate buys
# nothing until it is distributed. macOS will not gatekeep an app you built
# locally, but it will refuse one that moved between machines.
set -euo pipefail
cd "$(dirname "$0")"

command -v xcodegen >/dev/null || { echo "need xcodegen: brew install xcodegen"; exit 1; }
command -v magi >/dev/null || echo "warning: the magi engine is not on PATH; the app will look for it in ~/.local/bin"

xcodegen generate
xcodebuild -project MAGI.xcodeproj -scheme MAGI -configuration Release \
  -derivedDataPath build build | tail -3

APP="build/Build/Products/Release/MAGI.app"
[ -d "$APP" ] || { echo "build produced no app"; exit 1; }

rm -rf /Applications/MAGI.app
cp -R "$APP" /Applications/
echo "installed /Applications/MAGI.app"
