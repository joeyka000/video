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
- 影片 → `ffprobe` 規格；每支出時間碼縮圖（`ffmpeg -vf "fps=2,scale=180:-1,drawtext=…%{pts\:hms}…,tile=10x6"`）逐張看，記下每個動作的秒數，以及每個鏡頭的功能（建立／主體／細節／反應／收）、主色、主形狀、主體位置（配對 match cut 用）；手持素材先穩定化（`VL/scripts/footage.py stabilize` 或 vidstab 兩段式）
- 照片、歌 → 照 video-lab 技能 C 段（`analyze.py`）與 footage.md
- 相簿要先分辨「素材」和「成品」：使用者常把剪好的片（自己剪的 IG 片、我們交過的舊成品）存回同一本相簿；有字、有調色、長度剛好 30／60 秒的 mp4 先看縮圖確認，不當素材用。跟舊專案重複的檔案用硬連結（`os.link`），不重抓也不多佔磁碟
- 私人資訊：登機證（條碼含姓名與訂位代號）、證件號碼、地址、密碼 → 畫面裡讀得出就要處理。做法是只留主體清楚、其他淺景深糊掉（`seekkit.keep_sharp`）；條碼一定在羽化帶外面（羽化 ≤ 6 px），背景若有電視、螢幕會換畫面，用整段平均的一張糊圖當背景，不然會在剪點前閃一下。處理完 100% 放大確認讀不出來
- 素材與成品放 `projects/<案名>/`（不進 git）

## 2. 概念與分鏡（寫進 plan.md）
- 一句話概念＋**一個只屬於這個題材的巧思**（例：卡牌品牌的辦公室片＝「撕開一包」開場、PSA 卡盒標籤當段落標題）；照 `VL/references/story.md`〈一〉推導（題材的真東西 → 結構裝置 → 轉場動詞），五題概念壓力測試的答案寫進 plan.md，有一題不過就重想
- 結構排成五段（鉤子、建立、展開、高點、收；秒數表見 story.md〈二〉），寫出遞進方向（遠→近、白天→夜晚…選一條）
- 讀 `VL/references/masters.md`〈零〉的使用者回饋與〈六〉選擇器，挑一個主語言
- 鏡頭表：起訖秒（段落邊界落在小節上：100 BPM 一小節 2.4 秒）、功能、景別、素材與入點、字卡內容（真實文案）、特效（每個特效寫理由）。同一主體連續兩刀景別差兩級或換角度；入點用 `python VL/scripts/flow.py pick <素材> --from --to --dur [--clean bottom]` 挑
- 對照 `VL/references/review.md`〈禁用清單〉，有就換掉
- 有實拍素材：`python VL/scripts/look.py board <5–8 格代表素材> --moods clean,soft,day,golden,aot -o projects/<案名>/qa/look_board.jpg`，挑一個 mood 寫進 plan.md（刪掉格頭有紅字的；挑法見 `VL/references/finish.md`〈二〉〈三〉），look board 跟著概念一起給使用者看

## 3. 寫 seek(t) 引擎
- 複製 `VL/templates/engine.py` → `projects/<案名>/work/engine.py`；零件用 `VL/scripts/seekkit.py`（`Src`、`kenburns`、`scroll_page`、`rise`、`type_on`、`fit_text`、`wrap_text`、`glow_line`、`scrim`、`grain`…）
- 字多、版面複雜或要網頁特效時改走 HTML `render(t)`（video-lab 技能 D、G 段，`VL/scripts/render.py`）
- `MARKS` 列出要評分的格：每段代表格、每個大招峰值、字卡完全進場、轉場正中、片頭第一格內容、片尾定格
- 所有字用 `fit_text`／`wrap_text`；新字串先 `missing_glyphs()` 查豆腐字；移動中的字用 `blit`／`rise`（次像素），不要自己 `int()` 位置
- 實拍鏡頭：`face_safe(素材, MOOD)` → `match(…, REF, 0.7)`；截圖、UI、logo 不調色；快速運動包 `mblur`；手機原圖用 `image(path, max_side=2×輸出長邊)`

