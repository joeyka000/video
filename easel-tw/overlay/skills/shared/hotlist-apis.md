# 台灣熱門話題資料來源（台灣版）

免金鑰。優先用腳本，輸出是乾淨的 JSON，不必自己解析網頁。

| 來源 | 指令 | 內容 |
|---|---|---|
| Google 搜尋趨勢（台灣） | `python skills/shared/scripts/tw_trends.py google --json` | 熱搜詞、搜尋量（如 2萬+）、相關新聞 3 則 |
| Google 新聞（台灣） | `tw_trends.py news [--topic 科技] --json` | 頭條或指定主題（科技、娛樂、運動、商業、健康、科學、國際、台灣） |
| PTT 熱門看板 | `tw_trends.py ptt --json` | 看板人氣排行 |
| PTT 某看板最新文章 | `tw_trends.py ptt --board Gossiping --json` | 標題、推文數（已處理 18 歲確認） |
| 一次全抓 | `tw_trends.py all --json` | 上面三個合併，單一來源失敗不影響其他 |
| Threads 話題（日報封存） | `python skills/shared/scripts/trend_log.py top --days 2` | 最近日報的趨勢話題；即時掃描見 `tw-threads-daily` |

RSS 原始網址（需要時才直接 web_fetch）：
- `https://trends.google.com/trending/rss?geo=TW`
- `https://news.google.com/rss?hl=zh-TW&gl=TW&ceid=TW:zh-Hant`
- `https://www.ptt.cc/bbs/hotboards.html`

不可用：Dcard 公開 API 會擋伺服器 IP（403）；YouTube 發燒影片頁面是動態載入，用 YouTube Data API 才穩定（需要金鑰）。
