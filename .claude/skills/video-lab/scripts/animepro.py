#!/usr/bin/env python3
"""動漫風・撮影質感版（seek(t) 引擎用）：高質感動畫的「撮影」後製，套在實拍上。

animefx.py 的卡通濾鏡（色塊＋描邊）、平面向量特效（白集中線、放射色塊、膠囊徽章、遊戲對話框）、粗描邊字，
使用者看了說「很陽春的動畫」。高級的動漫感不是把實拍畫成卡通，而是動畫撮影那一層：
  光（ブルーム、ディフュージョン、透過光、光束、鏡頭光斑）、空氣（パラ、景深粒子、浮塵）、天空色彩、
  有體積與光澤的元素（立體打光的球、玻璃質感的徽章與面板）、打在拍上的鏡頭動作（推近、放射模糊、色散）。

全部是 t 的純函式；影像 float32 RGB 0–1。用法與分寸見 references/anime.md〈四之二〉。

  python animepro.py demo in.jpg -o qa/animepro_demo.jpg
"""
import argparse
import functools
import math
import os
import sys

import cv2
import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from seekkit import CJK_B, CJK_R, CJK_TC, blit, ease, ease_out, frame_rng, text_sprite  # noqa: E402

GOLD = (1.00, 0.84, 0.45)
WARM = (1.00, 0.90, 0.78)
COOL = (0.75, 0.88, 1.00)
RED = (0.88, 0.07, 0.10)
TYPE = {'火': (1.00, 0.45, 0.16), '水': (0.22, 0.58, 1.00), '草': (0.36, 0.80, 0.30), '森': (0.20, 0.62, 0.38),
        '土': (0.86, 0.62, 0.28), '雲': (0.62, 0.74, 1.00)}


def lum(x):
    return x[..., 0] * 0.2126 + x[..., 1] * 0.7152 + x[..., 2] * 0.0722


# ───────────────────────── 合成工具 ─────────────────────────
def _shift(img, fx, fy):
    if fx < 1e-3 and fy < 1e-3:
        return img
    h, w = img.shape[:2]
    img = cv2.copyMakeBorder(img, 0, 1, 0, 1, cv2.BORDER_CONSTANT, value=0)
    return cv2.warpAffine(img, np.float32([[1, 0, fx], [0, 1, fy]]), (w + 1, h + 1), flags=cv2.INTER_LINEAR)


def add(c, rgb, x, y, op=1.0):
    """加光（screen 合成）：rgb＝光的顏色與亮度（黑＝不加），(x, y) 左上角，次像素。"""
    if op <= 0.004:
        return
    ix, iy = math.floor(x), math.floor(y)
    rgb = _shift(rgb, x - ix, y - iy)
    h, w = rgb.shape[:2]
    x0, y0, x1, y1 = max(0, ix), max(0, iy), min(c.shape[1], ix + w), min(c.shape[0], iy + h)
    if x1 <= x0 or y1 <= y0:
        return
    s = rgb[y0 - iy:y1 - iy, x0 - ix:x1 - ix]
    c[y0:y1, x0:x1] = 1 - (1 - c[y0:y1, x0:x1]) * (1 - np.clip(s * op, 0, 1))


def add_c(c, rgb, cx, cy, op=1.0):
    add(c, rgb, cx - rgb.shape[1] / 2, cy - rgb.shape[0] / 2, op)


def screen(c, layer, k=1.0):
    c[:] = 1 - (1 - c) * (1 - np.clip(layer * k, 0, 1))


