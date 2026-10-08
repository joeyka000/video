---
name: new-video
description: 一句話開一支新影片並做到交付：產品／品牌片（丟網址）、活動或空間導覽、旅遊 vlog、教學說明、片頭與字卡。從一句需求自動補齊規格、抓真素材、寫 seek(t) 引擎、縮圖總覽評分到全部 8 分以上、試渲、平行渲染、壓成可上傳的檔案。使用者說「做一支…影片」「幫我剪一支新片」「用這個網址做產品影片」「/new-video …」時使用。小修舊片不用這個技能（用 video-lab）。
argument-hint: "[網址或素材] [長度] [比例] [用途]"
effort: xhigh
---

# 一句話開片

先讀 repo 根目錄 `CLAUDE.md`（工作室規範）。工具都在 `.claude/skills/video-lab/`（下面簡寫 `VL/`）。

## 0. 從一句話補齊規格（不要回頭問能自己決定的事）
| 項目 | 沒講時的預設 |
|---|---|
| 比例與尺寸 | 9:16、1080×1920、30fps（IG Reels／限動）；說「YouTube」「簡報」才用 16:9 |
| 長度 | 產品／品牌片 20–30 秒；導覽、教學 45–75 秒；vlog 60 秒；片頭 5–8 秒 |
| 音樂 | 有給歌就踩歌；沒給就用 `VL/templates/music.py` 合成原創配樂（沒版權問題），段落對齊畫面 |
| 字 | 繁體中文（臺灣用語），Noto Sans CJK TC；品牌有字型且授權可用才換 |
| 語氣 | 從素材與品牌推：品牌色、網站文案的口氣 |

把補上的假設寫在 `projects/<案名>/work/plan.md` 開頭，交付時一起說。
**只在這些情況停下來問**：要花錢（AI 生成，照 CLAUDE.md 花錢規則）、完全沒有素材也沒有網址、內容涉及私人資訊要對外發。

## 1. 收素材
- 網址 → `python VL/scripts/brand.py <網址> -o projects/<案名>/brand`，看 `brand.md`、`swatches.png`、截圖與 logo 候選（每張都要看過再用）
- 影片 → `ffprobe` 規格；每支出時間碼縮圖（`ffmpeg -vf "fps=2,scale=180:-1,drawtext=…%{pts\:hms}…,tile=10x6"`）逐張看，記下每個動作的秒數；手持素材先穩定化（`VL/scripts/footage.py stabilize` 或 vidstab 兩段式）
- 照片、歌 → 照 video-lab 技能 C 段（`analyze.py`）與 footage.md
- 素材與成品放 `projects/<案名>/`（不進 git）

## 2. 概念與分鏡（寫進 plan.md）
- 一句話概念＋**一個只屬於這個題材的巧思**（例：卡牌品牌的辦公室片＝「撕開一包」開場、PSA 卡盒標籤當段落標題）
- 讀 `VL/references/masters.md`〈零〉的使用者回饋與〈六〉選擇器，挑一個主語言
- 鏡頭表：起訖秒（段落邊界落在小節上：100 BPM 一小節 2.4 秒）、素材與入點、字卡內容（真實文案）、特效（每個特效寫理由）
- 對照 `VL/references/review.md`〈禁用清單〉，有就換掉

## 3. 寫 seek(t) 引擎
- 複製 `VL/templates/engine.py` → `projects/<案名>/work/engine.py`；零件用 `VL/scripts/seekkit.py`（`Src`、`kenburns`、`scroll_page`、`rise`、`type_on`、`fit_text`、`wrap_text`、`glow_line`、`scrim`、`grain`…）
- 字多、版面複雜或要網頁特效時改走 HTML `render(t)`（video-lab 技能 D、G 段，`VL/scripts/render.py`）
- `MARKS` 列出要評分的格：每段代表格、每個大招峰值、字卡完全進場、轉場正中、片頭第一格內容、片尾定格
- 所有字用 `fit_text`／`wrap_text`；新字串先 `missing_glyphs()` 查豆腐字

## 4. 縮圖總覽關卡（沒過不准渲全片）
```
python VL/scripts/frames.py sheet projects/<案名>/work/engine.py -o projects/<案名>/qa/sheet.jpg
# 看圖，依 VL/references/review.md 的錨點逐格寫 score / why / fix 進 qa/sheet.review.json
python VL/scripts/review.py gate projects/<案名>/qa/sheet.review.json
```
沒過：修最差的 3 格 → 重出（round 自動 +1）→ 重評 → `review.py diff` 看進步；第 4 輪還沒過就停下來給使用者看分數表。

## 5. 試渲（看動態與聲音）
- 配樂：複製 `VL/templates/music.py`，改 `BPM`、`DUR`、`SECTIONS`、`LOGO`、`TICKS` 對齊鏡頭表，輸出 wav，在引擎設 `AUDIO`
- `frames.py video engine.py -o qa/test.mp4 --from <大招前 3 秒> --to <後 7 秒>`，再 `review.py sheet --video qa/test.mp4 --every 0.5` 看轉場與進場節奏；聽落拍有沒有對到畫面

## 6. 全片與交付
```
python VL/scripts/frames.py video projects/<案名>/work/engine.py -o projects/<案名>/deliver/master.mp4   # run_in_background
python VL/scripts/frames.py deliver projects/<案名>/deliver/master.mp4 -o projects/<案名>/deliver/<名稱>.mp4
python VL/scripts/review.py sheet --video projects/<案名>/deliver/<名稱>.mp4 -o projects/<案名>/qa/final.jpg --n 32
```
- 成品總覽再看一次（壓縮後字有沒有糊、有沒有黑格）；分段渲染的中間檔用完即刪
- 用 SendUserFile 傳成品（≤ 30 MiB），回覆附：長度與規格、能不能直接發、段落內容、自己補的假設、最後一輪評分（平均／最低）、要使用者確認的地方

## 7. 收尾
- 這次學到、可以重複用的做法：零件寫回 `VL/scripts/seekkit.py`，規則寫回 `CLAUDE.md` 或 `VL/references/`；使用者的回饋寫進 `VL/references/masters.md`〈零〉
- 只 commit 工具與規則，不 commit 素材與成品
