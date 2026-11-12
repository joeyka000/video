#!/usr/bin/env python3
"""可愛手帳風零件庫（旅行手帳、情侶日常、開箱）：粉彩紙底、拍立得、紙膠帶標籤、對話框、圓章、emoji 貼紙、愛心圖釘。
畫面只由 t 決定；精靈都是預乘 alpha 的 RGBA float32，用 paste() 貼（次像素、可旋轉縮放）。配方見 references/scrapbook.md。

  paper(w, h, base, ink, pattern)      粉彩紙底：dots／gingham／hearts／stripes／grid／stars（靜態，壓檔省位元）
  instax(photo, w, caption)            拍立得卡（3:4 直式相片、下方留白寫字、柔陰影）；photo 先用 cover_crop 裁好
  tile(photo, r)                       圓角相片磚（白邊＋陰影），九宮格用
  cover_crop(img, w, h, faces, zoom)   依臉的位置裁切填滿（faces＝[(x, y, w, h) 比例座標]）
  text(s, size, fill, stroke, …)       字貼紙：自動分字型（中文粉圓體、韓文 Jua、手寫 Gaegu）、白色粗描邊＋柔陰影
  emoji(ch, size)                      彩色 emoji 貼紙（Noto Color Emoji，白邊）
  tape(lines, color)                   紙膠帶標籤（半透明、斜條紋、鋸齒邊）：頁首的日期與地名
  bubble(s, size)                      對話框（圓角白底＋小尾巴）
  badge(lines, d, color)               圓章貼紙（花邊），放「這一站幾張」這種數字
  pin(d, color, label)                 愛心圖釘
  paste(c, spr, cx, cy, scale, angle, op, anchor)   貼到畫布（RGB 或預乘 RGBA 圖層）
  pop(u) / back_out(u)                 彈出來的緩動（超過一點再回來）
  scallop_wipe(a, b, u)                花邊換頁：b 從右邊蓋過來，邊緣是波浪＋白線

  python cutefx.py demo -o out/cutefx_demo.jpg [--img 照片.jpg]
字型（OFL）：jf open 粉圓、Jua、Gaegu、Mochiy Pop One——啟動腳本會下載到 ~/.fonts。
"""
import functools
import math
import os
import sys

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
FD = os.path.expanduser('~/.fonts')
FONT = {'zh': os.path.join(FD, 'jf-openhuninn.ttf'), 'ko': os.path.join(FD, 'Jua-Regular.ttf'), 'hand': os.path.join(FD, 'Gaegu-Bold.ttf'),
        'jp': os.path.join(FD, 'MochiyPopOne-Regular.ttf'), 'emoji': '/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf'}
INK = (0.36, 0.27, 0.25)          # 手帳的字色：暖棕，不用純黑


def hexrgb(s):
    s = s.lstrip('#')
    return tuple(int(s[i:i + 2], 16) / 255 for i in (0, 2, 4))


def clamp01(u):
    return 0.0 if u < 0 else 1.0 if u > 1 else u


def ease_out(u, p=3):
    return 1 - (1 - clamp01(u)) ** p


def back_out(u, s=1.70158):
    u = clamp01(u) - 1
    return 1 + (s + 1) * u ** 3 + s * u ** 2


def pop(u):
    """0→1：貼紙彈出來（先衝過頭 8% 再回來）。u ≤ 0 回 0。"""
    return 0.0 if u <= 0 else back_out(u)


