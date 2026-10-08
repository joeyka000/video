#!/usr/bin/env python3
"""tw_trends.py — 台灣熱門話題（免金鑰、純標準庫）。Easel 台灣版新增，取代中國平臺熱搜。

子命令（-h 看參數）：
    google     Google 搜尋趨勢（台灣，每日熱門關鍵字＋搜尋量＋相關新聞）
    news       Google 新聞台灣版頭條（可加 --topic 科技/娛樂/運動/商業/健康）
    ptt        PTT 熱門看板（看板名、人氣、分類）；--board 看某板最新文章標題與推文數
    all        以上三個一起抓，合併成一份 JSON
共同參數：--limit N（每個來源最多幾筆）、--json（輸出 JSON，預設是給人看的表）

輸出 JSON 結構：{"source": "...", "fetched_at": "...", "items": [{"rank", "title", "url", "hot", "extra"}]}
Dcard 的公開 API 擋伺服器 IP（403），不在這裡；要看 Dcard 熱門請用瀏覽器技能或手動貼連結。
"""
from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET

UA = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15'
NEWS_TOPICS = {  # Google 新聞台灣版的主題代碼
    '科技': 'TECHNOLOGY', '娛樂': 'ENTERTAINMENT', '運動': 'SPORTS', '商業': 'BUSINESS',
    '健康': 'HEALTH', '科學': 'SCIENCE', '國際': 'WORLD', '台灣': 'NATION',
}


def get(url: str, cookie: str = '') -> str:
    req = urllib.request.Request(url, headers={'User-Agent': UA, 'Accept-Language': 'zh-TW,zh;q=0.9', **({'Cookie': cookie} if cookie else {})})
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read().decode('utf-8', 'replace')


def wrap(source: str, items: list[dict]) -> dict:
    return {'source': source, 'fetched_at': dt.datetime.now().isoformat(timespec='seconds'), 'items': items}


def google(limit: int) -> dict:
    root = ET.fromstring(get('https://trends.google.com/trending/rss?geo=TW'))
    ns = {'ht': 'https://trends.google.com/trending/rss'}
    items = []
    for i, it in enumerate(root.iter('item')):
        if i >= limit:
            break
        news = [{'title': html.unescape(n.findtext('ht:news_item_title', '', ns)), 'url': n.findtext('ht:news_item_url', '', ns),
                 'source': n.findtext('ht:news_item_source', '', ns)} for n in it.findall('ht:news_item', ns)]
        items.append({'rank': i + 1, 'title': it.findtext('title', ''), 'url': news[0]['url'] if news else '',
                      'hot': it.findtext('ht:approx_traffic', '', ns), 'extra': {'news': news[:3], 'pub_date': it.findtext('pubDate', '')}})
    return wrap('Google 搜尋趨勢（台灣）', items)


def news(limit: int, topic: str | None) -> dict:
    if topic:
        code = NEWS_TOPICS.get(topic, topic.upper())
        url = f'https://news.google.com/rss/headlines/section/topic/{code}?hl=zh-TW&gl=TW&ceid=TW:zh-Hant'
    else:
        url = 'https://news.google.com/rss?hl=zh-TW&gl=TW&ceid=TW:zh-Hant'
    root = ET.fromstring(get(url))
    items = []
    for i, it in enumerate(root.iter('item')):
        if i >= limit:
            break
        title = it.findtext('title', '')
        src = it.findtext('source', '')
        if src and title.endswith(' - ' + src):
            title = title[:-len(src) - 3]
        items.append({'rank': i + 1, 'title': title, 'url': it.findtext('link', ''), 'hot': '', 'extra': {'source': src, 'pub_date': it.findtext('pubDate', '')}})
    return wrap('Google 新聞（台灣' + (f'・{topic}' if topic else '') + '）', items)


def ptt(limit: int, board: str | None) -> dict:
    if board:
        page = get(f'https://www.ptt.cc/bbs/{board}/index.html', cookie='over18=1')
        items = []
        for m in re.finditer(r'<div class="r-ent">.*?<div class="nrec">(.*?)</div>.*?<div class="title">\s*(?:<a href="([^"]+)">(.*?)</a>|(.*?))\s*</div>', page, re.S):
            nrec = re.sub('<[^>]+>', '', m.group(1)).strip()
            if not m.group(2):
                continue  # 已刪除的文章
            items.append({'title': html.unescape(m.group(3).strip()), 'url': 'https://www.ptt.cc' + m.group(2), 'hot': nrec, 'extra': {}})
        items = items[::-1][:limit]  # 看板頁面是舊→新，翻成新→舊
        for i, it in enumerate(items):
            it['rank'] = i + 1
        return wrap(f'PTT {board} 板最新', items)
    page = get('https://www.ptt.cc/bbs/hotboards.html')
    items = []
    for i, m in enumerate(re.finditer(r'<a class="board" href="/bbs/([^/]+)/index.html">.*?<div class="board-name">(.*?)</div>.*?<div class="board-nuser">.*?<span[^>]*>(.*?)</span>.*?<div class="board-class">(.*?)</div>.*?<div class="board-title">(.*?)</div>', page, re.S)):
        if i >= limit:
            break
        items.append({'rank': i + 1, 'title': html.unescape(m.group(5).strip()), 'url': f'https://www.ptt.cc/bbs/{m.group(1)}/index.html',
                      'hot': m.group(3).strip(), 'extra': {'board': m.group(2).strip(), 'class': m.group(4).strip()}})
    return wrap('PTT 熱門看板', items)


def show(d: dict) -> None:
    print(f"== {d['source']}（{d['fetched_at']}）")
    for it in d['items']:
        hot = f"  [{it['hot']}]" if it.get('hot') else ''
        print(f"{it['rank']:>3}. {it['title']}{hot}")


def main() -> None:
    ap = argparse.ArgumentParser(description='台灣熱門話題（Google 趨勢、Google 新聞、PTT）')
    sp = ap.add_subparsers(dest='cmd', required=True)
    for name in ('google', 'news', 'ptt', 'all'):
        p = sp.add_parser(name)
        p.add_argument('--limit', type=int, default=20)
        p.add_argument('--json', action='store_true')
        if name == 'news':
            p.add_argument('--topic', help='、'.join(NEWS_TOPICS))
        if name == 'ptt':
            p.add_argument('--board', help='看板英文名，例：Gossiping、Lifeismoney、movie')
    a = ap.parse_args()
    out, errors = [], []
    jobs = {'google': lambda: google(a.limit), 'news': lambda: news(a.limit, getattr(a, 'topic', None)),
            'ptt': lambda: ptt(a.limit, getattr(a, 'board', None))}
    for name in (['google', 'news', 'ptt'] if a.cmd == 'all' else [a.cmd]):
        try:
            out.append(jobs[name]())
        except Exception as e:  # 單一來源失敗不影響其他來源
            errors.append({'source': name, 'error': f'{type(e).__name__}: {e}'})
    if a.json:
        print(json.dumps(out[0] if a.cmd != 'all' and out else {'results': out, 'errors': errors}, ensure_ascii=False, indent=1))
    else:
        for d in out:
            show(d)
        for e in errors:
            print(f"!! {e['source']} 失敗：{e['error']}", file=sys.stderr)
    sys.exit(1 if not out else 0)


if __name__ == '__main__':
    main()
