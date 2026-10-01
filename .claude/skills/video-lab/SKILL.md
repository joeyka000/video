---
name: video-lab
description: 日常剪片與程式動畫工作台。剪片（剪段、去停頓、橫轉直 9:16、合併、音量標準化）、上字幕（Whisper 轉逐字稿→繁中 SRT→燒進影片、卡拉OK逐字字幕）、踩點剪、做片頭／字卡／數據動畫並輸出 mp4 時使用。參考庫：pdoom-video（程式渲染 MV 引擎）與 awesome-opus5-5-videos（282 支程式動畫 prompt）。
---

# Video Lab

## 參考庫位置
- `~/video-lab/refs/pdoom-video`：程式渲染 MV 範本
  - `docs/ENGINE.md`：引擎、動態模糊、逐格取樣
  - `app/scripts/render.ts`：headless Chrome 逐格截圖 → ffmpeg 合成
  - `analysis/align.py`：Whisper＋CTC 逐字時間碼對齊
  - `analysis/analyze.py`：節拍／小節／段落分析
- `~/video-lab/refs/awesome-opus5-5-videos`：程式動畫 prompt 庫
  - `data/videos.json`：全索引（含技術標籤 Canvas／SVG·GSAP／Three.js／GLSL）
  - `prompts/*.md`：單支 prompt。找風格先用 videos.json 依標籤篩，再讀對應 prompt

## 工作原則
- 素材原檔不動，輸出一律寫到 `./out/`，檔名加後綴（_cut、_sub、_9x16）
- 動手前先 `ffprobe` 看解析度、fps、長度、音軌
- 轉檔預估超過一分鐘時，先用 10 秒片段試跑給我看，確認再跑全片
- 字幕與畫面文字一律繁體中文（台灣用語）；Whisper 出簡體時用 OpenCC `s2twp` 轉
- 缺工具就先裝（ffmpeg、bun、faster-whisper、opencc、auto-editor、playwright），Python 套件裝在 `~/video-lab/.venv`
- 工具參數以 `--help` 為準，不憑記憶

## A. 日常剪輯（ffmpeg）
- 剪段：`ffmpeg -ss 開始 -to 結束 -i in.mp4 -c copy out.mp4`；要精準到格改重編碼
- 去停頓（口播）：`auto-editor`，邊界留 0.2 秒
- 橫轉直 9:16
  - 裁切：`-vf "crop=ih*9/16:ih,scale=1080:1920"`
  - 模糊背景填滿：`-filter_complex "[0:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=20[bg];[0:v]scale=1080:-2[fg];[bg][fg]overlay=(W-w)/2:(H-h)/2"`
- 合併：同規格用 concat demuxer `-f concat -safe 0 -i list.txt -c copy`；規格不同先統一重編碼
- 音量標準化（社群平台）：`-af loudnorm=I=-14:TP=-1.5:LRA=11`
- 社群輸出規格：H.264、`-pix_fmt yuv420p`、AAC 192k、`-movflags +faststart`

## B. 字幕
1. faster-whisper（large-v3、language=zh、開字級時間碼）→ JSON
2. OpenCC `s2twp` 轉繁 → 依我給的專有名詞清單校正（品牌名、產品名、人名）
3. 產 SRT；短影音每行 14 字內、不跨句斷行
4. 燒字幕：`subtitles=` filter，字型 Noto Sans TC Bold、白字黑描邊
5. 卡拉OK逐字亮字：產 ASS（`\k` 標籤）；要更花的效果就參照 pdoom 的逐字時間碼做成程式動畫疊加（見 D）

## C. 踩點剪
- 參照 `analysis/analyze.py` 的做法抓 beats／downbeats（librosa 即可，不必跑 Demucs）
- 剪點對齊 downbeat，先輸出剪點表（秒數＋對應素材段）給我確認再剪

