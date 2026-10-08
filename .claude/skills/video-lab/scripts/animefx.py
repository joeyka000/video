#!/usr/bin/env python3
"""動漫風特效（seek(t) 引擎用）：實拍轉賽璐璐畫風、集中線、速度線、衝擊格、白閃、畫面震動、放射光、星點、閃電、
屬性粒子、描邊字與卡拉 OK、カットイン色帶、狀聲字、遊戲對話框、收服用的球、球形轉場、進化閃光、光束。

全部是 t 的純函式：亂數用 frame_rng(t) 或固定種子，線條「一拍二」抖動用 twos(t)。影像一律 float32 RGB 0–1。
術語、節奏原則與分寸見 references/anime.md（衝擊格、白閃是標點，只放在重拍；特效疊在實拍上，不取代實拍）。

  from animefx import cel, speed_lines, impact, shake, sparkles, karaoke, ...
  python animefx.py demo in.jpg -o qa/animefx_demo.jpg     # 每個效果一格的對照表
"""
import argparse
import functools
import math
import os
import sys

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from seekkit import CJK_B, CJK_TC, back_out, blit, ease, ease_out, frame_rng  # noqa: E402

CJK_JP = 0
YELLOW = (1.00, 0.80, 0.02)     # 黃（#FFCB05）
BLUE = (0.16, 0.46, 0.73)       # 藍（#2A75BB）
NAVY = (0.08, 0.13, 0.33)       # 描邊深藍
RED = (0.90, 0.12, 0.15)
WHITE = (1.0, 1.0, 1.0)
# 屬性色（遊戲裡屬性標籤的慣用色系）
TYPE = {'火': (0.93, 0.51, 0.19), '水': (0.39, 0.56, 0.94), '草': (0.48, 0.78, 0.30), '森': (0.36, 0.62, 0.22),
        '土': (0.80, 0.62, 0.30), '雲': (0.58, 0.68, 0.95), '電': (0.97, 0.82, 0.17), '妖': (0.93, 0.52, 0.72)}


def twos(t, fps=30, n=2):
    """一拍二：時間量化到每 n 格換一次（線條抖動、粒子閃爍的手繪頓挫感）。"""
    return math.floor(t * fps / n) * n / fps


def _lum(x):
    return x[..., 0] * 0.299 + x[..., 1] * 0.587 + x[..., 2] * 0.114


# ───────────────────────── 1. 實拍 → 賽璐璐 ─────────────────────────
def _guided(I, p, r=8, eps=1e-3):
    mI = cv2.blur(I, (r, r))
    mp = cv2.blur(p, (r, r))
    cov = cv2.blur(I[..., None] * p, (r, r)) - mI[..., None] * mp
    var = cv2.blur(I * I, (r, r)) - mI * mI
    a = cov / (var[..., None] + eps)
    b = mp - a * mI[..., None]
    return cv2.blur(a, (r, r)) * I[..., None] + cv2.blur(b, (r, r))