# ═════════ 紙 ═════════
@functools.lru_cache(maxsize=16)
def paper(w, h, base, ink, pattern='dots', scale=1.0):
    """粉彩紙底。base、ink 是 '#RRGGBB'。回傳唯讀 float32 RGB（用之前 .copy()）。"""
    b, k = np.float32(hexrgb(base)), np.float32(hexrgb(ink))
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    m = np.zeros((h, w), np.float32)
    s = scale
    if pattern == 'dots':
        p = 96 * s
        for ox, oy in ((0, 0), (p / 2, p / 2)):
            d = np.hypot((xx - ox) % p - p / 2, (yy - oy) % p - p / 2)
            m = np.maximum(m, np.clip(13 * s - d, 0, 1))
    elif pattern == 'gingham':
        p = 120 * s
        a = ((xx % p) < p / 2).astype(np.float32)
        c = ((yy % p) < p / 2).astype(np.float32)
        m = (a + c) * 0.45
    elif pattern == 'stripes':
        p = 84 * s
        v = ((xx + yy) % p) / p
        m = np.clip((0.5 - np.abs(v - 0.5)) * p / 2 - p * 0.14, 0, 1)
    elif pattern == 'grid':
        p = 72 * s
        m = np.maximum(np.clip(2.2 - np.minimum(xx % p, p - xx % p), 0, 1), np.clip(2.2 - np.minimum(yy % p, p - yy % p), 0, 1)) * 0.9
    elif pattern in ('hearts', 'stars'):
        p = int(150 * s)
        cell = np.zeros((p, p), np.float32)
        im = Image.new('L', (p * 4, p * 4), 0)
        d = ImageDraw.Draw(im)
        for cx, cy in ((p, p), (p * 3, p * 3)):
            if pattern == 'hearts':
                r = p * 0.42
                pts = [(cx + r * 16 * math.sin(a) ** 3 / 16, cy - r * (13 * math.cos(a) - 5 * math.cos(2 * a) - 2 * math.cos(3 * a) - math.cos(4 * a)) / 16)
                       for a in np.linspace(0, 2 * math.pi, 60)]
            else:
                pts = [(cx + (p * 0.5 if i % 2 == 0 else p * 0.2) * math.sin(i * math.pi / 5), cy - (p * 0.5 if i % 2 == 0 else p * 0.2) * math.cos(i * math.pi / 5))
                       for i in range(10)]
            d.polygon(pts, fill=255)
        cell = np.asarray(im.resize((p, p), Image.LANCZOS)).astype(np.float32) / 255
        m = np.tile(cell, (h // p + 1, w // p + 1))[:h, :w]
    out = b + (k - b) * m[..., None]
    rng = np.random.default_rng(7)
    out = out + (cv2.GaussianBlur(rng.normal(0, 1, (h, w)).astype(np.float32), (0, 0), 1.2) * 0.012)[..., None]     # 一點紙紋（靜態）
    out = np.clip(out, 0, 1).astype(np.float32)
    out.setflags(write=False)
    return out


# ═════════ 形狀 ═════════
@functools.lru_cache(maxsize=64)
def rrect(w, h, r):
    """圓角矩形遮罩 float32（抗鋸齒）。"""
    S = 3
    im = Image.new('L', (w * S, h * S), 0)
    ImageDraw.Draw(im).rounded_rectangle([0, 0, w * S - 1, h * S - 1], radius=int(r * S), fill=255)
    return np.asarray(im.resize((w, h), Image.LANCZOS)).astype(np.float32) / 255


def _shadow(alpha, pad, blur, off, k):
    """把一張 alpha 加上柔陰影：回傳 (加了邊界的 alpha, 陰影層 alpha)。"""
    A = cv2.copyMakeBorder(alpha, pad, pad, pad, pad, cv2.BORDER_CONSTANT, value=0)
    sh = cv2.warpAffine(A, np.float32([[1, 0, off[0]], [0, 1, off[1]]]), (A.shape[1], A.shape[0]))
    return A, cv2.GaussianBlur(sh, (0, 0), blur) * k


def _with_shadow(rgb, alpha, pad=24, blur=9, off=(4, 9), k=0.28, col=(0.25, 0.16, 0.14)):
    """rgb（未預乘）＋alpha → 預乘 RGBA，四周加 pad 並墊柔陰影。"""
    A, sh = _shadow(alpha, pad, blur, off, k)
    RGB = cv2.copyMakeBorder(rgb, pad, pad, pad, pad, cv2.BORDER_CONSTANT, value=0)
    out_a = A + sh * (1 - A)
    pm = RGB * A[..., None] + np.float32(col) * (sh * (1 - A))[..., None]
    return np.dstack([pm, out_a]).astype(np.float32)


def cover_crop(img, w, h, faces=None, zoom=1.0, bias=(0.5, 0.42)):
    """裁切填滿 w×h。有臉時把所有臉的中心放在畫面 bias 的位置附近（不超出邊界）。img float32 或 uint8。"""
    ih, iw = img.shape[:2]
    k = max(w / iw, h / ih) * zoom
    cw, ch = w / k, h / k
    if faces:
        fx = float(np.mean([f[0] + f[2] / 2 for f in faces])) * iw
        fy = float(np.mean([f[1] + f[3] / 2 for f in faces])) * ih
        x0, y0 = fx - cw * bias[0], fy - ch * bias[1]
    else:
        x0, y0 = (iw - cw) / 2, (ih - ch) * 0.4
    x0, y0 = min(max(x0, 0), iw - cw), min(max(y0, 0), ih - ch)
    M = np.float32([[k, 0, -x0 * k], [0, k, -y0 * k]])
    out = cv2.warpAffine(img, M, (w, h), flags=cv2.INTER_AREA if k < 0.9 else cv2.INTER_CUBIC, borderMode=cv2.BORDER_REFLECT)
    return np.clip(out.astype(np.float32) / (255 if img.dtype == np.uint8 else 1), 0, 1)


def instax(photo, w, caption=None, cap_size=None, card=(1.0, 0.995, 0.975)):
    """拍立得卡：photo＝已裁成 3:4 的 float32 RGB（任何大小），w＝卡片寬。回傳預乘 RGBA（含陰影邊界 pad＝w×0.06）。"""
    side, top, bot = round(w * 0.055), round(w * 0.065), round(w * 0.205)
    pw = w - 2 * side
    ph = round(pw * 4 / 3)
    hh = top + ph + bot
    ph_img = cv2.resize(photo, (pw, ph), interpolation=cv2.INTER_AREA if photo.shape[1] > pw else cv2.INTER_CUBIC)
    rgb = np.ones((hh, w, 3), np.float32) * np.float32(card)
    m = rrect(pw, ph, max(2, w * 0.012))[..., None]
    rgb[top:top + ph, side:side + pw] = rgb[top:top + ph, side:side + pw] * (1 - m) + np.clip(ph_img, 0, 1) * m
    if caption:
        ts = text(caption, cap_size or round(w * 0.085), fill=INK, stroke=None, font='hand', shadow=False)
        th, tw = ts.shape[:2]
        if tw < pw:
            y, x = top + ph + (bot - th) // 2, side + round(w * 0.02)
            a = ts[..., 3:4]
            rgb[y:y + th, x:x + tw] = rgb[y:y + th, x:x + tw] * (1 - a) + ts[..., :3]
    pad = max(8, round(w * 0.06))
    return _with_shadow(rgb, rrect(w, hh, max(3, w * 0.02)), pad=pad, blur=max(3, w * 0.022), off=(w * 0.008, w * 0.02), k=0.30)


def tile(photo, r=None, border=None):
    """圓角相片磚：photo＝已裁好的 float32 RGB；白邊＋陰影。回傳預乘 RGBA。"""
    h, w = photo.shape[:2]
    b = border if border is not None else max(4, round(w * 0.03))
    r = r if r is not None else w * 0.12
    rgb = np.ones((h + 2 * b, w + 2 * b, 3), np.float32)
    m = rrect(w, h, max(2, r - b))[..., None]
    rgb[b:b + h, b:b + w] = rgb[b:b + h, b:b + w] * (1 - m) + photo * m
    return _with_shadow(rgb, rrect(w + 2 * b, h + 2 * b, r), pad=max(8, round(w * 0.07)), blur=max(3, w * 0.03), off=(w * 0.01, w * 0.025), k=0.26)


# ═════════ 字 ═════════
def _script(ch):
    o = ord(ch)
    if 0xAC00 <= o <= 0xD7A3 or 0x1100 <= o <= 0x11FF or 0x3130 <= o <= 0x318F:
        return 'ko'
    return 'zh'


@functools.lru_cache(maxsize=512)
def text(s, size, fill=(1, 1, 1), stroke=(1, 1, 1), stroke_w=0.14, font=None, shadow=True, tracking=0.0):
    """字貼紙（預乘 RGBA）。font=None 時逐字分：韓文 Jua、其他粉圓體；'hand'＝Gaegu 手寫、'jp'＝Mochiy Pop One。
    stroke=None 不描邊；stroke_w＝描邊寬（字級比例）。兩倍大畫再縮。"""
    SS = 2
    S = size * SS
    sw = int(round(stroke_w * S)) if stroke is not None else 0
    runs = []
    for ch in s:
        f = font or _script(ch)
        if runs and runs[-1][0] == f:
            runs[-1][1] += ch
        else:
            runs.append([f, ch])
    fonts = {f: ImageFont.truetype(FONT[f], S if f != 'hand' else int(S * 1.12)) for f, _ in runs}
    wd = sum(fonts[f].getlength(tx) for f, tx in runs) + tracking * S * max(0, len(s) - 1)
    Wd, Hd = int(wd + 2 * sw + S * 0.5), int(S * 1.6 + 2 * sw)
    lay_s = Image.new('L', (Wd, Hd), 0)
    lay_f = Image.new('L', (Wd, Hd), 0)
    ds, df = ImageDraw.Draw(lay_s), ImageDraw.Draw(lay_f)
    x = sw + S * 0.25
    for f, tx in runs:
        for ch in tx:
            if sw:
                ds.text((x, Hd / 2), ch, font=fonts[f], fill=255, anchor='lm', stroke_width=sw, stroke_fill=255)
            df.text((x, Hd / 2), ch, font=fonts[f], fill=255, anchor='lm')
            x += fonts[f].getlength(ch) + tracking * S
    aS = np.asarray(lay_s).astype(np.float32) / 255
    aF = np.asarray(lay_f).astype(np.float32) / 255
    alpha = np.maximum(aS, aF)
    ys, xs = np.nonzero(alpha > 0.01)
    if not len(ys):
        return np.zeros((2, 2, 4), np.float32)
    y0, y1, x0, x1 = max(0, ys.min() - 2), ys.max() + 3, max(0, xs.min() - 2), xs.max() + 3
    aS, aF, alpha = aS[y0:y1, x0:x1], aF[y0:y1, x0:x1], alpha[y0:y1, x0:x1]
    rgb = (np.float32(stroke if stroke is not None else fill) * (1 - aF[..., None]) + np.float32(fill) * aF[..., None])
    nh, nw = max(1, alpha.shape[0] // SS), max(1, alpha.shape[1] // SS)
    rgb = cv2.resize(rgb, (nw, nh), interpolation=cv2.INTER_AREA)
    alpha = cv2.resize(alpha, (nw, nh), interpolation=cv2.INTER_AREA)
    if shadow:
        out = _with_shadow(rgb, alpha, pad=max(6, size // 5), blur=max(2, size * 0.06), off=(size * 0.02, size * 0.06), k=0.30)
    else:
        out = np.dstack([rgb * alpha[..., None], alpha]).astype(np.float32)
    out.setflags(write=False)
    return out


@functools.lru_cache(maxsize=128)
def emoji(ch, size, outline=True):
    """彩色 emoji 貼紙（預乘 RGBA）。Noto Color Emoji 只有 109 px 的點陣，畫好再縮放；outline＝白色貼紙邊。"""
    f = ImageFont.truetype(FONT['emoji'], 109)
    im = Image.new('RGBA', (180, 180), (0, 0, 0, 0))
    ImageDraw.Draw(im).text((90, 90), ch, font=f, embedded_color=True, anchor='mm')
    a = np.asarray(im).astype(np.float32) / 255
    ys, xs = np.nonzero(a[..., 3] > 0.02)
    if not len(ys):
        return np.zeros((2, 2, 4), np.float32)
    a = a[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
    k = size / max(a.shape[:2])
    a = cv2.resize(a, (max(1, round(a.shape[1] * k)), max(1, round(a.shape[0] * k))), interpolation=cv2.INTER_AREA if k < 1 else cv2.INTER_CUBIC)
    a = np.clip(a, 0, 1)
    rgb, al = a[..., :3], a[..., 3]
    if outline:
        px = max(2, round(size * 0.07))
        A = cv2.copyMakeBorder(al, px + 2, px + 2, px + 2, px + 2, cv2.BORDER_CONSTANT, value=0)
        RGB = cv2.copyMakeBorder(rgb, px + 2, px + 2, px + 2, px + 2, cv2.BORDER_CONSTANT, value=0)
        dist = cv2.distanceTransform((A < 0.5).astype(np.uint8), cv2.DIST_L2, 5)
        ring = cv2.GaussianBlur(np.clip(px + 0.5 - dist, 0, 1).astype(np.float32), (0, 0), 0.6)
        al2 = np.maximum(A, ring)
        rgb2 = RGB * A[..., None] + (1 - A[..., None])
        out = _with_shadow(rgb2, al2, pad=max(6, size // 8), blur=max(2, size * 0.04), off=(size * 0.015, size * 0.04), k=0.28)
    else:
        out = np.dstack([rgb * al[..., None], al]).astype(np.float32)
    out.setflags(write=False)
    return out


@functools.lru_cache(maxsize=64)
def tape(lines, color, w=None, pad=(34, 16)):
    """紙膠帶標籤：lines＝((字, 字級), …) 由上到下；color '#RRGGBB'。半透明斜條紋、左右鋸齒邊。回傳預乘 RGBA。"""
    sprs = [text(s, sz, fill=INK, stroke=None, shadow=False) for s, sz in lines]
    tw = max(s.shape[1] for s in sprs)
    th = sum(s.shape[0] for s in sprs) + 6 * (len(sprs) - 1)
    W = (w or tw + 2 * pad[0])
    H = th + 2 * pad[1]
    col = np.float32(hexrgb(color))
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    stripe = (((xx + yy) % 26) < 9).astype(np.float32)
    rgb = col * (1 - 0.16 * stripe[..., None]) + 0.16 * stripe[..., None]
    zig = 7 * np.abs(((yy / 9) % 2) - 1)                   # 鋸齒邊
    a = ((xx > zig) & (xx < W - 1 - zig)).astype(np.float32) * 0.90
    y = pad[1]
    for s in sprs:
        x = pad[0]
        sa = s[..., 3:4]
        rgb[y:y + s.shape[0], x:x + s.shape[1]] = rgb[y:y + s.shape[0], x:x + s.shape[1]] * (1 - sa) + s[..., :3]
        y += s.shape[0] + 6
    out = _with_shadow(rgb, a, pad=14, blur=5, off=(2, 5), k=0.22)
    out.setflags(write=False)
    return out


@functools.lru_cache(maxsize=64)
def bubble(s, size=58, fill=(1, 1, 1), ink=INK, tail='left'):
    """對話框：圓角白底＋下方小尾巴。回傳預乘 RGBA。"""
    t = text(s, size, fill=ink, stroke=None, shadow=False)
    px, py = round(size * 0.75), round(size * 0.5)
    W, H = t.shape[1] + 2 * px, t.shape[0] + 2 * py
    tl = round(size * 0.6)
    S = 3
    im = Image.new('L', (W * S, (H + tl) * S), 0)
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([0, 0, W * S - 1, H * S - 1], radius=int(H * S * 0.46), fill=255)
    tx = W * (0.24 if tail == 'left' else 0.76)
    d.polygon([((tx - tl * 0.5) * S, (H - 4) * S), ((tx + tl * 0.5) * S, (H - 4) * S), ((tx - tl * (0.5 if tail == 'left' else -0.5)) * S, (H + tl) * S)], fill=255)
    a = np.asarray(im.resize((W, H + tl), Image.LANCZOS)).astype(np.float32) / 255
    rgb = np.ones((H + tl, W, 3), np.float32) * np.float32(fill)
    ta = t[..., 3:4]
    rgb[py:py + t.shape[0], px:px + t.shape[1]] = rgb[py:py + t.shape[0], px:px + t.shape[1]] * (1 - ta) + t[..., :3]
    out = _with_shadow(rgb, a, pad=22, blur=8, off=(3, 8), k=0.26)
    out.setflags(write=False)
    return out


@functools.lru_cache(maxsize=256)
def badge(lines, d=360, color='#FF8FB1', ink=(1, 1, 1), petals=18):
    """圓章貼紙（花邊圓）：lines＝((字, 字級), …)。白色外圈＋底色＋白字。回傳預乘 RGBA。"""
    S = 3
    R = d * S / 2
    im = Image.new('L', (d * S, d * S), 0)
    pts = []
    for i in range(petals * 16):
        a = i / (petals * 16) * 2 * math.pi
        r = R * (0.94 + 0.06 * math.cos(a * petals))
        pts.append((R + r * math.cos(a), R + r * math.sin(a)))
    ImageDraw.Draw(im).polygon(pts, fill=255)
    outer = np.asarray(im.resize((d, d), Image.LANCZOS)).astype(np.float32) / 255
    yy, xx = np.mgrid[0:d, 0:d].astype(np.float32)
    inner = np.clip(d * 0.43 - np.hypot(xx - d / 2, yy - d / 2), 0, 1)
    rgb = np.ones((d, d, 3), np.float32)
    rgb = rgb * (1 - inner[..., None]) + np.float32(hexrgb(color)) * inner[..., None]
    sprs = [text(s, sz, fill=ink, stroke=None, shadow=False, font=fnt) for s, sz, *rest in lines for fnt in [rest[0] if rest else None]]
    th = sum(s.shape[0] for s in sprs) + 4 * (len(sprs) - 1)
    y = int(d / 2 - th / 2)
    for s in sprs:
        x = int(d / 2 - s.shape[1] / 2)
        if x < 0 or y < 0 or y + s.shape[0] > d:
            y += s.shape[0] + 4
            continue
        sa = s[..., 3:4]
        rgb[y:y + s.shape[0], x:x + s.shape[1]] = rgb[y:y + s.shape[0], x:x + s.shape[1]] * (1 - sa) + s[..., :3]
        y += s.shape[0] + 4
    out = _with_shadow(rgb, outer, pad=22, blur=8, off=(3, 9), k=0.30)
    out.setflags(write=False)
    return out


@functools.lru_cache(maxsize=64)
def pin(d=90, color='#FF6F9C', label=None):
    """愛心圖釘：白邊愛心＋下方小尖端；label（一兩個字或數字）寫在愛心裡。錨點在尖端（anchor=(0.5, 1.0) 附近）。"""
    S = 3
    W, H = d * S, int(d * 1.25 * S)
    im_o = Image.new('L', (W, H), 0)
    im_i = Image.new('L', (W, H), 0)
    cx, cy = W / 2, d * S * 0.52
    def heart(r):
        return [(cx + r * math.sin(a) ** 3, cy - r * (13 * math.cos(a) - 5 * math.cos(2 * a) - 2 * math.cos(3 * a) - math.cos(4 * a)) / 16) for a in np.linspace(0, 2 * math.pi, 80)]
    ro = d * S * 0.46
    ImageDraw.Draw(im_o).polygon(heart(ro), fill=255)
    ImageDraw.Draw(im_o).polygon([(cx - ro * 0.28, cy + ro * 0.55), (cx + ro * 0.28, cy + ro * 0.55), (cx, H - 2)], fill=255)
    ImageDraw.Draw(im_i).polygon(heart(ro * 0.80), fill=255)
    o = np.asarray(im_o.resize((d, int(d * 1.25)), Image.LANCZOS)).astype(np.float32) / 255
    i = np.asarray(im_i.resize((d, int(d * 1.25)), Image.LANCZOS)).astype(np.float32) / 255
    rgb = np.ones(o.shape + (3,), np.float32)
    rgb = rgb * (1 - i[..., None]) + np.float32(hexrgb(color)) * i[..., None]
    if label:
        t = text(str(label), int(d * 0.40), fill=(1, 1, 1), stroke=None, shadow=False, font='jp')
        y, x = int(d * 0.50 - t.shape[0] / 2), int(d / 2 - t.shape[1] / 2)
        if x >= 0 and y >= 0:
            ta = t[..., 3:4]
            rgb[y:y + t.shape[0], x:x + t.shape[1]] = rgb[y:y + t.shape[0], x:x + t.shape[1]] * (1 - ta) + t[..., :3]
    out = _with_shadow(rgb, o, pad=14, blur=5, off=(2, 6), k=0.32)
    out.setflags(write=False)
    return out


# ═════════ 貼 ═════════
def paste(c, spr, cx, cy, scale=1.0, angle=0.0, op=1.0, anchor=(0.5, 0.5), sx=1.0, sy=1.0):
    """預乘 RGBA 精靈貼到畫布（RGB 或預乘 RGBA）：anchor 點放在 (cx, cy)，可縮放、旋轉（度）、壓扁拉長。就地修改 c。"""
    if op <= 0.004 or scale <= 0.01:
        return c
    hh, ww = spr.shape[:2]
    ax, ay = anchor[0] * ww, anchor[1] * hh
    ca, sa = math.cos(math.radians(angle)), math.sin(math.radians(angle))
    A = np.array([[ca * scale * sx, -sa * scale * sy], [sa * scale * sx, ca * scale * sy]])
    tv = np.array([cx, cy]) - A @ np.array([ax, ay])
    pts = np.array([[0, 0], [ww, 0], [0, hh], [ww, hh]], np.float64) @ A.T + tv
    H, W = c.shape[:2]
    x0, y0 = max(0, int(math.floor(pts[:, 0].min())) - 1), max(0, int(math.floor(pts[:, 1].min())) - 1)
    x1, y1 = min(W, int(math.ceil(pts[:, 0].max())) + 1), min(H, int(math.ceil(pts[:, 1].max())) + 1)
    if x1 <= x0 or y1 <= y0:
        return c
    if abs(angle) < 1e-3 and abs(scale * sx - 1) < 1e-3 and abs(scale * sy - 1) < 1e-3 and abs(tv[0] - round(tv[0])) < 1e-3 and abs(tv[1] - round(tv[1])) < 1e-3:
        ix, iy = int(round(tv[0])), int(round(tv[1]))        # 整數位置、不縮放不旋轉：直接貼，不重取樣
        sx0, sy0 = max(0, -ix), max(0, -iy)
        x0, y0 = max(0, ix), max(0, iy)
        x1, y1 = min(W, ix + ww), min(H, iy + hh)
        wv = spr[sy0:sy0 + (y1 - y0), sx0:sx0 + (x1 - x0)]
    else:
        M = np.float32([[A[0, 0], A[0, 1], tv[0] - x0], [A[1, 0], A[1, 1], tv[1] - y0]])
        wv = cv2.warpAffine(spr, M, (x1 - x0, y1 - y0), flags=cv2.INTER_AREA if scale < 0.6 else cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=0)
    a = wv[..., 3:4] * op
    roi = c[y0:y1, x0:x1]
    if c.shape[2] == 4:
        c[y0:y1, x0:x1] = roi * (1 - a) + wv * op
    else:
        c[y0:y1, x0:x1] = roi * (1 - a) + wv[..., :3] * op
    return c


def scallop_wipe(a, b, u, amp=26, period=150, line=10):
    """花邊換頁：b 從右往左蓋過 a，邊緣是波浪，帶一條白線與淡陰影。u 0–1。"""
    if u <= 0:
        return a
    if u >= 1:
        return b
    h, w = a.shape[:2]
    yy = np.arange(h, dtype=np.float32)[:, None]
    xx = np.arange(w, dtype=np.float32)[None, :]
    edge = (w + amp + line) * (1 - ease_out(u, 2.2)) - amp + amp * np.sin(yy / period * 2 * np.pi)
    d = xx - edge
    m = np.clip(d, 0, 1)[..., None]                          # 1＝b
    white = np.clip(1 - np.abs(d - line / 2) / (line / 2), 0, 1)[..., None]
    shade = (np.clip(1 + d / 36, 0, 1) * (d < 0))[..., None] * 0.18
    out = a * (1 - shade) * (1 - m) + b * m
    return out * (1 - white) + white


# ═════════ demo ═════════
def _demo(a):
    W, H = 1080, 1920
    c = paper(W, H, '#FFE6EE', '#FFC9DA', 'hearts').copy()
    if a.img:
        im = cv2.cvtColor(cv2.imread(a.img), cv2.COLOR_BGR2RGB)
    else:
        im = (np.dstack([np.tile(np.linspace(0.3, 0.9, 600, dtype=np.float32), (800, 1))] * 3) * 255).astype(np.uint8)
    ph = cover_crop(im, 600, 800)
    paste(c, instax(ph, 520, "14:26"), 330, 760, angle=-5)
    paste(c, instax(ph, 520, "14:27"), 720, 900, angle=6)
    paste(c, tile(cover_crop(im, 300, 300)), 220, 1500)
    paste(c, tape((('DAY 6・11/06', 40), ('青沙浦 청사포', 76)), '#FF9DBB'), 60, 150, angle=-2, anchor=(0, 0.5))
    paste(c, bubble('在馬路中間跳起來', 56), 620, 1420)
    paste(c, badge((('這一站', 44), ('367', 120, 'jp'), ('張', 44)), 380, '#FF8FB1'), 800, 1600, angle=8)
    paste(c, pin(110, '#FF6F9C', 5), 150, 1150, anchor=(0.5, 0.95))
    for k, e in enumerate('🌊💙🥯🎆🍁'):
        paste(c, emoji(e, 120), 150 + 190 * k, 400, angle=(-10, 8, -5, 12, -8)[k])
    paste(c, text('釜山手帳', 170, fill=hexrgb('#FF6F9C'), stroke=(1, 1, 1)), 540, 1790)
    out = (np.clip(c, 0, 1) * 255 + 0.5).astype(np.uint8)
    os.makedirs(os.path.dirname(os.path.abspath(a.o)), exist_ok=True)
    cv2.imwrite(a.o, cv2.cvtColor(out, cv2.COLOR_RGB2BGR), [cv2.IMWRITE_JPEG_QUALITY, 90])
    print('寫入', a.o)


if __name__ == '__main__':
    import argparse
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('cmd', choices=['demo'])
    p.add_argument('-o', default='out/cutefx_demo.jpg')
    p.add_argument('--img')
    _demo(p.parse_args())
