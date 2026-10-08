#!/usr/bin/env python3
"""trend_log.py — 「Threads 熱門話題日報」格式的匯入、查詢與新增（Easel 台灣版）。

日報格式（每天三次掃描，新資料追加在文件底部）：
  A1：`2026/10/08 ─ 09:00 掃描（A1 熱搜）` → Google Trends 台灣熱搜 TOP 20（`1. 關鍵字（2萬+）─ 分類`）
  A2：`[2026/10/06] [15:00] A2 Threads 掃描` → ▌趨勢話題（`話題1｜標題｜2萬則`、摘要、每題前 3 則貼文：
      作者、內容、互動 讚/回覆/轉發/分享、連結、熱門留言）、▌For You 動態牆精選、▌數據摘要、▌方法備註

子命令（-h 看參數）：
  import  <檔案>       匯入日報（Google 文件「下載 → 純文字 .txt」或 Markdown 皆可，也吃 .docx）→ 封存檔
  stats                封存檔統計（掃描次數、日期範圍、話題數、貼文數）
  search  <關鍵字>     在熱搜詞、話題標題、摘要、貼文內容裡找（依日期新→舊）
  top                  近 N 天反覆上榜的熱搜詞與話題（--days 7）
  hot-posts            近 N 天互動最高的貼文（--days 3 --by 讚|回覆|分享）
  render  --date D     把某天的掃描輸出成日報原格式（貼回 Google 文件用）
  add-a1               把 tw_trends.py google --json 的結果存成一筆 A1 掃描（分類欄留給代理補）

封存檔預設 outputs/_trends/archive.jsonl（每行一筆掃描）；--archive 可改。資料含他人帳號與貼文，只存本機，不要提交到公開 repo。
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sys
import zipfile
from collections import Counter, defaultdict
from pathlib import Path

DEFAULT_ARCHIVE = os.environ.get('EASEL_TREND_ARCHIVE', 'outputs/_trends/archive.jsonl')

RE_DATE = re.compile(r'(\d{4})/(\d{1,2})/(\d{1,2})')
RE_TIME = re.compile(r'(\d{1,2}:\d{2})')
RE_A1_ITEM = re.compile(r'^(\d{1,2})[.、]\s*(.+?)[（(]([^（）()]*)[）)]\s*[─—-]+\s*(.+)$')
RE_TOPIC = re.compile(r'^話題\s*(\d+)\s*[｜|]\s*(.+?)\s*[｜|]\s*(.+?)\s*$')
RE_POST = re.compile(r'^\[(\d+)\]\s*@(\S+)')
RE_COMMENT = re.compile(r'^[-－・]\s*(?:(.+?)：)?(.+?)(?:（讚\s*([^）]*)）)?$')
NUM_UNITS = {'萬': 10000, '千': 1000, '億': 100000000}


def clean(text: str) -> str:
    """去掉 Markdown 粗體與跳脫字元（Google 文件匯出的 .md 會有 **、\\[、\\_）。"""
    text = text.replace('**', '')
    text = re.sub(r'\\([\[\]_.*~\-#()!+`>|])', r'\1', text)
    return text


def read_any(path: str) -> str:
    p = Path(path)
    if p.suffix.lower() == '.docx':
        with zipfile.ZipFile(p) as z:
            xml = z.read('word/document.xml').decode('utf-8')
        xml = re.sub(r'</w:p>', '\n', xml)
        return re.sub(r'<[^>]+>', '', xml)
    if p.suffix.lower() == '.json':  # 連接器匯出的 {"fileContent": ...}
        d = json.load(open(p, encoding='utf-8'))
        return d.get('fileContent', '')
    return p.read_text(encoding='utf-8', errors='replace')


def to_num(s: str | None) -> int | None:
    """『2.3萬』『1,385』『9萬+』『數千』→ 整數；讀不出來回 None。"""
    if not s:
        return None
    s = s.replace(',', '').replace('+', '').replace('則', '').replace(' ', '').strip()
    m = re.match(r'^([\d.]+)\s*([萬千億]?)', s)
    if not m:
        return None
    try:
        return int(float(m.group(1)) * NUM_UNITS.get(m.group(2), 1))
    except ValueError:
        return None


def parse_engage(s: str) -> dict:
    out = {}
    for key in ('讚', '回覆', '轉發', '分享'):
        m = re.search(key + r'\s*([\d.,]+\s*[萬千億]?)', s)
        out[key] = to_num(m.group(1)) if m else None
    return out


def header_kind(ln: str) -> str | None:
    """掃描標題的寫法不太固定（全形／半形括號、[日期 …] [時間 …]、缺日期或時間），用關鍵字判斷。"""
    if '掃描' not in ln or '結束' in ln or len(ln) > 60:
        return None
    if 'A2' in ln and 'Threads' in ln:
        return 'A2'
    if 'A1' in ln and RE_DATE.search(ln):
        return 'A1'
    return None


def parse(text: str) -> list[dict]:
    lines = [ln.strip() for ln in clean(text).split('\n')]
    scans: list[dict] = []
    cur: dict | None = None
    section = None
    topic = post = None
    for ln in lines:
        if not ln or set(ln) <= set('─—- '):
            continue
        kind = header_kind(ln)
        if kind:
            md, mt = RE_DATE.search(ln), RE_TIME.search(ln)
            date = f'{int(md.group(1)):04d}-{int(md.group(2)):02d}-{int(md.group(3)):02d}' if md else (scans[-1]['date'] if scans else '')
            cur = {'type': kind, 'date': date, 'time': mt.group(1).zfill(5) if mt else '', 'items': [], 'topics': [], 'for_you': [],
                   'summary': {}, 'notes': []}
            if not md:
                cur['notes'].append('（標題沒有日期，沿用上一場的日期）')
            if not mt:
                cur['notes'].append('（標題沒有時間）')
            scans.append(cur)
            section, topic, post = ('a1' if kind == 'A1' else None), None, None
            continue
        if cur is None:
            continue
        if '掃描結束' in ln:
            cur, section, topic, post = None, None, None, None
            continue
        if cur['type'] == 'A1':
            m = RE_A1_ITEM.match(ln)
            if m:
                cur['items'].append({'rank': int(m.group(1)), 'term': m.group(2).strip(), 'traffic': m.group(3).strip(),
                                     'traffic_n': to_num(m.group(3)), 'category': m.group(4).strip()})
            continue
        # A2
        if ln.startswith('▌'):
            name = ln[1:]
            section = 'topics' if '趨勢話題' in name else 'for_you' if 'For You' in name or 'For' in name else \
                'summary' if '數據摘要' in name else 'notes' if '備註' in name else 'other'
            topic = post = None
            continue
        m = RE_TOPIC.match(ln)
        if m:
            topic = {'no': int(m.group(1)), 'title': m.group(2).strip(), 'volume': m.group(3).strip(),
                     'volume_n': to_num(m.group(3)), 'summary': '', 'posts': []}
            cur['topics'].append(topic)
            section, post = 'topics', None
            continue
        if ln.startswith('摘要：') and topic is not None:
            topic['summary'] = ln[3:].strip()
            continue
        m = RE_POST.match(ln)
        if m:
            post = {'author': m.group(2).rstrip('｜'), 'content': '', 'engage': {}, 'url': '', 'comments': []}
            if section == 'for_you':
                cur['for_you'].append(post)
            elif topic is not None:
                topic['posts'].append(post)
            continue
        if post is not None:
            if ln.startswith('內容：'):
                post['content'] = ln[3:].strip()
                continue
            if ln.startswith('互動：'):
                post['engage'] = parse_engage(ln)
                continue
            if ln.startswith('連結：'):
                post['url'] = ln[3:].strip()
                continue
            if ln.startswith('留言：'):
                continue
            mc = RE_COMMENT.match(ln)
            if mc and ln[:1] in '-－・':
                post['comments'].append({'author': (mc.group(1) or '').strip(), 'text': mc.group(2).strip(), 'likes': to_num(mc.group(3))})
                continue
        if section == 'summary' and '：' in ln:
            k, v = ln.split('：', 1)
            cur['summary'][k.strip()] = v.strip()
        elif section == 'notes' or ln.startswith('備註'):
            cur['notes'].append(ln)
    return scans


def load(archive: str) -> list[dict]:
    if not os.path.exists(archive):
        return []
    return [json.loads(x) for x in open(archive, encoding='utf-8') if x.strip()]


def save(archive: str, scans: list[dict]) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(archive)), exist_ok=True)
    scans = sorted(scans, key=lambda s: (s['date'], s['time'], s['type']))
    with open(archive, 'w', encoding='utf-8') as f:
        for s in scans:
            f.write(json.dumps(s, ensure_ascii=False) + '\n')


def key(s: dict) -> tuple:
    return (s['type'], s['date'], s['time'])


def cmd_import(a) -> None:
    new = parse(read_any(a.file))
    old = {key(s): s for s in load(a.archive)}
    added = sum(1 for s in new if key(s) not in old)
    for s in new:
        old[key(s)] = s  # 同一場掃描以新匯入為準
    save(a.archive, list(old.values()))
    a1 = [s for s in new if s['type'] == 'A1']
    a2 = [s for s in new if s['type'] == 'A2']
    print(f'解析：A1 {len(a1)} 場（{sum(len(s["items"]) for s in a1)} 個熱搜詞）、A2 {len(a2)} 場'
          f'（{sum(len(s["topics"]) for s in a2)} 個話題、{sum(len(t["posts"]) for s in a2 for t in s["topics"]) + sum(len(s["for_you"]) for s in a2)} 則貼文）')
    print(f'新增 {added} 場，封存檔共 {len(old)} 場 → {a.archive}')
    empty = [f'{s["type"]} {s["date"]} {s["time"]}' for s in new if not (s['items'] or s['topics'] or s['for_you'])]
    if empty:
        print(f'⚠ {len(empty)} 場沒解析到內容（格式可能不同）：{empty[:5]}')


def in_days(s: dict, days: int | None) -> bool:
    if not days:
        return True
    return dt.date.fromisoformat(s['date']) >= dt.date.today() - dt.timedelta(days=days)


def cmd_stats(a) -> None:
    scans = load(a.archive)
    if not scans:
        sys.exit('封存檔是空的，先 import')
    by = Counter(s['type'] for s in scans)
    print(f'{scans[0]["date"]} → {scans[-1]["date"]}；A1 {by["A1"]} 場、A2 {by["A2"]} 場')
    print(f'熱搜詞 {sum(len(s["items"]) for s in scans)} 筆；話題 {sum(len(s["topics"]) for s in scans)} 個；'
          f'貼文 {sum(len(t["posts"]) for s in scans for t in s["topics"]) + sum(len(s["for_you"]) for s in scans)} 則')


def cmd_search(a) -> None:
    q = a.query.lower()
    hits = []
    for s in load(a.archive):
        for it in s['items']:
            if q in it['term'].lower():
                hits.append((s['date'], s['time'], 'A1', f'#{it["rank"]} {it["term"]}（{it["traffic"]}）─ {it["category"]}'))
        for t in s['topics']:
            blob = ' '.join([t['title'], t['summary']] + [p['content'] for p in t['posts']]).lower()
            if q in blob:
                hits.append((s['date'], s['time'], 'A2', f'{t["title"]}｜{t["volume"]}｜{t["summary"]}'))
    for h in sorted(hits, reverse=True)[:a.limit]:
        print(f'{h[0]} {h[1]} {h[2]}  {h[3]}')
    print(f'共 {len(hits)} 筆' + (f'（顯示前 {a.limit}）' if len(hits) > a.limit else ''))


def norm_term(s: str) -> str:
    return re.sub(r'\s+', '', s.lower())


def cmd_top(a) -> None:
    terms, topics, cats = Counter(), Counter(), Counter()
    label = {}
    for s in load(a.archive):
        if not in_days(s, a.days):
            continue
        for it in s['items']:
            k = norm_term(it['term'])
            terms[k] += 1
            label[k] = it['term']
            cats[it['category'].split('／')[0].split('/')[0]] += 1
        for t in s['topics']:
            topics[t['title']] += 1
    print(f'== 近 {a.days} 天反覆上榜的熱搜詞')
    for k, n in terms.most_common(a.limit):
        print(f'{n:>3} 次  {label[k]}')
    print(f'\n== 熱搜分類分布')
    for c, n in cats.most_common(10):
        print(f'{n:>4}  {c}')
    print(f'\n== 話題（出現次數）')
    for k, n in topics.most_common(a.limit):
        print(f'{n:>3} 次  {k}')


def cmd_hot_posts(a) -> None:
    rows = []
    for s in load(a.archive):
        if not in_days(s, a.days):
            continue
        for t in s['topics']:
            for p in t['posts']:
                rows.append((p['engage'].get(a.by) or 0, s['date'], t['title'], p))
        for p in s['for_you']:
            rows.append((p['engage'].get(a.by) or 0, s['date'], 'For You', p))
    seen = set()
    n = 0
    for v, d, title, p in sorted(rows, key=lambda r: -r[0]):
        if p['url'] in seen:
            continue
        seen.add(p['url'])
        e = p['engage']
        print(f'{d} ｜{title}｜@{p["author"]}  讚{e.get("讚")} 回覆{e.get("回覆")} 分享{e.get("分享")}\n    {p["content"][:80]}\n    {p["url"]}')
        n += 1
        if n >= a.limit:
            break


def fmt_n(v) -> str:
    return '—' if v is None else f'{v:,}'


def render(s: dict) -> str:
    out = []
    if s['type'] == 'A1':
        out += ['─' * 29, f'{s["date"].replace("-", "/")} ─ {s["time"]} 掃描（A1 熱搜）', '─' * 29, '', 'Google Trends 台灣熱搜 TOP 20', '']
        out += [f'{it["rank"]}. {it["term"]}（{it["traffic"]}）─ {it["category"] or "待分類"}' for it in s['items']]
        out += ['', '── A1 掃描結束 ──']
        return '\n'.join(out)
    out += [f'[{s["date"].replace("-", "/")}] [{s["time"]}] A2 Threads 掃描', '', '▌趨勢話題', '']
    for t in s['topics']:
        out += [f'話題{t["no"]}｜{t["title"]}｜{t["volume"]}', f'摘要：{t["summary"]}', '']
        for i, p in enumerate(t['posts'], 1):
            e = p['engage']
            out += [f'  [{i}] @{p["author"]}', f'      內容：{p["content"]}',
                    f'      互動：讚{fmt_n(e.get("讚"))}｜回覆{fmt_n(e.get("回覆"))}｜轉發{fmt_n(e.get("轉發"))}｜分享{fmt_n(e.get("分享"))}',
                    f'      連結：{p["url"]}']
            if p['comments']:
                out.append('      留言：')
                out += [f'        - {c["author"] + "：" if c["author"] else ""}{c["text"]}' + (f'（讚{fmt_n(c["likes"])}）' if c['likes'] else '')
                        for c in p['comments']]
            out.append('')
    if s['for_you']:
        out += ['▌For You 動態牆精選']
        for i, p in enumerate(s['for_you'], 1):
            e = p['engage']
            out += [f'  [{i}] @{p["author"]}', f'      內容：{p["content"]}',
                    f'      互動：讚{fmt_n(e.get("讚"))}｜回覆{fmt_n(e.get("回覆"))}｜轉發{fmt_n(e.get("轉發"))}｜分享{fmt_n(e.get("分享"))}',
                    f'      連結：{p["url"]}']
    if s['summary']:
        out += ['▌數據摘要'] + [f'{k}：{v}' for k, v in s['summary'].items()]
    out += s['notes'] + ['── A2 掃描結束 ──']
    return '\n'.join(out)


def cmd_render(a) -> None:
    for s in load(a.archive):
        if s['date'] == a.date and (not a.type or s['type'] == a.type):
            print(render(s) + '\n')


def cmd_add_a1(a) -> None:
    d = json.load(open(a.file, encoding='utf-8')) if a.file != '-' else json.load(sys.stdin)
    if 'results' in d:
        d = next(r for r in d['results'] if 'Google' in r['source'] and '趨勢' in r['source'])
    now = dt.datetime.now()
    scan = {'type': 'A1', 'date': now.date().isoformat(), 'time': now.strftime('%H:%M'), 'topics': [], 'for_you': [], 'summary': {}, 'notes': [],
            'items': [{'rank': it['rank'], 'term': it['title'], 'traffic': it['hot'], 'traffic_n': to_num(it['hot']), 'category': ''}
                      for it in d['items'][:20]]}
    scans = {key(s): s for s in load(a.archive)}
    scans[key(scan)] = scan
    save(a.archive, list(scans.values()))
    print(render(scan))


def main() -> None:
    ap = argparse.ArgumentParser(description='Threads 熱門話題日報：匯入、查詢、輸出')
    ap.add_argument('--archive', default=DEFAULT_ARCHIVE)
    sp = ap.add_subparsers(dest='cmd', required=True)
    p = sp.add_parser('import'); p.add_argument('file')
    sp.add_parser('stats')
    p = sp.add_parser('search'); p.add_argument('query'); p.add_argument('--limit', type=int, default=30)
    p = sp.add_parser('top'); p.add_argument('--days', type=int, default=7); p.add_argument('--limit', type=int, default=20)
    p = sp.add_parser('hot-posts'); p.add_argument('--days', type=int, default=3); p.add_argument('--by', default='讚', choices=['讚', '回覆', '轉發', '分享'])
    p.add_argument('--limit', type=int, default=10)
    p = sp.add_parser('render'); p.add_argument('--date', required=True); p.add_argument('--type', choices=['A1', 'A2'])
    p = sp.add_parser('add-a1'); p.add_argument('file', help='tw_trends.py google --json 的輸出檔，- 代表 stdin')
    a = ap.parse_args()
    {'import': cmd_import, 'stats': cmd_stats, 'search': cmd_search, 'top': cmd_top, 'hot-posts': cmd_hot_posts,
     'render': cmd_render, 'add-a1': cmd_add_a1}[a.cmd](a)


if __name__ == '__main__':
    main()