def _smooth(img, it=4):
    h, w = img.shape[:2]
    s = cv2.resize(img, (w // 3, h // 3), interpolation=cv2.INTER_AREA)
    for _ in range(it):
        s = cv2.bilateralFilter(s, 7, 0.16, 5)
    up = cv2.resize(s, (w, h), interpolation=cv2.INTER_CUBIC)
    return _guided(cv2.cvtColor(img, cv2.COLOR_RGB2GRAY), up, 6, 2e-3)


def _cel_steps(L, steps=5, soft=0.14):
    """柔性色階：台階邊緣平滑，影片不會閃。"""
    x = L * steps
    f = np.floor(x)
    r = x - f
    r = 0.5 + 0.5 * np.tanh((r - 0.5) / soft) / np.tanh(0.5 / soft)
    return (f + r) / steps


def xdog(L, sigma=1.3, k=1.6, tau=0.975, phi=70.0):
    g1 = cv2.GaussianBlur(L, (0, 0), sigma)
    g2 = cv2.GaussianBlur(L, (0, 0), sigma * k)
    d = g1 - tau * g2
    return np.clip(np.where(d >= 0, 1.0, 1.0 + np.tanh(phi * d)), 0, 1).astype(np.float32)


def cel(img, k=1.0, line=0.95, sat=1.45, steps=4, cel_mix=0.75, detail=0.35, night=False, ink=(0.10, 0.08, 0.16)):
    """實拍 → 日系動畫畫風：邊緣保留平滑（色塊）＋柔性色階＋動畫式陰影（暗部偏藍紫、亮部偏暖）＋墨線（XDoG，深藍紫不用純黑）
    ＋原片高頻加回 detail（卡盒、包裝上的圖案與字不會糊成一團）＋柔光。k=0 回原片。
    v1（峇里島 Reels 動畫版）平滑 4 次、墨線 0.7：寶可夢片實測像水彩、包裝圖被抹掉；v2 平滑 2 次、墨線 0.95、加回細節。
    1080×1920 一格約 0.6–0.8 秒。"""
    if k <= 0:
        return img
    img = np.clip(img, 0, 1).astype(np.float32)
    h, w = img.shape[:2]
    s = cv2.resize(img, (w // 2, h // 2), interpolation=cv2.INTER_AREA)
    for _ in range(2):
        s = cv2.bilateralFilter(s, 9, 0.12, 6)
    up = cv2.resize(s, (w, h), interpolation=cv2.INTER_CUBIC)
    sm = np.clip(_guided(cv2.cvtColor(img, cv2.COLOR_RGB2GRAY), up, 4, 1e-3), 0, 1)
    lab = cv2.cvtColor(sm, cv2.COLOR_RGB2Lab)
    L = lab[..., 0] / 100.0
    L2 = np.clip((L - 0.02) / 0.94, 0, 1) ** (0.82 if not night else 0.72)
    Lq = L2 * (1 - cel_mix) + _cel_steps(L2, steps, 0.10) * cel_mix
    lab[..., 0] = Lq * 100
    lab[..., 1:] *= sat
    sh = np.clip((0.5 - Lq) / 0.5, 0, 1)
    hi = np.clip((Lq - 0.62) / 0.38, 0, 1)
    lab[..., 1] += sh * 6.0 + hi * 1.0
    lab[..., 2] += -sh * 18.0 + hi * 4.0
    out = cv2.cvtColor(lab, cv2.COLOR_Lab2RGB)
    out = out + (img - cv2.GaussianBlur(img, (0, 0), 2.0)) * detail
    e = xdog(_lum(sm).astype(np.float32), sigma=0.9, k=1.6, tau=0.982, phi=90)
    e = 1 - (1 - e) * line
    out = out * e[..., None] + np.float32(ink) * (1 - e[..., None])
    b = cv2.GaussianBlur(np.clip(out - 0.70, 0, 1), (0, 0), 22)
    out = np.clip(1 - (1 - out) * (1 - np.clip(b, 0, 1)), 0, 1)
    return img * (1 - k) + out * k if k < 1 else out


# ───────────────────────── 2. 打在拍上的：震動、白閃、衝擊格 ─────────────────────────
def shake(img, t, t0, amp=18.0, dur=0.35, fps=30, seed=0, zoom=1.04):
    """畫面震動：t0 起 dur 秒、振幅衰減；先放大 zoom 倍免得露邊。不在範圍內就原樣回傳。"""
    e = t - t0
    if e < 0 or e > dur:
        return img
    a = amp * (1 - e / dur) ** 2
    r = frame_rng(t, fps, 900 + seed)
    dx, dy = (r.random(2) - 0.5) * 2 * a
    h, w = img.shape[:2]
    M = np.float32([[zoom, 0, w / 2 * (1 - zoom) + dx], [0, zoom, h / 2 * (1 - zoom) + dy]])
    return cv2.warpAffine(img, M, (w, h), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)


def flash(c, op, col=WHITE):
    if op > 0:
        c[:] = c * (1 - op) + np.float32(col) * op


def flash_at(t, t0, frames=2, fps=30, peak=0.85):
    """白閃的不透明度：t0 那格最亮，frames 格內退掉。"""
    e = (t - t0) * fps
    return 0.0 if e < 0 or e >= frames else peak * (1 - e / frames)


def impact(c, col_dark=NAVY, col_light=(1.0, 0.97, 0.90), accent=RED, op=1.0):
    """衝擊格：用「這一格實拍本身」做高反差反轉（亮的變深藍、暗的變米白），再從中心放一圈紅。最多 2 格，只在重拍。"""
    L = _lum(c)
    L = cv2.GaussianBlur(L, (0, 0), 1.2)
    m = np.clip((L - 0.42) / 0.10, 0, 1)[..., None]           # 亮部 → 深色（反轉）
    out = np.float32(col_light) * (1 - m) + np.float32(col_dark) * m
    h, w = L.shape
    yy, xx = np.ogrid[0:h, 0:w]
    r = np.sqrt(((xx - w / 2) / w) ** 2 + ((yy - h / 2) / h) ** 2)
    out = out * (1 - 0.35 * np.clip(r * 2.2 - 0.6, 0, 1)[..., None]) + np.float32(accent) * 0.35 * np.clip(r * 2.2 - 0.6, 0, 1)[..., None]
    c[:] = c * (1 - op) + out * op


# ───────────────────────── 3. 線：集中線、速度線、閃電 ─────────────────────────
def speed_lines(c, t, cx, cy, k=1.0, n=90, inner=0.38, col=WHITE, seed=0, fps=30, width=(3, 12)):
    """集中線：從畫面外往 (cx, cy) 收的細楔形，尖端停在 inner×對角線的圓上（主體不被蓋）。一拍二換一組。"""
    if k <= 0:
        return
    h, w = c.shape[:2]
    s = 2
    lay = np.zeros((h // s, w // s), np.float32)
    r = frame_rng(twos(t, fps), fps, 300 + seed)
    diag = math.hypot(w, h)
    for _ in range(n):
        a = r.random() * 2 * math.pi
        r_in = diag / 2 * (inner + 0.25 * r.random())   # inner＝半對角線的比例：尖端停在這個圓上
        wid = (width[0] + (width[1] - width[0]) * r.random()) / diag
        p_tip = (cx + math.cos(a) * r_in, cy + math.sin(a) * r_in)
        R = diag
        p1 = (cx + math.cos(a - wid) * R, cy + math.sin(a - wid) * R)
        p2 = (cx + math.cos(a + wid) * R, cy + math.sin(a + wid) * R)
        pts = np.array([p_tip, p1, p2], np.float32) / s
        cv2.fillPoly(lay, [np.round(pts * 16).astype(np.int32)], 1.0, cv2.LINE_AA, shift=4)
    lay = cv2.resize(lay, (w, h), interpolation=cv2.INTER_LINEAR)[..., None] * k
    c[:] = c * (1 - lay) + np.float32(col) * lay


def streaks(c, t, k=1.0, n=46, col=WHITE, seed=0, speed=2600, angle=0.0, alpha=0.75):
    """速度線：水平（或 angle 弧度）的長細線往一邊衝，衝刺、甩鏡、蓄力。"""
    if k <= 0:
        return
    h, w = c.shape[:2]
    lay = np.zeros((h, w), np.float32)
    r = np.random.default_rng(500 + seed)
    for _ in range(n):
        y = r.random() * h
        L = 200 + 700 * r.random()
        x = (r.random() * (w + L) - speed * t * (0.6 + 0.8 * r.random())) % (w + L) - L
        th = 1 + int(3 * r.random())
        cv2.line(lay, (int(x), int(y)), (int(x + L), int(y)), 0.5 + 0.5 * r.random(), th, cv2.LINE_AA)
    if angle:
        M = cv2.getRotationMatrix2D((w / 2, h / 2), math.degrees(angle), 1.3)
        lay = cv2.warpAffine(lay, M, (w, h))
    lay = cv2.GaussianBlur(lay, (0, 0), 0.8)[..., None] * k * alpha
    c[:] = c * (1 - lay) + np.float32(col) * lay


def _bolt_path(p0, p1, rng, depth=6, disp=0.22):
    pts = [np.float32(p0), np.float32(p1)]
    for d in range(depth):
        out = [pts[0]]
        for a, b in zip(pts[:-1], pts[1:]):
            m = (a + b) / 2
            v = b - a
            nrm = np.float32([-v[1], v[0]])
            m = m + nrm * (rng.random() - 0.5) * disp * (0.62 ** d) * 2
            out += [m, b]
        pts = out
    return np.array(pts, np.float32)


def lightning(c, t, p0, p1, k=1.0, seed=0, width=5, col=YELLOW, glow=16, branches=2, fps=30):
    """閃電：中點位移的鋸齒折線，白色芯＋黃色光暈；一拍二重新長一次。"""
    if k <= 0:
        return
    h, w = c.shape[:2]
    rng = frame_rng(twos(t, fps), fps, 700 + seed)
    core = np.zeros((h, w), np.float32)
    paths = [_bolt_path(p0, p1, rng)]
    for _ in range(branches):
        base = paths[0][int(len(paths[0]) * (0.25 + 0.5 * rng.random()))]
        v = np.float32(p1) - np.float32(p0)
        ang = math.atan2(v[1], v[0]) + (rng.random() - 0.5) * 1.6
        L = np.linalg.norm(v) * (0.25 + 0.3 * rng.random())
        paths.append(_bolt_path(base, base + np.float32([math.cos(ang), math.sin(ang)]) * L, rng, depth=5))
    for i, pth in enumerate(paths):
        cv2.polylines(core, [np.round(pth * 16).astype(np.int32)], False, 1.0, max(1, width if i == 0 else width // 2), cv2.LINE_AA, shift=4)
    g = cv2.GaussianBlur(cv2.resize(core, (w // 4, h // 4), interpolation=cv2.INTER_AREA), (0, 0), glow / 4)
    g = cv2.resize(g, (w, h))
    add = core[..., None] * np.float32(WHITE) + np.clip(g * 3.0, 0, 1)[..., None] * np.float32(col)
    c[:] = 1 - (1 - c) * (1 - np.clip(add * k, 0, 1))


# ───────────────────────── 4. 光：放射光、星點、光束、柔光 ─────────────────────────
@functools.lru_cache(maxsize=8)
def _rays(w, h, n, r0):
    yy, xx = np.mgrid[0:h // 2, 0:w // 2].astype(np.float32)
    return (xx * 2 - w / 2, yy * 2 - h / 2)


def sunburst(c, t, cx, cy, k=0.35, n=16, col=YELLOW, spin=0.25, inner=180, soft=True):
    """放射光：旋轉的放射色塊（登場、慶祝、收服）。中心 inner 半徑內淡掉，主體不被蓋；screen 疊，看得到下面的實拍。"""
    if k <= 0:
        return
    h, w = c.shape[:2]
    s = 4
    yy, xx = np.mgrid[0:h // s, 0:w // s].astype(np.float32)
    dx, dy = xx * s - cx, yy * s - cy
    a = np.arctan2(dy, dx) + spin * t
    rr = np.sqrt(dx * dx + dy * dy)
    m = (np.sin(a * n) > 0).astype(np.float32)
    if soft:
        m = cv2.GaussianBlur(m, (0, 0), 0.8)
    m *= np.clip((rr - inner) / 260, 0, 1)
    m = cv2.resize(m, (w, h), interpolation=cv2.INTER_LINEAR)[..., None] * k
    c[:] = 1 - (1 - c) * (1 - m * np.float32(col))


@functools.lru_cache(maxsize=32)
def star_sprite(size, col=WHITE, glow=True):
    """四角星（キラキラ）：細長十字＋中心亮點＋柔光。"""
    S = int(size * 2) | 1
    a = np.zeros((S, S), np.float32)
    c0 = S // 2
    pts = []
    for i in range(8):
        ang = i * math.pi / 4
        rad = c0 if i % 2 == 0 else c0 * 0.16
        pts.append((c0 + math.cos(ang) * rad, c0 + math.sin(ang) * rad))
    cv2.fillPoly(a, [np.round(np.array(pts) * 16).astype(np.int32)], 1.0, cv2.LINE_AA, shift=4)
    if glow:
        a = np.maximum(a, cv2.GaussianBlur(a, (0, 0), S * 0.08) * 1.4)
    a = np.clip(a, 0, 1)
    out = np.zeros((S, S, 4), np.float32)
    out[..., :3] = col
    out[..., 3] = a
    return out


def sparkles(c, t, pts, size=36, col=WHITE, period=0.8, op=1.0):
    """星點閃爍：pts = [(x, y, phase), ...]；每顆依 phase 錯開一閃一閃（大小與亮度一起脈動）。"""
    for x, y, ph in pts:
        u = ((t / period + ph) % 1.0)
        s = math.sin(u * math.pi) ** 2
        if s < 0.05:
            continue
        sz = max(4, int(size * (0.4 + 0.6 * s)))
        blit(c, star_sprite(sz, col), x, y, op * s, anchor='c')


def scatter(seed, n, x0, y0, x1, y1):
    """固定種子的散布點（給 sparkles 用）。"""
    r = np.random.default_rng(seed)
    return [(x0 + (x1 - x0) * r.random(), y0 + (y1 - y0) * r.random(), r.random()) for _ in range(n)]


def god_rays(c, cx, cy, k=0.5, thr=0.72, n=10, spread=0.06):
    """光束：亮部從 (cx, cy) 往外放射模糊（透過光、新海誠式天空）。1/4 解析度算。"""
    if k <= 0:
        return
    h, w = c.shape[:2]
    s = 4
    sm = cv2.resize(c, (w // s, h // s), interpolation=cv2.INTER_AREA)
    hi = np.clip((_lum(sm) - thr) / (1 - thr), 0, 1)[..., None] * sm
    acc = np.zeros_like(hi)
    for i in range(n):
        z = 1 + spread * i
        M = np.float32([[z, 0, cx / s * (1 - z)], [0, z, cy / s * (1 - z)]])
        acc += cv2.warpAffine(hi, M, (w // s, h // s)) * (1 - i / n)
    acc = cv2.resize(acc / n * 2.2, (w, h), interpolation=cv2.INTER_LINEAR)
    c[:] = 1 - (1 - c) * (1 - np.clip(acc * k, 0, 1))


def para(c, top=(0.35, 0.20, 0.55), bottom=None, k=0.35):
    """パラ：上方（與下方）漸層覆蓋，空氣感、時段。"""
    h = c.shape[0]
    y = np.linspace(0, 1, h, dtype=np.float32)[:, None, None]
    c[:] = c * (1 - k * (1 - y)) + np.float32(top) * k * (1 - y)
    if bottom is not None:
        c[:] = c * (1 - k * y) + np.float32(bottom) * k * y


# ───────────────────────── 5. 粒子（屬性） ─────────────────────────
@functools.lru_cache(maxsize=64)
def _dot(r, col, soft):
    S = int(r * 4) | 1
    a = np.zeros((S, S), np.float32)
    cv2.circle(a, (S // 2, S // 2), max(1, int(r)), 1.0, -1, cv2.LINE_AA)
    if soft:
        a = np.maximum(a, cv2.GaussianBlur(a, (0, 0), r * 0.9) * 1.2)
    out = np.zeros((S, S, 4), np.float32)
    out[..., :3] = col
    out[..., 3] = np.clip(a, 0, 1)
    return out


@functools.lru_cache(maxsize=64)
def _bubble(r):
    S = int(r * 2.6) | 1
    a = np.zeros((S, S), np.float32)
    c0 = S // 2
    cv2.circle(a, (c0, c0), int(r), 0.85, max(2, int(r * 0.12)), cv2.LINE_AA)
    cv2.circle(a, (c0 - int(r * 0.35), c0 - int(r * 0.35)), max(2, int(r * 0.22)), 1.0, -1, cv2.LINE_AA)
    inner = np.zeros_like(a)
    cv2.circle(inner, (c0, c0), int(r), 0.12, -1, cv2.LINE_AA)
    out = np.zeros((S, S, 4), np.float32)
    out[..., :3] = (0.92, 0.98, 1.0)
    out[..., 3] = np.clip(a + inner, 0, 1)
    return out


@functools.lru_cache(maxsize=64)
def _leaf(r, col):
    S = int(r * 3) | 1
    a = np.zeros((S, S), np.float32)
    c0 = S // 2
    cv2.ellipse(a, (c0, c0), (int(r), max(2, int(r * 0.45))), 0, 0, 360, 1.0, -1, cv2.LINE_AA)
    cv2.line(a, (c0 - int(r), c0), (c0 + int(r), c0), 0.55, 1, cv2.LINE_AA)
    out = np.zeros((S, S, 4), np.float32)
    out[..., :3] = col
    out[..., 3] = a
    out[..., :3] *= (0.75 + 0.25 * (a > 0.6))[..., None]
    return out


@functools.lru_cache(maxsize=32)
def _heart(r, col):
    S = int(r * 3) | 1
    im = Image.new('L', (S * 2, S * 2), 0)
    d = ImageDraw.Draw(im)
    R = r * 2
    cx, cy = S, S
    d.ellipse([cx - R, cy - R * 0.9, cx, cy + R * 0.1], fill=255)
    d.ellipse([cx, cy - R * 0.9, cx + R, cy + R * 0.1], fill=255)
    d.polygon([(cx - R * 0.98, cy - R * 0.25), (cx + R * 0.98, cy - R * 0.25), (cx, cy + R * 1.1)], fill=255)
    a = np.asarray(im.resize((S, S), Image.LANCZOS), np.float32) / 255
    out = np.zeros((S, S, 4), np.float32)
    out[..., :3] = col
    out[..., 3] = a
    return out


def _rot(spr, deg):
    if abs(deg) < 0.5:
        return spr
    h, w = spr.shape[:2]
    D = int(math.hypot(w, h)) + 2
    pad = np.zeros((D, D, 4), np.float32)
    y0, x0 = (D - h) // 2, (D - w) // 2
    pad[y0:y0 + h, x0:x0 + w] = spr
    pm = pad.copy()
    pm[..., :3] *= pm[..., 3:4]
    M = cv2.getRotationMatrix2D((D / 2, D / 2), deg, 1.0)
    pm = cv2.warpAffine(pm, M, (D, D), flags=cv2.INTER_LINEAR)
    pm[..., :3] /= np.maximum(pm[..., 3:4], 1e-6)
    return pm


def particles(c, t, kind, k=1.0, seed=0, n=40, region=None, t0=0.0):
    """屬性粒子。kind：ember 火星（往上飄、閃爍）、bubble 泡泡（往上浮）、leaf 葉子（落下旋轉）、dust 塵土（往外噴）、
    cloud 雲（大片柔白飄過）、confetti 彩紙、heart 愛心、spark 電花（黃色短促）。位置全由 t 算，不累積狀態。"""
    if k <= 0:
        return
    h, w = c.shape[:2]
    x0, y0, x1, y1 = region or (0, 0, w, h)
    r = np.random.default_rng(1000 + seed)
    e = t - t0
    for i in range(n):
        px, py, ph, sp, sz, rot = r.random(), r.random(), r.random(), 0.6 + 0.8 * r.random(), r.random(), r.random()
        if kind == 'ember':
            yy = y1 - ((py * (y1 - y0) + e * 260 * sp) % (y1 - y0))
            xx = x0 + px * (x1 - x0) + math.sin(e * 3 * sp + ph * 6) * 26
            fl = 0.55 + 0.45 * math.sin(e * 22 * sp + ph * 9)
            col = (1.0, 0.45 + 0.35 * sz, 0.10)
            blit(c, _dot(round(3 + 5 * sz), col, True), xx, yy, k * fl, anchor='c')
        elif kind == 'bubble':
            yy = y1 - ((py * (y1 - y0) + e * 220 * sp) % (y1 - y0))
            xx = x0 + px * (x1 - x0) + math.sin(e * 2.4 * sp + ph * 6) * 18
            blit(c, _bubble(round(8 + 22 * sz)), xx, yy, k * 0.85, anchor='c')
        elif kind == 'leaf':
            yy = y0 + ((py * (y1 - y0) + e * 240 * sp) % (y1 - y0))
            xx = x0 + px * (x1 - x0) + math.sin(e * 2 * sp + ph * 6) * 60
            col = (0.30 + 0.25 * sz, 0.62 + 0.2 * sz, 0.20)
            blit(c, _rot(_leaf(round(14 + 14 * sz), col), (rot * 360 + e * 200 * sp) % 360), xx, yy, k, anchor='c')
        elif kind == 'dust':
            cx_, cy_ = (x0 + x1) / 2, y1
            ang = -math.pi * (0.1 + 0.8 * px)
            dist = ((e * 600 * sp + ph * 300) % 700)
            xx, yy = cx_ + math.cos(ang) * dist, cy_ + math.sin(ang) * dist * 0.7
            blit(c, _dot(round(6 + 9 * sz), (0.90, 0.76, 0.52), True), xx, yy, k * (1 - dist / 700), anchor='c')
        elif kind == 'cloud':
            xx = x0 + ((px * (x1 - x0 + 600) + e * 120 * sp) % (x1 - x0 + 600)) - 300
            yy = y0 + py * (y1 - y0)
            blit(c, _dot(round(40 + 50 * sz), (1, 1, 1), True), xx, yy, k * 0.35, anchor='c')
        elif kind == 'confetti':
            yy = y0 + ((py * (y1 - y0) + e * 420 * sp) % (y1 - y0))
            xx = x0 + px * (x1 - x0) + math.sin(e * 4 * sp + ph * 6) * 40
            cols = [YELLOW, RED, BLUE, (0.48, 0.78, 0.30), (0.93, 0.52, 0.72)]
            spr = np.zeros((10, 22, 4), np.float32)
            spr[..., :3] = cols[i % len(cols)]
            spr[..., 3] = 1
            blit(c, _rot(spr, (rot * 360 + e * 400 * sp) % 360), xx, yy, k, anchor='c')
        elif kind == 'heart':
            yy = y1 - ((py * (y1 - y0) + e * 160 * sp) % (y1 - y0))
            xx = x0 + px * (x1 - x0) + math.sin(e * 3 * sp + ph * 6) * 22
            blit(c, _heart(round(10 + 10 * sz), (1.0, 0.45, 0.66)), xx, yy, k * 0.9, anchor='c')
        elif kind == 'spark':
            u = (e * 3 * sp + ph) % 1.0
            if u < 0.25:
                xx, yy = x0 + px * (x1 - x0), y0 + py * (y1 - y0)
                blit(c, star_sprite(round(18 + 22 * sz), YELLOW), xx, yy, k * (1 - u / 0.25), anchor='c')


# ───────────────────────── 6. 字：描邊字、卡拉 OK、標籤、狀聲字、色帶、對話框 ─────────────────────────
@functools.lru_cache(maxsize=256)
def outline_sprite(text, size, font=CJK_B, index=CJK_TC, fill=WHITE, stroke=NAVY, sw=None, shadow=(0.06, 0.07), tracking=0.02):
    """描邊字（動畫 OP 字幕、片名、狀聲字）：粗描邊＋硬陰影（往右下偏移的同色描邊塊）。兩倍大畫再縮。"""
    ss = 2
    S = size * ss
    sw = int(round((sw if sw is not None else size * 0.12) * ss))
    f = ImageFont.truetype(font, S, index=index)
    widths = [f.getlength(ch) for ch in text]
    tw = int(sum(widths) + tracking * S * max(0, len(text) - 1) + S + 4 * sw)
    th = int(S * 1.9 + 4 * sw)
    im = Image.new('RGBA', (tw, th), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    to8 = lambda col: tuple(int(v * 255) for v in col) + (255,)
    for pass_ in ('shadow', 'main'):
        if pass_ == 'shadow' and not shadow:
            continue
        x = sw * 2 + S * 0.2
        ox, oy = (shadow[0] * S, shadow[1] * S) if pass_ == 'shadow' else (0, 0)
        for ch, wd in zip(text, widths):
            if pass_ == 'shadow':
                d.text((x + ox, th * 0.5 + oy), ch, font=f, fill=to8(stroke), anchor='lm', stroke_width=sw, stroke_fill=to8(stroke))
            else:
                d.text((x, th * 0.5), ch, font=f, fill=to8(fill), anchor='lm', stroke_width=sw, stroke_fill=to8(stroke))
            x += wd + tracking * S
    a = np.asarray(im).astype(np.float32) / 255
    a[..., :3] *= a[..., 3:4]
    a = cv2.resize(a, (tw // ss, th // ss), interpolation=cv2.INTER_AREA)
    a[..., :3] /= np.maximum(a[..., 3:4], 1e-6)
    ys, xs = np.nonzero(a[..., 3] > 0.01)
    if len(xs):
        a = a[max(0, ys.min() - 2):ys.max() + 3, max(0, xs.min() - 2):xs.max() + 3]
    return a


def karaoke(c, text, u, cx, cy, size=52, base=WHITE, sung=YELLOW, stroke=NAVY, op=1.0, font=CJK_B, index=CJK_TC, sw=None):
    """卡拉 OK 字幕：整行白字深藍描邊，唱到的部分（由左到右 u＝0–1）變黃；中心對齊 (cx, cy)。"""
    A = outline_sprite(text, size, font, index, base, stroke, sw)
    B = outline_sprite(text, size, font, index, sung, stroke, sw)
    h, w = A.shape[:2]
    x, y = cx - w / 2, cy - h / 2
    blit(c, A, x, y, op)
    if u > 0:
        cut = int(np.clip(u, 0, 1) * w)
        if cut > 0:
            Bc = B.copy()
            Bc[:, cut:, 3] = 0
            edge = min(6, w - cut)
            if edge > 0:
                Bc[:, cut - 0:cut + edge, 3] = 0
            blit(c, Bc, x, y, op)


@functools.lru_cache(maxsize=64)
def tag_sprite(text, col, size=40, txt_col=WHITE, font=CJK_B, index=CJK_TC):
    """屬性標籤（膠囊形色塊＋白色粗字＋深一點的邊框），遊戲裡屬性圖示的語法。"""
    t = outline_sprite(text, size, font, index, txt_col, tuple(v * 0.55 for v in col), sw=size * 0.08, shadow=None)
    th, tw = t.shape[:2]
    pad_x, pad_y = int(size * 0.75), int(size * 0.30)
    H, W = th + 2 * pad_y, tw + 2 * pad_x
    S = 3
    m = np.zeros((H * S, W * S), np.float32)
    r = H * S // 2
    cv2.rectangle(m, (r, 0), (W * S - r, H * S), 1.0, -1)
    cv2.circle(m, (r, r), r, 1.0, -1, cv2.LINE_AA)
    cv2.circle(m, (W * S - r, r), r, 1.0, -1, cv2.LINE_AA)
    m = cv2.resize(m, (W, H), interpolation=cv2.INTER_AREA)
    inner = cv2.erode(m, np.ones((5, 5), np.uint8))
    out = np.zeros((H, W, 4), np.float32)
    out[..., :3] = np.float32([v * 0.55 for v in col])
    out[..., :3] = out[..., :3] * (1 - inner[..., None]) + np.float32(col) * inner[..., None]
    yy = np.linspace(0, 1, H, dtype=np.float32)[:, None, None]
    out[..., :3] = np.clip(out[..., :3] * (1.12 - 0.24 * yy), 0, 1)
    out[..., 3] = m
    blit(out[..., :3], t, pad_x, pad_y, 1.0)   # 字貼在色塊上（RGB 部分），外形仍是膠囊
    return out


def slam(c, spr, e, x, y, dur=0.9, rot=-6.0, anchor='c', pop=1.7, op=1.0):
    """砸進來：0.16 秒內從 pop 倍縮到 1（back_out 過頭一點）、最後 0.2 秒淡出；e＝進場後秒數。"""
    if e < 0 or e > dur:
        return
    u = min(1.0, e / 0.16)
    s = pop + (1 - pop) * back_out(u)
    a = op * (1 if e < dur - 0.2 else (dur - e) / 0.2)
    h, w = spr.shape[:2]
    sp = cv2.resize(spr, (max(1, int(w * s)), max(1, int(h * s))), interpolation=cv2.INTER_LINEAR)
    blit(c, _rot(sp, rot), x, y, a, anchor=anchor)


def cut_in(c, e, dur, text_spr, y, h=150, col=YELLOW, angle=-7.0, side=1, op=1.0):
    """カットイン：斜向色帶從側邊滑進、停住、滑出；字在色帶上。e＝進場後秒數。"""
    if e < 0 or e > dur:
        return
    H_, W_ = c.shape[:2]
    if e < 0.22:
        off = (1 - ease_out(e / 0.22)) * W_ * 1.2
    elif e > dur - 0.22:
        off = -ease((e - (dur - 0.22)) / 0.22) * W_ * 1.2
    else:
        off = 0.0
    off *= side
    band = np.zeros((h * 3, W_ * 2, 4), np.float32)
    band[h:2 * h, :, :3] = col
    band[h:2 * h, :, 3] = 1.0
    band[h - 6:h, :, :3], band[h - 6:h, :, 3] = WHITE, 1.0
    band[2 * h:2 * h + 6, :, :3], band[2 * h:2 * h + 6, :, 3] = WHITE, 1.0
    th, tw = text_spr.shape[:2]
    blit(band[..., :3], text_spr, W_ - tw / 2, 1.5 * h - th / 2, 1.0)
    band = _rot(band, angle)
    blit(c, band, W_ / 2 - off, y, op, anchor='c')


@functools.lru_cache(maxsize=8)
def _box(w, h, r=26):
    S = 2
    m = np.zeros((h * S, w * S), np.float32)
    cv2.rectangle(m, (r * S, 0), (w * S - r * S, h * S), 1, -1)
    cv2.rectangle(m, (0, r * S), (w * S, h * S - r * S), 1, -1)
    for cx, cy in [(r, r), (w - r, r), (r, h - r), (w - r, h - r)]:
        cv2.circle(m, (cx * S, cy * S), r * S, 1, -1, cv2.LINE_AA)
    return cv2.resize(m, (w, h), interpolation=cv2.INTER_AREA)


def dialog_box(c, lines, e, x, y, w=920, h=210, cps=16, size=44, op=1.0):
    """遊戲對話框：白底圓角、深色雙框、字逐字打出（cps 每秒字數）、打完右下角 ▼ 閃。e＝進場後秒數。"""
    if e < 0:
        return
    m = _box(w, h)
    outer = np.zeros((h, w, 4), np.float32)
    outer[..., :3] = (0.20, 0.22, 0.28)
    outer[..., 3] = m
    blit(c, outer, x, y, op * min(1.0, e / 0.08))
    m2 = _box(w - 16, h - 16, 20)
    inner = np.zeros((h - 16, w - 16, 4), np.float32)
    inner[..., :3] = (0.98, 0.98, 0.96)
    inner[..., 3] = m2
    blit(c, inner, x + 8, y + 8, op * min(1.0, e / 0.08))
    n_total = sum(len(s) for s in lines)
    shown = int(e * cps)
    yy = y + 44
    for s in lines:
        k = max(0, min(len(s), shown))
        if k > 0:
            spr = outline_sprite(s[:k], size, CJK_B, CJK_TC, (0.16, 0.17, 0.22), (0.16, 0.17, 0.22), sw=0, shadow=None)
            blit(c, spr, x + 48, yy, op)
        shown -= len(s)
        yy += size * 1.45
    if e * cps > n_total and (e * 2.5) % 1 < 0.6:
        al = np.zeros((22, 26), np.float32)
        cv2.fillPoly(al, [np.array([[0, 0], [25, 0], [12, 21]], np.int32)], 1.0, cv2.LINE_AA)
        tri = np.zeros((22, 26, 4), np.float32)
        tri[..., :3], tri[..., 3] = (0.85, 0.20, 0.18), al
        blit(c, tri, x + w - 70, y + h - 54, op)


# ───────────────────────── 7. 收服用的球、球形轉場、收服成功、進化 ─────────────────────────
@functools.lru_cache(maxsize=32)
def ball_sprite(d, top=RED, bottom=(0.97, 0.97, 0.97), line=(0.07, 0.07, 0.09)):
    """收服用的紅白球：上紅下白、中間黑帶、中央按鈕、左上高光。d＝直徑 px。"""
    S = 3
    D = d * S
    R = D / 2
    yy, xx = np.mgrid[0:D, 0:D].astype(np.float32)
    dx, dy = xx - R, yy - R
    rr = np.sqrt(dx * dx + dy * dy)
    disk = np.clip(R - rr, 0, 1)
    col = np.where((dy < 0)[..., None], np.float32(top), np.float32(bottom))
    shade = np.clip(1.08 - 0.38 * np.clip((dx + dy) / (2 * R) + 0.3, 0, 1), 0.6, 1.1)
    col = col * shade[..., None]
    band = (np.abs(dy) < D * 0.045)
    col[band] = line
    btn_o, btn_i = D * 0.17, D * 0.11
    col[rr < btn_o] = line
    col[rr < btn_o * 0.82] = (0.97, 0.97, 0.97)
    col[rr < btn_i * 0.75] = (0.86, 0.86, 0.88)
    edge = (rr > R - D * 0.035)
    col[edge] = line
    hl = np.clip(1 - np.sqrt(((dx + R * 0.38) / (R * 0.28)) ** 2 + ((dy + R * 0.48) / (R * 0.14)) ** 2), 0, 1) ** 0.6
    col = col + hl[..., None] * 0.55
    out = np.zeros((D, D, 4), np.float32)
    out[..., :3] = np.clip(col, 0, 1)
    out[..., 3] = disk
    pm = out.copy()
    pm[..., :3] *= pm[..., 3:4]
    pm = cv2.resize(pm, (d, d), interpolation=cv2.INTER_AREA)
    pm[..., :3] /= np.maximum(pm[..., 3:4], 1e-6)
    return pm


def ball(c, x, y, d, rot=0.0, op=1.0):
    blit(c, _rot(ball_sprite(int(d)), rot), x, y, op, anchor='c')


def ball_wipe(c, u, band=34, btn=150):
    """球形轉場：上紅下白兩半從上下合起來（u 0→0.5），中間黑帶＋按鈕，合上那一下按鈕亮，再打開（0.5→1）。
    合上前的 c 給 A 鏡頭、打開時的 c 給 B 鏡頭（引擎決定底下是哪一顆）。"""
    if u <= 0 or u >= 1:
        return
    h, w = c.shape[:2]
    p = ease(u / 0.5) if u < 0.5 else 1 - ease((u - 0.5) / 0.5)
    yt = int(h / 2 * p)
    yb = int(h - h / 2 * p)
    if yt > 0:
        g = np.linspace(1.0, 0.82, yt, dtype=np.float32)[:, None, None]
        c[:yt] = np.float32(RED) * g
        c[max(0, yt - band // 2):yt] = (0.07, 0.07, 0.09)
    if yb < h:
        g = np.linspace(0.85, 1.0, h - yb, dtype=np.float32)[:, None, None]
        c[yb:] = np.float32((0.96, 0.96, 0.96)) * g
        c[yb:min(h, yb + band // 2)] = (0.07, 0.07, 0.09)
    if p > 0.82:
        k = (p - 0.82) / 0.18
        r = int(btn * (0.6 + 0.4 * k))
        cv2.circle(c, (w // 2, h // 2), r, (0.07, 0.07, 0.09), -1, cv2.LINE_AA)
        cv2.circle(c, (w // 2, h // 2), int(r * 0.80), (0.97, 0.97, 0.97), -1, cv2.LINE_AA)
        cv2.circle(c, (w // 2, h // 2), int(r * 0.52), (0.88, 0.88, 0.90), -1, cv2.LINE_AA)
        if abs(u - 0.5) < 0.06:
            g = np.zeros((h // 4, w // 4), np.float32)
            cv2.circle(g, (w // 8, h // 8), int(r * 0.55 / 4), 1.0, -1)
            g = cv2.resize(cv2.GaussianBlur(g, (0, 0), 14), (w, h))[..., None]
            c[:] = 1 - (1 - c) * (1 - np.clip(g * 1.6, 0, 1))


def capture_burst(c, e, x, y, size=46, n=3, dist=170):
    """收服成功的星星：從 (x, y) 往上方三個方向飛出、轉、淡掉（0.7 秒）。"""
    if e < 0 or e > 0.7:
        return
    u = ease_out(e / 0.7)
    for i in range(n):
        ang = -math.pi / 2 + (i - (n - 1) / 2) * 0.75
        xx, yy = x + math.cos(ang) * dist * u, y + math.sin(ang) * dist * u
        blit(c, _rot(star_sprite(size, YELLOW), e * 300), xx, yy, 1 - e / 0.7, anchor='c')


def wobble(e, beats=(0.5, 1.0, 1.5), amp=22.0, dur=0.28):
    """球搖三下的角度：每個 beat 起一次左右擺（衰減），其他時間停住。"""
    for b in beats:
        if b <= e < b + dur:
            v = (e - b) / dur
            return amp * math.sin(v * math.pi * 2) * (1 - v)
    return 0.0


def silhouette(img, tint=(0.88, 0.94, 1.0)):
    """進化時的白色剪影：整體推到近白、保留墨線讓形狀認得出來、外加柔光。"""
    L = _lum(img)
    e = xdog(cv2.GaussianBlur(L, (0, 0), 1.0).astype(np.float32), sigma=1.6, tau=0.985, phi=40)
    base = (0.72 + 0.28 * np.clip(L * 1.4, 0, 1))[..., None] * np.float32(tint)
    out = base * (0.45 + 0.55 * e[..., None])
    g = cv2.GaussianBlur(out, (0, 0), 18)
    return np.clip(1 - (1 - out) * (1 - g * 0.6), 0, 1)


def evolution(a, b, u, f0=2.5, f1=16.0, dur=1.6):
    """進化閃光：A、B 的白色剪影交替閃（越閃越快），最後白閃、B 出現。u 0→1；dur＝這段的秒數（決定閃爍頻率）。"""
    if u < 0.78:
        tt = u / 0.78 * dur
        ph = f0 * tt + (f1 - f0) * tt * tt / (2 * dur)
        return silhouette(a) if int(ph * 2) % 2 == 0 else silhouette(b)
    if u < 0.86:
        return np.ones_like(a)
    v = (u - 0.86) / 0.14
    return np.ones_like(b) * (1 - ease(v)) + b * ease(v)


# ───────────────────────── 8. 漫畫搞笑：絕望直線、汗滴 ─────────────────────────
def gloom(c, k=1.0, seed=0, depth=0.45, col=(0.10, 0.12, 0.30)):
    """絕望直線（漫畫的「ガーン」）：畫面上方垂下的細直線＋偏藍暗。"""
    if k <= 0:
        return
    h, w = c.shape[:2]
    y = np.linspace(0, 1, h, dtype=np.float32)[:, None, None]
    shade = np.clip(1 - y / depth, 0, 1) * 0.55 * k
    c[:] = c * (1 - shade) + np.float32(col) * shade
    lay = np.zeros((h, w), np.float32)
    r = np.random.default_rng(1300 + seed)
    for _ in range(70):
        x = int(r.random() * w)
        L = int(h * depth * (0.4 + 0.6 * r.random()))
        cv2.line(lay, (x, 0), (x, L), 1.0, 2 + int(3 * r.random()), cv2.LINE_AA)
    lay = lay * np.clip(1 - y[..., 0] / depth, 0, 1) ** 0.7
    lay = lay[..., None] * 0.85 * k
    c[:] = c * (1 - lay) + np.float32(col) * lay


@functools.lru_cache(maxsize=8)
def sweat_sprite(size=90):
    S = size * 2
    im = Image.new('RGBA', (S, int(S * 1.4)), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    R = S * 0.32
    cx, cy = S / 2, S * 0.9
    d.polygon([(cx, cy - R * 2.4), (cx - R * 0.95, cy - R * 0.2), (cx + R * 0.95, cy - R * 0.2)], fill=(120, 190, 255, 255), outline=(20, 40, 90, 255))
    d.ellipse([cx - R, cy - R, cx + R, cy + R], fill=(120, 190, 255, 255), outline=(20, 40, 90, 255), width=int(S * 0.04))
    d.ellipse([cx - R * 0.5, cy - R * 0.6, cx - R * 0.1, cy - R * 0.1], fill=(235, 248, 255, 255))
    a = np.asarray(im.resize((size, int(size * 1.4)), Image.LANCZOS)).astype(np.float32) / 255
    return a


# ───────────────────────── demo ─────────────────────────
def _demo(a):
    img = cv2.imread(a.input)[..., ::-1].astype(np.float32) / 255
    img = cv2.resize(img, (540, 960), interpolation=cv2.INTER_AREA)
    tiles = []

    def tile(name, fn):
        c = img.copy()
        fn(c)
        c = np.clip(c, 0, 1)
        t = (c * 255).astype(np.uint8)[..., ::-1].copy()
        cv2.putText(t, name, (12, 40), cv2.FONT_HERSHEY_SIMPLEX, 1.1, (255, 255, 255), 3, cv2.LINE_AA)
        tiles.append(t)

    tile('cel', lambda c: c.__setitem__(slice(None), cel(c)))
    tile('speed_lines', lambda c: speed_lines(c, 0.0, 270, 400, 0.9))
    tile('impact', lambda c: impact(c))
    tile('sunburst', lambda c: sunburst(c, 0.0, 270, 420, 0.4))
    tile('lightning', lambda c: lightning(c, 0.0, (60, 120), (480, 700)))
    tile('sparkles', lambda c: sparkles(c, 0.3, scatter(3, 14, 40, 80, 500, 900), 30))
    tile('ember', lambda c: particles(c, 1.0, 'ember', region=(0, 300, 540, 960)))
    tile('bubble', lambda c: particles(c, 1.0, 'bubble', n=24))
    tile('leaf', lambda c: particles(c, 1.0, 'leaf', n=24))
    tile('ball', lambda c: (ball(c, 270, 480, 180, 15), capture_burst(c, 0.3, 270, 400)))
    tile('ball_wipe', lambda c: ball_wipe(c, 0.47, btn=80))
    tile('evolution', lambda c: c.__setitem__(slice(None), silhouette(c)))
    tile('karaoke', lambda c: karaoke(c, '一定要收服你', 0.55, 270, 800, 44))
    tile('tag', lambda c: blit(c, tag_sprite('火', TYPE['火'], 44), 40, 120))
    tile('dialog', lambda c: dialog_box(c, ['咦？戰利品的樣子……！'], 9, 20, 700, 500, 140, size=30))
    tile('gloom', lambda c: (gloom(c), blit(c, sweat_sprite(60), 380, 200)))
    rows = [np.hstack(tiles[i:i + 4]) for i in range(0, len(tiles), 4)]
    w = max(r.shape[1] for r in rows)
    rows = [np.pad(r, ((0, 0), (0, w - r.shape[1]), (0, 0))) for r in rows]
    cv2.imwrite(a.out, np.vstack(rows), [cv2.IMWRITE_JPEG_QUALITY, 85])
    print(a.out)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = p.add_subparsers(dest='cmd', required=True)
    s = sp.add_parser('demo')
    s.add_argument('input')
    s.add_argument('-o', '--out', required=True)
    a = p.parse_args()
    _demo(a)


if __name__ == '__main__':
    main()
