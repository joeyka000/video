---
name: video-lab
description: 日常剪片、程式動畫與 MV／藝術影片工作臺。剪片（剪段、去停頓、橫轉直 9:16、合併、音量標準化）、上字幕（Whisper 逐字稿→繁中 SRT→燒進影片、卡拉OK逐字字幕）、踩點剪、片頭／字卡／資料動畫，以及 MV／藝術影片（概念與 treatment、分鏡、音訊分析踩點、歌詞逐字對齊、程式渲染時間軸、動態模糊輸出、實拍打光與精修、自檢）並輸出 mp4 時使用。參考庫：pdoom-video（程式渲染 MV 引擎）、anime-op（動畫 OP 分鏡）、awesome-opus5-5-videos（475 支程式動畫 prompt）。
---

# Video Lab

## 參考庫位置
- `~/video-lab/refs/pdoom-video`：程式渲染 MV 範本
  - `docs/TREATMENT.md`：概念與風格聖經的典範（只借結構，條目與內容不可用）
  - `docs/ENGINE.md`：引擎、動態模糊、逐格取樣
  - `app/scripts/render.ts`：headless Chrome 逐格截圖 → ffmpeg 合成
  - `analysis/align.py`：Whisper＋CTC 逐字時間碼對齊
  - `analysis/analyze.py`：節拍／小節／段落分析
- `~/video-lab/refs/anime-op`：動畫 OP 範例；`STORYBOARD.md` 是依 BPM 排的分鏡表典範（程式碼 ISC；歌曲與影片素材不可用）
- `~/video-lab/refs/awesome-opus5-5-videos`：程式動畫 prompt 庫
  - `data/videos.json`：全索引（475 支，含技術標籤 Canvas／SVG·GSAP／Three.js／GLSL）
  - `prompts/*.md`：單支 prompt。找風格先用 videos.json 依標籤篩，再讀對應 prompt；MV 與藝術向的先查 `references/awesome-mv-index.md`

## 技能內檔案地圖
路徑相對於 `.claude/skills/video-lab/`（`python scripts/analyze.py` 就是 `python .claude/skills/video-lab/scripts/analyze.py`）；`data/`、`out/`、`media/` 相對於 repo 根目錄，指令在那裡執行。
- `references/mv-direction.md`：MV／藝術影片的思考順序（brief → 聽歌拆結構 → 概念 → 母題 → treatment → 分鏡 → 素材 → 剪輯 → 自檢），每步的產出物與確認點；三種型態、概念方法、藝術影片骨架、密度與歌詞模式、分鏡表規格與動態分鏡
- `references/editing.md`：音樂驅動的剪輯文法（剪在哪裡、密度表、標點符號原則、對嘴對時）、14 招各附 `MV.timeline` 寫法與實測 ffmpeg 配方、剪點表工作流程、剪輯自檢
- `references/craft.md`：色彩與調色、字型排印（可用字型、字級、安全區、字幕規格、kerning、網格）、動態與緩動、動態模糊取樣、聲畫對位、輸出規格與 ffprobe 核對、視覺自檢
- `references/footage.md`：實拍打光（on-set）、後製重新打光、影片精修（降噪、穩定、柔膚、去背、顏色匹配）、照片修圖、靜圖進 MV、「不過度美化」判準、自檢
- `references/awesome-mv-index.md`：awesome 庫 29 支 MV／歌詞動畫／音訊反應／動態字型／生成藝術精選，依需求查詢表與可遷移的手法
- `references/anime.md`：日系演出術語對照、實拍動漫化 ffmpeg 做法、風格方向
- `templates/treatment.md`：treatment（風格聖經）填空範本，12 節，每欄附填寫提示
- `templates/cuts.csv`：剪點表範本（`bar,beat,src,in,speed,label`），含 12 列範例
- `assets/mv-kit.js`：MV 工具庫（全域 `MV`）：資料與等拍格、節拍、歌詞、數學與緩動、時間軸與轉場、字型排印、後製；畫面全是 t 的純函式
- `assets/mv-template.html`：一支 MV 的骨架與五段示範（字卡、歌詞、副歌、紙底、尾奏）；檔頭寫了換歌、瀏覽器預覽、輸出順序與估時
- `assets/anime-fx.js`、`assets/anime-demo.html`：動漫演出效果庫（`AFX.*`）與示範頁
- `assets/blobtrace.html`：blob tracking 疊加特效工具（F 段）
- `scripts/analyze.py`：歌曲 → `data/audio.json`（tempo、beats、downbeats、sections、env、onsets）
- `scripts/align.py`：歌詞文字 → `data/lyrics.json` 逐字時間碼（faster-whisper，或 `--from-json` 吃現成時間碼）
- `scripts/render.py`：HTML `render(t)` → mp4／透明 mov／webm、預覽拼圖、剪點拼圖、子格動態模糊、4K
- `scripts/cutlist.py`：cuts.csv ＋ audio.json → 踩拍 montage（精準到格）＋ `OUT.cuts.json`
- `scripts/qa.py`：成片 → `out/qa/report.md`（剪點對拍誤差、黑場、閃白、亮度）與每段落在 downbeat 抽格的拼圖
- `scripts/testsong.py`：合成測試歌與真值 JSON，還沒拿到歌時先跑通流程
- `scripts/footage.py`：實拍精修子命令（stabilize、denoise、sharpen、deflicker、skin、relight、match、photo、kenburns、upscale、slowmo），`--dry-run` 只印指令、`--preview 10` 只做前 10 秒

