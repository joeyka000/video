"""Easel 台灣版修補：在 s2twp 轉換「之後」套用（比對的是已轉成繁體的文字）。

每一條修補都要求原文存在，找不到就報錯停下：上游改版時寧可建置失敗，也不要悄悄漏改。
"""
from __future__ import annotations

import json
import re
from pathlib import Path

LANG_RULE = ('一律使用繁體中文（台灣用語）：回覆、文案、字幕、配音稿、檔名說明都一樣。技能文件若寫的是簡體或中國用語，'
             '產出時改成台灣說法（影片、帳號、貼文、按讚、留言、網路、行銷、短影音、直式）。')

TW_PLATFORMS_LINE = ('- **發出去**：Instagram（貼文／輪播／Reels／限動）、Threads、Facebook 粉專、YouTube（含 Shorts）、TikTok、'
                     'LINE 官方帳號、Dcard、PTT 的發文準備——平台規格適配、文案與 hashtag、封面、排程、發布前檢查；'
                     '台灣版不做自動登入發文，產出可直接上傳的成品與文案，由創作者本人發布')

AGENTS_TW = '''
## 台灣版規則（優先於本檔其他段落）

- 語言：{lang}
- 平台：Instagram、Threads、Facebook、YouTube／Shorts、TikTok、LINE 官方帳號、Dcard、PTT、部落格。不要建議或使用小紅書、抖音、快手、視頻號、知乎、B 站、微博、公眾號的流程；技能文件裡提到它們時，換成對應的台灣平台思路（例：小紅書圖文 → IG 輪播、抖音 → Reels／TikTok／Shorts）。
- 發布：沒有自動登入與發文。產出成品（圖、影片、文案、hashtag、封面、發文時間建議）存到 `outputs/`，由創作者手動上傳；發布中心可以複製各平台版本。
- 熱門話題：`python skills/shared/scripts/tw_trends.py all --json`（Google 搜尋趨勢台灣、Google 新聞台灣、PTT 熱門看板）；Threads 話題與歷史紀錄用 `tw-threads-daily` 技能與 `skills/shared/scripts/trend_log.py`。
- 配音：`tts.py speak ... --engine edge --voice zh-TW-HsiaoChenNeural`（女）／`zh-TW-YunJheNeural`（男）／`zh-TW-HsiaoYuNeural`（女）。字幕與逐字稿一律繁體。
- 節慶檔期：`skill-event-calendar/references/events-taiwan.md`。
- 花錢：會呼叫付費 API 的步驟（AI 生圖、生影片、AI 音樂、聲音複製、雲端配音）先告訴創作者要做什麼、用哪個服務、大概多少錢，等他同意這一次再做。
- 帳號數據與留言：台灣版不自動抓。請創作者提供 IG 洞察報告截圖、Meta Business Suite 匯出檔或留言內容，再用 `skill-content-postmortem`、`skill-comment-insights` 分析。
'''.format(lang=LANG_RULE)

TW_ACCOUNT_LINES = '''- 帳號、粉絲、作品、最近發布 → 台灣版不自動登入抓資料，請創作者提供 IG 洞察報告截圖、Meta Business Suite 匯出檔或後台數字。
- 貼文留言 → 請創作者貼上或匯出，`skill-comment-insights` 分析。'''

TW_LOGIN_RUNNERS = '''LOGIN_RUNNERS: dict[str, dict] = {
    # 台灣版：不做自動登入發文，帳號頁只列出平台與說明。發布中心產出各平台版本，由創作者手動上傳。
    "instagram": {"name": "Instagram", "backend": "unsupported", "note": "台灣版暫不支援自動登入發布：請用發布中心產出的文案與成品手動上傳"},
    "threads": {"name": "Threads", "backend": "unsupported", "note": "台灣版暫不支援自動登入發布"},
    "facebook": {"name": "Facebook 粉專", "backend": "unsupported", "note": "可用 Meta Business Suite 排程發布"},
    "youtube": {"name": "YouTube", "backend": "unsupported", "note": "請在 YouTube Studio 上傳"},
    "tiktok": {"name": "TikTok", "backend": "unsupported", "note": "台灣版暫不支援自動登入發布"},
    "line": {"name": "LINE 官方帳號", "backend": "unsupported", "note": "請在 LINE Official Account Manager 群發"},
}
'''

