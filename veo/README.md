# Veo 生成工具

用 Gemini API 的 Veo 模型把分鏡生成直式影片片段，之後再交給剪輯流程。

## 省錢流程（預設，一律照做）
先用便宜的方式試，使用者看過、點頭後才花大錢。**任何付費步驟送出前都要先通知使用者（做什麼、等級、預估金額），取得這一筆的明確同意才加 `--yes`，不論金額多小，前一次的同意不延用。**

| 步驟 | 指令 | 預設等級 | 單價（2026-10 查） |
|---|---|---|---|
| 1. 首格 | `python veo.py keyframe shots.json --yes` | Nano Banana 2（1K） | 每張 $0.067；`--pro` 為 $0.134 |
| 2. 試片 | `python veo.py gen shots.json --yes` | Veo 3.1 lite、720p、每段 4 秒 | 每秒 $0.05 |
| 3. 定稿 | `python veo.py gen shots.json s2 s3 --tier fast --res 1080p --seconds 8 --yes` | 只重生點頭的鏡頭 | fast 1080p 每秒 $0.12 |
| （最高畫質） | 再加 `--tier standard --final` | 使用者明確要求才用 | 每秒 $0.40 |

- 沒加 `--yes` 只印預估；超過 `--budget`（預設 $2）直接拒絕。
- 首格已存在不會重做（要重做加 `--redo`），避免重複付費。
- 試片與定稿分開存成 `out/<id>_<tier>.mp4`；實際花費記在 `out/spend.jsonl`，`python veo.py spend` 看累計。
- 價格會變，大筆花費前到 https://ai.google.dev/gemini-api/docs/pricing 再查一次。

## 準備
1. 在雲端環境設定加入環境變數 `GEMINI_API_KEY`（Google AI Studio 金鑰，需開啟計費；不要貼在對話或 commit 進 repo）。
2. 把 `shots.template.json` 複製成 `shots.json`，填入主角外觀描述，參考照片放在同資料夾的 `ref.jpg`（照片不進 repo）。
3. `python veo.py models` 確認能用的模型（免費）。
