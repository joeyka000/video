// tw-trends：台灣熱門話題（免金鑰）——Google 搜尋趨勢台灣、Google 新聞台灣、PTT 熱門看板／看板最新文章。
//
// GET  /tw-trends?sources=google,news,ptt&limit=20[&topic=科技][&board=Gossiping]
//      → { results: [{ source, label, fetched_at, items: [{ rank, title, url, hot, extra }] }], errors: [...] }
// POST /tw-trends  { "action": "save_a1" }
//      → 抓 Google 搜尋趨勢 TOP 20 存成一場 A1 掃描（trend_scans + trend_terms），分類欄留空給 ai 函式補
//
// 權限：一般呼叫要登入且在 members 名單；排程呼叫帶 x-cron-secret（等於環境變數 CRON_SECRET）。
import { createClient } from "npm:@supabase/supabase-js@2";

const UA =
  "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15";
const CORS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type, x-cron-secret",
  "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
};
const NEWS_TOPICS: Record<string, string> = {
  科技: "TECHNOLOGY", 娛樂: "ENTERTAINMENT", 運動: "SPORTS", 商業: "BUSINESS",
  健康: "HEALTH", 科學: "SCIENCE", 國際: "WORLD", 台灣: "NATION",
};

export interface TrendItem { rank: number; title: string; url: string; hot: string; extra: Record<string, unknown> }
export interface TrendResult { source: string; label: string; fetched_at: string; items: TrendItem[] }

const decode = (s: string) =>
  s.replace(/<!\[CDATA\[([\s\S]*?)\]\]>/g, "$1")
    .replace(/&lt;/g, "<").replace(/&gt;/g, ">").replace(/&quot;/g, '"').replace(/&#39;/g, "'")
    .replace(/&#(\d+);/g, (_, n) => String.fromCodePoint(Number(n))).replace(/&amp;/g, "&").trim();
const tag = (xml: string, name: string) => {
  const m = xml.match(new RegExp(`<${name}[^>]*>([\\s\\S]*?)</${name}>`));
  return m ? decode(m[1]) : "";
};
const tags = (xml: string, name: string) =>
  [...xml.matchAll(new RegExp(`<${name}[^>]*>([\\s\\S]*?)</${name}>`, "g"))].map((m) => m[1]);
const now = () => new Date().toISOString();

async function get(url: string, cookie = ""): Promise<string> {
  const r = await fetch(url, {
    headers: { "User-Agent": UA, "Accept-Language": "zh-TW,zh;q=0.9", ...(cookie ? { Cookie: cookie } : {}) },
  });
  if (!r.ok) throw new Error(`${r.status} ${url}`);
  return await r.text();
}

export async function google(limit: number): Promise<TrendResult> {
  const xml = await get("https://trends.google.com/trending/rss?geo=TW");
  const items = tags(xml, "item").slice(0, limit).map((it, i) => {
    const news = tags(it, "ht:news_item").map((n) => ({
      title: tag(n, "ht:news_item_title"), url: tag(n, "ht:news_item_url"), source: tag(n, "ht:news_item_source"),
    }));
    return {
      rank: i + 1, title: tag(it, "title"), url: news[0]?.url ?? "", hot: tag(it, "ht:approx_traffic"),
      extra: { news: news.slice(0, 3), pub_date: tag(it, "pubDate") },
    };
  });
  return { source: "google", label: "Google 熱搜", fetched_at: now(), items };
}

export async function news(limit: number, topic?: string | null): Promise<TrendResult> {
  const code = topic ? (NEWS_TOPICS[topic] ?? topic.toUpperCase()) : null;
  const url = code
    ? `https://news.google.com/rss/headlines/section/topic/${code}?hl=zh-TW&gl=TW&ceid=TW:zh-Hant`
    : "https://news.google.com/rss?hl=zh-TW&gl=TW&ceid=TW:zh-Hant";
  const xml = await get(url);
  const items = tags(xml, "item").slice(0, limit).map((it, i) => {
    let title = tag(it, "title");
    const src = tag(it, "source");
    if (src && title.endsWith(" - " + src)) title = title.slice(0, -(src.length + 3));
    return { rank: i + 1, title, url: tag(it, "link"), hot: "", extra: { source: src, pub_date: tag(it, "pubDate") } };
  });
  return { source: "news", label: `Google 新聞${topic ? "・" + topic : ""}`, fetched_at: now(), items };
}

export async function ptt(limit: number, board?: string | null): Promise<TrendResult> {
  const strip = (s: string) => decode(s.replace(/<[^>]+>/g, ""));
  if (board) {
    const page = await get(`https://www.ptt.cc/bbs/${encodeURIComponent(board)}/index.html`, "over18=1");
    const rows: TrendItem[] = [];
    for (const m of page.matchAll(/<div class="r-ent">[\s\S]*?<div class="nrec">([\s\S]*?)<\/div>[\s\S]*?<div class="title">\s*(?:<a href="([^"]+)">([\s\S]*?)<\/a>|[\s\S]*?)\s*<\/div>/g)) {
      if (!m[2]) continue; // 已刪除的文章
      rows.push({ rank: 0, title: strip(m[3]), url: "https://www.ptt.cc" + m[2], hot: strip(m[1]), extra: {} });
    }
    const items = rows.reverse().slice(0, limit).map((r, i) => ({ ...r, rank: i + 1 }));
    return { source: "ptt", label: `PTT ${board} 板`, fetched_at: now(), items };
  }
  const page = await get("https://www.ptt.cc/bbs/hotboards.html");
  const items: TrendItem[] = [];
  for (const m of page.matchAll(/<a class="board" href="\/bbs\/([^/]+)\/index.html">[\s\S]*?<div class="board-name">([\s\S]*?)<\/div>[\s\S]*?<div class="board-nuser">[\s\S]*?<span[^>]*>([\s\S]*?)<\/span>[\s\S]*?<div class="board-class">([\s\S]*?)<\/div>[\s\S]*?<div class="board-title">([\s\S]*?)<\/div>/g)) {
    if (items.length >= limit) break;
    items.push({
      rank: items.length + 1, title: strip(m[5]), url: `https://www.ptt.cc/bbs/${m[1]}/index.html`, hot: strip(m[3]),
      extra: { board: strip(m[2]), class: strip(m[4]) },
    });
  }
  return { source: "ptt", label: "PTT 熱門看板", fetched_at: now(), items };
}

/** 「2萬+」「1,385」「5,000+」→ 整數 */
export function toNum(s: string | null | undefined): number | null {
  if (!s) return null;
  const m = s.replace(/[,+則\s]/g, "").match(/^([\d.]+)([萬千億]?)/);
  if (!m) return null;
  const unit: Record<string, number> = { 萬: 10000, 千: 1000, 億: 100000000 };
  return Math.round(parseFloat(m[1]) * (unit[m[2]] ?? 1));
}

function taipeiNow() {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Taipei", year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hour12: false,
  }).formatToParts(new Date());
  const p = Object.fromEntries(parts.map((x) => [x.type, x.value]));
  return { date: `${p.year}-${p.month}-${p.day}`, time: `${p.hour === "24" ? "00" : p.hour}:${p.minute}` };
}

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { ...CORS, "Content-Type": "application/json" } });

