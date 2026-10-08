# Easel 台灣版

把 [ZJU-REAL/Easel](https://github.com/ZJU-REAL/easel)（社群內容 AI 工作台，Apache-2.0）自動轉成台灣版：繁體中文介面、台灣平台、台灣熱門話題、台灣配音，網頁後台在自己的電腦上跑。

這個資料夾只放「轉換工具」與台灣版新增的檔案；上游程式在安裝時從 GitHub 下載（固定版本，見 `UPSTREAM`），不重新散布原作者的檔案。

## 需要
- macOS 或 Linux（Windows 請用 WSL）
- git、Python 3.10 以上（macOS：`xcode-select --install`、`brew install python`）
- Anthropic API 金鑰：在 [console.anthropic.com](https://console.anthropic.com/) 建立，**只在安裝程式詢問時輸入到自己電腦的終端機**，不要貼到任何對話或文件裡；建議在 Console 設定每月花費上限
- 約 2 GB 磁碟（Node、OpenClaw、Python 套件、Chromium）

## 安裝
```bash
git clone https://github.com/joeyka000/video.git
cd video/easel-tw
bash install.sh            # 裝到 ~/easel-tw；加 --no-showcase 可省約 430 MB 示範影片
```
安裝程式會問模型服務：選 **1）Anthropic API**，輸入金鑰（不會顯示）；模型名直接按 Enter 用 `anthropic/claude-opus-5-5`，想省一半費用輸入 `anthropic/claude-sonnet-5-5`。

## 使用
```bash
~/easel-tw/start.sh        # 啟動閘道器與網頁後台，自動開 http://localhost:7860
```
- 工作台：今日熱點（Google 熱搜、Threads 話題）、選題庫、排程、最近成品
- 熱點雷達：Google 搜尋趨勢台灣、Threads 話題、PTT 熱門看板、Google 新聞
- 發布中心：一段文字 → AI 改寫成 IG／Threads／FB／YouTube／TikTok／LINE／Dcard／PTT 版本 → 複製到平台手動發布
- 對話：直接說「做今天的 Threads 日報」「看看最近熱搜挑三個選題」「把這篇改成 IG 輪播文案」

## 匯入「Threads 熱門話題日報」
Google 文件「檔案 → 下載 → 純文字（.txt）」，然後：
```bash
cd ~/easel-tw
.venv/bin/python skills/shared/scripts/trend_log.py import ~/Downloads/Threads熱門話題日報.txt
.venv/bin/python skills/shared/scripts/trend_log.py stats          # 看匯入了幾場掃描
.venv/bin/python skills/shared/scripts/trend_log.py top --days 7   # 這週反覆上榜的話題
```
匯入後熱點雷達的「Threads 話題」顯示最近一次 A2 掃描。之後每天的掃描交給技能 `tw-threads-daily`（格式和日報相同）。
日報資料存在 `~/easel-tw/outputs/_trends/`，含他人帳號與貼文，只留在自己電腦。

## 更新
再跑一次 `bash install.sh`：會建新版、搬回 `.env`、`outputs/`、人設與登入資料，舊版留一份備份資料夾。

## 費用（粗估）
Easel 每次對話會帶入人設、技能清單與工具結果，一個完整任務（例如做一份選題＋文案）大約 10–20 輪：
- Claude Opus 5.5（輸入 $4、輸出 $20／百萬 token）：約 US$0.5–2／任務
- Claude Sonnet 5.5（輸入 $2、輸出 $10／百萬 token）：約一半
實際依內容長短而定；以 Anthropic Console 的用量頁為準。AI 生圖、生影片、AI 音樂、聲音複製要另外接付費服務，代理會先問你再花。

## 台灣版改了什麼
見 `overlay/TAIWAN.md`（安裝後也在 `~/easel-tw/TAIWAN.md`）。簡述：
- 介面、技能、代理提示詞轉繁體中文（台灣用語）
- 平台換成台灣常用平台；拿掉小紅書、抖音、快手、視頻號、知乎、B 站、公眾號的技能與自動發文
- 熱門話題：`tw_trends.py`（Google 趨勢台灣、Google 新聞、PTT）、`trend_log.py`＋`tw-threads-daily`（Threads 日報）
- 台灣節慶檔期、台灣平台規格、台灣配音（曉臻／雲哲／曉雨）、逐字稿與字幕轉繁體
- 只用官方套件來源，OpenClaw 固定 2026.9.8

## 已知限制
- 沒有自動登入發文：Meta、YouTube、TikTok 的自動發文需要商業帳號與官方 API 審核，目前由你手動上傳
- 帳號數據不自動抓：把 IG 洞察報告截圖或 Meta Business Suite 匯出檔丟給它分析
- Dcard 擋程式抓取，Threads 即時掃描需要已登入的瀏覽器
- 少數技能說明仍提到中國平台（上游原文轉繁），代理已被規定改用台灣平台思路
- 雲端環境只測過轉換、網頁後台與熱門資料；完整安裝與對話要在你的電腦上跑過才算數

## 開發
- `build.py`：取得上游 → 刪技能 → OpenCC s2twp＋用語修正 → `patches.py` → `overlay/`
- `python3 build.py --check`：在暫存目錄跑一遍，確認每個修補點都還對得上（上游更新後先跑這個；對不上會直接報錯）
- 換上游版本：改 `UPSTREAM` 的 sha，跑 `--check`，修 `patches.py`
