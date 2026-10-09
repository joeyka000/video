"""動畫「一集」的語言：章節標題卡、漫畫分格、圖鑑掃描、つづく（未完待續）片尾卡。

給長一點的紀錄片／旅行片用：每天一章，章與章之間用不同的招牌手法，不要整支片同一套光斑。
所有字都必須是真實資訊（日期、時間、GPS 地名、畫面裡讀得到的店名），不編號碼、不編數據。
  import epfx as E
  E.chapter(c, e, 1, '10.02 FRI', '再見了，真新鎮', '桃園 → 峇里島')      # e＝進場後秒數
  polys = E.layout('h3', W, H); c = E.panels(bg, [img1, img2, img3], polys, [e1, e2, e3])
  E.dex_scan(c, m, e, no=4, name='TCG Collector', lines=['Sidakarya, Denpasar', '10.04 15:13'])
  E.tsuzuku(c, e, '未完待續', '峇里島　還有七天')
  E.dex_tag(c, e, 640, 300, 420, 760, 25, '皮卡丘', ['電'], '30th CELEBRATION　印尼版')   # 指著東西的小圖鑑卡
  python epfx.py demo 人物照.jpg [A.jpg B.jpg] -o /tmp/ep.jpg
"""
import functools
import math
import os
import sys

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from animepro import GOLD, WARM, add_c, glint_sprite, glass, light_sweep, put_text  # noqa: E402
from seekkit import CJK_B, CJK_R, CJK_TC, blit, ease, ease_out  # noqa: E402

FONTS = os.path.expanduser('~/video-lab/fonts')
MARU = os.path.join(FONTS, 'ZenMaruGothic-Bold.ttf')       # 圓體：つづく、章名（寶可夢動畫字卡的圓潤感）
CINZEL = os.path.join(FONTS, 'Cinzel.ttf')                   # 羅馬大寫：DAY、編號
SERIF = '/usr/share/fonts/opentype/noto/NotoSerifCJK-Bold.ttc'
PAPER = (0.97, 0.955, 0.925)
INK = (0.06, 0.07, 0.10)
RED = (0.90, 0.16, 0.18)


@functools.lru_cache(maxsize=256)
def font_for(text, pref=MARU, index=0):
    """偏好字型缺字（例如圓體沒有「卡」「峇」）就整串改用思源黑體，避免一行裡混兩種字體或出現豆腐字。"""
    from seekkit import missing_glyphs
    return (pref, index) if not missing_glyphs(text, pref, index) else (CJK_B, CJK_TC)


def _u(e, t0, d):
    return ease_out(min(1.0, max(0.0, (e - t0) / d)))


def poly_mask(h, w, pts, S=4):
    m = np.zeros((h, w), np.uint8)
    cv2.fillPoly(m, [np.round(np.array(pts) * S).astype(np.int32)], 255, cv2.LINE_AA, shift=2)
    return m.astype(np.float32) / 255


def _pool(c, cx, cy, rx, ry, k):
    h, w = c.shape[:2]
    yy, xx = np.mgrid[0:h:4, 0:w:4].astype(np.float32)
    p = np.exp(-(((xx - cx) / rx) ** 2 + ((yy - cy) / ry) ** 2) * 1.1)
    p = cv2.resize(p, (w, h), interpolation=cv2.INTER_LINEAR)[..., None]
    c *= 1 - k * p