## 工作原則
- 素材原檔不動，輸出一律寫到 `./out/`，檔名加字尾（_cut、_sub、_9x16）；分析資料放 `./data/`（已在 `.gitignore`；`data/lyrics.json` 含整首歌詞、`data/audio.json` 是客戶歌曲的分析資料，都不要 commit）
- 動手前先 `ffprobe` 看解析度、fps、長度、音軌
- 轉檔預估超過一分鐘時，先用 10 秒片段試跑給我看，確認再跑全片
- 字幕與畫面文字一律繁體中文（臺灣用語）；Whisper 出簡體時用 OpenCC `s2twp` 轉
- 缺工具就先裝（ffmpeg、bun、faster-whisper、opencc、auto-editor、playwright），Python 套件裝在 `~/video-lab/.venv`
- 工具選項以 `--help` 為準，不憑記憶

## A. 日常剪輯（ffmpeg）
- 剪段：`ffmpeg -ss 開始 -to 結束 -i in.mp4 -c copy out.mp4`；要精準到格改重編碼
- 去停頓（口播）：`auto-editor`，邊界留 0.2 秒
- 橫轉直 9:16
  - 裁切：`-vf "crop=ih*9/16:ih,scale=1080:1920"`
  - 模糊背景填滿：`-filter_complex "[0:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=20[bg];[0:v]scale=1080:-2[fg];[bg][fg]overlay=(W-w)/2:(H-h)/2"`
- 合併：同規格用 concat demuxer `-f concat -safe 0 -i list.txt -c copy`；規格不同先統一重編碼
- 音量標準化（社群平臺）：`-af loudnorm=I=-14:TP=-1.5:LRA=11`；交付母帶用 `references/craft.md`〈交付指令〉的兩段式（先量再套實測值）
- 社群輸出規格：H.264、`-pix_fmt yuv420p`、AAC 192k、`-movflags +faststart`
- 實拍素材要穩定、降噪、柔膚、重新打光、兩段顏色匹配：`scripts/footage.py` 的子命令，配方與量級見 `references/footage.md`

## B. 字幕
1. 口播沒有講稿：faster-whisper（large-v3、language=zh、開字級時間碼）→ JSON
2. 有既定文字（歌詞、講稿）要逐字時間碼：`python scripts/align.py song.mp3 lyrics.txt -o data/lyrics.json`（lyrics.txt 一行一句；`--language en` 英文歌；辨識出簡體自動 s2twp）→ `lyrics.json`（中文一字一個 word，英文一個單字一個 word）。模型下載不了時先在本機跑 faster-whisper 出 words.json，再 `--from-json words.json`，不載模型
3. OpenCC `s2twp` 轉繁 → 依我給的專有名詞清單校正（品牌名、產品名、人名）
4. 產 SRT；短影音每行 14 字內、不跨句斷行
5. 燒字幕：`subtitles=` filter，字型 Noto Sans TC Bold、白字黑描邊；字級、位置、描邊規格與 letterbox 時怎麼算位置見 `references/craft.md`〈字幕規格〉〈安全區與平臺遮擋區〉
6. 卡拉OK逐字亮字：產 ASS（`\k` 標籤）；要更花的效果就用 `lyrics.json` 配 `assets/mv-kit.js` 的 `MV.karaoke`（亮字永不超前人聲）做程式動畫疊加（見 D、G）

