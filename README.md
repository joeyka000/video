# video

剪片與程式動畫工作臺，搭配 Claude Code 的 `video-lab` 技能使用。

## 內容

- `CLAUDE.md`：工作室規範（每次 session 自動載入）：seek(t) 原則、禁用的老套、產品片用真素材、縮圖總覽評分關卡、先問再花錢、effort 建議
- `.claude/skills/new-video/SKILL.md`：一句話開片到交付的流程（frontmatter `effort: xhigh`）
- `.claude/skills/video-lab/SKILL.md`：技能本體（剪輯、字幕、踩點剪、程式動畫、MV／藝術影片的做法與規範，含技能內檔案地圖）
- `.claude/hooks/session-start.sh`：在 Claude Code 雲端 session 開啟時自動安裝環境
  - ffmpeg、Noto CJK 字型（`Noto Sans TC` 別名）
  - `~/video-lab/.venv`：faster-whisper、opencc、auto-editor、librosa、playwright
  - 參考庫 clone 到 `~/video-lab/refs/`：
    - [mexicat/pdoom-video](https://github.com/mexicat/pdoom-video)（MIT；`audio/`、`lyrics/`、`data/lyrics.json` 屬原作者）
    - [yihui-dev/awesome-opus5-5-videos](https://github.com/yihui-dev/awesome-opus5-5-videos)（每支 prompt 屬原作者）
    - [2606156052/Pdoom-video-anime-version](https://github.com/2606156052/Pdoom-video-anime-version)（程式碼 ISC；歌曲與影片素材屬原作者）
- `.claude/skills/video-lab/references/`
  - `mv-direction.md`：MV／藝術影片的創作思考：從 brief 到交付的九步、三種型態、概念方法、分鏡表規格、思考自檢
  - `editing.md`：音樂驅動的剪輯文法、14 招與實測 ffmpeg 配方、剪點表工作流程、剪輯自檢
  - `craft.md`：色彩、字型排印、動態與緩動、動態模糊、聲畫對位、輸出規格、視覺自檢
  - `footage.md`：實拍打光、後製重新打光、影片精修、照片修圖、靜圖進 MV
  - `awesome-mv-index.md`：awesome 庫 MV／藝術向 29 支精選與可遷移的手法
  - `anime.md`：日系動漫剪輯元素與風格清單
  - `masters.md`：導演與動畫 OP 演出家的手法、使用者回饋教訓
  - `review.md`：評分錨點、評分紀律、禁用清單
- `.claude/skills/video-lab/templates/`
  - `treatment.md`：treatment（風格聖經）填空範本
  - `cuts.csv`：剪點表範本（`bar,beat,src,in,speed,label`）
  - `engine.py`：seek(t) 影片引擎範本
  - `music.py`：原創合成配樂範本（段落表對齊畫面）
- `.claude/skills/video-lab/assets/`
  - `mv-kit.js`：MV 工具庫（全域 `MV`：節拍、歌詞、緩動、時間軸、字型排印、後製）
  - `mv-template.html`：一支 MV 的骨架與示範
  - `anime-fx.js`、`anime-demo.html`：動漫演出效果庫（集中線、衝擊格、カットイン等）與示範
  - `blobtrace.html`：blob tracking 疊加特效工具
- `.claude/skills/video-lab/scripts/`
  - `analyze.py`：歌曲 → `audio.json`（拍格、downbeat、段落、包絡線、鼓點）
  - `align.py`：歌詞 → `lyrics.json` 逐字時間碼
  - `render.py`：HTML `render(t)` → mp4／透明 mov／webm、預覽拼圖、剪點拼圖、動態模糊、4K
  - `cutlist.py`：剪點表 → 踩拍 montage
  - `qa.py`：成片檢查（剪點對拍、黑場、閃白、每段抽格拼圖）
  - `testsong.py`：合成測試歌與真值
  - `footage.py`：實拍與照片精修子命令
  - `seekkit.py`：Python seek(t) 引擎零件（隨機存取影片、取景、捲動截圖、字型排印與自動換行、遮罩升起、光線、顆粒）
  - `frames.py`：引擎執行器（抽格、縮圖總覽＋評分表、切段平行渲染、HEVC 交付壓檔）
  - `review.py`：縮圖總覽評分關卡（全部 ≥ 8 分才放行）
  - `brand.py`：網址 → 品牌素材包（真截圖、logo、品牌色、字型、文案）

參考庫不放進本 repo，每次從上游取得。本 repo 為公開，客戶素材與成品不要 commit（`out/` 已忽略）。`data/`（`audio.json`、含整首歌詞的 `lyrics.json`）已被 `.gitignore` 忽略，同樣不要 commit。

## 注意

- 字幕辨識的 Whisper 模型從 huggingface.co 下載，雲端環境的網路政策需放行該網域。
- 本機（Mac）不跑 hook，依 SKILL.md 自行安裝工具。
