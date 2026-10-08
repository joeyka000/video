#!/usr/bin/env bash
# Easel 台灣版：安裝／更新（macOS、Linux）
#   bash install.sh                 安裝到 ~/easel-tw（已存在就更新，保留 .env、outputs/、人設、登入資料）
#   bash install.sh ~/某個資料夾      指定位置
#   bash install.sh --no-showcase   不下載首頁示範影片與 README 圖（省約 430 MB）
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
TARGET="$HOME/easel-tw"
BUILD_ARGS=()
for a in "$@"; do
  case "$a" in
    --no-showcase) BUILD_ARGS+=(--no-showcase) ;;
    *) TARGET="$a" ;;
  esac
done
say() { printf '\n\033[1;36m▸ %s\033[0m\n' "$*"; }

command -v git >/dev/null || { echo "需要 git（macOS：xcode-select --install）"; exit 1; }
command -v python3 >/dev/null || { echo "需要 Python 3.10 以上（macOS：brew install python）"; exit 1; }
python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' || { echo "Python 版本太舊，需要 3.10 以上"; exit 1; }

say "準備轉換工具（OpenCC）"
TOOLS="$HOME/.easel-tw-tools"
[ -x "$TOOLS/bin/python" ] || python3 -m venv "$TOOLS"
"$TOOLS/bin/pip" install -q --upgrade pip opencc

NEW="$TARGET"
if [ -d "$TARGET" ] && [ -n "$(ls -A "$TARGET" 2>/dev/null)" ]; then
  NEW="$TARGET.new"
  rm -rf "$NEW"
  say "偵測到既有安裝，先建新版到 $NEW"
fi

say "下載上游並轉成台灣版"
"$TOOLS/bin/python" "$HERE/build.py" --out "$NEW" "${BUILD_ARGS[@]}"

if [ "$NEW" != "$TARGET" ]; then
  say "搬移你的資料（.env、outputs/、人設、登入資料）"
  for f in .env cookies.json outputs; do
    [ -e "$TARGET/$f" ] && { rm -rf "$NEW/$f"; cp -a "$TARGET/$f" "$NEW/$f"; }
  done
  if [ -d "$TARGET/profiles" ]; then
    for d in "$TARGET"/profiles/*/; do
      n="$(basename "$d")"; [ "$n" = "_template" ] && continue
      cp -a "$d" "$NEW/profiles/$n"
    done
  fi
  BACKUP="$TARGET.bak-$(date +%Y%m%d-%H%M%S)"
  mv "$TARGET" "$BACKUP"
  mv "$NEW" "$TARGET"
  echo "舊版備份在 $BACKUP（確認新版正常後可以刪掉）"
fi

cp "$HERE/start.sh" "$TARGET/start.sh"
chmod +x "$TARGET/start.sh"

say "執行 Easel 安裝程式（Node、OpenClaw、Python 套件、網頁介面、Chromium）"
echo "  模型服務請選 1）Anthropic API，金鑰在終端機輸入（不會顯示、只存在本機 .env）"
echo "  模型名直接按 Enter 用預設 anthropic/claude-opus-5-5（想省一半費用可輸入 anthropic/claude-sonnet-5-5）"
cd "$TARGET"
bash setup.sh

say "完成"
echo "  啟動：$TARGET/start.sh   （會開啟 http://localhost:7860）"
echo "  匯入 Threads 日報：Google 文件「檔案 → 下載 → 純文字」後"
echo "    cd $TARGET && .venv/bin/python skills/shared/scripts/trend_log.py import ~/Downloads/<檔名>.txt"