## 4. 縮圖總覽關卡（沒過不准渲全片）
```
python VL/scripts/frames.py sheet projects/<案名>/work/engine.py -o projects/<案名>/qa/sheet.jpg
# 看圖，依 VL/references/review.md 的錨點逐格寫 score / why / fix 進 qa/sheet.review.json
python VL/scripts/review.py gate projects/<案名>/qa/sheet.review.json
```
沒過：修最差的 3 格 → 重出（round 自動 +1）→ 重評 → `review.py diff` 看進步；第 4 輪還沒過就停下來給使用者看分數表。

剪點關卡（同樣全部 ≥ 8 才渲全片；engine 的 `SHOTS` 就是剪點表）：
```
python VL/scripts/flow.py check --engine projects/<案名>/work/engine.py -o projects/<案名>/qa/flow
# 看 qa/flow/cuts.jpg 與 report.md，依 VL/references/review.md〈剪點評分〉逐刀填 qa/flow/cuts.review.json
python VL/scripts/review.py gate projects/<案名>/qa/flow/cuts.review.json
```

## 5. 試渲（看動態與聲音）
- 配樂：複製 `VL/templates/music.py`，改 `BPM`、`DUR`、`SECTIONS`、`LOGO`、`TICKS` 對齊鏡頭表，輸出 wav，在引擎設 `AUDIO`
- `frames.py video engine.py -o qa/test.mp4 --from <大招前 3 秒> --to <後 7 秒>`，再 `review.py sheet --video qa/test.mp4 --every 0.5` 看轉場與進場節奏；聽落拍有沒有對到畫面；`flow.py check qa/test.mp4 -o qa/flow_test` 看入點糊、重複格（engine 模式只看得到剪點前後 7 格）

## 6. 全片與交付
```
python VL/scripts/frames.py video projects/<案名>/work/engine.py -o projects/<案名>/deliver/master.mp4   # run_in_background
python VL/scripts/frames.py deliver projects/<案名>/deliver/master.mp4 -o projects/<案名>/deliver/<名稱>.mp4
python VL/scripts/review.py sheet --video projects/<案名>/deliver/<名稱>.mp4 -o projects/<案名>/qa/final.jpg --n 32
python VL/scripts/flow.py check projects/<案名>/deliver/<名稱>.mp4 -o projects/<案名>/qa/flow_final
python VL/scripts/finish.py check projects/<案名>/deliver/<名稱>.mp4 --flow projects/<案名>/qa/flow_final/flow.json -o projects/<案名>/qa/finish_final
```
- `finish_final/report.md` 的「要處理」逐條處理或在評分表寫理由（夜景死黑、復古偏色這種刻意的）；色階 > 8：母帶的 grain 拉到 0.016 以上重渲，來不及重渲就 `frames.py deliver … --grain 3` 重壓（實測 38 → 12.6 px，finish.md〈八〉）
- 成品總覽再看一次（壓縮後字有沒有糊、有沒有黑格）；分段渲染的中間檔用完即刪
- 用 SendUserFile 傳成品（≤ 30 MiB），回覆附：長度與規格、能不能直接發、段落內容、自己補的假設、最後一輪評分（縮圖與剪點各自的平均／最低）、`flow_final/report.md` 的平均鏡頭長、實拍不到半個畫面的時間、剪輯速度 vs 音樂能量、`finish_final/report.md` 的黑位標準差與偏色分散、用了哪個 mood、要使用者確認的地方

## 7. 收尾
- 這次學到、可以重複用的做法：零件寫回 `VL/scripts/seekkit.py`，規則寫回 `CLAUDE.md` 或 `VL/references/`；使用者的回饋寫進 `VL/references/masters.md`〈零〉
- 只 commit 工具與規則，不 commit 素材與成品