# ───────── 章節標題卡 ─────────
def chapter(c, e, day, date, title, sub=None, x=84, y=1090, out=None, col=GOLD, k=1.0):
    """左下的章名：DAY（字距拉開）→ 大數字（白到金漸層、從遮罩升起、光掃過）→ 細金線畫出 → 章名（圓體）→ 小字（地點）。
    e＝進場後秒數；out＝(開始收的秒數) 之後往下沉＋變淡。底下自動壓一塊柔暗。"""
    if e < 0 or k <= 0:
        return
    o = k
    if out is not None and e > out:
        o *= max(0.0, 1 - (e - out) / 0.35)
    if o <= 0:
        return
    dy = 0 if out is None or e < out else 30 * ease((e - out) / 0.35)
    from seekkit import brightness
    kb = float(np.clip((brightness(c, int(x), int(y - 260), int(x + 620), int(y + 300)) - 0.35) / 0.35, 0, 1))   # 底亮就壓多一點
    _pool(c, x + 240, y + 30, 560, 380, (0.38 + 0.30 * kb) * o * _u(e, 0, 0.3))
    u0 = _u(e, 0.0, 0.45)
    put_text(c, 'DAY', 38, x + 8, y - 170 + (1 - u0) * 16 + dy, o * u0, CINZEL, 0, 0.62, col=col, shadow=0.6, glow=0.25, align='left')
    u1 = _u(e, 0.08, 0.55)
    put_text(c, f'{day:02d}', 250, x - 8, y - 20 + (1 - u1) * 60 + dy, o * u1, SERIF, CJK_TC, -0.02,
             grad=((1.0, 1.0, 1.0), (1.0, 0.80, 0.42)), shadow=0.75, glow=0.35, align='left')
    put_text(c, date, 42, x + 300, y - 62 + (1 - _u(e, 0.2, 0.5)) * 18 + dy, o * _u(e, 0.2, 0.5), CINZEL, 0, 0.18, shadow=0.7,
             glow=0.1, align='left')
    ln = int(560 * _u(e, 0.25, 0.6))
    if ln > 1:
        bar = np.zeros((3, ln, 4), np.float32)
        bar[..., :3] = col
        bar[1, :, 3], bar[0, :, 3], bar[2, :, 3] = 1.0, 0.35, 0.35
        blit(c, bar, x + 4, y + 110 + dy, o * 0.95)
    u2 = _u(e, 0.35, 0.5)
    f, fi = font_for(title)
    put_text(c, title, 78, x, y + 190 + (1 - u2) * 24 + dy, o * u2, f, fi, 0.04, shadow=0.8, glow=0.15, align='left')
    if sub:
        u3 = _u(e, 0.5, 0.5)
        put_text(c, sub, 32, x + 2, y + 270 + (1 - u3) * 14 + dy, o * u3 * 0.95, CJK_B, CJK_TC, 0.22, col=col, shadow=0.7,
                 glow=0.0, align='left')
    if 0.45 < e < 1.4:
        add_c(c, glint_sprite(150, (1.0, 0.95, 0.8)), x + 150, y - 90 + dy, o * math.sin(math.pi * (e - 0.45) / 0.95))


# ───────── 漫畫分格 ─────────
def layout(kind, W=1080, H=1920, gut=16, slant=70):
    """分格的多邊形（順時針，螢幕座標）。h2/h3＝上下斜切兩格／三格；v2＝左右斜切；L3＝上一大格＋下兩格。"""
    g = gut / 2
    if kind == 'h2':
        y = H * 0.5
        return [[(0, 0), (W, 0), (W, y - slant - g), (0, y + slant - g)],
                [(0, y + slant + g), (W, y - slant + g), (W, H), (0, H)]]
    if kind == 'h3':
        y1, y2 = H * 0.34, H * 0.67
        return [[(0, 0), (W, 0), (W, y1 - slant - g), (0, y1 + slant - g)],
                [(0, y1 + slant + g), (W, y1 - slant + g), (W, y2 + slant - g), (0, y2 - slant - g)],
                [(0, y2 - slant + g), (W, y2 + slant + g), (W, H), (0, H)]]
    if kind == 'v2':
        x = W * 0.5
        return [[(0, 0), (x + slant - g, 0), (x - slant - g, H), (0, H)],
                [(x + slant + g, 0), (W, 0), (W, H), (x - slant + g, H)]]
    if kind == 'L3':
        y = H * 0.56
        x = W * 0.5
        return [[(0, 0), (W, 0), (W, y - slant - g), (0, y + slant - g)],
                [(0, y + slant + g), (x + 30 - g, y + 2 * g), (x - 30 - g, H), (0, H)],
                [(x + 30 + g, y - slant / 3 + g), (W, y - slant + g), (W, H), (x - 30 + g, H)]]
    raise ValueError(kind)