TW_TRENDS = '''TREND_SOURCES: dict[str, tuple[str | None, str | None]] = {
    # 台灣版：資料由 skills/shared/scripts/tw_trends.py 與 trend_log.py 取得（見 _fetch_platform）
    "google": (None, None),
    "news": (None, None),
    "ptt": (None, None),
    "threads": (None, None),
}
TREND_LABELS = {
    "google": "Google 熱搜",
    "news": "Google 新聞",
    "ptt": "PTT 熱門看板",
    "threads": "Threads 話題",
}
'''

TW_FETCH = '''def _fetch_platform(pf: str) -> list[dict]:
    """台灣版：Google 搜尋趨勢（台灣）、Google 新聞台灣、PTT 熱門看板、Threads 話題（日報封存檔最新一場）。"""
    sys.path.insert(0, str(SHARED_SCRIPTS))
    try:
        if pf == "threads":
            import trend_log  # noqa: E402
            archive = os.environ.get("EASEL_TREND_ARCHIVE") or str(OUTPUTS_DIR / "_trends" / "archive.jsonl")
            scans = [s for s in trend_log.load(archive) if s.get("type") == "A2" and s.get("topics")]
            if not scans:
                return []
            last = scans[-1]
            return [{"title": t["title"], "hot": t.get("volume", ""),
                     "url": (t["posts"][0]["url"] if t.get("posts") else "")} for t in last["topics"]]
        import tw_trends  # noqa: E402
        fn = {"google": lambda: tw_trends.google(30), "news": lambda: tw_trends.news(30, None),
              "ptt": lambda: tw_trends.ptt(30, None)}.get(pf)
        if not fn:
            return []
        return [{"title": it["title"], "hot": str(it.get("hot") or ""), "url": it.get("url") or ""} for it in fn()["items"]]
    except Exception:
        return []
'''

TW_PUBLISH = """// 台灣版平台。字數是平台上限或建議值（hint 會說明）；台灣版沒有一鍵發布，產出各平台版本後手動上傳。
const PLATFORMS: { key: string; label: string; titleLimit?: number; bodyLimit: number; hint: string }[] = [
  { key: 'instagram', label: 'Instagram', bodyLimit: 2200, hint: '貼文說明上限 2,200 字、hashtag 最多 30 個；前兩行是鉤子（會被折疊），需附圖片或影片' },
  { key: 'threads', label: 'Threads', bodyLimit: 500, hint: '單則上限 500 字；口語、短句、丟問題引留言，長內容拆成串文' },
  { key: 'facebook', label: 'Facebook', bodyLimit: 5000, hint: '粉專貼文；前 2–3 行決定會不會被展開，連結放留言或文末' },
  { key: 'youtube', label: 'YouTube', titleLimit: 100, bodyLimit: 5000, hint: '標題上限 100 字、說明上限 5,000 字；Shorts 用直式影片' },
  { key: 'tiktok', label: 'TikTok', bodyLimit: 2200, hint: '說明精簡、前幾個字是鉤子，搭配 3–5 個 hashtag' },
  { key: 'line', label: 'LINE 官方帳號', bodyLimit: 500, hint: '群發訊息建議 300 字內、一則一個重點、附明確行動（連結／優惠碼）' },
  { key: 'dcard', label: 'Dcard', titleLimit: 50, bodyLimit: 20000, hint: '先看該板板規；分享口吻、少廣告感，業配要揭露' },
  { key: 'ptt', label: 'PTT', titleLimit: 40, bodyLimit: 20000, hint: '標題要加分類【心得】【情報】…；遵守各板板規，商業文多數板禁止' },
];
const LABEL2KEY = Object.fromEntries(PLATFORMS.map((p) => [p.label, p.key]));

// 台灣版沒有自動發布的平台
const PUBLISHABLE = new Set<string>([]);
const MEDIA_REQUIRED = new Set<string>([]);
const VIDEO_ONLY = new Set<string>([]);
"""