## C. 踩點剪
1. `python scripts/analyze.py song.mp3 -o data/audio.json --sections "intro:0,verse1:4,chorus1:12"`（數字是小節序，bar 0 = 第一個 downbeat；`--bpm N` 固定 tempo、`--first-beat 秒` 校正第一拍、`--plot out/structure.png` 出分析圖；librosa 即可，不必跑 Demucs）。核對印出的摘要：拍數 ≈ 歌長 × BPM ÷ 60，印出的 tempo 與點頭的速度差一倍（快歌估成一半、慢歌估成兩倍）就用 `--bpm` 覆寫重跑
2. 複製 `templates/cuts.csv` 填剪點表：`bar,beat,src,in,speed,label`（bar 從 0 起、beat 1–4 可填 2.5 半拍；每列從該拍起播 src 的 in 秒處，播到下一列為止；speed 只為設計用，不拿來湊拍）。剪點對齊 downbeat，密度照 `references/editing.md`〈3. 剪輯密度表〉；對嘴鏡頭的 `in` 用〈10. 對嘴鏡頭對時〉的交叉相關算，不手填
3. 先把剪點表給我確認，再 `python scripts/cutlist.py cuts.csv --audio-json data/audio.json -o out/montage.mp4 --music song.mp3 --sheet`：先印絕對秒數的剪點表再精準到格重編碼，另寫 `out/montage.cuts.json` 與拼圖 `out/montage.cuts.png`
4. `python scripts/qa.py out/montage.mp4 --audio-json data/audio.json -o out/qa --cuts out/montage.cuts.json`：讀 `report.md` 的預期剪點命中、±1 格內比例（≥ 90%，門檻以 `references/editing.md`〈1. 剪在哪裡〉為準）、黑場與閃白，逐張看 `sheet_<section>.png`，改最弱三處的 in-point 再跑
- 拍點效果（白閃、負片、punch-in）在 montage 上後製，時間先減 cuts.json 的 offset：`references/editing.md`〈四、剪點表工作流程〉步驟 4

## D. 片頭／字卡／資料動畫（程式渲染）
1. 從 awesome 庫挑 1–3 支風格參考（MV 向先查 `references/awesome-mv-index.md`），改寫成我的內容；原 prompt 只當參考，不照抄
2. 寫成單一 HTML，畫面必須是時間 t 的純函式（`render(t)`；不用 requestAnimationFrame 累加狀態、不用 Math.random／Date.now），預覽和輸出才會一致（pdoom 的核心做法）；每格換一次的東西（抖動、閃爍、顆粒種子）用 `MV.frameIdx(t)`
3. 輸出：playwright 開 headless Chrome，逐格設定 t → 截圖 → ffmpeg 合成 mp4。預設 1920×1080、30fps；直式用 `--w 1080 --h 1920`，版面要在頁面裡另排
4. 要疊在實拍影片上時輸出透明背景：ProRes 4444（.mov）或 VP9 alpha（.webm）
5. 輸出程式 `python scripts/render.py page.html -o out/x.mp4 --dur 5`：
   - 既有：`--alpha` 透明（.mov／.webm）、`--sheet 0.5,2,4` 預覽拼圖（每格標秒數）、`--audio song.mp3` 合音軌、`--from 秒` 起點（音軌同步偏移）、`--w --h --fps`
   - `--data audio=data/audio.json --data lyrics=data/lyrics.json`：頁面載入前注入 `window.DATA`；另注入 `window.RENDER_FPS`、`window.RENDER_SCALE`
   - `--samples 8 --shutter 0.5`：子格平均動態模糊（Canvas 2D；靜態 4、一般動作 8–12、whip／slam 24+，見 `references/craft.md`〈動態模糊與取樣〉）
   - `--scale 2`：deviceScaleFactor 2 輸出 3840×2160，頁面仍以 1920×1080 版面；頁面要依 `window.RENDER_SCALE` 放大 canvas 才是真 4K
   - `--cuts`：讀 `window.CUTS` 出每個剪點前後各 2 格的拼圖；`--dump-cuts out/cuts.json` 把 CUTS 寫成 qa.py 吃的格式；`--profile` 印每格 render／截圖毫秒數，用來估全片時間
   - 頁面的 console.error 與 pageerror 印到 stderr，pageerror 以非 0 結束：每次渲染都看 stderr
