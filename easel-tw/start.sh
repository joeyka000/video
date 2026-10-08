#!/usr/bin/env bash
# 啟動 Easel 台灣版：OpenClaw 閘道器＋網頁後台，並開啟瀏覽器
set -e
cd "$(dirname "$0")"
[ -x .venv/bin/easel ] || { echo "還沒安裝：先在 easel-tw 資料夾執行 bash install.sh"; exit 1; }
PORT="${EASEL_PORT:-7860}"
.venv/bin/easel gateway start || echo "⚠ 閘道器沒有啟動成功：網頁可以開，但對話會失敗，請看 .venv/bin/easel gateway logs"
( sleep 3; command -v open >/dev/null && open "http://localhost:$PORT" || xdg-open "http://localhost:$PORT" >/dev/null 2>&1 || true ) &
exec .venv/bin/easel web --port "$PORT"
