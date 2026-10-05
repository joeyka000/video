# Veo 生成工具

用 Gemini API 的 Veo 模型把分鏡生成直式影片片段，之後再交給剪輯流程。

1. 在雲端環境設定加入環境變數 `GEMINI_API_KEY`（Google AI Studio 金鑰，需開啟計費；不要貼在對話或 commit 進 repo）。
2. 把 `shots.template.json` 複製成 `shots.json`，填入主角外觀描述，參考照片放在同資料夾的 `ref.jpg`（照片不進 repo）。
3. `python veo.py models` 確認能用的模型（免費）。
4. `python veo.py keyframe shots.json` 用參考照片做每個鏡頭的首格（付費，量小）。
5. `python veo.py gen shots.json` 先看預估秒數，確認後加 `--yes` 才會送出生成（付費）。

輸出在 `out/`（`*.png` 首格、`*.mp4` 片段）。