TW_PLATFORM_NAMES = "['Instagram', 'Threads', 'Facebook', 'YouTube', 'TikTok', 'LINE', 'Dcard', 'PTT', '部落格']"

TW_TREND_TABS = """const ALL_PLATFORMS: { key: string; label: string }[] = [
  { key: 'google', label: 'Google 熱搜' },
  { key: 'threads', label: 'Threads 話題' },
  { key: 'ptt', label: 'PTT 熱門看板' },
  { key: 'news', label: 'Google 新聞' },
];"""


TW_SPECS = """## 台灣平台（台灣版優先使用）

| 平台 | 長度 | 語氣 | 格式 | 標籤 |
|------|------|------|------|------|
| Instagram 貼文／輪播 | 說明 ≤ 2,200 字；輪播最多 20 張（4:5 直式最吃版面） | 生活化、有畫面、前兩行是鉤子（會被折疊） | 圖文、輪播、Reels、限動 | 5–15 個 hashtag 放文末（上限 30） |
| Instagram Reels | 直式 9:16；前 3 秒決定滑走與否 | 快節奏、有字幕（很多人靜音看） | 短影音＋說明 | 3–5 個 |
| Threads | 單則 ≤ 500 字；長內容拆串文 | 口語、像跟朋友聊天、丟問題引留言 | 純文字、圖、短串 | 最多 1 個主題標籤 |
| Facebook 粉專 | 長度不限，前 2–3 行決定展開 | 親切、資訊完整、適合 30 歲以上受眾 | 圖文、影片、連結 | 少量或不用 |
| YouTube／Shorts | 標題 ≤ 100 字、說明 ≤ 5,000 字 | 標題含搜尋關鍵字、資訊密度高 | 長片／直式 Shorts | 說明欄 3–5 個 |
| TikTok | 說明精簡 | 真實、好笑、跟風 | 短影音 | 3–5 個 |
| LINE 官方帳號 | 群發建議 ≤ 300 字 | 直接、一則一重點、有行動 | 文字、圖文訊息、優惠券 | 不用 |
| Dcard | 依看板 | 分享口吻、少廣告感；業配須揭露 | 長文＋圖 | 依板規 |
| PTT | 依看板 | 標題加分類【心得】【情報】；鄉民語感、忌業配 | 純文字 | 不用 |

全文繁體中文（台灣用語）：影片、帳號、貼文、留言、按讚、限時動態、連結放留言或個人檔案。
"""


class Patcher:
    def __init__(self, root: Path):
        self.root = root
        self.done: list[str] = []

    def text(self, rel: str) -> str:
        return (self.root / rel).read_text(encoding='utf-8')

    def write(self, rel: str, s: str) -> None:
        (self.root / rel).write_text(s, encoding='utf-8')

    def sub(self, rel: str, old: str, new: str, count: int = 1, label: str = '') -> None:
        s = self.text(rel)
        n = s.count(old)
        if n == 0 or (count and n < count):
            raise SystemExit(f'修補失敗：{rel} 找不到（{label or old[:60]!r}）')
        s = s.replace(old, new) if count == 0 else s.replace(old, new, count)
        self.write(rel, s)
        self.done.append(f'{rel}: {label or old[:40]}')

    def resub(self, rel: str, pattern: str, new: str, label: str, flags=re.S) -> None:
        s = self.text(rel)
        s2, n = re.subn(pattern, new, s, flags=flags)
        if n == 0:
            raise SystemExit(f'修補失敗：{rel} 比對不到 {label}')
        self.write(rel, s2)
        self.done.append(f'{rel}: {label}（{n} 處）')


