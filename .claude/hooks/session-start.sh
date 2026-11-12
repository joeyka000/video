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
# playwright 固定 1.56.0；預裝 Chromium 版本不同時下面會把路徑連過去，不跑 playwright install
if command -v uv >/dev/null; then
  [ -x "$LAB/.venv/bin/python" ] || uv venv -q --python 3.11 "$LAB/.venv" >>"$LOG" 2>&1
  VIRTUAL_ENV="$LAB/.venv" uv pip install -q \
    faster-whisper opencc auto-editor librosa soundfile scipy pillow opencv-python-headless edge-tts playwright==1.56.0 >>"$LOG" 2>&1
else
  [ -x "$LAB/.venv/bin/python" ] || python3 -m venv "$LAB/.venv"
  "$LAB/.venv/bin/pip" install -q \
    faster-whisper opencc auto-editor librosa soundfile scipy pillow opencv-python-headless edge-tts playwright==1.56.0 >>"$LOG" 2>&1
fi
# auto-editor 第一次執行會下載自己的執行檔，先跑一次
"$LAB/.venv/bin/auto-editor" --version >>"$LOG" 2>&1 || warnings+=("auto-editor 執行檔下載失敗")

if [ -n "${CLAUDE_ENV_FILE:-}" ]; then
  echo "export PATH=\"$LAB/.venv/bin:\$PATH\"" >> "$CLAUDE_ENV_FILE"
fi

# 預裝 Chromium 的版本跟 playwright 套件期望的不同時（映像更新後常見，例：套件要 1194、預裝 1243），
# 把套件期望的路徑連到預裝那一份；不跑 playwright install、不下載瀏覽器
want_full=$("$LAB/.venv/bin/python" -c 'from playwright.sync_api import sync_playwright
with sync_playwright() as p: print(p.chromium.executable_path)' 2>/dev/null || true)
if [ -n "$want_full" ]; then
  want_shell=$(echo "$want_full" | sed 's#/chromium-\([0-9]*\)/chrome-linux/chrome#/chromium_headless_shell-\1/chrome-linux/headless_shell#')
  have_full=$(ls -d /opt/pw-browsers/chromium-*/chrome-linux*/chrome 2>/dev/null | sort -V | tail -1 || true)
  have_shell=$(ls -d /opt/pw-browsers/chromium_headless_shell-*/chrome-*/chrome-headless-shell \
    /opt/pw-browsers/chromium_headless_shell-*/chrome-*/headless_shell 2>/dev/null | sort -V | tail -1 || true)
  for pair in "$want_full|$have_full" "$want_shell|$have_shell"; do
    want=${pair%%|*}; have=${pair##*|}
    if [ ! -e "$want" ] && [ -n "$have" ]; then
      { mkdir -p "$(dirname "$want")" && ln -sf "$have" "$want" && echo "playwright 瀏覽器路徑 $want → $have" >>"$LOG"; } \
        || warnings+=("playwright 瀏覽器路徑對齊失敗")
    fi
  done
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
sync_ref https://github.com/2606156052/Pdoom-video-anime-version anime-op
# Easel（Apache-2.0）整個 repo 760 MB，只稀疏取 skills/ 與 docs/（約 25 MB）
if [ -d "$LAB/refs/easel/.git" ]; then
  GIT_LFS_SKIP_SMUDGE=1 git -C "$LAB/refs/easel" pull -q --ff-only >>"$LOG" 2>&1 || warnings+=("easel 更新失敗，沿用舊版")
else
  rm -rf "$LAB/refs/easel"
  { GIT_LFS_SKIP_SMUDGE=1 git clone -q --depth 1 --filter=blob:none --sparse https://github.com/ZJU-REAL/easel "$LAB/refs/easel" \
    && git -C "$LAB/refs/easel" sparse-checkout set skills docs; } >>"$LOG" 2>&1 || warnings+=("easel clone 失敗")
fi

# 模型與字型（matte.py 的去背 ISNet、精修用的 YuNet 臉部偵測、Klee One 手寫感日文字型、迷幻 MV 的日文粗體；都只下載一次）
fetch() {
  local out="$1"; shift
  [ -s "$out" ] && return 0
  mkdir -p "$(dirname "$out")"
  for u in "$@"; do curl -sSfL -o "$out.part" "$u" >>"$LOG" 2>&1 && mv -f "$out.part" "$out" && return 0; done
  rm -f "$out.part"; warnings+=("$(basename "$out") 下載失敗")
}
fetch "$LAB/models/isnet.onnx" https://github.com/danielgatis/rembg/releases/download/v0.0.0/isnet-general-use.onnx
fetch "$LAB/models/yunet.onnx" \
  https://media.githubusercontent.com/media/opencv/opencv_zoo/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx \
  https://huggingface.co/opencv/face_detection_yunet/resolve/main/face_detection_yunet_2023mar.onnx
for f in KleeOne-Regular KleeOne-SemiBold; do
  fetch "$HOME/.fonts/$f.ttf" "https://raw.githubusercontent.com/google/fonts/main/ofl/kleeone/$f.ttf"
done
# 可愛手帳風（cutefx.FONT；OFL）：粉圓體（繁中）、Jua 與 Gaegu（韓文、手寫）、Mochiy Pop One
fetch "$HOME/.fonts/jf-openhuninn.ttf" https://raw.githubusercontent.com/justfont/open-huninn-font/master/font/jf-openhuninn-2.1.ttf
for f in jua/Jua-Regular gaegu/Gaegu-Bold mochiypopone/MochiyPopOne-Regular; do
  fetch "$HOME/.fonts/$(basename $f).ttf" "https://raw.githubusercontent.com/google/fonts/main/ofl/$f.ttf"
done
# 迷幻卡點 MV 的背景日文大字（psyfx.FONTS；OFL）
for f in delagothicone/DelaGothicOne-Regular rocknrollone/RocknRollOne-Regular rampartone/RampartOne-Regular; do
  fetch "$HOME/.fonts/$(basename $f).ttf" "https://raw.githubusercontent.com/google/fonts/main/ofl/$f.ttf"
done

if [ ${#warnings[@]} -eq 0 ]; then
  echo "video-lab 環境就緒（紀錄：$LOG）"
else
  printf 'video-lab 環境部分未完成：%s（紀錄：%s）\n' "$(IFS='、'; echo "${warnings[*]}")" "$LOG"
fi
