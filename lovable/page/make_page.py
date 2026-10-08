import json, sys
steps = json.load(open(sys.argv[1]))
meta = {
 '00-開專案': dict(title='開專案：骨架、登入、版面', what='建立新專案時直接貼上。做出側欄七個頁面、Email 登入、成員檢查、配色與深色模式。', before=['在 Lovable 建立新專案，若它問要不要開啟 Lovable Cloud，選開啟。']),
 '01-資料庫': dict(title='資料庫與權限', what='建立 9 張資料表、成員名單與權限（只有名單上的 Email 能讀寫）、本月 AI 花費檢視表。', before=['上方先填你的 Email：複製時會自動換進 SQL 最後一行，成為第一位管理員。'], email=True),
 '02-熱點雷達': dict(title='熱點雷達', what='雲端函式 tw-trends（Google 熱搜台灣、Google 新聞、PTT，免金鑰）＋熱點頁，可收進選題庫或拿去改寫。'),
 '03-Threads日報': dict(title='Threads 日報', what='匯入你的 Google 文件日報（已用整份實測：169 場、1,759 則貼文），查歷史、排行、爆文，可複製回日報格式。', after=['完成後到 Google 文件「檔案 → 下載 → 純文字（.txt）」，在 Threads 日報頁匯入。']),
 '04-發布中心': dict(title='發布中心（AI 改寫）', what='雲端函式 ai（Claude）：一段內容改寫成 IG、Threads、FB、YouTube、TikTok、LINE、Dcard、PTT 版本，記錄每次費用，超過月上限自動停。', before=['先在 Lovable Cloud → Secrets 新增 ANTHROPIC_API_KEY，值貼你的 Anthropic 金鑰。只貼在 Secrets 欄位，不要貼進 Lovable 的對話框。'], warn=True),
 '05-選題庫與日曆': dict(title='選題庫與內容日曆', what='看板式選題庫、月曆排程，日曆標出 2026–2027 台灣節日與檔期。'),
 '06-工作台與設定': dict(title='工作台首頁與設定', what='首頁數字卡、今日熱點、這週一直紅、近期排程；設定頁管理成員、看 AI 用量。'),
 '07-自動A1掃描-選用': dict(title='每天自動存 Google 熱搜（選用）', what='每天 10:00、15:00、21:00 自動存一場 A1 並用 AI 補分類，取代手動掃 Google 熱搜這一段。', before=['先在 Secrets 新增 CRON_SECRET（自己想一串長亂碼）。若 Lovable Cloud 不支援排程，跳過這步，改用熱點雷達的「立即存一場 A1」按鈕。'], optional=True),
 '08-驗收': dict(title='驗收', what='讓 Lovable 逐項自我檢查：權限、繁體用語、各頁資料、金鑰不外洩、手機版、深色模式。'),
}
data = []
for s in steps:
    m = meta[s['id']]
    data.append({**m, 'id': s['id'], 'no': s['id'][:2], 'text': s['text'], 'chars': s['chars']})
payload = json.dumps(data, ensure_ascii=False).replace('</', '<\\/')
html = open(sys.argv[2]).read().replace('__DATA__', payload)
open(sys.argv[3], 'w').write(html)
print(len(html))
