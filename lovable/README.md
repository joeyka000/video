# 內容工作台（台灣版）— Lovable 精簡版

Easel 台灣版裡最常用的網頁功能，改成可以部署在 Lovable（Lovable Cloud）的版本：熱點雷達、Threads 熱門話題日報、AI 改寫成各平台版本、選題庫、內容日曆。
不含 AI 代理技能、影片、字幕、配音、自動發文（那些留在 `easel-tw/` 或 video-lab）。

## 現在的 Lovable 專案要注意
Lovable 新開的專案是 TanStack Start（伺服器函式、Drizzle 遷移），不是 Vite＋Supabase Edge Functions。下面的 `supabase/functions/` 與 `dist/` 指令是給舊架構用的；在 TanStack Start 專案裡，同樣的功能已改寫成伺服器函式（`src/lib/*.server.ts`＋`src/lib/workbench.functions.ts`、排程入口 `src/routes/api/cron/save-a1.ts`），直接 push 到 Lovable 專案的 GitHub repo 即可同步，不用貼指令。

## 怎麼用（舊架構）
照 `dist/` 的順序，一步一個檔案，整段貼進 Lovable 對話框（`dist/` 已把程式碼嵌進指令）：

| 步驟 | 檔案 | 內容 |
|---|---|---|
| 00 | `dist/00-開專案.txt` | 骨架、登入、版面、配色 |
| 01 | `dist/01-資料庫.txt` | 資料表、成員權限（先把 `YOUR_EMAIL@example.com` 換成你的 Email） |
| 02 | `dist/02-熱點雷達.txt` | `tw-trends` 雲端函式＋熱點頁 |
| 03 | `dist/03-Threads日報.txt` | 日報解析與匯入、紀錄、排行、爆文、搜尋 |
| 04 | `dist/04-發布中心.txt` | `ai` 雲端函式（Claude）＋發布中心；先在 Secrets 加 `ANTHROPIC_API_KEY` |
| 05 | `dist/05-選題庫與日曆.txt` | 選題看板、內容日曆＋台灣節日 |
| 06 | `dist/06-工作台與設定.txt` | 首頁、成員管理、AI 用量 |
| 07 | `dist/07-自動A1掃描-選用.txt` | 每天自動存 Google 熱搜並補分類（選用，需 `CRON_SECRET`） |
| 08 | `dist/08-驗收.txt` | 讓 Lovable 逐項自我檢查 |

## 原始碼
- `supabase/migrations/001_schema.sql`：資料表與 RLS（只有 members 名單能讀寫），`002_cron_optional.sql`：排程
- `supabase/functions/tw-trends/index.ts`：Google 搜尋趨勢台灣、Google 新聞台灣、PTT（免金鑰）；存 A1 掃描
- `supabase/functions/ai/index.ts`：Claude 改寫成 8 個台灣平台版本、熱搜補分類；記錄費用、每月上限、安全誤擋自動備援
- `src/lib/trendLog.ts`：日報解析／輸出／批次匯入（與 `easel-tw` 的 `trend_log.py` 結果一致：169 場、2,362 詞、542 話題、1,759 貼文）
- 改了原始碼或指令後：`python3 build_prompts.py` 重新產生 `dist/`；說明頁：`page/make_page.py`

## 已驗證
- SQL 用 Postgres 解析器（pglast）檢查語法
- 兩個雲端函式與 `trendLog.ts` 以 TypeScript strict 模式、對 @anthropic-ai/sdk 0.132.1 與 @supabase/supabase-js 2.117 型別檢查通過
- `tw-trends` 的抓取函式實際連線測試（Google 熱搜、新聞科技主題、PTT 熱門看板與 Lifeismoney 板）
- `trendLog.ts` 對整份日報解析，結果與 Python 版相同
- 沒有實際呼叫 Claude（會花錢）；在 Lovable 上的部署要照指令跑過才算數
