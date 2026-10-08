---
name: tw-threads-daily
description: >-
  Threads 熱門話題日報（台灣）：每天固定時段掃描 Google 搜尋趨勢台灣 TOP 20（A1）與 Threads 趨勢話題、
  各話題熱門貼文、For You 動態牆精選（A2），用固定格式寫成日報並存進封存檔，可查歷史、找反覆上榜的話題、
  挑互動最高的貼文拆解。當使用者說「做今天的 Threads 日報」「掃一下 Threads 熱門」「A1／A2 掃描」
  「最近 Threads 在聊什麼」「把日報匯入」「查某個話題之前有沒有紅過」時使用。
layer: discover
---

# Threads 熱門話題日報（台灣）

一天三次（建議 10:00／15:00／21:00），每次兩段：**A1** Google 搜尋趨勢、**A2** Threads 趨勢與熱門貼文。
資料存在 `outputs/_trends/archive.jsonl`（每行一場掃描），日報文字照下面的格式輸出，可以直接貼回 Google 文件。

## 工具
- `python skills/shared/scripts/tw_trends.py google --json --limit 20`：A1 的資料來源（Google 搜尋趨勢台灣 RSS，免金鑰）
- `python skills/shared/scripts/trend_log.py ...`：封存檔
  - `add-a1 <tw_trends 的 JSON 檔>`：存一場 A1（分類欄由你補，見下）
  - `import <檔案>`：匯入既有日報（Google 文件「檔案 → 下載 → 純文字 .txt」或 .docx）
  - `stats`、`search <關鍵字>`、`top --days 7`、`hot-posts --days 3 --by 分享`、`render --date YYYY-MM-DD`
- A2 需要已登入 Threads 的瀏覽器：用你可用的瀏覽器工具開 `https://www.threads.net/search` 看「趨勢」清單與各話題的貼文；
  沒有瀏覽器工具或沒登入時，請使用者打開 Threads 搜尋頁截圖或貼上，再整理成格式

## A1 流程
1. `tw_trends.py google --json --limit 20 > /tmp/a1.json`，`trend_log.py add-a1 /tmp/a1.json`
2. 為每個熱搜詞補「分類」（財經／ETF、娛樂／藝人、政治／人物、體育／棒球、生活、社會、科技、時事／國際…），寫回封存檔
   （直接改 archive.jsonl 那一行的 `category`，或重新輸出日報時補上）
3. 輸出格式：
```
─────────────────────────────
2026/10/08 ─ 09:00 掃描（A1 熱搜）
─────────────────────────────
Google Trends 台灣熱搜 TOP 20
1. 關鍵字（2萬+）─ 分類／子分類
...
── A1 掃描結束 ──
```

## A2 流程
1. Threads 搜尋頁的趨勢清單：依貼文量排序，取前 10–15 個話題深挖（話題標題、貼文量「N 萬則」、一句摘要）
2. 每個話題挑 3 則有代表性的貼文（至少一則高互動、一則一般網友觀點）：作者帳號、內容摘要、讚／回覆／轉發／分享、連結；
   回覆數多的貼文附 1–2 則熱門留言（作者、要點、讚數）
3. For You 動態牆精選 5 則（不在趨勢清單、但互動高的貼文）
4. 數據摘要：趨勢話題數、擷取貼文總數、最高讚數與最高回覆的貼文
5. 方法備註：這次用什麼方式擷取、哪些話題沒抓到、為什麼
6. 輸出格式：
```
[2026/10/06] [15:00] A2 Threads 掃描
▌趨勢話題
話題1｜話題標題｜2萬則
摘要：一句話說清楚發生什麼事
  [1] @帳號
      內容：貼文重點（精簡改寫，不整段照抄）
      互動：讚4.9萬｜回覆1,385｜轉發896｜分享4,736
      連結：https://www.threads.net/@帳號/post/...
      留言：
        - 帳號：留言重點（讚5,699）
▌For You 動態牆精選
  [1] @帳號 ...
▌數據摘要
趨勢話題數：N 個
擷取貼文總數：N 則
最高讚數：@帳號（N 讚）
最高回覆：@帳號（N 回覆）
▌方法備註
...
── A2 掃描結束 ──
```
7. 把整段 A2 文字存成檔案，`trend_log.py import 那個檔案` 寫進封存檔

## 給創作者的用法
- 「這週什麼話題一直紅」→ `trend_log.py top --days 7`
- 「某品牌／某人之前有沒有上過熱搜」→ `trend_log.py search 關鍵字`
- 「拆幾篇爆文給我參考」→ `trend_log.py hot-posts --days 3 --by 分享`，再用 `skill-hook-generator` 拆開頭鉤子、用 `skill-trend-rider` 想二創切角
- 每週日歸檔：`trend_log.py render --date ...` 把一週的掃描輸出成週報

## 規範
- 內容一律繁體中文（台灣用語）
- 貼文內容精簡改寫、標明出處連結，不整段複製；不要收集與話題無關的個人資料
- 掃描頻率維持一天三次左右，不要高頻抓取；遵守 Threads 使用條款
- 封存檔含他人帳號與貼文，只存本機 `outputs/`，不要上傳或提交到公開的程式碼庫
