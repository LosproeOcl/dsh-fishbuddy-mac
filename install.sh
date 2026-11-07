#!/bin/sh
# 一键安装：建 venv → 装依赖 → 生成 .app → 告诉你怎么开
# 用法：./install.sh [python3]      （默认用 PATH 里的 python3）
set -e
HERE="$(cd "$(dirname "$0")" && pwd)"
PYBASE="${1:-python3}"
VENV="$HERE/.venv"

echo "==> 用的 Python：$("$PYBASE" -V 2>&1)"
"$PYBASE" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' || {
  echo "需要 Python 3.9 以上" >&2
  exit 1
}

if [ ! -x "$VENV/bin/python" ]; then
  echo "==> 建 venv：$VENV"
  "$PYBASE" -m venv "$VENV"
fi

echo "==> 装依赖"
"$VENV/bin/pip" install --upgrade pip -q
"$VENV/bin/pip" install -r "$HERE/requirements.txt" -q

echo "==> 生成 .app"
"$HERE/build.sh" "$VENV/bin/python"

cat <<TXT

好了 ✓

启动：
  open "$HERE/DSH-FishBuddy.app"

第一次会要三个权限（系统设置 → 隐私与安全性）：
  麦克风      按住说话
  语音识别    说话转文字
  屏幕录制    陪看截图
  辅助功能    全局热键 ⌥Space（可选）

DSH 那边要装插件并绑会话：
  dsh plugin --profile desktop add dsh-fish-buddy
  然后 ~/.dsh/fish-buddy-config.json 里填 "会话" 和 "回调"
TXT
