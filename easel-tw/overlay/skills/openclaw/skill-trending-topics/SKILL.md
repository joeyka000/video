---
name: skill-trending-topics
description: >-
  抓台灣即時熱門話題（Google 搜尋趨勢台灣、Google 新聞台灣、PTT 熱門看板、Threads 話題日報），篩選與創作者賽道相關的熱點，
  輸出二創選題建議。當使用者說「今天有什麼熱搜」「熱點」「最近大家在聊什麼」「追熱點」「蹭熱點」「二創選題」「熱搜榜」時使用。
  和 skill-news-intelligence 的區別：本 SKILL 抓即時熱門做快速二創選題；news-intelligence 做日級深度產業資訊。
  要做固定格式的 Threads 熱門話題日報時用 tw-threads-daily。
layer: discover
---

# 熱點發現（台灣版）

> 抓台灣即時熱門資料，篩選與創作者賽道相關的熱點，輸出可操作的二創選題。

## 輸入（都可省略）
- **來源**：Google 熱搜／Google 新聞／PTT／Threads（預設：Google 熱搜＋Threads＋PTT）
- **賽道**：例「科技 3C」「美妝」「職場」「親子」（有人設檔時自動讀取）
- **目的**：看熱搜／找二創選題／追熱點寫內容

## 輸出
```markdown
# 熱點速報
日期：{date}
來源：{sources}

## 🔥 熱門 Top 10
| # | 來源 | 話題 | 熱度 | 與你的相關度 |

## 🎯 推薦二創選題（3–5 個）
### 選題 1：{標題}
- 熱點來源：{來源＋原話題}
- 二創角度：{怎麼切}
- 建議形式：{IG 輪播／Reels／Threads 串文／短影音}
- 時效：{要多快發}

## 📊 趨勢觀察
{跨來源重疊的話題、上升中的話題、可預期的後續}
```

## 執行步驟
1. **抓資料**（免金鑰）
   - `python skills/shared/scripts/tw_trends.py all --json --limit 20`：Google 搜尋趨勢台灣（含搜尋量與相關新聞）、Google 新聞台灣頭條、PTT 熱門看板
   - 指定主題新聞：`tw_trends.py news --topic 科技|娛樂|運動|商業|健康 --json`
   - PTT 某板最新：`tw_trends.py ptt --board Lifeismoney --json`（八卦板 Gossiping、股票 Stock、美妝 MakeUp、3C PC_Shopping…）
   - Threads：`python skills/shared/scripts/trend_log.py top --days 2` 看最近日報的話題；要即時掃描就照 `tw-threads-daily` 的 A2 流程
   - Dcard 擋伺服器 IP，不要直接抓；需要時請使用者貼上 Dcard 熱門文章連結或截圖
   - 全部失敗時如實說明，請使用者貼上熱搜截圖或文字
2. **整理**：每個來源取標題與熱度，去重（同一事件在多個來源出現，合併成一筆並標註來源）
3. **賽道比對**：有人設檔或指定賽道時，標註相關度（高／中／低）；沒有就列全部 Top 10
4. **二創分析**：挑 3–5 個有二創價值的選題——有討論空間、與創作者定位相符、時效還夠、能做出差異化（不是搬運）
5. **趨勢觀察**：同時出現在 Google 熱搜與 Threads／PTT 的是大事件；連續幾場日報都在的是長尾話題（`trend_log.py search`）
6. **輸出**：照上面的格式，全文繁體中文（台灣用語）

## 人設檔
- 有人設檔：讀 `identity.md`（賽道與定位）、`style.md`（內容形式）、`platforms.md`（活躍平台）、`audience.md`（受眾在意什麼）
- 沒有人設檔：列全部 Top 10，二創建議給通用角度，最後附一句「指定賽道或建立人設檔，可以篩得更準」

## 注意
- 涉及災害、事故、政治、社會案件的話題，二創要謹慎：不消費受害者、不帶未經證實的說法
- 熱搜詞是搜尋量，不代表正面或負面，下結論前先看相關新聞
