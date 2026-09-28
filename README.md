# video

剪片與程式動畫工作台，搭配 Claude Code 的 `video-lab` 技能使用。

## 內容

- `.claude/skills/video-lab/SKILL.md`：技能本體（剪輯、字幕、踩點剪、程式動畫的做法與規範）
- `.claude/hooks/session-start.sh`：在 Claude Code 雲端 session 開啟時自動安裝環境
  - ffmpeg、Noto CJK 字型（`Noto Sans TC` 別名）
  - `~/video-lab/.venv`：faster-whisper、opencc、auto-editor、librosa、playwright
  - 參考庫 clone 到 `~/video-lab/refs/`：
    - [mexicat/pdoom-video](https://github.com/mexicat/pdoom-video)（MIT；`audio/`、`lyrics/`、`data/lyrics.json` 屬原作者）
    - [yihui-dev/awesome-opus5-5-videos](https://github.com/yihui-dev/awesome-opus5-5-videos)（每支 prompt 屬原作者）
    - [2606156052/Pdoom-video-anime-version](https://github.com/2606156052/Pdoom-video-anime-version)（程式碼 ISC；歌曲與影像素材屬原作者）
- `.claude/skills/video-lab/references/anime.md`：日系動漫剪輯元素與風格清單
- `.claude/skills/video-lab/assets/anime-fx.js`：動漫演出效果庫（集中線、衝擊格、カットイン等）
- `.claude/skills/video-lab/scripts/render.py`：HTML `render(t)` → mp4／透明 mov／webm

參考庫不放進本 repo，每次從上游取得。本 repo 為公開，客戶素材與成品不要 commit（`out/` 已忽略）。

## 注意

- 字幕辨識的 Whisper 模型從 huggingface.co 下載，雲端環境的網路政策需放行該網域。
- 本機（Mac）不跑 hook，依 SKILL.md 自行安裝工具。
