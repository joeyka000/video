#!/bin/bash
# 雲端 session 啟動時安裝 video-lab 技能需要的工具與參考庫。
# 本機（Mac）不跑，依 .claude/skills/video-lab/SKILL.md 自行安裝。
set -euo pipefail

if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

LAB="$HOME/video-lab"
LOG="$LAB/setup.log"
mkdir -p "$LAB/refs"
: > "$LOG"
warnings=()

# 1. ffmpeg + Noto CJK 字型
if ! command -v ffmpeg >/dev/null || ! fc-list 2>/dev/null | grep -q 'Noto Sans CJK TC'; then
  # 部分第三方 PPA 會被網路政策擋，update 失敗不影響主要套件來源
  apt-get update -qq >>"$LOG" 2>&1 || true
  DEBIAN_FRONTEND=noninteractive apt-get install -y -qq --no-install-recommends \
    ffmpeg fonts-noto-cjk fontconfig >>"$LOG" 2>&1
fi

# SKILL.md 用的字型名是 Noto Sans TC，apt 裝的是 Noto Sans CJK TC，設別名讓兩邊都找得到
mkdir -p "$HOME/.config/fontconfig/conf.d"
cat > "$HOME/.config/fontconfig/conf.d/60-noto-sans-tc.conf" <<'EOF'
<?xml version="1.0"?>
<!DOCTYPE fontconfig SYSTEM "fonts.dtd">
<fontconfig>
  <alias binding="same">
    <family>Noto Sans TC</family>
    <prefer><family>Noto Sans CJK TC</family></prefer>
  </alias>
</fontconfig>
EOF
fc-cache -f >>"$LOG" 2>&1 || true

# 2. bun（渲染參考 pdoom 的 app/ 用）
if ! command -v bun >/dev/null; then
  if [ -x "$HOME/.bun/bin/bun" ]; then
    export PATH="$HOME/.bun/bin:$PATH"
    [ -n "${CLAUDE_ENV_FILE:-}" ] && echo "export PATH=\"$HOME/.bun/bin:\$PATH\"" >> "$CLAUDE_ENV_FILE"
  else
    npm install -g bun >>"$LOG" 2>&1 || warnings+=("bun 安裝失敗")
  fi
fi

# 3. Python 套件裝在 ~/video-lab/.venv
# playwright 版本對齊 /opt/pw-browsers 預裝的 Chromium（chromium-1194），不跑 playwright install
if command -v uv >/dev/null; then
  [ -x "$LAB/.venv/bin/python" ] || uv venv -q --python 3.11 "$LAB/.venv" >>"$LOG" 2>&1
  VIRTUAL_ENV="$LAB/.venv" uv pip install -q \
    faster-whisper opencc auto-editor librosa soundfile playwright==1.56.0 >>"$LOG" 2>&1
else
  [ -x "$LAB/.venv/bin/python" ] || python3 -m venv "$LAB/.venv"
  "$LAB/.venv/bin/pip" install -q \
    faster-whisper opencc auto-editor librosa soundfile playwright==1.56.0 >>"$LOG" 2>&1
fi
# auto-editor 第一次執行會下載自己的執行檔，先跑一次
"$LAB/.venv/bin/auto-editor" --version >>"$LOG" 2>&1 || warnings+=("auto-editor 執行檔下載失敗")

if [ -n "${CLAUDE_ENV_FILE:-}" ]; then
  echo "export PATH=\"$LAB/.venv/bin:\$PATH\"" >> "$CLAUDE_ENV_FILE"
fi

# 4. 參考庫：公開 repo 不重新散布第三方內容，每次從上游 clone／更新
sync_ref() {
  local url="$1" dir="$LAB/refs/$2"
  if [ -d "$dir/.git" ]; then
    git -C "$dir" pull -q --ff-only >>"$LOG" 2>&1 || warnings+=("$2 更新失敗，沿用舊版")
  else
    rm -rf "$dir"
    git clone -q --depth 1 "$url" "$dir" >>"$LOG" 2>&1 || warnings+=("$2 clone 失敗")
  fi
}
sync_ref https://github.com/mexicat/pdoom-video pdoom-video
sync_ref https://github.com/yihui-dev/awesome-opus5-5-videos awesome-opus5-5-videos

if [ ${#warnings[@]} -eq 0 ]; then
  echo "video-lab 環境就緒（紀錄：$LOG）"
else
  printf 'video-lab 環境部分未完成：%s（紀錄：%s）\n' "$(IFS='、'; echo "${warnings[*]}")" "$LOG"
fi