## D. 片頭／字卡／數據動畫（程式渲染）
1. 從 awesome 庫挑 1–3 支風格參考，改寫成我的內容；原 prompt 只當參考，不照抄
2. 寫成單一 HTML，畫面必須是時間 t 的純函數（`render(t)`，不用 requestAnimationFrame 累加狀態），預覽和輸出才會一致（pdoom 的核心做法）
3. 輸出：playwright 開 headless Chrome，逐格設定 t → 截圖 → ffmpeg 合成 mp4。參照 `app/scripts/render.ts` 寫簡化版，預設 1080×1920 或 1920×1080、30fps
4. 要疊在實拍影片上時輸出透明背景：ProRes 4444（.mov）或 VP9 alpha（.webm）
5. 已寫好的輸出腳本：`python scripts/render.py page.html -o out/x.mp4 --dur 5`（`--alpha` 透明、`--sheet 0.5,2,4` 先出預覽拼圖、`--audio` 合音軌）

## E. 日系動漫風格
- 要做動漫風（集中線、衝擊格、明朝體字卡、カットイン、透過光、MAD 節奏等）時，先讀 `references/anime.md`
- 效果庫：`assets/anime-fx.js`（`AFX.*`），示範：`assets/anime-demo.html`
- 實拍轉動漫感的 ffmpeg 做法也在 `references/anime.md`
- 參考庫：`~/video-lab/refs/anime-op`（動畫 OP 範例，程式碼 ISC；歌曲與影像素材不可用）

## F. Blob tracking 疊加特效（Blobtrace）
- 工具：`assets/blobtrace.html`，單一 HTML 檔，直接用瀏覽器開；全部在本機運算，不上傳檔案
- 用途：對影片做斑點追蹤（亮部／暗部／動態），疊上追蹤框、連線、標籤、框內濾鏡、全畫面故障效果，即時預覽並錄成 WebM（不支援時 MP4）
- 做 TouchDesigner 風格的 blob tracking 段落時先用它試效果；要逐格精準輸出時，照 D 段的做法改寫成 `render(t)` 純函數再用 `scripts/render.py` 輸出

## 品質標準（所有作品）
- 目標是 Awwwards、Webby Awards、FWA 獲獎等級；完成後依下表逐項自檢，修到沒有明顯可提升之處才交付，交付時附上自檢結果
- 排版：網格與對齊一致；字級有明確層級；中文字距、行距調過；字幕與標題不壓到人臉與主體
- 留白：每個畫面只有一個重點；文字周圍留足呼吸空間，不塞滿
- 視覺層級：觀眾一眼知道先看哪裡；主標、副標、資訊三層以內
- 色彩：全片一套色票（主色、輔色、中性色）；調色統一，膚色自然，不過度美化
- 動效：每個動作有緩動與節奏、對齊拍點；同一支片的轉場語言一致，克制使用特效
- 微互動（影片中對應「小動態」）：字卡、數字、圖示、底線等細節有精緻的進出場，不用預設淡入淡出湊數
- 響應式（影片中對應「多比例與安全區」）：需要時輸出 9:16、1:1、16:9；文字避開 IG／TikTok／YouTube 介面遮擋區
- 原創性：至少一個只屬於這個題材的設計巧思，避免模板感
- 自檢方法：每段抽格拼成總覽圖逐張看；看完整片一次確認節奏；找出最弱的三處修改後再看一次

## 授權
- pdoom-video 程式碼 MIT 可商用；`audio/`、`lyrics/`、`data/lyrics.json` 屬原作者，不可使用
- awesome 庫每支 prompt 與影片屬原作者，客戶案一律改寫
- 字型只用可商用字型（Noto Sans TC 等 OFL 授權字型）

## 雲端 session（Claude Code on the web）
- 開 session 時 `.claude/hooks/session-start.sh` 會自動：apt 裝 ffmpeg 與 Noto CJK 字型（`Noto Sans TC` 已設成 `Noto Sans CJK TC` 的別名，ffmpeg 與 Chromium 都吃得到）、在 `~/video-lab/.venv` 裝 Python 套件並加進 PATH、把兩個參考庫 clone／更新到 `~/video-lab/refs/`。安裝紀錄在 `~/video-lab/setup.log`
- Chromium 已預裝在 `/opt/pw-browsers`，不要跑 `playwright install`；Python playwright 版本已對齊預裝的 Chromium
- Whisper 模型從 huggingface.co 下載，環境網路政策沒放行時會失敗，先告訴我，不要改用其他來源
- 這個 repo 是公開的：客戶素材、成品、`refs/` 內容都不要 commit