def glow_layer(layer, r=24, k=1.4):
    """光的圖層加上光暈：1/4 解析度多尺度模糊，再加回原圖層。"""
    h, w = layer.shape[:2]
    s = cv2.resize(layer, (w // 4, h // 4), interpolation=cv2.INTER_AREA)
    g = 0.5 * cv2.GaussianBlur(s, (0, 0), r / 16) + 0.35 * cv2.GaussianBlur(s, (0, 0), r / 8) + 0.25 * cv2.GaussianBlur(s, (0, 0), r / 4)
    return layer + cv2.resize(g, (w, h), interpolation=cv2.INTER_LINEAR) * k


# ───────────────────────── 1. 撮影調色 ─────────────────────────
def _sky_mask(x):
    h, w = x.shape[:2]
    s = cv2.resize(x, (w // 8, h // 8), interpolation=cv2.INTER_AREA)
    L = lum(s)
    blue = ((s[..., 2] - s[..., 0]) > 0.07) & (L > 0.30)
    m = blue.astype(np.float32)
    m = cv2.dilate(m, np.ones((5, 5), np.uint8))          # 雲（白、不藍）只要貼著藍天就算
    bright = (L > 0.55).astype(np.float32)
    m = np.maximum(m * 1.0, bright * cv2.GaussianBlur(m, (0, 0), 3) * 1.5)
    yy = np.linspace(0, 1, m.shape[0], dtype=np.float32)[:, None]
    m = np.clip(m, 0, 1) * np.clip(1 - (yy - 0.25) / 0.35, 0, 1)   # 只在畫面上半
    m = cv2.GaussianBlur(m, (0, 0), 2.5)
    return cv2.resize(m, (w, h), interpolation=cv2.INTER_LINEAR)[..., None]


def satsuei(img, sky=True, paint=0.32, sat=1.22, shadow=(0.020, 0.035, 0.085), warm=(0.030, 0.012, -0.022)):
    """動畫撮影調色：輕微繪畫感（邊緣保留平滑，不描邊、不色階化）＋飽和＋暗部藍紫、亮部暖＋天空（新海誠式青藍漸層、雲更白）。"""
    x = np.clip(img, 0, 1).astype(np.float32)
    h, w = x.shape[:2]
    if paint > 0:
        s = cv2.resize(x, (w // 2, h // 2), interpolation=cv2.INTER_AREA)
        s = cv2.bilateralFilter(s, 9, 0.07, 5)
        s = cv2.bilateralFilter(s, 7, 0.05, 4)
        x = x * (1 - paint) + cv2.resize(s, (w, h), interpolation=cv2.INTER_CUBIC) * paint
    L = lum(x)[..., None]
    x = L + (x - L) * sat
    blue = np.clip((x[..., 2:3] - x[..., 0:1]) * 3, 0, 1)
    x = x + blue * np.float32([-0.02, 0.025, 0.02])         # 藍往青
    green = np.clip((x[..., 1:2] - np.maximum(x[..., 0:1], x[..., 2:3])) * 4, 0, 1)
    x = x + green * np.float32([0.03, 0.02, -0.03])         # 綠往黃綠，比較鮮
    sh = np.clip(1 - L / 0.45, 0, 1) ** 1.5
    hi = np.clip((L - 0.6) / 0.4, 0, 1)
    x = x + sh * np.float32(shadow) + hi * np.float32(warm)
    if sky:
        m = _sky_mask(x)
        if float(m.max()) > 0.2:
            yy = np.linspace(0, 1, h, dtype=np.float32)[:, None, None]
            top, bot = np.float32([0.08, 0.32, 0.80]), np.float32([0.52, 0.78, 0.98])
            g = top + (bot - top) * np.clip(yy / 0.5, 0, 1)
            Lx = lum(x)[..., None]
            cloud = np.clip((Lx - 0.68) / 0.22, 0, 1) * np.clip(1 - (x.max(-1, keepdims=True) - x.min(-1, keepdims=True)) * 3, 0, 1)
            tgt = g * (1 - cloud) + np.clip(x * 1.10 + 0.04, 0, 1) * cloud
            x = x * (1 - m * 0.62) + tgt * m * 0.62
    return np.clip(x, 0, 1)


def bloom(c, thr=0.62, k=0.38, r=30, tint=WARM):
    """ブルーム：亮部往外暈（多尺度），screen 疊回去。"""
    h, w = c.shape[:2]
    s = cv2.resize(c, (w // 4, h // 4), interpolation=cv2.INTER_AREA)
    hi = np.clip((lum(s) - thr) / (1 - thr), 0, 1)[..., None] ** 1.6 * s
    g = 0.5 * cv2.GaussianBlur(hi, (0, 0), r / 16) + 0.3 * cv2.GaussianBlur(hi, (0, 0), r / 8) + 0.25 * cv2.GaussianBlur(hi, (0, 0), r / 4)
    screen(c, cv2.resize(g, (w, h), interpolation=cv2.INTER_LINEAR) * np.float32(tint), k)


def diffusion(c, k=0.10):
    """ディフュージョン：整張畫面一層柔焦光（動畫撮影的空氣感）。"""
    h, w = c.shape[:2]
    s = cv2.GaussianBlur(cv2.resize(c, (w // 4, h // 4), interpolation=cv2.INTER_AREA), (0, 0), 5)
    screen(c, cv2.resize(s, (w, h), interpolation=cv2.INTER_LINEAR), k)


def para(c, top=None, bottom=None, k_top=0.3, k_bot=0.3, mode='soft'):
    """パラ：上／下方漸層色光（時段、空氣）。mode='soft' 柔光式，不會把畫面洗灰。"""
    h = c.shape[0]
    y = np.linspace(0, 1, h, dtype=np.float32)[:, None, None]
    for col, k, wgt in ((top, k_top, np.clip(1 - y / 0.6, 0, 1) ** 1.4), (bottom, k_bot, np.clip((y - 0.4) / 0.6, 0, 1) ** 1.4)):
        if col is None or k <= 0:
            continue
        col = np.float32(col)
        soft = np.where(col < 0.5, c - (1 - 2 * col) * c * (1 - c), c + (2 * col - 1) * (np.sqrt(np.clip(c, 0, 1)) - c))
        c[:] = c * (1 - wgt * k) + soft * wgt * k


def desat(c, k=0.5, tint=(0.80, 0.88, 1.0)):
    L = lum(c)[..., None]
    c[:] = c * (1 - k) + L * np.float32(tint) * k


def vignette(c, k=0.25):
    h, w = c.shape[:2]
    c *= _vig(h, w, k)


@functools.lru_cache(maxsize=4)
def _vig(h, w, k):
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    r = np.sqrt(((xx - w / 2) / (w / 2)) ** 2 + ((yy - h / 2) / (h / 1.7)) ** 2) / math.sqrt(2)
    return (1 - k * np.clip(r, 0, 1.2) ** 2.2)[..., None]


# ───────────────────────── 2. 光：透過光、景深光斑、光束、鏡頭光斑、漏光 ─────────────────────────
@functools.lru_cache(maxsize=64)
def glint_sprite(size, col=(1.0, 0.97, 0.90), diag=0.35):
    """透過光：細長十字光芒（指數衰減）＋短斜芒＋芯＋光暈。加光用（add），不是貼圖。"""
    S = int(size * 2) | 1
    c0 = S // 2
    yy, xx = np.mgrid[0:S, 0:S].astype(np.float32) - c0
    wd = 0.012 * size + 0.7
    rx = np.exp(-np.abs(xx) / size * 4.2) * np.exp(-(yy / wd) ** 2)
    ry = np.exp(-np.abs(yy) / size * 4.2) * np.exp(-(xx / wd) ** 2)
    u, v = (xx + yy) / math.sqrt(2), (xx - yy) / math.sqrt(2)
    rd = (np.exp(-np.abs(u) / size * 9) * np.exp(-(v / wd) ** 2) + np.exp(-np.abs(v) / size * 9) * np.exp(-(u / wd) ** 2)) * diag
    r2 = xx * xx + yy * yy
    core = np.exp(-r2 / (2 * (0.05 * size) ** 2)) * 1.3
    halo = np.exp(-r2 / (2 * (0.22 * size) ** 2)) * 0.30
    I = rx + ry + rd + core + halo
    return np.clip(I[..., None] * np.float32(col), 0, 1)


def glints(c, t, pts, size=60, col=(1.0, 0.97, 0.90), period=1.1, op=1.0):
    """透過光閃爍：pts=[(x, y, phase)]，每顆依 phase 錯開亮起。"""
    for x, y, ph in pts:
        u = (t / period + ph) % 1.0
        s = math.sin(u * math.pi) ** 3
        if s < 0.04:
            continue
        add_c(c, glint_sprite(max(8, int(size * (0.55 + 0.45 * s))), col), x, y, op * s)


@functools.lru_cache(maxsize=64)
def bokeh_sprite(d, col, soft=0.0):
    """景深光斑：圓盤＋略亮的外緣（真實鏡頭的光斑長這樣）；soft>0 再糊一點（更遠／更近）。"""
    S = int(d * 1.3) + 6
    c0 = S / 2
    yy, xx = np.mgrid[0:S, 0:S].astype(np.float32)
    r = np.sqrt((xx - c0) ** 2 + (yy - c0) ** 2)
    R = d / 2
    disk = np.clip((R - r) / max(1.0, 0.06 * R), 0, 1)
    rim = np.exp(-((r - R * 0.88) / (0.08 * R + 0.5)) ** 2) * 0.35
    I = (0.42 + rim) * disk
    if soft:
        I = cv2.GaussianBlur(I, (0, 0), soft * R * 0.25 + 0.5)
    return np.clip(I[..., None] * np.float32(col), 0, 1)


def scatter(seed, n, x0, y0, x1, y1):
    r = np.random.default_rng(seed)
    return [(x0 + (x1 - x0) * r.random(), y0 + (y1 - y0) * r.random(), r.random()) for _ in range(n)]


def bokeh(c, t, n=24, seed=0, region=None, dmin=30, dmax=150, cols=(WARM, GOLD), k=0.8, vx=0.0, vy=-18.0):
    """浮在空氣裡的景深光斑：大的近（糊、淡）、小的遠（清楚），慢慢飄、亮度呼吸。"""
    if k <= 0:
        return
    h, w = c.shape[:2]
    x0, y0, x1, y1 = region or (0, 0, w, h)
    r = np.random.default_rng(4000 + seed)
    for i in range(n):
        z, px, py, ph = r.random(), r.random(), r.random(), r.random()
        d = int(dmin + (dmax - dmin) * z ** 1.5)
        spd = 0.4 + 0.9 * z
        x = x0 + ((px * (x1 - x0) + vx * spd * t) % (x1 - x0 + d)) - d / 2
        y = y0 + ((py * (y1 - y0) + vy * spd * t) % (y1 - y0 + d)) - d / 2
        tw = 0.55 + 0.45 * math.sin(t * (1.2 + ph) + ph * 6.28)
        col = cols[i % len(cols)]
        add_c(c, bokeh_sprite(d, tuple(col), round(z * 0.8, 1)), x, y, k * tw * (0.55 + 0.45 * (1 - z)))


def god_rays(c, cx, cy, k=0.5, thr=0.70, n=12, spread=0.055, tint=WARM):
    """光束：亮部從 (cx, cy) 往外放射（1/4 解析度）。"""
    if k <= 0:
        return
    h, w = c.shape[:2]
    s = 4
    sm = cv2.resize(c, (w // s, h // s), interpolation=cv2.INTER_AREA)
    hi = np.clip((lum(sm) - thr) / (1 - thr), 0, 1)[..., None] * sm
    acc = np.zeros_like(hi)
    for i in range(n):
        z = 1 + spread * i
        M = np.float32([[z, 0, cx / s * (1 - z)], [0, z, cy / s * (1 - z)]])
        acc += cv2.warpAffine(hi, M, (w // s, h // s)) * (1 - i / n)
    acc = cv2.resize(acc / n * 2.4, (w, h), interpolation=cv2.INTER_LINEAR) * np.float32(tint)
    screen(c, acc, k)


@functools.lru_cache(maxsize=8)
def _ray_base(w, h, seed):
    r = np.random.default_rng(seed)
    return r.random(24) * 6.28, r.random(24) * 0.6 + 0.4, r.integers(5, 40, 24)


def halo_rays(c, t, cx, cy, k=0.3, col=GOLD, r0=120, seed=0, spin=0.12):
    """後光：主體背後一圈柔和的放射光束（體積光，不是放射色塊），中心淡、中段最亮。"""
    if k <= 0:
        return
    h, w = c.shape[:2]
    s = 4
    yy, xx = np.mgrid[0:h // s, 0:w // s].astype(np.float32)
    dx, dy = xx * s - cx, yy * s - cy
    a = np.arctan2(dy, dx) + spin * t
    rr = np.sqrt(dx * dx + dy * dy)
    ph, amp, fr = _ray_base(w, h, seed)
    v = np.zeros_like(a)
    for p, am, f in zip(ph, amp, fr):
        v += am * (0.5 + 0.5 * np.cos(a * f + p + 0.3 * math.sin(t * 0.7 + p)))
    v = np.clip((v / len(ph) - 0.40) * 3.6, 0, 1) ** 1.6
    fall = np.clip((rr - r0) / 180, 0, 1) * np.exp(-rr / (0.55 * max(w, h)))
    lay = cv2.GaussianBlur(v * fall, (0, 0), 1.5) * 1.8
    lay = cv2.resize(lay, (w, h), interpolation=cv2.INTER_LINEAR)[..., None] * np.float32(col)
    screen(c, lay, k)


def lens_flare(c, sx, sy, k=0.6, seed=0):
    """鏡頭光斑：光源往畫面中心連線上的鬼影（彩色圓環與圓盤）＋水平變形光帶＋光源光暈。"""
    if k <= 0:
        return
    h, w = c.shape[:2]
    cx, cy = w / 2, h / 2
    vx, vy = cx - sx, cy - sy
    ghosts = [(0.35, 60, (0.55, 0.85, 1.0), 0.45), (0.62, 26, (1.0, 0.75, 0.45), 0.6), (0.95, 110, (0.55, 1.0, 0.75), 0.25),
              (1.25, 44, (0.85, 0.55, 1.0), 0.45), (1.6, 150, (0.6, 0.8, 1.0), 0.2), (1.9, 34, (1.0, 0.85, 0.55), 0.55)]
    for f, rad, col, a in ghosts:
        add_c(c, bokeh_sprite(int(rad * 2), col, 0.6), sx + vx * f, sy + vy * f, k * a)
    add_c(c, glint_sprite(260, (1.0, 0.95, 0.85), 0.2), sx, sy, k)
    st = np.zeros((40, w * 2, 3), np.float32)
    yy = np.arange(40, dtype=np.float32)[:, None]
    xx = np.arange(w * 2, dtype=np.float32)[None, :]
    st[..., :] = (np.exp(-((yy - 20) / 3.0) ** 2) * np.exp(-np.abs(xx - w) / (w * 0.35)))[..., None] * np.float32([0.45, 0.70, 1.0])
    add_c(c, st, sx, sy, k * 0.7)


def light_leak(c, t, k=0.35, seed=0, col=(1.0, 0.55, 0.22), side='left'):
    """漏光：畫面邊緣一團暖色光慢慢移動、呼吸（screen）。"""
    if k <= 0:
        return
    h, w = c.shape[:2]
    s = 8
    yy, xx = np.mgrid[0:h // s, 0:w // s].astype(np.float32)
    r = np.random.default_rng(seed)
    ph = r.random() * 6.28
    lx = (0.0 if side == 'left' else 1.0) * w / s + math.sin(t * 0.6 + ph) * w / s * 0.12
    ly = h / s * (0.35 + 0.25 * math.sin(t * 0.45 + ph * 2))
    g = np.exp(-(((xx - lx) / (w / s * 0.45)) ** 2 + ((yy - ly) / (h / s * 0.35)) ** 2))
    g *= 0.8 + 0.2 * math.sin(t * 1.7 + ph)
    lay = cv2.resize(g, (w, h), interpolation=cv2.INTER_LINEAR)[..., None] * np.float32(col)
    screen(c, lay, k)


def light_sweep(c, u, k=0.35, width=0.16, angle=0.35, col=(1.0, 0.95, 0.85)):
    """一道柔光帶斜掃過畫面（箔面、卡、片名用）。u 0→1。"""
    if k <= 0 or u <= 0 or u >= 1:
        return
    h, w = c.shape[:2]
    s = 4
    yy, xx = np.mgrid[0:h // s, 0:w // s].astype(np.float32)
    d = (xx * s / w + yy * s / h * angle) - (-0.3 + 1.6 * u)
    band = np.exp(-(d / width) ** 2)
    lay = cv2.resize(band, (w, h), interpolation=cv2.INTER_LINEAR)[..., None] * np.float32(col)
    screen(c, lay, k)


# ───────────────────────── 3. 鏡頭動作：推近、放射模糊、色散、發光閃 ─────────────────────────
def punch(img, t, t0, dur=0.32, zoom=0.07, rgb=8.0, blur=0.6, cx=0.5, cy=0.5):
    """打在拍上：t0 那一下畫面放大後回彈、放射模糊與色散一起衰減（取代全白閃）。不在範圍內原樣回傳。"""
    e = (t - t0) / dur
    if e < 0 or e >= 1:
        return img
    u = (1 - ease_out(e)) ** 1.3
    h, w = img.shape[:2]
    px, py = w * cx, h * cy

    def sc(im, z):
        M = np.float32([[z, 0, px * (1 - z)], [0, z, py * (1 - z)]])
        return cv2.warpAffine(im, M, (w, h), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
    z = 1 + zoom * u
    out = sc(img, z)
    if blur > 0 and u > 0.05:
        acc = out.copy()
        n = 5
        for i in range(1, n):
            acc += sc(img, z * (1 + 0.014 * blur * u * i))
        out = acc / n
    if rgb > 0 and u > 0.05:
        dz = rgb * u / (w / 2)
        r_ = sc(out[..., 0], 1 + dz)
        b_ = sc(out[..., 2], 1 - dz)
        out = np.dstack([r_, out[..., 1], b_])
    return out


def luminous(c, k):
    """發光閃：不是蓋一層白，而是整張曝光往上推＋亮部暈開（畫面還看得到）。"""
    if k <= 0:
        return
    c[:] = 1 - (1 - c) * (1 - k * 0.75)
    bloom(c, 0.45, k * 0.9, 40, (1.0, 0.97, 0.92))


def flash_k(t, t0, frames=4, fps=30, peak=0.9):
    e = (t - t0) * fps
    return 0.0 if e < 0 or e >= frames else peak * (1 - e / frames) ** 1.5


def smear(img, k=1.0, angle=0.0, length=60):
    """方向模糊（倒帶、甩鏡的拖影），1/2 解析度算。"""
    if k <= 0:
        return img
    h, w = img.shape[:2]
    s = cv2.resize(img, (w // 2, h // 2), interpolation=cv2.INTER_AREA)
    L = max(3, int(length * k / 2)) | 1
    ker = np.zeros((L, L), np.float32)
    ker[L // 2, :] = 1.0 / L
    if angle:
        M = cv2.getRotationMatrix2D((L / 2 - 0.5, L / 2 - 0.5), math.degrees(angle), 1.0)
        ker = cv2.warpAffine(ker, M, (L, L))
        ker /= max(ker.sum(), 1e-6)
    b = cv2.filter2D(s, -1, ker)
    return cv2.resize(b, (w, h), interpolation=cv2.INTER_LINEAR)


def impact_duo(c, dark=(0.04, 0.02, 0.10), mid=(0.80, 0.08, 0.16), light=(1.0, 0.96, 0.90)):
    """衝擊格（質感版）：該格實拍做成三色分色（深靛、朱紅、米白），不是黑白反轉。只放 2 格。"""
    L = cv2.GaussianBlur(lum(c), (0, 0), 1.0)
    m1 = np.clip((L - 0.22) / 0.18, 0, 1)[..., None]
    m2 = np.clip((L - 0.55) / 0.15, 0, 1)[..., None]
    c[:] = np.float32(dark) * (1 - m1) + np.float32(mid) * m1 * (1 - m2) + np.float32(light) * m2


def speed_lines(c, t, cx, cy, k=0.5, n=150, inner=0.40, fps=30, seed=0, col=(1, 1, 1)):
    """集中線（質感版）：很多條細線、半透明、每格往內推進，加一點光暈；尖端停在 inner×半對角線外。"""
    if k <= 0:
        return
    h, w = c.shape[:2]
    lay = np.zeros((h // 2, w // 2), np.float32)
    f = int(round(t * fps))
    r = np.random.default_rng(6000 + seed)
    half = math.hypot(w, h) / 2
    for i in range(n):
        a = r.random() * 2 * math.pi
        ln = 0.25 + 0.5 * r.random()
        sp = 0.02 + 0.04 * r.random()
        off = ((f * sp + r.random()) % 1.0)
        r1 = half * (inner + (1 - inner) * (1 - off) * 0.6 + 0.05)
        r2 = r1 + half * ln
        al = 0.45 + 0.55 * r.random()
        p1 = (cx + math.cos(a) * r1, cy + math.sin(a) * r1)
        p2 = (cx + math.cos(a) * r2, cy + math.sin(a) * r2)
        cv2.line(lay, (int(p1[0] / 2 * 16), int(p1[1] / 2 * 16)), (int(p2[0] / 2 * 16), int(p2[1] / 2 * 16)), al, 1 + (r.random() < 0.25), cv2.LINE_AA, shift=4)
    lay = cv2.resize(lay, (w, h), interpolation=cv2.INTER_LINEAR)[..., None] * np.float32(col)
    screen(c, glow_layer(lay, 10, 0.8), k)


def shockwave(c, e, x, y, rmax=420, dur=0.45, col=(1.0, 0.92, 0.75), width=10, k=1.0):
    """衝擊波光環：細亮環從 (x, y) 擴散、變細、淡掉，帶光暈。e＝開始後秒數。"""
    if e < 0 or e > dur:
        return
    u = e / dur
    rad = rmax * ease_out(u)
    h, w = c.shape[:2]
    pad = int(rad + 60)
    x0, y0 = int(x - pad), int(y - pad)
    lay = np.zeros((2 * pad, 2 * pad), np.float32)
    cv2.circle(lay, (pad * 4, pad * 4), int(rad * 4), 1.0, max(1, int(width * (1 - u))), cv2.LINE_AA, shift=2)
    lay = lay[..., None] * np.float32(col)
    add(c, glow_layer(lay, 20, 1.2), x0, y0, k * (1 - u) ** 0.8)


# ───────────────────────── 4. 粒子（光的圖層＋景深） ─────────────────────────
def embers(c, t, k=1.0, seed=0, n=90, region=None, t0=0.0, col=(1.0, 0.55, 0.15)):
    """火星：細短的發光拖尾往上飄、閃爍，整層加光暈。"""
    if k <= 0:
        return
    h, w = c.shape[:2]
    x0, y0, x1, y1 = region or (0, 0, w, h)
    lay = np.zeros((h, w, 3), np.float32)
    r = np.random.default_rng(7000 + seed)
    e = t - t0
    for _ in range(n):
        px, py, sp, ph, z = r.random(), r.random(), 0.6 + 0.9 * r.random(), r.random(), r.random()
        vy = -(180 + 320 * sp)
        vx = math.sin(e * 2.2 * sp + ph * 6) * 50
        x = x0 + px * (x1 - x0) + math.sin(e * 1.3 + ph * 9) * 30
        y = y1 - ((py * (y1 - y0) - vy * e) % (y1 - y0))
        fl = 0.55 + 0.45 * math.sin(e * 25 * sp + ph * 11)
        L = 10 + 26 * z
        cv2.line(lay, (int(x * 4), int(y * 4)), (int((x - vx * 0.03) * 4), int((y - vy * 0.03 * L / 10) * 4)),
                 tuple(float(v * fl) for v in (col[0], col[1] * (0.7 + 0.3 * z), col[2])), 2 + int(4 * z), cv2.LINE_AA, shift=2)
    screen(c, glow_layer(lay, 26, 2.2), k)


def dust(c, t, k=0.6, seed=0, n=60, region=None, col=WARM):
    """浮塵：光裡慢慢飄的小亮點（遠的清楚、近的大而糊）。"""
    bokeh(c, t, n, seed, region, 6, 40, (col,), k, vx=8, vy=-6)


@functools.lru_cache(maxsize=64)
def _leaf_spr(r, col, blur):
    S = int(r * 3) | 1
    im = Image.new('L', (S * 4, S * 4), 0)
    d = ImageDraw.Draw(im)
    c0 = S * 2
    pts = []
    for i in range(41):                      # 葉形：上下兩條弧，尖端在左右
        u = i / 40
        pts.append((c0 + (u * 2 - 1) * r * 4, c0 - math.sin(u * math.pi) ** 0.8 * r * 4 * 0.42))
    for i in range(41):
        u = 1 - i / 40
        pts.append((c0 + (u * 2 - 1) * r * 4, c0 + math.sin(u * math.pi) ** 0.8 * r * 4 * 0.30))
    d.polygon(pts, fill=255)
    a = np.asarray(im.resize((S, S), Image.LANCZOS), np.float32) / 255
    vein = np.zeros_like(a)
    cv2.line(vein, (int(c0 / 4 - r), int(c0 / 4)), (int(c0 / 4 + r), int(c0 / 4)), 1.0, 1, cv2.LINE_AA)
    out = np.zeros((S, S, 4), np.float32)
    yy = np.linspace(0, 1, S, dtype=np.float32)[:, None]
    base = np.float32(col)
    out[..., :3] = base * (1.15 - 0.35 * yy[..., None]) * (1 - 0.25 * vein[..., None] * a[..., None])
    out[..., 3] = a
    if blur:
        out[..., :3] *= out[..., 3:4]
        out = cv2.GaussianBlur(out, (0, 0), blur)
        out[..., :3] /= np.maximum(out[..., 3:4], 1e-6)
    return np.clip(out, 0, 1)


def _rot(spr, deg):
    if abs(deg) < 0.5:
        return spr
    h, w = spr.shape[:2]
    D = int(math.hypot(w, h)) + 2
    pad = np.zeros((D, D, spr.shape[2]), np.float32)
    y0, x0 = (D - h) // 2, (D - w) // 2
    pad[y0:y0 + h, x0:x0 + w] = spr
    if spr.shape[2] == 4:
        pad[..., :3] *= pad[..., 3:4]
    M = cv2.getRotationMatrix2D((D / 2, D / 2), deg, 1.0)
    pad = cv2.warpAffine(pad, M, (D, D), flags=cv2.INTER_LINEAR)
    if spr.shape[2] == 4:
        pad[..., :3] /= np.maximum(pad[..., 3:4], 1e-6)
    return pad


def leaves(c, t, k=1.0, seed=0, n=26, t0=0.0, cols=((0.42, 0.78, 0.26), (0.62, 0.84, 0.30), (0.30, 0.62, 0.22))):
    """落葉（景深）：近的大而糊、遠的小而清楚，旋轉飄落。"""
    if k <= 0:
        return
    h, w = c.shape[:2]
    r = np.random.default_rng(8000 + seed)
    e = t - t0
    for i in range(n):
        z, px, py, sp, ph, rot = r.random(), r.random(), r.random(), 0.6 + 0.8 * r.random(), r.random(), r.random()
        size = int(10 + 40 * z ** 2)
        blur = round(max(0.0, (z - 0.6) * 12), 0)
        y = ((py * (h + 200) + e * (160 + 200 * z) * sp) % (h + 200)) - 100
        x = px * w + math.sin(e * 1.6 * sp + ph * 6) * (40 + 60 * z)
        spr = _rot(_leaf_spr(size, cols[i % len(cols)], blur), (rot * 360 + e * 150 * sp) % 360)
        blit(c, spr, x, y, k * (0.75 + 0.25 * (1 - z)), anchor='c')


def caustics(c, t, k=0.28, y0=0.45, col=(0.80, 1.0, 1.0), scale=1.0):
    """水面焦散：會動的亮網紋，只在畫面 y0 以下（泳池）。"""
    if k <= 0:
        return
    h, w = c.shape[:2]
    s = 4
    yy, xx = np.mgrid[0:h // s, 0:w // s].astype(np.float32) * s / 60 * scale
    v1 = np.sin(xx * 1.1 + np.sin(yy * 0.9 + t * 1.3) * 1.8 + t * 0.8)
    v2 = np.sin(yy * 1.3 + np.sin(xx * 0.8 - t * 1.1) * 1.6 - t * 0.6)
    lines = np.exp(-((v1 + v2) ** 2) / 0.10)
    m = np.clip((np.linspace(0, 1, h // s, dtype=np.float32)[:, None] - y0) / 0.15, 0, 1)
    lay = cv2.resize(cv2.GaussianBlur(lines * m, (0, 0), 0.8), (w, h), interpolation=cv2.INTER_LINEAR)[..., None] * np.float32(col)
    screen(c, lay, k)


def clouds_fg(c, t, k=0.35, seed=0):
    """前景雲霧：畫面邊緣大片柔白慢慢飄過（像鏡頭前的雲）。"""
    if k <= 0:
        return
    h, w = c.shape[:2]
    s = 8
    r = np.random.default_rng(9000 + seed)
    yy, xx = np.mgrid[0:h // s, 0:w // s].astype(np.float32)
    acc = np.zeros_like(xx)
    for _ in range(9):
        cx = (r.random() * (w + 600) + t * (40 + 60 * r.random())) % (w + 600) - 300
        cy = (r.random() * 0.5 + (0 if r.random() < 0.5 else 0.55)) * h
        rx, ry = (220 + 260 * r.random()) / s, (90 + 120 * r.random()) / s
        acc += np.exp(-(((xx - cx / s) / rx) ** 2 + ((yy - cy / s) / ry) ** 2))
    lay = cv2.resize(cv2.GaussianBlur(np.clip(acc, 0, 1), (0, 0), 3), (w, h), interpolation=cv2.INTER_LINEAR)[..., None]
    c[:] = c * (1 - lay * k) + np.float32([0.97, 0.98, 1.0]) * lay * k


# ───────────────────────── 5. 閃電（質感版） ─────────────────────────
def _bolt(p0, p1, rng, depth=7, disp=0.13):
    pts = [np.float32(p0), np.float32(p1)]
    for d in range(depth):
        out = [pts[0]]
        for a, b in zip(pts[:-1], pts[1:]):
            v = b - a
            m = (a + b) / 2 + np.float32([-v[1], v[0]]) * (rng.random() - 0.5) * disp * (0.65 ** d) * 2
            out += [m, b]
        pts = out
    return np.array(pts, np.float32)


def lightning(c, t, p0, p1, k=1.0, seed=0, fps=30, col=(1.0, 0.86, 0.35), relight=0.10):
    """閃電：細白芯＋多層黃色光暈＋細分岔；每 2 格重劈一次、亮度閃爍；整個畫面跟著被照亮一下。"""
    if k <= 0:
        return
    h, w = c.shape[:2]
    fq = math.floor(t * fps / 2)
    rng = np.random.default_rng(9500 + seed * 101 + fq)
    fl = 0.55 + 0.45 * frame_rng(t, fps, 9600 + seed).random()
    lay = np.zeros((h, w), np.float32)
    main = _bolt(p0, p1, rng)
    cv2.polylines(lay, [np.round(main * 4).astype(np.int32)], False, 1.0, 5, cv2.LINE_AA, shift=2)
    for _ in range(3):
        base = main[int(len(main) * (0.2 + 0.6 * rng.random()))]
        v = np.float32(p1) - np.float32(p0)
        ang = math.atan2(v[1], v[0]) + (rng.random() - 0.5) * 1.4
        L = float(np.linalg.norm(v)) * (0.15 + 0.25 * rng.random())
        br = _bolt(base, base + np.float32([math.cos(ang), math.sin(ang)]) * L, rng, 5, 0.18)
        cv2.polylines(lay, [np.round(br * 4).astype(np.int32)], False, 0.6, 1, cv2.LINE_AA, shift=2)
    rgb = lay[..., None] * np.float32([1, 1, 1])
    g = glow_layer(lay[..., None] * np.float32(col), 60, 4.0)
    screen(c, (rgb + g) * fl, k)
    if relight:
        screen(c, np.ones_like(c[:1, :1]) * np.float32(col), relight * fl * k)


# ───────────────────────── 6. 收服用的球（立體打光）、轉場、能量 ─────────────────────────
@functools.lru_cache(maxsize=64)
def ball_sprite(d, glow=0.0):
    """立體的紅白球：漫射＋高光＋菲涅耳邊緣光＋環境反射；中間黑帶有倒角、中央按鈕有凹凸。3 倍超取樣。glow＝按鈕發光 0–1。"""
    S = 3
    D = d * S
    yy, xx = np.mgrid[0:D, 0:D].astype(np.float32)
    nx, ny = (xx + 0.5) / D * 2 - 1, (yy + 0.5) / D * 2 - 1
    r2 = nx * nx + ny * ny
    inside = r2 < 1
    nz = np.sqrt(np.clip(1 - r2, 0, 1))
    Lx, Ly, Lz = -0.45, -0.62, 0.64
    ln = math.sqrt(Lx * Lx + Ly * Ly + Lz * Lz)
    Lx, Ly, Lz = Lx / ln, Ly / ln, Lz / ln
    Hx, Hy, Hz = Lx, Ly, Lz + 1
    hn = math.sqrt(Hx * Hx + Hy * Hy + Hz * Hz)
    Hx, Hy, Hz = Hx / hn, Hy / hn, Hz / hn
    rr = np.sqrt(r2)
    band = np.abs(ny) < 0.075
    btn_o, btn_i, btn_c = rr < 0.27, rr < 0.20, rr < 0.12
    # 按鈕的法線往外凸一點（倒角）
    bx, by = nx.copy(), ny.copy()
    bz = nz.copy()
    bev = btn_i & ~btn_c
    bx[bev] *= 1.6
    by[bev] *= 1.6
    nrm = np.sqrt(bx * bx + by * by + bz * bz) + 1e-6
    bx, by, bz = bx / nrm, by / nrm, bz / nrm
    diff = np.clip(bx * Lx + by * Ly + bz * Lz, 0, 1)
    spec = np.clip(bx * Hx + by * Hy + bz * Hz, 0, 1) ** 70
    fres = (1 - nz) ** 3
    base = np.where((ny < 0)[..., None], np.float32(RED), np.float32([0.95, 0.95, 0.96]))
    base = np.where(band[..., None] | (btn_o & ~btn_i)[..., None], np.float32([0.05, 0.05, 0.06]), base)
    base = np.where(btn_i[..., None], np.float32([0.96, 0.96, 0.97]), base)
    base = np.where(btn_c[..., None], np.float32([0.90, 0.90, 0.92]), base)
    env = np.where((ny < 0)[..., None], np.float32([0.55, 0.70, 0.95]), np.float32([0.85, 0.72, 0.55]))
    col = base * (0.22 + 0.85 * diff[..., None]) + spec[..., None] * 0.95 + fres[..., None] * env * 0.45
    # 頂部柔和反射窗
    win = np.exp(-(((nx + 0.30) / 0.30) ** 2 + ((ny + 0.52) / 0.16) ** 2)) * inside
    col = col + win[..., None] * 0.35
    if glow > 0:
        gl = np.exp(-(rr / 0.20) ** 2)[..., None] * np.float32([1.0, 0.55, 0.50]) * glow * 1.6
        col = col + gl * btn_o[..., None]
    a = inside.astype(np.float32)
    out = np.zeros((D, D, 4), np.float32)
    out[..., :3] = np.clip(col, 0, 1) * a[..., None]
    out[..., 3] = a
    out = cv2.resize(out, (d, d), interpolation=cv2.INTER_AREA)
    out[..., :3] /= np.maximum(out[..., 3:4], 1e-6)
    return np.clip(out, 0, 1)


def ball(c, x, y, d, rot=0.0, glow=0.0, op=1.0, shadow=None):
    """畫球；shadow＝(地面 y) 時在下方畫柔和接觸陰影；glow>0 按鈕發光＋光暈。"""
    d = int(d)
    if d < 6:
        return
    if shadow is not None:
        al = np.zeros((int(d * 0.5), int(d * 1.4)), np.float32)
        cv2.ellipse(al, (al.shape[1] // 2, al.shape[0] // 2), (int(d * 0.55), int(d * 0.14)), 0, 0, 360, 0.45, -1, cv2.LINE_AA)
        sh = np.zeros(al.shape + (4,), np.float32)
        sh[..., 3] = cv2.GaussianBlur(al, (0, 0), d * 0.08)
        blit(c, sh, x, shadow, op, anchor='c')
    g = round(glow * 4) / 4
    blit(c, _rot(ball_sprite(d, g), rot), x, y, op, anchor='c')
    if g > 0:
        add_c(c, glint_sprite(int(d * 0.9), (1.0, 0.75, 0.70), 0.2), x, y, op * g * 0.9)


def ball_mblur(c, path, n=6, glow=0.0):
    """快速移動的球：沿路徑取 n 個子位置合成（真正的動態模糊，不是殘影）。path(u) → (x, y, d, rot)，u 0–1 為這一格快門內。"""
    pts = [path(i / (n - 1)) for i in range(n)]
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    dm = max(p[2] for p in pts)
    x0, y0 = int(min(xs) - dm), int(min(ys) - dm)
    W_, H_ = int(max(xs) - min(xs) + 2 * dm) + 2, int(max(ys) - min(ys) + 2 * dm) + 2
    acc = np.zeros((H_, W_, 4), np.float32)
    for x, y, dd, rr in pts:
        spr = _rot(ball_sprite(int(dd), round(glow * 4) / 4), rr)
        h, w = spr.shape[:2]
        px, py = x - x0 - w / 2, y - y0 - h / 2
        sub = np.zeros((H_, W_, 4), np.float32)
        ix, iy = int(round(px)), int(round(py))
        sx0, sy0 = max(0, ix), max(0, iy)
        sx1, sy1 = min(W_, ix + w), min(H_, iy + h)
        if sx1 > sx0 and sy1 > sy0:
            s = spr[sy0 - iy:sy1 - iy, sx0 - ix:sx1 - ix]
            sub[sy0:sy1, sx0:sx1, :3] = s[..., :3] * s[..., 3:4]
            sub[sy0:sy1, sx0:sx1, 3] = s[..., 3]
        acc += sub
    acc /= n
    out = acc.copy()
    out[..., :3] = acc[..., :3] / np.maximum(acc[..., 3:4], 1e-6)
    blit(c, out, x0, y0, 1.0)


def trail(c, pts, col=(1.0, 0.45, 0.40), width=10, k=0.8):
    """球後面的能量尾巴：一條由細到粗、由淡到亮的發光線。pts＝由舊到新的點。"""
    if len(pts) < 2 or k <= 0:
        return
    h, w = c.shape[:2]
    lay = np.zeros((h // 2, w // 2), np.float32)
    n = len(pts)
    for i in range(n - 1):
        a, b = pts[i], pts[i + 1]
        u = (i + 1) / n
        cv2.line(lay, (int(a[0] / 2 * 4), int(a[1] / 2 * 4)), (int(b[0] / 2 * 4), int(b[1] / 2 * 4)), u, max(1, int(width / 2 * u)), cv2.LINE_AA, shift=2)
    lay = cv2.resize(lay, (w, h), interpolation=cv2.INTER_LINEAR)[..., None]
    rgb = lay * np.float32([1, 0.95, 0.92]) * 0.8 + lay * np.float32(col) * 0.6
    screen(c, glow_layer(rgb, 26, 1.8), k)


def energy_lines(c, e, dur, src_rect, dst, k=1.0, seed=0, n=16, col=(1.0, 0.30, 0.28)):
    """收服的紅色能量：從目標（src_rect 範圍）沿弧線流進球（dst）。e 0→dur。"""
    if e < 0 or e > dur or k <= 0:
        return
    h, w = c.shape[:2]
    lay = np.zeros((h // 2, w // 2), np.float32)
    r = np.random.default_rng(9900 + seed)
    x0, y0, x1, y1 = src_rect
    for _ in range(n):
        p0 = np.float32([x0 + (x1 - x0) * r.random(), y0 + (y1 - y0) * r.random()])
        p2 = np.float32(dst)
        mid = (p0 + p2) / 2 + np.float32([(r.random() - 0.5) * 300, -(80 + 200 * r.random())])
        lag = r.random() * 0.3
        u = np.clip((e / dur - lag) / 0.7, 0, 1)
        if u <= 0:
            continue
        ts = np.linspace(max(0.0, u - 0.35), u, 14)
        pts = [((1 - s) ** 2 * p0 + 2 * (1 - s) * s * mid + s * s * p2) / 2 for s in ts]
        for i in range(len(pts) - 1):
            cv2.line(lay, tuple(int(v * 4) for v in pts[i]), tuple(int(v * 4) for v in pts[i + 1]), (i + 1) / len(pts), 2, cv2.LINE_AA, shift=2)
    lay = cv2.resize(lay, (w, h), interpolation=cv2.INTER_LINEAR)[..., None]
    rgb = lay * np.float32([1, 0.9, 0.88]) * 0.6 + lay * np.float32(col)
    screen(c, glow_layer(rgb, 30, 2.0), k * (1 - max(0.0, (e / dur - 0.85) / 0.15)))


def ball_transition(c, t, tc, fps=30, approach=0.30, after=0.28, cx=None, cy=None):
    """球形轉場（質感版）：tc 前 approach 秒球從遠處旋轉飛向鏡頭（動態模糊）、按鈕亮起；tc 那一格白紅光從按鈕炸開；
    tc 後 after 秒新畫面從光裡亮回來（發光閃衰減＋衝擊波）。引擎在 tc 前畫 A 鏡頭、tc 後畫 B 鏡頭，再呼叫這個。"""
    h, w = c.shape[:2]
    cx = w / 2 if cx is None else cx
    cy = h / 2 if cy is None else cy
    if tc - approach <= t < tc:
        def path(s):
            tt = t + (s - 0.5) / fps * 0.5
            u = np.clip((tt - (tc - approach)) / approach, 0, 1)
            d = 120 + (2600 - 120) * u ** 2.6
            return (cx + (1 - u) * 90, cy - (1 - u) * 260, d, -540 * (1 - u) + 25)
        u = (t - (tc - approach)) / approach
        ball_mblur(c, path, 12, glow=min(1.0, max(0.0, (u - 0.55) / 0.45)))
        if u > 0.75:
            luminous(c, (u - 0.75) / 0.25 * 0.85)
    elif tc <= t < tc + after:
        e = (t - tc) / after
        luminous(c, (1 - e) ** 1.8 * 0.95)
        shockwave(c, t - tc, cx, cy, 700, after + 0.1, (1.0, 0.88, 0.85), 14)


# ───────────────────────── 7. 屬性徽章（玻璃質感） ─────────────────────────
def _glyph(key, S):
    """徽章裡的圖形（白色向量）：火焰、水滴、葉、樹、山、雲。S＝畫布邊長（4 倍取樣）。"""
    im = Image.new('L', (S, S), 0)
    d = ImageDraw.Draw(im)
    c = S / 2
    u = S / 100
    if key == '火':
        outer = []
        for i in range(60):
            a = i / 59 * 2 * math.pi
            rad = 30 * u
            x = c + math.sin(a) * rad * (1 - 0.15 * math.cos(a))
            y = c + 8 * u - math.cos(a) * rad * (1.5 if math.cos(a) > 0 else 0.85)
            outer.append((x + (6 * u * math.sin(a * 3) if math.cos(a) > 0.3 else 0), y))
        d.polygon(outer, fill=255)
        inner = [(c, c - 12 * u), (c + 11 * u, c + 14 * u), (c, c + 26 * u), (c - 11 * u, c + 14 * u)]
        d.polygon(inner, fill=90)
    elif key == '水':
        d.ellipse([c - 24 * u, c - 4 * u, c + 24 * u, c + 44 * u], fill=255)
        d.polygon([(c, c - 40 * u), (c - 22 * u, c + 10 * u), (c + 22 * u, c + 10 * u)], fill=255)
        d.ellipse([c - 14 * u, c + 6 * u, c - 4 * u, c + 24 * u], fill=120)
    elif key == '草':
        pts = []
        for i in range(41):
            s = i / 40
            pts.append((c - 30 * u + 60 * u * s, c - 26 * u * math.sin(s * math.pi) + 10 * u - 20 * u * s))
        for i in range(41):
            s = 1 - i / 40
            pts.append((c - 30 * u + 60 * u * s, c + 18 * u * math.sin(s * math.pi) + 10 * u - 20 * u * s))
        d.polygon(pts, fill=255)
        d.line([(c - 26 * u, c + 10 * u), (c + 26 * u, c - 8 * u)], fill=110, width=int(3 * u))
    elif key == '森':
        for k_, (yy, ww) in enumerate([(-34, 20), (-16, 28), (2, 36)]):
            d.polygon([(c, c + (yy - 14) * u), (c - ww * u, c + (yy + 18) * u), (c + ww * u, c + (yy + 18) * u)], fill=255)
        d.rectangle([c - 5 * u, c + 20 * u, c + 5 * u, c + 34 * u], fill=255)
    elif key == '土':
        d.polygon([(c - 38 * u, c + 26 * u), (c - 10 * u, c - 22 * u), (c + 8 * u, c + 4 * u), (c + 18 * u, c - 10 * u), (c + 38 * u, c + 26 * u)], fill=255)
        d.polygon([(c - 10 * u, c - 22 * u), (c - 2 * u, c - 8 * u), (c - 18 * u, c - 6 * u)], fill=130)
    elif key == '雲':
        for (x, y, r) in [(-16, 6, 18), (6, -6, 24), (22, 8, 16)]:
            d.ellipse([c + (x - r) * u, c + (y - r) * u, c + (x + r) * u, c + (y + r) * u], fill=255)
        d.rectangle([c - 30 * u, c + 6 * u, c + 34 * u, c + 24 * u], fill=255)
        d.ellipse([c - 34 * u, c + 6 * u, c - 22 * u, c + 24 * u], fill=255)
    return np.asarray(im, np.float32) / 255


@functools.lru_cache(maxsize=32)
def emblem_sprite(key, d=120):
    """屬性徽章：深色玻璃圓盤、內部依屬性色的放射漸層、頂部光澤弧、亮色細環＋暗色外環、白色圖形帶柔光。"""
    S = 4
    D = d * S
    yy, xx = np.mgrid[0:D, 0:D].astype(np.float32)
    nx, ny = (xx + 0.5) / D * 2 - 1, (yy + 0.5) / D * 2 - 1
    rr = np.sqrt(nx * nx + ny * ny)
    col = np.float32(TYPE[key])
    a = np.clip((1 - rr) * D / 4, 0, 1)
    body = col * (0.35 + 0.65 * np.exp(-((nx) ** 2 + (ny + 0.15) ** 2) / 0.35))[..., None] + np.float32([0.02, 0.02, 0.05])
    ring = np.exp(-((rr - 0.90) / 0.025) ** 2)[..., None] * (col * 0.5 + 0.5)
    outer = (rr > 0.94)[..., None]
    body = np.where(outer, col * 0.25, body + ring)
    gloss = (np.exp(-(((nx) / 0.62) ** 2 + ((ny + 0.52) / 0.26) ** 2)) * (ny < -0.15))[..., None] * 0.30
    body = body + gloss
    g = _glyph(key, D)
    gs = cv2.GaussianBlur(g, (0, 0), D * 0.03)
    body = body * (1 - g[..., None] * 0.95) + np.float32([1, 1, 1]) * g[..., None] * 0.97 + gs[..., None] * col * 0.5
    out = np.zeros((D, D, 4), np.float32)
    out[..., :3] = np.clip(body, 0, 1) * a[..., None]
    out[..., 3] = a
    out = cv2.resize(out, (d, d), interpolation=cv2.INTER_AREA)
    out[..., :3] /= np.maximum(out[..., 3:4], 1e-6)
    return np.clip(out, 0, 1)


def emblem(c, key, e, x, y, d=120, op=1.0, label=None):
    """徽章進場：0.22 秒從 1.35 倍縮到 1（後半有一點過衝）、同時一圈衝擊波光環與光芒；e＝進場後秒數。"""
    if e < 0:
        return
    u = min(1.0, e / 0.22)
    s = 1.35 - 0.35 * ease_out(u) + 0.05 * math.sin(min(1.0, e / 0.35) * math.pi) * (e > 0.22)
    spr = emblem_sprite(key, d)
    sp = cv2.resize(spr, (max(2, int(d * s)), max(2, int(d * s))), interpolation=cv2.INTER_LINEAR)
    al = op * min(1.0, e / 0.08)
    sh = np.zeros_like(sp)
    sh[..., 3] = cv2.GaussianBlur(sp[..., 3], (0, 0), d * 0.08) * 0.55
    blit(c, sh, x, y + d * 0.06, al, anchor='c')
    blit(c, sp, x, y, al, anchor='c')
    shockwave(c, e, x, y, d * 1.1, 0.35, tuple(min(1.0, v * 0.6 + 0.5) for v in TYPE[key]), 6, op)
    if e < 0.5:
        add_c(c, glint_sprite(int(d * 1.2), tuple(min(1.0, v * 0.5 + 0.55) for v in TYPE[key]), 0.3), x + d * 0.28, y - d * 0.28,
              op * (1 - e / 0.5))
    if label:
        put_text(c, label, 26, x, y + d * 0.68, al * 0.95, CJK_B, tracking=0.25, shadow=0.6, glow=0.0)


# ───────────────────────── 8. 字：柔陰影＋光、漸層填色、卡拉 OK、玻璃面板 ─────────────────────────
@functools.lru_cache(maxsize=256)
def _txt(text, size, font, index, tracking, col):
    return text_sprite(text, size, font, index, tracking, col, palt=False)


@functools.lru_cache(maxsize=256)
def _txt_fx(text, size, font, index, tracking):
    s = _txt(text, size, font, index, tracking, (1.0, 1.0, 1.0))
    pad = int(size * 0.7)
    a = np.pad(s[..., 3], pad)
    sh = cv2.GaussianBlur(a, (0, 0), size * 0.16)
    return s, sh, pad


@functools.lru_cache(maxsize=128)
def grad_sprite(text, size, font, index, tracking, top, bottom):
    s = _txt(text, size, font, index, tracking, (1.0, 1.0, 1.0)).copy()
    h = s.shape[0]
    yy = np.linspace(0, 1, h, dtype=np.float32)[:, None, None]
    s[..., :3] = np.float32(top) * (1 - yy) + np.float32(bottom) * yy
    return s


def put_text(c, text, size, x, y, op=1.0, font=CJK_B, index=CJK_TC, tracking=0.04, col=(1.0, 1.0, 1.0), grad=None,
             shadow=0.55, glow=0.25, align='center', cut=None):
    """字（中心線 y）：寬柔陰影＋淡光暈＋字本身；grad=(上色, 下色) 漸層填色；cut＝0–1 只顯示左邊這一段（卡拉 OK 用）。"""
    if op <= 0:
        return
    s, sh, pad = _txt_fx(text, size, font, index, tracking)
    if grad:
        s = grad_sprite(text, size, font, index, tracking, tuple(grad[0]), tuple(grad[1]))
    elif col != (1.0, 1.0, 1.0):
        s = _txt(text, size, font, index, tracking, tuple(col))
    h, w = s.shape[:2]
    x0 = x - w / 2 if align == 'center' else x
    y0 = y - h / 2
    if cut is not None:
        if cut <= 0:
            return
        s = s.copy()
        cx = int(cut * w)
        ramp = np.clip((cx - np.arange(w, dtype=np.float32)) / 10 + 0.5, 0, 1)
        s[..., 3] *= ramp[None, :]
    else:
        if shadow > 0:
            shs = np.zeros(sh.shape + (4,), np.float32)
            shs[..., 3] = np.clip(sh * 1.25, 0, 1)
            blit(c, shs, x0 - pad, y0 - pad + size * 0.05, op * shadow)
        if glow > 0:
            g = np.clip(sh, 0, 1)[..., None] * np.float32(s[h // 2, w // 2, :3] if grad else col)
            add(c, g, x0 - pad, y0 - pad, op * glow)
    blit(c, s, x0, y0, op)


def karaoke(c, cn, jp, u, cy=1400, op=1.0, size=54, jp_size=26, sung=((1.0, 0.92, 0.62), (1.0, 0.72, 0.30))):
    """動畫 OP 卡拉 OK（質感版）：白字＋寬柔陰影（不描邊），唱到的部分換成金色漸層、邊緣柔和推進；日文原句細字在上。"""
    if op <= 0:
        return
    put_text(c, jp, jp_size, 540, cy - size * 0.95, op * 0.85, CJK_R, 0, 0.12, shadow=0.6, glow=0.0)
    put_text(c, cn, size, 540, cy, op, CJK_B, CJK_TC, 0.05, shadow=0.65, glow=0.15)
    if u > 0:
        put_text(c, cn, size, 540, cy, op, CJK_B, CJK_TC, 0.05, grad=sung, cut=min(1.0, u), shadow=0, glow=0)


@functools.lru_cache(maxsize=16)
def _rrect(w, h, r):
    S = 3
    m = np.zeros((h * S, w * S), np.float32)
    cv2.rectangle(m, (r * S, 0), ((w - r) * S, h * S), 1, -1)
    cv2.rectangle(m, (0, r * S), (w * S, (h - r) * S), 1, -1)
    for cx, cy in [(r, r), (w - r, r), (r, h - r), (w - r, h - r)]:
        cv2.circle(m, (cx * S, cy * S), r * S, 1, -1, cv2.LINE_AA)
    return cv2.resize(m, (w, h), interpolation=cv2.INTER_AREA)


def glass(c, x0, y0, w, h, op=1.0, r=26, blur=14, fill=0.10, tint=(1.0, 1.0, 1.0), border=0.45):
    """毛玻璃面板：底下畫面糊掉＋一層淡白＋細亮邊＋頂部微光。比實色對話框高級，底下的實拍還透得出來。"""
    if op <= 0:
        return
    x0, y0, w, h = int(x0), int(y0), int(w), int(h)
    H_, W_ = c.shape[:2]
    if x0 < 0 or y0 < 0 or x0 + w > W_ or y0 + h > H_:
        return
    reg = c[y0:y0 + h, x0:x0 + w]
    sm = cv2.resize(reg, (w // 2, h // 2), interpolation=cv2.INTER_AREA)
    bl = cv2.resize(cv2.GaussianBlur(sm, (0, 0), blur / 2), (w, h), interpolation=cv2.INTER_LINEAR)
    m = _rrect(w, h, r)[..., None]
    yy = np.linspace(0, 1, h, dtype=np.float32)[:, None, None]
    panel = bl * 0.80 + np.float32(tint) * (fill + 0.06 * np.clip(1 - yy / 0.4, 0, 1))
    reg[:] = reg * (1 - m * op) + panel * m * op
    edge = np.clip(m[..., 0] - cv2.erode(m[..., 0], np.ones((3, 3), np.uint8)), 0, 1)[..., None]
    reg[:] = reg * (1 - edge * border * op) + np.float32([1, 1, 1]) * edge * border * op


def panel_text(c, e, lines, x0, y0, w, h, op=1.0, accent=GOLD):
    """毛玻璃面板＋文字：lines=[(字, 字級, 色或 None)]；每行依序遮罩升起（0.08 秒間隔）。"""
    if e < 0 or op <= 0:
        return
    a = op * min(1.0, e / 0.12)
    glass(c, x0, y0, w, h, a)
    yy = y0 + 34
    for i, (txt, size, col) in enumerate(lines):
        ee = e - 0.08 * (i + 1)
        if ee > 0:
            u = ease_out(min(1.0, ee / 0.3))
            put_text(c, txt, size, x0 + 40, yy + size * 0.55 + (1 - u) * 14, a * u, CJK_B, CJK_TC, 0.06 if size < 34 else 0.03,
                     col=col or (1.0, 1.0, 1.0), shadow=0.3, glow=0.0, align='left')
        yy += size * 1.35
    if e > 0.2:
        ln = int((w - 80) * ease_out(min(1.0, (e - 0.2) / 0.4)))
        if ln > 0:
            bar = np.zeros((2, ln, 4), np.float32)
            bar[..., :3], bar[..., 3] = accent, 0.9
            blit(c, bar, x0 + 40, y0 + h - 22, a)


# ───────────────────────── 9. 進化（質感版） ─────────────────────────
def light_form(img):
    """發光的形：畫面推成白藍色光，只留亮度結構；中央亮、四周沉到深藍。"""
    h, w = img.shape[:2]
    L = cv2.GaussianBlur(lum(img), (0, 0), 1.2)
    form = (0.55 + 0.45 * np.clip(L * 1.3, 0, 1) ** 0.7)[..., None] * np.float32([0.90, 0.96, 1.0])
    yy, xx = np.mgrid[0:h // 4, 0:w // 4].astype(np.float32)
    core = np.exp(-(((xx - w / 8) / (w / 4 * 0.75)) ** 2 + ((yy - h / 8) / (h / 4 * 0.55)) ** 2))
    core = cv2.resize(core, (w, h), interpolation=cv2.INTER_LINEAR)[..., None]
    out = form * (0.25 + 0.75 * core) + np.float32([0.03, 0.06, 0.22]) * (1 - core) * 0.8
    bloom(out, 0.50, 1.1, 60, (0.85, 0.93, 1.0))
    screen(out, core * np.float32([0.75, 0.85, 1.0]), 0.35)
    return out


def spiral(c, t, cx, cy, k=0.6, n=60, seed=0):
    """往中心旋轉收束的光點（進化時）。"""
    if k <= 0:
        return
    h, w = c.shape[:2]
    lay = np.zeros((h // 2, w // 2), np.float32)
    r = np.random.default_rng(9990 + seed)
    for _ in range(n):
        a0, rr0, sp = r.random() * 6.28, 250 + 650 * r.random(), 0.7 + 0.6 * r.random()
        ph = (t * 0.6 * sp + r.random()) % 1.0
        rad = rr0 * (1 - ph)
        for j in range(5):
            aa = a0 + ph * 5 * sp - j * 0.04
            rj = rad + j * 6
            x, y = cx + math.cos(aa) * rj, cy + math.sin(aa) * rj
            cv2.circle(lay, (int(x / 2 * 4), int(y / 2 * 4)), 8, (1 - j / 5) * (0.5 + 0.5 * ph), -1, cv2.LINE_AA, shift=2)
    lay = cv2.resize(lay, (w, h), interpolation=cv2.INTER_LINEAR)[..., None] * np.float32([0.85, 0.95, 1.0])
    screen(c, glow_layer(lay, 18, 1.5), k)


def evolution(a, b, u, t, dur=1.3, f0=2.5, f1=16.0):
    """進化：A、B 的發光形交替閃（越來越快）＋旋轉光點收束；白光爆開後 B 從光裡亮回來。u 0→1。"""
    h, w = a.shape[:2]
    if u < 0.78:
        tt = u / 0.78 * dur
        ph = f0 * tt + (f1 - f0) * tt * tt / (2 * dur)
        out = light_form(a if int(ph * 2) % 2 == 0 else b)
        spiral(out, t, w / 2, h / 2, 0.7)
        luminous(out, 0.25 * u)
        return out
    if u < 0.86:
        out = np.ones_like(a) * np.float32([0.97, 0.98, 1.0])
        return out
    v = (u - 0.86) / 0.14
    out = b.copy()
    luminous(out, (1 - v) ** 1.5)
    return out


# ───────────────────────── demo ─────────────────────────
def _demo(a):
    img = cv2.imread(a.input)[..., ::-1].astype(np.float32) / 255
    img = cv2.resize(img, (1080, 1920), interpolation=cv2.INTER_AREA)
    tiles = []

    def tile(name, fn):
        c = img.copy()
        r = fn(c)
        c = r if isinstance(r, np.ndarray) else c
        t = (np.clip(c, 0, 1) * 255).astype(np.uint8)[..., ::-1]
        t = cv2.resize(t, (360, 640), interpolation=cv2.INTER_AREA)
        cv2.putText(t, name, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2, cv2.LINE_AA)
        tiles.append(t)

    tile('satsuei', lambda c: (c.__setitem__(slice(None), satsuei(c)), bloom(c), diffusion(c)))
    tile('glints+bokeh', lambda c: (bokeh(c, 0.5, 20), glints(c, 0.3, scatter(1, 8, 100, 300, 980, 1500), 90)))
    tile('halo_rays', lambda c: halo_rays(c, 0.3, 540, 900, 0.45))
    tile('punch', lambda c: punch(c, 0.03, 0.0))
    tile('impact_duo', lambda c: impact_duo(c))
    tile('speed_lines', lambda c: speed_lines(c, 0.0, 540, 800, 0.7))
    tile('lightning', lambda c: lightning(c, 0.0, (100, 150), (500, 900)))
    tile('embers', lambda c: embers(c, 1.0, 1.0))
    tile('leaves', lambda c: leaves(c, 1.0))
    tile('caustics', lambda c: caustics(c, 1.0, 0.4, 0.3))
    tile('ball', lambda c: (ball(c, 540, 900, 300, 12, 0.0, shadow=1080), ball(c, 820, 500, 160, -20, 1.0)))
    tile('transition', lambda c: ball_transition(c, 0.95, 1.0))
    tile('emblems', lambda c: [emblem(c, k, 1.0, 120 + i * 150, 330, 120, label=k) for i, k in enumerate('火水草森土雲')])
    tile('panel', lambda c: panel_text(c, 1.0, [('10.03', 28, GOLD), ('戰利品 收服成功！', 50, None)], 80, 1180, 920, 210))
    tile('karaoke', lambda c: karaoke(c, '一定要收服你　寶可夢', '必ずゲットだぜ　ポケモン', 0.55))
    tile('evolution', lambda c: evolution(c, c, 0.3, 0.4))
    tile('lens_flare', lambda c: lens_flare(c, 760, 300, 0.8))
    tile('energy', lambda c: energy_lines(c, 0.25, 0.5, (100, 900, 700, 1500), (820, 500)))
    rows = [np.hstack(tiles[i:i + 6]) for i in range(0, len(tiles), 6)]
    w = max(r.shape[1] for r in rows)
    rows = [np.pad(r, ((0, 0), (0, w - r.shape[1]), (0, 0))) for r in rows]
    cv2.imwrite(a.out, np.vstack(rows), [cv2.IMWRITE_JPEG_QUALITY, 88])
    print(a.out)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = p.add_subparsers(dest='cmd', required=True)
    s = sp.add_parser('demo')
    s.add_argument('input')
    s.add_argument('-o', '--out', required=True)
    _demo(p.parse_args())


if __name__ == '__main__':
    main()
