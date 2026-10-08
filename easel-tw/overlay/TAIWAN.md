# Easel 台灣版

本目錄是以 [ZJU-REAL/Easel](https://github.com/ZJU-REAL/easel)（Apache License 2.0）為基礎，用 `easel-tw/build.py` 自動轉換出來的台灣版本。
上游 commit 記在 `TAIWAN-BUILD.json`；上游的 `LICENSE` 原封不動保留。Easel 名稱與商標屬原作者，這個版本與原作者無關、未經其背書。

## 跟上游不一樣的地方
- 全部介面、技能說明、代理提示詞轉成繁體中文（台灣用語）（OpenCC s2twp 加社群用語修正表）
- 代理（SOUL.md、AGENTS.md、每輪提醒）規定一律繁體中文回覆與產出、以台灣平台為準、花錢前先問
- 平台換成 Instagram、Threads、Facebook、YouTube、TikTok、LINE 官方帳號、Dcard、PTT；沒有自動登入發文，發布中心產出各平台版本後手動上傳
- 移除只服務中國平臺的技能（小紅書、抖音、快手、視頻號、知乎、B 站、公眾號）與 AGPL 授權的 gzh-design
- 熱門話題換成 Google 搜尋趨勢台灣、Google 新聞台灣、PTT、Threads 日報（`skills/shared/scripts/tw_trends.py`、`trend_log.py`、技能 `tw-threads-daily`）
- 節慶檔期新增 `events-taiwan.md`；人設範本的平台換成台灣平台
- 配音預設台灣音色（曉臻、雲哲、曉雨），逐字稿與字幕一律轉繁體，字幕字型改 Noto Sans CJK TC
- 安裝只用官方來源（nodejs.org、npmjs.org、PyPI），OpenClaw 固定 2026.9.8，預設模型 anthropic/claude-opus-5-5

## 匯入既有的 Threads 熱門話題日報
Google 文件「檔案 → 下載 → 純文字（.txt）」後：
```
python skills/shared/scripts/trend_log.py import ~/Downloads/Threads熱門話題日報.txt
python skills/shared/scripts/trend_log.py stats
```
匯入後，網頁後台「熱門」頁的「Threads 話題」分頁會顯示最近一次 A2 掃描的話題。