def fix_bing(root: Path) -> None:
    """s2twp 把連接詞「并」轉成「併」的錯：除了合併／併購／兼併／吞併／併發／併入／併案，其餘改「並」。"""
    for p in root.rglob('*'):
        if not p.is_file() or p.suffix not in {'.md', '.py', '.ts', '.tsx', '.html', '.sh', '.json5', '.yaml', '.yml'}:
            continue
        if any(x in p.parts for x in ('node_modules', '.git', 'dist')):
            continue
        s = p.read_text(encoding='utf-8', errors='ignore')
        if '併' not in s:
            continue
        s2 = re.sub(r'(?<![合兼吞歸])併(?![購發入案吞])', '並', s)
        if s2 != s:
            p.write_text(s2, encoding='utf-8')


def vocab_extra(root: Path) -> None:
    for p in root.rglob('*'):
        if not p.is_file() or p.suffix not in {'.md', '.py', '.ts', '.tsx', '.html', '.json5'}:
            continue
        if any(x in p.parts for x in ('node_modules', '.git', 'dist')):
            continue
        s = p.read_text(encoding='utf-8', errors='ignore')
        s2 = s.replace('分割槽', '分區').replace('豎版', '直式').replace('豎屏', '直式').replace('橫屏', '橫式') \
            .replace('營銷', '行銷').replace('落地頁', '到達頁')
        if s2 != s:
            p.write_text(s2, encoding='utf-8')


def prune_capability_menu(P: Patcher, removed: set[str]) -> None:
    rel = 'web/frontend/src/lib/capabilityMenu.ts'
    s = P.text(rel)
    head, sep, body = s.partition('= {')
    if not sep:
        raise SystemExit(f'修補失敗：{rel} 格式變了')
    body = '{' + body
    end = body.rstrip().rstrip(';')
    menu = json.loads(end)
    n = 0
    for tab in menu['tabs']:
        for g in tab['groups']:
            keep = [it for it in g['items'] if it.get('skill') not in removed]
            n += len(g['items']) - len(keep)
            g['items'] = keep
        tab['groups'] = [g for g in tab['groups'] if g['items']]
    P.write(rel, head + '= ' + json.dumps(menu, ensure_ascii=False, indent=1) + ';\n')
    P.done.append(f'{rel}: 移除 {n} 個中國平臺技能入口')


def prune_display_names(P: Patcher, removed: set[str]) -> None:
    rel = 'web/frontend/src/lib/skillDisplayNames.ts'
    lines = P.text(rel).split('\n')
    keep = [ln for ln in lines if not any(re.match(rf"\s*'{re.escape(k)}':", ln) for k in removed)]
    P.write(rel, '\n'.join(keep))
    P.done.append(f'{rel}: 移除 {len(lines) - len(keep)} 個顯示名稱')