async function handler(req: Request): Promise<Response> {
  if (req.method === "OPTIONS") return new Response("ok", { headers: CORS });
  const url = Deno.env.get("SUPABASE_URL")!;
  const cronOk = !!Deno.env.get("CRON_SECRET") && req.headers.get("x-cron-secret") === Deno.env.get("CRON_SECRET");
  if (!cronOk) {
    const userClient = createClient(url, Deno.env.get("SUPABASE_ANON_KEY")!, {
      global: { headers: { Authorization: req.headers.get("Authorization") ?? "" } },
    });
    const { data: member } = await userClient.rpc("is_member");
    if (member !== true) return json({ error: "請先登入，並確認你的 Email 在成員名單裡" }, 401);
  }

  if (req.method === "POST") {
    const body = await req.json().catch(() => ({}));
    if (body.action !== "save_a1") return json({ error: "未知的 action" }, 400);
    const g = await google(20);
    const admin = createClient(url, Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!);
    const { date, time } = taipeiNow();
    const { data: scan, error } = await admin.from("trend_scans")
      .upsert({ kind: "A1", scan_date: date, scan_time: time, source: cronOk ? "auto" : "manual" }, { onConflict: "kind,scan_date,scan_time" })
      .select("id").single();
    if (error) return json({ error: error.message }, 500);
    await admin.from("trend_terms").delete().eq("scan_id", scan.id);
    const rows = g.items.map((it) => ({ scan_id: scan.id, rank: it.rank, term: it.title, traffic: it.hot, traffic_n: toNum(it.hot), category: "" }));
    const ins = await admin.from("trend_terms").insert(rows);
    if (ins.error) return json({ error: ins.error.message }, 500);
    // 排程呼叫時順便請 ai 函式補分類（需要已部署 ai 函式並設定 ANTHROPIC_API_KEY）
    let classified: unknown = null;
    if (body.classify) {
      const r = await fetch(`${url}/functions/v1/ai`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${Deno.env.get("SUPABASE_ANON_KEY")}`,
          "x-cron-secret": Deno.env.get("CRON_SECRET") ?? "",
        },
        body: JSON.stringify({ action: "classify_terms", scan_id: scan.id }),
      });
      classified = await r.json().catch(() => null);
    }
    return json({ scan_id: scan.id, date, time, count: rows.length, classified });
  }

  const q = new URL(req.url).searchParams;
  const sources = (q.get("sources") ?? "google,news,ptt").split(",").map((s) => s.trim()).filter(Boolean);
  const limit = Math.min(Math.max(Number(q.get("limit") ?? 20), 1), 50);
  const jobs: Record<string, () => Promise<TrendResult>> = {
    google: () => google(limit),
    news: () => news(limit, q.get("topic")),
    ptt: () => ptt(limit, q.get("board")),
  };
  const valid = sources.filter((s) => jobs[s]);
  const settled = await Promise.allSettled(valid.map((s) => jobs[s]()));
  const results: TrendResult[] = [];
  const errors: { source: string; error: string }[] = [];
  settled.forEach((r, i) => {
    if (r.status === "fulfilled") results.push(r.value);
    else errors.push({ source: valid[i], error: String(r.reason) });
  });
  return json({ results, errors }, results.length ? 200 : 502);
}

if (typeof Deno !== "undefined" && typeof Deno.serve === "function") Deno.serve(handler);