def _cover(img, w, h, z=1.0, cx=0.5, cy=0.5):
    ih, iw = img.shape[:2]
    s = max(w / iw, h / ih) * z
    M = np.float32([[s, 0, w / 2 - cx * iw * s], [0, s, h / 2 - cy * ih * s]])
    return cv2.warpAffine(img, M, (w, h), flags=cv2.INTER_AREA if s < 1 else cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)


def panels(bg, imgs, polys, es, dirs=None, focus=None, zooms=None, gutter=PAPER, border=0, shadow=0.45, slide=0.42, gut_w=8):
    """把 imgs（各自整格大小的畫面）放進 polys 的格子裡。es[i]＝第 i 格進場後秒數（<0 還沒進場）。
    每格從 dirs[i]（'l','r','u','d'）滑進來、0.42 秒減速停住；每格外圍一圈紙白（相鄰兩格接起來就是溝），格子邊下有柔陰影。
    bg＝格子底下的畫面（上一個鏡頭的延續、壓暗），不要整片白紙：剛進場那幾格會像空白格。"""
    h, w = bg.shape[:2]
    out = bg.copy()
    n = len(polys)
    dirs = dirs or ['l', 'r', 'l', 'r'][:n]
    focus = focus or [(0.5, 0.5)] * n
    zooms = zooms or [1.0] * n
    if max(es) >= 0:                       # 格子進來以後底下壓暗一點，格子才浮在上面
        out = out * (1 - 0.45 * min(1.0, max(es) / 0.25))
    for i, (pts, img, e) in enumerate(zip(polys, imgs, es)):
        if e < 0:
            continue
        u = ease_out(min(1.0, e / slide), 4)
        dx, dy = {'l': (-1, 0), 'r': (1, 0), 'u': (0, -1), 'd': (0, 1)}[dirs[i]]
        off = (1 - u) * (w if dx else h) * 0.9
        P = [(x + dx * off, y + dy * off) for x, y in pts]
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        x0, y0, x1, y1 = int(min(xs)), int(min(ys)), int(math.ceil(max(xs))), int(math.ceil(max(ys)))
        bw, bh = max(2, x1 - x0), max(2, y1 - y0)
        cell = _cover(img, bw, bh, zooms[i] * (1 + 0.03 * (1 - u)), *focus[i])
        full = np.zeros_like(out)
        ox, oy = int(round(x0 + dx * off)), int(round(y0 + dy * off))
        sx0, sy0 = max(0, ox), max(0, oy)
        sx1, sy1 = min(w, ox + bw), min(h, oy + bh)
        if sx1 <= sx0 or sy1 <= sy0:
            continue
        full[sy0:sy1, sx0:sx1] = cell[sy0 - oy:sy1 - oy, sx0 - ox:sx1 - ox]
        m = poly_mask(h, w, P)
        gw = max(3, int(gut_w))                    # 溝＝每格外圍一圈紙白（相鄰兩格的外框接起來就是溝）
        ring = np.clip(cv2.dilate(m, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * gw + 1, 2 * gw + 1))) - m, 0, 1)
        out = out * (1 - ring[..., None]) + np.float32(gutter) * ring[..., None]
        if shadow > 0:
            sh = cv2.GaussianBlur(np.roll(np.roll(m, 10, 0), 6, 1), (0, 0), 14)
            out *= 1 - (sh * shadow * (1 - m))[..., None]
        out = out * (1 - m[..., None]) + full * m[..., None]
        if border > 0:
            ed = poly_mask(h, w, P) - cv2.erode(poly_mask(h, w, P), np.ones((border, border), np.uint8))
            out = out * (1 - ed[..., None]) + np.float32(INK) * ed[..., None]
    return out.astype(np.float32)