def apply(root: Path, removed: list[str] | None = None) -> list[str]:
    P = Patcher(root)
    removed_set = set(removed or [])
    vocab_extra(root)
    fix_bing(root)

    # ── 代理的語言與平台 ──
    P.sub('openclaw/workspace/SOUL.md', '- 中文為主', '- ' + LANG_RULE, label='語言規則')
    P.resub('openclaw/workspace/SOUL.md', r'- \*\*發出去\*\*：[^\n]*', TW_PLATFORMS_LINE, '平台清單')
    P.sub('openclaw/workspace/SOUL.md', '小紅書卡', 'IG 輪播圖卡', label='小紅書卡 → IG 輪播')
    P.sub('openclaw/workspace/SOUL.md', '整套小紅書筆記', '整套 IG 輪播貼文', label='小紅書筆記 → IG 輪播')
    P.resub('openclaw/workspace/AGENTS.md', r'- 帳號、粉絲、作品、最近發布、身份 → `skill-my-account`[^\n]*\n- 貼文評論 → [^\n]*',
            TW_ACCOUNT_LINES, '帳號／留言改成台灣版做法')
    s = P.text('openclaw/workspace/AGENTS.md')
    first_h2 = s.find('\n## ')
    P.write('openclaw/workspace/AGENTS.md', s[:first_h2] + '\n' + AGENTS_TW + s[first_h2:])
    P.done.append('openclaw/workspace/AGENTS.md: 加入〈台灣版規則〉')
    P.resub('easel/persona.py', r'(TURN_REMINDER = \(\n)', r'\1    "〔台灣版〕一律用繁體中文（台灣用語）回覆與產出；平台以 IG／Threads／FB／YouTube／TikTok／LINE／Dcard／PTT 為準。"\n',
            '每輪提醒加語言規則')

    # ── 後端：平台、熱門話題、模型 ──
    P.resub('web/app.py', r'LOGIN_RUNNERS: dict\[str, dict\] = \{.*?\n\}\n', TW_LOGIN_RUNNERS, '帳號平台換成台灣平台')
    P.resub('web/app.py', r'TREND_SOURCES: dict\[str, tuple\[str, str \| None\]\] = \{.*?\n\}\nTREND_LABELS = \{.*?\n\}\n', TW_TRENDS, '熱門來源換成台灣')
    P.resub('web/app.py', r'def _fetch_platform\(pf: str\) -> list\[dict\]:\n.*?\n    return \[\]\n', TW_FETCH, '熱門抓取改用 tw_trends')
    P.sub('web/app.py', 'async def api_trends(platforms: str = "weibo,douyin,zhihu"', 'async def api_trends(platforms: str = "google,threads,ptt"',
          label='熱門預設來源')
    P.sub('web/app.py', 'or "claude-sonnet-4-6"', 'or "claude-opus-5-5"', count=0, label='預設模型（後端）')

    # ── 前端 ──
    fe = 'web/frontend'
    P.resub(f'{fe}/src/components/PublishPage.tsx',
            r'// 平台列表須與後端 LOGIN_RUNNERS 對齊.*?const VIDEO_ONLY = new Set\(\[[^\]]*\]\);\n', TW_PUBLISH, '發布中心換成台灣平台')
    P.sub(f'{fe}/src/components/PublishPage.tsx', '一次編輯 → AI 一鍵改寫成各平台版本 → 預檢 → 附媒體 → 一鍵真發布。',
          '一次編輯 → AI 一鍵改寫成各平台版本 → 預檢 → 複製文案、下載成品，到各平台手動發布。', label='發布中心說明')
    P.resub(f'{fe}/src/components/TrendsPage.tsx', r'const ALL_PLATFORMS: \{ key: string; label: string \}\[\] = \[.*?\];', TW_TREND_TABS, '熱門頁來源')
    P.sub(f'{fe}/src/components/TrendsPage.tsx', "useState<string[]>(['weibo', 'douyin', 'zhihu'])", "useState<string[]>(['google', 'threads', 'ptt'])",
          label='熱門頁預設')
    P.sub(f'{fe}/src/components/DashboardPage.tsx', "fetchTrends('weibo,douyin', 6)", "fetchTrends('google,threads', 6)", label='首頁熱門')
    P.resub(f'{fe}/src/components/OnboardingWizard.tsx', r"const PLATFORMS = \[[^\]]*\];", f'const PLATFORMS = {TW_PLATFORM_NAMES};', '新手引導平台')
    P.resub(f'{fe}/src/components/CalendarPage.tsx', r"const PLATFORMS = \[[^\]]*\];", f'const PLATFORMS = {TW_PLATFORM_NAMES};', '日曆平台')
    P.resub(f'{fe}/src/components/ChatPage.tsx', r"prompt: '看看現在微博和抖音有什麼熱搜，[^']*'",
            "prompt: '看看現在台灣 Google 熱搜、Threads 和 PTT 在聊什麼，挑幾個適合我做二創的選題'", '對話預設：熱點')
    P.resub(f'{fe}/src/components/ChatPage.tsx', r"title: '寫小紅書文案', prompt: '[^']*'",
            "title: '寫 IG 貼文', prompt: '幫我寫一則 IG 貼文文案（含前兩行鉤子與 hashtag），主題先問我'", '對話預設：文案')
    for rel in (f'{fe}/src/components/ProfilePage.tsx', f'{fe}/src/components/TrendsPage.tsx'):
        P.sub(rel, "'zh-CN'", "'zh-TW'", count=0, label='日期數字格式 zh-TW')
    P.resub(f'{fe}/index.html', r'<html lang="[^"]*"', '<html lang="zh-Hant-TW"', 'html lang')
    P.sub(f'{fe}/index.html', 'Noto+Serif+SC', 'Noto+Serif+TC', count=0, label='Google Fonts 換 TC')
    P.resub(f'{fe}/index.html', r'<title>[^<]*</title>', '<title>Easel 台灣版</title>', '網頁標題')
    css = f'{fe}/src/styles/index.css'
    P.sub(css, "'Noto Sans SC'", "'PingFang TC', 'Noto Sans TC'", count=0, label='字型 Noto Sans TC')
    P.sub(css, "'Noto Serif SC'", "'Noto Serif TC'", count=0, label='字型 Noto Serif TC')
    P.sub(css, "'Microsoft YaHei'", "'Microsoft JhengHei'", count=0, label='Windows 字型 正黑體')
    pub = f'{fe}/src/components/PublishPage.tsx'
    P.sub(pub, '小紅書可用 emoji 和 #話題標籤，按平台習慣自然分行即可。',
          'IG／Threads 可用 emoji 與 #hashtag（IG 放文末、最多 30 個），按平台習慣自然分行；全文繁體中文（台灣用語）。', label='AI 改寫提示改台灣平台')
    P.sub(pub, '（逗號分隔，如「AI,職場,乾貨」；小紅書會用 # 聯想真正繫結話題）', '（逗號分隔，如「AI,職場,乾貨」；IG／Threads 會轉成 #hashtag）', label='標籤說明')
    P.sub(pub, '（小紅書/抖音/快手/微信影片號/B站必需，從內容庫選；抖音、影片號、B站須為影片）', '（從內容庫選；IG、Reels、TikTok、YouTube 需要圖片或影片，發布時手動上傳）', label='附件說明')
    P.sub(pub, "所選平台無一鍵發布（B站走終端 biliup）", '台灣版沒有一鍵發布：請用各平台卡片的「複製」，到平台手動發布', label='發布鈕提示')
    P.sub(pub, '一鍵發布僅對「已登入 + 媒體齊全」的平台生效。', '台灣版不自動發文：複製各平台版本後到平台發布。', label='發布頁說明')
    P.sub(pub, "所選平台暫不支援一鍵發布（B站請用「複製」或終端 biliup）", '台灣版沒有一鍵發布：請用「複製」後到平台手動發布', label='發布提示')
    acc = f'{fe}/src/components/AccountsPage.tsx'
    P.resub(acc, r'用手機 App 掃描 QR Code登入，登入態本地持久化，之後發布免登。<br />\s*⚠️ [^\n]*',
            '台灣版不做自動登入與發文：這裡列出常用平台與建議的發布方式。內容在發布中心改寫成各平台版本後，複製到平台手動發布。',
            '帳號頁說明')
    names = f'{fe}/src/lib/skillDisplayNames.ts'
    P.resub(names, r"(export const [A-Z_a-z]+[^=]*= \{\n)", "\\1  'tw-threads-daily': 'Threads 日報',\n", 'Threads 日報顯示名稱')
    spec = 'skills/openclaw/skill-content-repurposing/references/platform-specs.md'
    P.sub(spec, '## 平台適配表', TW_SPECS + '\n## 平台適配表（通用，台灣版以上表為準）', label='台灣平台規格')
    prune_capability_menu(P, removed_set)
    prune_display_names(P, removed_set)

    # ── 配音、字幕、逐字稿 ──
    P.sub('skills/shared/scripts/tts.py', 'DEFAULT_VOICE = "zh-CN-XiaoxiaoNeural"', 'DEFAULT_VOICE = "zh-TW-HsiaoChenNeural"', label='預設配音台灣女聲')
    P.sub('skills/shared/scripts/multivoice.py', '"zh-TW-HsiaoChenNeural", "zh-TW-YunJheNeural",',
          '"zh-TW-HsiaoChenNeural", "zh-TW-YunJheNeural", "zh-TW-HsiaoYuNeural",', label='台灣音色清單')
    P.sub('skills/shared/scripts/multivoice.py', 'DEFAULT_NARRATOR_VOICE = "zh-CN-YunyangNeural"', 'DEFAULT_NARRATOR_VOICE = "zh-TW-YunJheNeural"',
          label='旁白台灣男聲')
    P.sub('skills/shared/scripts/subtitle_ops.py', '"Noto Sans CJK SC"', '"Noto Sans CJK TC"', count=0, label='字幕字型 TC')
    P.sub('skills/shared/scripts/asr.py',
          '        language=language,\n        vad_filter=True,',
          '        language=language,\n        vad_filter=True,\n'
          '        initial_prompt=os.environ.get("EASEL_ASR_PROMPT", "以下是台灣繁體中文的逐字稿，包含標點符號。"),',
          label='逐字稿提示詞（繁體）')
    P.sub('skills/shared/scripts/asr.py', '        text = (seg.text or "").strip()\n',
          '        text = _to_tw((seg.text or "").strip())\n', label='逐字稿轉繁')
    P.sub('skills/shared/scripts/asr.py', '\ndef cmd_transcribe(a) -> int:',
          '\ndef _to_tw(text: str) -> str:\n'
          '    """台灣版：辨識結果一律轉成繁體（臺灣用語）；沒裝 opencc 就原樣回傳。"""\n'
          '    try:\n        import opencc\n    except ImportError:\n        return text\n'
          '    global _CC\n    try:\n        _CC\n    except NameError:\n        _CC = opencc.OpenCC("s2twp")\n'
          '    return _CC.convert(text).replace("臺", "台")\n\n\ndef cmd_transcribe(a) -> int:', label='OpenCC 轉換函式')
    s = P.text('skills/shared/scripts/asr.py')
    if not re.search(r'^import os$', s, re.M):
        P.write('skills/shared/scripts/asr.py', s.replace('\nimport sys\n', '\nimport os\nimport sys\n', 1))

    # ── 節慶檔期 ──
    P.sub('skills/openclaw/skill-event-calendar/SKILL.md', '讀取 [events-china.md](references/events-china.md) 獲取中國全年節日和電商節點資料',
          '讀取 [events-taiwan.md](references/events-taiwan.md) 獲取台灣全年節日、電商與檔期節點（台灣版預設；對中國市場才看 events-china.md）',
          label='節慶改用台灣')
    P.sub('skills/openclaw/skill-event-calendar/SKILL.md', '參照 references/events-china.md', '參照 references/events-taiwan.md', label='節慶參照')

    # ── 安裝：官方來源、預設模型、固定 OpenClaw 版本 ──
    sh = 'setup.sh'
    P.sub(sh, 'NODE_MIRROR_DEFAULT="https://mirrors.aliyun.com/nodejs-release"', 'NODE_MIRROR_DEFAULT="https://nodejs.org/dist"', label='Node 官方來源')
    P.resub(sh, r'NPM_REGISTRY="https://registry\.npmmirror\.com"', 'NPM_REGISTRY="https://registry.npmjs.org"', 'npm 不回落中國映像')
    P.resub(sh, r'PIP_INDEX_ARGS=\(-i "https://pypi\.tuna\.tsinghua\.edu\.cn/simple"\)', 'PIP_INDEX_ARGS=()', 'pip 不回落清華映像')
    P.sub(sh, 'npm install -g openclaw@latest', 'npm install -g openclaw@${EASEL_OPENCLAW_VERSION:-2026.9.8}', label='固定 OpenClaw 版本')
    P.sub(sh, 'anthropic/claude-sonnet-4-6', 'anthropic/claude-opus-5-5', count=0, label='預設模型（安裝精靈）')
    P.sub('.env.example', 'CLAUDE_MODEL=anthropic/claude-sonnet-4-6', 'CLAUDE_MODEL=anthropic/claude-opus-5-5', label='預設模型（.env）')
    P.sub('pyproject.toml', '"markdown>=3.5,<4",', '"markdown>=3.5,<4",\n    "opencc>=1.1,<2",           # 台灣版：逐字稿、字幕轉繁體（s2twp）', label='依賴加 opencc')
    return P.done
