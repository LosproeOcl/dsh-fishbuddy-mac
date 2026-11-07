#!/bin/sh
# 生成 DSH-FishBuddy.app（本地自用）
# 用法：./build.sh [python路径]   默认用 ./.venv/bin/python
set -e
HERE="$(cd "$(dirname "$0")" && pwd)"
PY="${1:-$HERE/.venv/bin/python}"
APP="$HERE/DSH-FishBuddy.app"

if [ ! -x "$PY" ]; then
  echo "找不到 python：$PY" >&2
  echo "先建个 venv：python3 -m venv .venv && .venv/bin/pip install pyobjc-framework-Cocoa pyobjc-framework-Quartz pyobjc-framework-Speech sounddevice numpy pillow" >&2
  exit 1
fi

rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"

cat > "$APP/Contents/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleName</key><string>大肥鱼</string>
  <key>CFBundleDisplayName</key><string>大肥鱼</string>
  <key>CFBundleIdentifier</key><string>com.dafish.fishbuddy</string>
  <key>CFBundleExecutable</key><string>FishBuddy</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleShortVersionString</key><string>0.2.0</string>
  <key>CFBundleVersion</key><string>2</string>
  <key>LSUIElement</key><true/>
  <key>NSHighResolutionCapable</key><true/>
  <key>NSMicrophoneUsageDescription</key><string>按住鲸鱼说话时要用麦克风</string>
  <key>NSSpeechRecognitionUsageDescription</key><string>把你说的话转成文字，送进 DSH 会话</string>
</dict>
</plist>
PLIST

cat > "$APP/Contents/MacOS/FishBuddy" <<SH
#!/bin/sh
exec "$PY" "$HERE/main.py"
SH
chmod +x "$APP/Contents/MacOS/FishBuddy"

echo "好了：$APP"
echo "启动：open \"$APP\""