# ───────── 圖鑑掃描 ─────────
def _bracket(c, x0, y0, x1, y1, L, col, op, width=3):
    S = 4
    h, w = c.shape[:2]
    lay = np.zeros((h, w), np.float32)
    for (ax, ay, sx, sy) in [(x0, y0, 1, 1), (x1, y0, -1, 1), (x0, y1, 1, -1), (x1, y1, -1, -1)]:
        p = np.int32([[(ax + sx * L) * S, ay * S], [ax * S, ay * S], [ax * S, (ay + sy * L) * S]])
        cv2.polylines(lay, [p], False, 1.0, width * S, cv2.LINE_AA, shift=2)
    g = cv2.GaussianBlur(lay, (0, 0), 6)
    c[:] = 1 - (1 - c) * (1 - np.clip((lay + g * 0.8)[..., None] * np.float32(col) * op, 0, 1))


def dex_scan(c, m, e, no=None, name='', lines=(), col=(0.80, 0.95, 1.0), accent=GOLD, side='auto', dur=1.1, hold=2.2,
             panel_y=None):
    """圖鑑掃描：背景壓暗、去飽和 → 一條掃描光從主體上緣掃到下緣（掃過的地方留一層細網格、輪廓亮起來）→
    角框從外收進主體 → 旁邊滑出資料卡（No.、名稱、地點與時間）。m＝主體遮罩（同畫布大小）。e＝開始後秒數。
    no：整數＝全國圖鑑編號（噴火龍 6、皮卡丘 25：用真的編號，懂的人會截圖）；字串＝其他標記（'SHOP'）。"""
    if e < 0:
        return
    from matte import bbox, edge
    h, w = c.shape[:2]
    bb = bbox(m, 0.5, 10)
    if bb is None:
        return
    x0, y0, x1, y1 = bb
    end = dur + hold
    fade = 1.0 if e < end else max(0.0, 1 - (e - end) / 0.35)
    if fade <= 0:
        return
    kin = _u(e, 0, 0.25) * fade
    L = c @ np.float32([0.2126, 0.7152, 0.0722])
    gray = (L[..., None] * 0.85 + c * 0.15) * np.float32([0.86, 0.92, 1.0])
    mm = m[..., None]
    c[:] = c * mm + (c * (1 - 0.55 * kin) + gray * 0.55 * kin) * (1 - mm) * (1 - 0.35 * kin)
    # 掃描線＋網格
    s = min(1.0, max(0.0, (e - 0.15) / (dur * 0.75)))
    ys = y0 + (y1 - y0) * ease(s)
    if 0 < s < 1 or e < dur + 0.2:
        yy = np.arange(h, dtype=np.float32)[:, None]
        xx = np.arange(w, dtype=np.float32)[None, :]
        grid = ((np.abs(((xx - x0) % 22) - 11) > 10.0) | (np.abs(((yy - y0) % 22) - 11) > 10.0)).astype(np.float32)
        passed = np.clip((ys - yy) / 40, 0, 1) * np.exp(-np.maximum(ys - yy, 0) / 260)
        lay = grid * passed * m * 0.35
        line = np.exp(-((yy - ys) / 3.0) ** 2) + np.exp(-((yy - ys) / 26.0) ** 2) * 0.45
        span = ((xx > x0 - 40) & (xx < x1 + 40)).astype(np.float32)
        lay = lay + line * span * (0.35 + 0.65 * m) * (1.0 if s < 1 else max(0.0, 1 - (e - dur) / 0.2))
        c[:] = 1 - (1 - c) * (1 - np.clip(lay[..., None] * np.float32(col) * fade, 0, 1))
    # 輪廓光
    ed = edge(m, 2.0)
    rk = _u(e, 0.2, dur) * fade
    lay = (ed * 0.9 + cv2.GaussianBlur(ed, (0, 0), 10) * 1.3)[..., None] * np.float32(col) * rk
    c[:] = 1 - (1 - c) * (1 - np.clip(lay, 0, 1))
    # 角框
    ub = _u(e, 0.35, 0.4)
    if ub > 0:
        pad = 60 * (1 - ub) + 14
        _bracket(c, x0 - pad, y0 - pad, x1 + pad, y1 + pad, 46, col, ub * fade)
    # 資料卡
    up = _u(e, dur * 0.7, 0.45)
    if up <= 0:
        return
    if side == 'auto':
        side = 'r' if (x0 + x1) / 2 < w / 2 else 'l'
    pw, ph = 470, 120 + 46 * len(lines)
    py = panel_y if panel_y is not None else min(h - ph - 260, max(240, (y0 + y1) / 2 - ph / 2))
    px = (w - pw - 56) if side == 'r' else 56
    px += (1 - up) * (60 if side == 'r' else -60)
    op = up * fade
    glass(c, px, py, pw, ph, op, r=18, blur=16, fill=0.16, tint=(0.75, 0.88, 1.0), border=0.35)
    if no is not None:
        put_text(c, f'No.{no:03d}' if isinstance(no, int) else str(no), 24, px + 28, py + 36, op, CINZEL, 0, 0.30, col=accent,
                 shadow=0.3, glow=0.2, align='left')
    dot = np.zeros((14, 14, 4), np.float32)
    cv2.circle(dot, (7, 7), 5, (*RED, 1.0), -1, cv2.LINE_AA)
    blit(c, dot, px + pw - 40, py + 29, op)
    put_text(c, name, 44, px + 26, py + 86, op, CJK_B, CJK_TC, 0.04, shadow=0.35, glow=0.08, align='left')
    for i, ln in enumerate(lines):
        put_text(c, ln, 25, px + 28, py + 134 + i * 44, op * 0.92, CJK_R, CJK_TC, 0.08, col=(0.88, 0.94, 1.0), shadow=0.3,
                 glow=0.0, align='left')
    # 卡片到角框的引線
    lx = px if side == 'r' else px + pw
    tx = x1 + 14 if side == 'r' else x0 - 14
    if (side == 'r' and tx >= lx) or (side == 'l' and tx <= lx):
        return                                  # 主體比卡片還寬：不畫引線
    S = 4
    lay = np.zeros((h, w), np.float32)
    cv2.line(lay, (int(lx * S), int((py + 36) * S)), (int(tx * S), int((py + 36) * S)), 1.0, 2 * S, cv2.LINE_AA, shift=2)
    c[:] = 1 - (1 - c) * (1 - np.clip(lay[..., None] * np.float32(col) * op * 0.8, 0, 1))


