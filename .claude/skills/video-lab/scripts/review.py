#!/usr/bin/env python3
"""縮圖總覽評分關卡：正式渲染前先出總覽、逐格打 1–10 分、修最差的 3 格，全部 ≥ 8 才輸出。

  python review.py sheet --video out/test.mp4 -o out/qa/sheet.jpg [--n 24 | --every 1.5 | --at 1,4,9]
  python review.py sheet --images out/stills/*.jpg -o out/qa/sheet.jpg     # 檔名含秒數時會標上
  python review.py gate out/qa/sheet.review.json [--min 8]                # 通過 exit 0；沒過 exit 1 並列出最差 3 格
  python review.py gate qa/flow/cuts.review.json                         # 剪點評分表（flow.py check 產生），同一個關卡
  python review.py diff old.review.json new.review.json                    # 兩輪分數對照

seek(t) 引擎直接用 `frames.py sheet engine.py -o ...`（同一個版面與評分表）。

評分表 <sheet>.review.json：
  {"source", "round", "min": 8, "cells": [{"i": 1, "t": 2.5, "label": "", "score": null, "why": "", "fix": ""}]}
  - score：1–10 整數，依 references/review.md 的錨點打；不能空著過關
  - why：一句話說為什麼是這個分數（≥ 8 也要寫，寫得出具體理由才算）
  - fix：< 8 的格子必填，要改什麼
  每一輪重出總覽時 round +1，舊分數表留著用 diff 對照，不要覆蓋
"""
import argparse
import glob
import json
import os
import re
import subprocess
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFont

FONT = '/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc'