6. MV 的起點：`assets/mv-kit.js`（全域 `MV`：`setData`／`setGrid`、`beatAt`／`timeOfBar`／`sectionAt`／`env`／`hit`、`line`／`karaoke`、`ease`／`prog`／`keys`／`spring`、`timeline`、`layout`／`fitSize`／`safeArea`、`post`）＋ `assets/mv-template.html`；用法照 G 段

## E. 日系動漫風格
- 要做動漫風（集中線、衝擊格、明朝體字卡、カットイン、透過光、MAD 節奏等）時，先讀 `references/anime.md`
- 效果庫：`assets/anime-fx.js`（`AFX.*`），示範：`assets/anime-demo.html`；可與 `MV` 並用
- 實拍轉動漫感的 ffmpeg 做法也在 `references/anime.md`
- 參考庫：`~/video-lab/refs/anime-op`（動畫 OP 範例，程式碼 ISC；歌曲與影片素材不可用）

## F. Blob tracking 疊加特效（Blobtrace）
- 工具：`assets/blobtrace.html`，單一 HTML 檔，直接用瀏覽器開；全部在本機運算，不上傳檔案
- 用途：對影片做斑點追蹤（亮部／暗部／動態），疊上追蹤框、連線、標籤、框內濾鏡、全畫面故障效果，即時預覽並錄成 WebM（不支援時 MP4）
- 做 TouchDesigner 風格的 blob tracking 段落時先用它試效果；要逐格精準輸出時，照 D 段的做法改寫成 `render(t)` 純函式再用 `scripts/render.py` 輸出

## G. MV 與藝術影片（高品質）
接到 MV、歌詞影片、藝術／實驗影片時走這段。先讀 `references/mv-direction.md`（每步的產出物與確認點都在那裡），步驟編號與它相同；沒確認就不進下一步，第 0–5 步走完才寫程式或剪片。
0. 接 brief：照〈0. 接 brief 時先問〉一次問完（歌與歌詞、分軌、演出者、平臺與比例、長度、素材、預算、禁忌、三支參考）；缺的先假設並標明
1. 聽歌拆結構：C 段第 1 步的 `analyze.py`（有分軌時鼓軌給它）；有歌詞再 B 段第 2 步的 `align.py`（人聲軌給它）；還沒拿到歌先 `python scripts/testsong.py -o out/test.wav --bpm 120 --bars 32` 跑通流程。產出段落表（名稱、起訖小節與秒、能量、第一句歌詞）與能量曲線
   - 給我確認：段落表與能量曲線（副歌幾次、哪次最大、breakdown 在哪）；BPM 與第一拍由我用耳朵核對
2. 一句話概念：提三個互不相像的概念，每個同時說出「畫面是什麼」與「怎麼隨歌變化」；型態依〈二、MV 的三種型態〉選，藝術影片依〈四、藝術影片／實驗影片的做法〉挑一種骨架，概念方法見〈三、概念思考方法〉
   - 給我確認：概念三選一。選定前不做任何視覺
3. 母題與貫穿物：一個物件、圖形或動作，片頭出現、每次副歌回來、片尾收束且每次有變化；列「段落 → 母題狀態 → 歌詞整合方式」的表（歌詞模式見〈歌詞如何「成為畫面」而不是字幕〉）
   - 給我確認：母題表