# ───────── 圖鑑小標籤 ─────────
TYPE_COL = {'火': (1.0, 0.45, 0.16), '水': (0.22, 0.58, 1.0), '草': (0.36, 0.80, 0.30), '電': (1.0, 0.80, 0.16),
            '飛行': (0.55, 0.72, 1.0), '超能力': (1.0, 0.42, 0.68), '一般': (0.75, 0.72, 0.65), '???': (0.55, 0.56, 0.62)}


def _chip(c, text, x, y, col, op, h=34):
    """屬性小膠囊：實色圓角＋白字（遊戲裡的屬性標，縮小成資訊標）。"""
    from animepro import _rrect
    f, fi = font_for(text, CJK_B, CJK_TC)
    w = int(len(text) * 22 + 30)
    m = _rrect(w, h, h // 2)[..., None]
    x0, y0 = int(x), int(y - h / 2)
    H_, W_ = c.shape[:2]
    if x0 < 0 or y0 < 0 or x0 + w > W_ or y0 + h > H_:
        return w
    reg = c[y0:y0 + h, x0:x0 + w]
    reg[:] = reg * (1 - m * 0.88 * op) + np.float32(col) * 0.92 * m * op
    put_text(c, text, 21, x0 + w / 2, y0 + h / 2, op, f, fi, 0.06, shadow=0.0, glow=0.0)
    return w


def dex_tag(c, e, x, y, px, py, no, name, types=(), sub=None, k=1.0, out=None, w=380, accent=GOLD):
    """圖鑑小標籤：目標點亮起 → 引線畫出 → 毛玻璃小卡（No.、名稱、屬性膠囊、一行小字）。
    (x, y)＝卡片左上；(px, py)＝指向的東西。e＝出現後秒數；out＝開始收的秒數。"""
    if e < 0 or k <= 0:
        return
    o = k if out is None or e < out else k * max(0.0, 1 - (e - out) / 0.3)
    if o <= 0:
        return
    h = 136 + (40 if sub else 0)
    ul = _u(e, 0.0, 0.25)
    cx, cy = (x if px < x else x + w), y + 44
    S = 4
    lay = np.zeros(c.shape[:2], np.float32)
    ex, ey = px + (cx - px) * ul, py + (cy - py) * ul
    cv2.line(lay, (int(px * S), int(py * S)), (int(ex * S), int(ey * S)), 1.0, 2 * S, cv2.LINE_AA, shift=2)
    cv2.circle(lay, (int(px * S), int(py * S)), 7 * S, 1.0, -1, cv2.LINE_AA, shift=2)
    g = cv2.GaussianBlur(lay, (0, 0), 6)
    c[:] = 1 - (1 - c) * (1 - np.clip((lay + g * 0.9)[..., None] * np.float32(accent) * o, 0, 1))
    uc = _u(e, 0.15, 0.35)
    if uc <= 0:
        return
    xx = x + (1 - uc) * (30 if px < x else -30)
    _pool(c, xx + w / 2, y + h / 2, w * 0.8, h, 0.35 * o * uc)
    glass(c, xx, y, w, h, o * uc, r=18, blur=16, fill=0.16, tint=(0.80, 0.90, 1.0), border=0.35)
    put_text(c, f'No.{no:03d}' if isinstance(no, int) else str(no), 26, xx + 24, y + 34, o * uc, CINZEL, 0, 0.26, col=accent,
             shadow=0.3, glow=0.2, align='left')
    tx = xx + 24 + len(f'No.{no:03d}' if isinstance(no, int) else str(no)) * 22 + 20   # 膠囊接在編號後面，不疊字
    for tp in types:
        tx += _chip(c, tp, tx, y + 34, TYPE_COL.get(tp, TYPE_COL['一般']), o * uc) + 8
    f, fi = font_for(name, CJK_B, CJK_TC)
    put_text(c, name, 42, xx + 22, y + 92, o * uc, f, fi, 0.03, shadow=0.35, glow=0.08, align='left')
    if sub:
        put_text(c, sub, 24, xx + 24, y + 140, o * uc * 0.92, CJK_R, CJK_TC, 0.08, col=(0.88, 0.94, 1.0), shadow=0.3, glow=0.0,
                 align='left')


# ───────── つづく ─────────
def tsuzuku(c, e, cn='未完待續', sub=None, x=None, y=None, col=GOLD):
    """寶可夢動畫的「つづく」：畫面定格、暖色舊照片化（褪色、暗角）、右下角大字「つづく」從左往右一筆一筆出現，
    底下中文與一行小字（下一集的真實資訊）。e＝進場後秒數。"""
    if e < 0:
        return
    h, w = c.shape[:2]
    x = w - 70 if x is None else x
    y = h - 520 if y is None else y
    k = _u(e, 0, 0.6)
    L = c @ np.float32([0.2126, 0.7152, 0.0722])
    sep = np.clip(L[..., None] * np.float32([1.08, 0.98, 0.82]) + np.float32([0.03, 0.02, 0.0]), 0, 1)
    c[:] = c * (1 - 0.55 * k) + sep * 0.55 * k
    yy, xx = np.mgrid[0:h:4, 0:w:4].astype(np.float32)
    v = np.clip(((xx - w / 2) / (w * 0.75)) ** 2 + ((yy - h / 2) / (h * 0.7)) ** 2, 0, 1)
    c *= 1 - 0.45 * k * cv2.resize(v, (w, h))[..., None]
    _pool(c, x - 240, y + 40, 560, 300, 0.40 * k)
    chars = 'つづく'
    size = 150
    adv = size * 1.0
    x0 = x - adv * len(chars)
    for i, ch in enumerate(chars):
        u = _u(e, 0.35 + i * 0.16, 0.35)
        if u <= 0:
            continue
        put_text(c, ch, size, x0 + i * adv + adv / 2, y + (1 - u) * 26, u, *font_for(chars), 0.0, grad=((1.0, 1.0, 1.0), (1.0, 0.84, 0.52)),
                 shadow=0.8, glow=0.25)
    u = _u(e, 0.95, 0.5)
    put_text(c, cn, 54, x, y + 128 + (1 - u) * 14, u, SERIF, CJK_TC, 0.35, shadow=0.75, glow=0.1, align='right')
    if sub:
        u = _u(e, 1.2, 0.5)
        put_text(c, sub, 30, x, y + 196 + (1 - u) * 10, u * 0.95, CJK_B, CJK_TC, 0.22, col=col, shadow=0.75, glow=0.0, align='right')
    if 0.9 < e < 2.0:
        light_sweep(c, (e - 0.9) / 1.1, 0.18, 0.08, 0.3)


def _demo(out, photo=None, a_img=None, b_img=None):
    """python epfx.py demo 人物照.jpg [畫面A.jpg 畫面B.jpg] -o 出圖.jpg：章名卡、圖鑑掃描、三格分格、つづく 各一格。"""
    from PIL import Image, ImageOps
    import matte as MT
    W, H = 1080, 1920

    def load(p, fb):
        if not p:
            yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
            return np.dstack([0.2 + 0.5 * xx / W, 0.3 + 0.2 * yy / H, 0.55 - 0.2 * yy / H]).astype(np.float32) * fb
        im = ImageOps.exif_transpose(Image.open(p)).convert('RGB')
        im = im.resize((W, int(W * im.height / im.width)), Image.LANCZOS)
        return _cover(np.asarray(im, np.float32) / 255, W, H)
    img, a, b = load(photo, 1.0), load(a_img, 0.8), load(b_img, 1.1)
    f1 = img.copy()
    chapter(f1, 1.6, 3, '10.04 SUN', '卡店大冒險！', 'DENPASAR　SANUR　SIDAKARYA')
    f2 = img.copy()
    dex_scan(f2, MT.isnet(img, key=f'demo:{photo}'), 1.5, 4, 'TCG Collector', ['SIDAKARYA, DENPASAR', '10.04　15:24'])
    f3 = panels(a, [a, b, img], layout('h3'), [0.5, 0.3, 0.1], focus=[(0.5, 0.5), (0.5, 0.6), (0.5, 0.35)])
    f4 = b.copy()
    tsuzuku(f4, 2.2, '未完待續', '峇里島　還有七天')
    sheet = np.concatenate([f1, f2, f3, f4], 1)
    sheet = cv2.resize(sheet, None, fx=0.45, fy=0.45, interpolation=cv2.INTER_AREA)
    cv2.imwrite(out, (np.clip(sheet, 0, 1)[..., ::-1] * 255).astype(np.uint8))
    print(out)


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == 'demo':
        args = [x for x in sys.argv[2:] if not x.startswith('-')]
        o = sys.argv[sys.argv.index('-o') + 1] if '-o' in sys.argv else '/tmp/ep.jpg'
        args = [x for x in args if x != o]
        _demo(o, *args[:3])