def make_sheet(frames, ts, out, cols=6, width=270, labels=None, source=''):
    """frames: uint8 RGB 陣列清單；輸出拼圖與 review.json（已存在的評分表保留分數，只換 round）。"""
    h0, w0 = frames[0].shape[:2]
    cw, ch = width, int(width * h0 / w0)
    pad, bar = 6, 30
    rows = (len(frames) + cols - 1) // cols
    sheet = Image.new('RGB', (cols * (cw + pad) + pad, rows * (ch + bar + pad) + pad), (18, 18, 18))
    d = ImageDraw.Draw(sheet)
    f = ImageFont.truetype(FONT, 18, index=3)
    for k, (fr, t) in enumerate(zip(frames, ts)):
        x = pad + (k % cols) * (cw + pad)
        y = pad + (k // cols) * (ch + bar + pad)
        sheet.paste(Image.fromarray(fr).resize((cw, ch), Image.LANCZOS), (x, y + bar))
        lab = labels[k] if labels and labels[k] else ''
        d.text((x + 4, y + 4), f'#{k + 1}  {t:.2f}s  {lab}'[:40], font=f, fill=(255, 214, 90))
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    sheet.save(out, quality=90)
    rj = os.path.splitext(out)[0] + '.review.json'
    old = json.load(open(rj)) if os.path.exists(rj) else None
    if old:
        bak = os.path.splitext(out)[0] + f'.review.r{old.get("round", 1)}.json'
        json.dump(old, open(bak, 'w'), ensure_ascii=False, indent=1)
    cells = [{'i': k + 1, 't': round(float(t), 3), 'label': (labels[k] if labels else '') or '', 'score': None, 'why': '', 'fix': ''}
             for k, t in enumerate(ts)]
    rnd = (old.get('round', 1) + 1) if old else 1
    json.dump({'source': source, 'round': rnd, 'min': 8, 'cells': cells}, open(rj, 'w'), ensure_ascii=False, indent=1)
    print(f'{out}\n{rj}（第 {rnd} 輪，{len(cells)} 格待評分）')


def video_frames(path, ts):
    r = subprocess.run(['ffprobe', '-v', 'error', '-select_streams', 'v', '-show_entries', 'stream=width,height', '-of', 'csv=p=0', path],
                       capture_output=True, text=True, check=True)
    w, h = map(int, r.stdout.strip().split(',')[:2])
    out = []
    for t in ts:
        raw = subprocess.run(['ffmpeg', '-v', 'error', '-ss', str(t), '-i', path, '-frames:v', '1', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-'],
                             capture_output=True, check=True).stdout
        out.append(np.frombuffer(raw, np.uint8)[:w * h * 3].reshape(h, w, 3) if raw else np.zeros((h, w, 3), np.uint8))
    return out


def dur(path):
    r = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', path], capture_output=True, text=True)
    return float(r.stdout)


def cmd_sheet(a):
    if a.video:
        D = dur(a.video)
        if a.at:
            ts = [float(x) for x in a.at.split(',')]
        elif a.every:
            ts = [round(a.every * (i + 0.5), 3) for i in range(int(D / a.every))]
        else:
            ts = [round(D * (i + 0.5) / a.n, 3) for i in range(a.n)]
        make_sheet(video_frames(a.video, ts), ts, a.out, a.cols, a.width, source=os.path.abspath(a.video))
    else:
        paths = sorted(p for g in a.images for p in glob.glob(g))
        ts = []
        for p in paths:
            m = re.search(r'(\d+(?:\.\d+)?)', os.path.basename(p))
            ts.append(float(m.group(1)) if m else 0.0)
        frames = [np.asarray(Image.open(p).convert('RGB')) for p in paths]
        make_sheet(frames, ts, a.out, a.cols, a.width, labels=[os.path.basename(p) for p in paths], source='images')


def cmd_gate(a):
    r = json.load(open(a.review))
    need = a.min or r.get('min', 8)
    cells = r['cells']
    blank = [c['i'] for c in cells if not isinstance(c.get('score'), int)]
    if blank:
        print(f'還沒評分：#{blank}（每格都要打整數分數）')
        sys.exit(1)
    nowhy = [c['i'] for c in cells if not c.get('why', '').strip()]
    nofix = [c['i'] for c in cells if c['score'] < need and not c.get('fix', '').strip()]
    worst = sorted(cells, key=lambda c: c['score'])[:3]
    low = [c for c in cells if c['score'] < need]
    avg = sum(c['score'] for c in cells) / len(cells)
    u = '刀' if r.get('kind') == 'cuts' else '格'
    print(f'第 {r.get("round", 1)} 輪：{len(cells)} {u}，平均 {avg:.1f}，最低 {worst[0]["score"]}，未達 {need} 分 {len(low)} {u}')
    for c in worst:
        print(f'  #{c["i"]:<3} {c["t"]:7.2f}s  {c["score"]:>2} 分  {c.get("why", "")}' + (f'  → 改：{c["fix"]}' if c.get('fix') else ''))
    if nowhy:
        print(f'缺理由：#{nowhy}（≥ 8 分也要寫具體理由）')
    if nofix:
        print(f'低於 {need} 分卻沒寫要怎麼改：#{nofix}')
    if low or nowhy or nofix:
        print(f'未通過：修最差的 3 {u} → ' + ('重跑 flow.py' if u == '刀' else '重出總覽') + '（round +1）→ 重新評分。')
        sys.exit(1)
    print(f'通過：全部 ≥ {need} 分' + ('（剪點）' if u == '刀' else '') + '，可以正式渲染。')


def cmd_diff(a):
    o, n = json.load(open(a.old)), json.load(open(a.new))
    om = {round(c['t'], 2): c.get('score') for c in o['cells']}
    for c in n['cells']:
        s0 = om.get(round(c['t'], 2))
        mark = '' if s0 is None or c.get('score') is None else ('↑' if c['score'] > s0 else '↓' if c['score'] < s0 else '=')
        print(f'#{c["i"]:<3} {c["t"]:7.2f}s  {s0} → {c.get("score")} {mark}')


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = p.add_subparsers(dest='cmd', required=True)
    s = sp.add_parser('sheet')
    g = s.add_mutually_exclusive_group(required=True)
    g.add_argument('--video')
    g.add_argument('--images', nargs='+')
    s.add_argument('-o', '--out', required=True)
    s.add_argument('--n', type=int, default=24)
    s.add_argument('--every', type=float)
    s.add_argument('--at')
    s.add_argument('--cols', type=int, default=6)
    s.add_argument('--width', type=int, default=270)
    s = sp.add_parser('gate')
    s.add_argument('review')
    s.add_argument('--min', type=int)
    s = sp.add_parser('diff')
    s.add_argument('old')
    s.add_argument('new')
    a = p.parse_args()
    {'sheet': cmd_sheet, 'gate': cmd_gate, 'diff': cmd_diff}[a.cmd](a)


if __name__ == '__main__':
    main()