4. 風格聖經：填 `templates/treatment.md`（語氣三擇一、母題表、色票、字型系統、質地與後製、禁止清單、逐段 treatment）；色票與字型的規則照 `references/craft.md`〈色票紀律〉〈可用字型〉〈字級層級〉
   - 給我確認：整份 treatment，重點是色票（色相 ≤ 4、稀有強調色只屬一個瞬間）、字型家族 ≤ 2、語氣只有一種、禁止清單具體
5. 分鏡表：照〈六、分鏡表規格〉一列一鏡，時間主鍵是小節／拍、秒數從 `data/audio.json` 換算；密度照 `references/editing.md`〈3. 剪輯密度表〉；程式動畫鏡頭到 `references/awesome-mv-index.md` 查做法，日系表現在備註標 `AFX.*`；要先看節奏就照同一節做動態分鏡（animatic，`render.py --fps 10 --audio`）
   - 給我確認：分鏡表（最後一次大改便宜的機會，之後只做小幅調整）
6. 素材計畫：來源分成實拍、靜圖、程式動畫三類（〈6. 素材計畫〉）。實拍打光與精修讀 `references/footage.md`、用 `scripts/footage.py`（每個子命令先 `--dry-run`、再 `--preview 10` 試前 10 秒給我看）；對嘴 take 的 `in` 照 `references/editing.md`〈10. 對嘴鏡頭對時〉算；靜圖一律過色票對映＋顆粒＋一種動態（`footage.py kenburns` 或視差）才上畫面；每個實拍 take 留 2 小節以上
   - 給我確認：素材清單與預算；沒素材的鏡頭在這裡決定改程式動畫或刪
7. 剪輯與輸出：
   - 程式動畫：複製 `assets/mv-template.html` 與 `assets/mv-kit.js`，一段一個 `MV.timeline` entry（段落邊界用 `MV.timeOfBar(小節)`、歌詞用 `MV.line('內容')` 找行，不寫死秒數）；順序：`render.py --sheet` 拼圖 → `--cuts` 剪點拼圖 → `--dur 10 --from 秒 --audio song.mp3` 試渲（最大副歌前後各 2 小節，要含一次轉場、一次全幅歌詞、一次母題變化）→ 全片放背景跑（`run_in_background`）。估時先跑 10 格加 `--profile`：1080p 約 0.5–1 秒/格，3 分鐘全片 1–1.5 小時，`--samples 8` 約 2.7 倍、`--scale 2` 約 3 倍
   - 實拍與靜圖：C 段第 2–4 步（`templates/cuts.csv` → `cutlist.py` → `qa.py`）；混用時 montage 當底，程式動畫 `--alpha` 疊上
   - 剪輯手法（J／L cut、match cut、速度斜坡、whip、閃白…）照 `references/editing.md`〈二、招式表〉與〈三、實拍 ffmpeg 配方〉；色彩、排印、動態、後製照 `references/craft.md`；日系表現照 `references/anime.md`
   - 給我確認：10 秒試渲染。沒看過試渲染不渲全片；超過半小時先給拼圖再決定要不要開 `--scale 2`／`--samples`
8. 自檢與交付：`python scripts/qa.py out/final.mp4 --audio-json data/audio.json -o out/qa --cuts out/montage.cuts.json`（程式動畫改用 `render.py --dump-cuts out/cuts.json` 寫出的檔）；讀 `report.md`（±1 格內比例 ≥ 90%，門檻同 C 段第 4 步，以 `references/editing.md`〈1. 剪在哪裡〉為準）與 `sheet_<section>.png`。逐題回答 `references/mv-direction.md`〈七、思考自檢清單〉、`references/editing.md`〈五、剪輯自檢清單〉、`references/craft.md`〈六、視覺自檢清單〉，有實拍另答 `references/footage.md`〈八、自檢清單〉；答不出的回到對應步驟改。交付依 `references/craft.md`〈五、輸出規格〉：loudnorm 兩段式、bt709 標記、多比例版本各自排版、縮圖格、ffprobe 核對表
   - 交付時附：自檢答案、qa 報告重點、拼圖、ffprobe 輸出、修了什麼
- 全片共用一套色票、字型角色、顆粒；每段一種視覺語言、一個大招；稀有強調色只用一次；逐條對〈三、概念思考方法〉的「不是 slop」清單

## H. AI 生成影片（Veo）
- 工具與流程：repo 根目錄 `veo/`（`veo.py`、`README.md`）。金鑰讀 `GEMINI_API_KEY`
- **省錢規則（使用者要求）**：一律先用便宜的方式試，使用者看過、點頭後才花大錢——首格用 Nano Banana 2 → 試片用 Veo 3.1 lite 720p 每段 4 秒 → 只把點頭的鏡頭用 fast 1080p 重生；standard（每秒 $0.40）只在使用者明確要求時用。**任何會花錢的步驟（含首格、試片、定稿，不論金額多小）送出前都要先通知使用者：說明要做什麼、用哪個等級、預估金額，等使用者在對話中明確同意這一筆才加 `--yes`；前一次的同意不延用到下一次**

## 品質標準（所有作品）
- 目標是 Awwwards、Webby Awards、FWA 獲獎等級；完成後依下表逐項自檢，修到沒有明顯可提升之處才交付，交付時附上自檢結果
- 排版：網格與對齊一致；字級有明確層級；中文字距、行距調過；字幕與標題不壓到人臉與主體
- 留白：每個畫面只有一個重點；文字周圍留足呼吸空間，不塞滿
- 視覺層級：觀眾一眼知道先看哪裡；主標、副標、資訊三層以內
- 色彩：全片一套色票（主色、輔色、中性色）；調色統一，膚色自然，不過度美化
- 動效：每個動作有緩動與節奏、對齊拍點；同一支片的轉場語言一致，節制使用特效
- 微互動（影片中對應「小動態」）：字卡、數字、圖示、底線等細節有精緻的進出場，不用預設淡入淡出湊數
- 響應式（影片中對應「多比例與安全區」）：需要時輸出 9:16、1:1、16:9；文字避開 IG／TikTok／YouTube 介面遮擋區
- 原創性：至少一個只屬於這個題材的設計巧思，避免模板感
- 自檢方法：每段抽格拼成總覽圖逐張看；看完整片一次確認節奏；找出最弱的三處修改後再看一次
- MV 另依 `references/craft.md`〈六、視覺自檢清單〉的視覺自檢與 `references/editing.md`〈五、剪輯自檢清單〉的剪輯自檢（都是可量測的題目）；實拍精修另依 `references/footage.md`〈八、自檢清單〉

## 授權
- pdoom-video 程式碼 MIT 可商用；`audio/`、`lyrics/`、`data/lyrics.json` 屬原作者，不可使用
- anime-op 程式碼 ISC；歌曲與影片素材屬原作者，不可使用
- awesome 庫每支 prompt 與影片屬原作者，客戶案一律改寫；貼文類（`prompt_partial`）只借概念
- 字型只用可商用字型（Noto Sans TC 等 OFL 授權字型）；明朝體寫全名 `Noto Serif CJK TC`（`Noto Serif TC` 沒有別名）
- 範例文案、歌詞、曲名、角色一律自創；參考庫的歌詞、音訊、圖片、角色不出現在作品裡

## 雲端 session（Claude Code on the web）
- 開 session 時 `.claude/hooks/session-start.sh` 會自動：apt 裝 ffmpeg 與 Noto CJK 字型（`Noto Sans TC` 已設成 `Noto Sans CJK TC` 的別名，ffmpeg 與 Chromium 都吃得到）、在 `~/video-lab/.venv` 裝 Python 套件並加進 PATH、把參考庫 clone／更新到 `~/video-lab/refs/`。安裝紀錄在 `~/video-lab/setup.log`
- Chromium 已預裝在 `/opt/pw-browsers`，不要跑 `playwright install`；Python playwright 版本已對齊預裝的 Chromium
- Whisper 模型從 huggingface.co 下載，環境網路政策沒放行時會失敗，先告訴我，不要改用其他來源；`align.py` 改走 `--from-json`
- 機器只有 4 核心：ffmpeg 試跑用短素材、playwright 渲染先出拼圖與 10 秒試渲，全片放背景跑
- 這個 repo 是公開的：客戶素材、成品、`refs/` 內容、`data/`（歌詞與分析資料，已被 `.gitignore` 忽略）都不要 commit
