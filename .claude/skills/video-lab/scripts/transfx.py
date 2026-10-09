"""題材轉場：轉場動詞從畫面裡的東西長出來（火→燒過去、水→漣漪、草→落葉掃過、天空→雲穿過、光→光帶）。

每個轉場都是純函式 f(a, b, u, ...) → 新畫面；a＝出去的鏡頭、b＝進來的鏡頭（float32 RGB 0–1、同尺寸），u＝0–1 進度。
兩邊的實拍一直看得到（轉場的峰值也只蓋住邊界帶），不做純圖像的過場。長度建議 8–14 格、正中落在拍上。
  import transfx as TX
  c = TX.burn(a, b, u, seed=3)              # 從下往上燒開：邊緣橘白發光＋餘燼
  c = TX.ripple(a, b, u, cx=540, cy=1300)   # 水滴落下的圈：圈內是下一個鏡頭，圈邊折射＋高光
  c = TX.leaves(a, b, u, t, seed=1)         # 一陣葉子斜掃過去，葉子後面換鏡頭
  c = TX.clouds(a, b, u, t)                 # 前景雲穿過（飛行、天空鏡頭）
  c = TX.light_band(a, b, u, angle=0.35)    # 一道光帶掃過，光後面換鏡頭（白天／日落之間）
  c = TX.whip(a, b, u, 'left')              # 甩鏡：方向性動態模糊，中點交換
  c = TX.zoom_through(a, b, u, cx, cy)      # 往 a 的一點衝進去、從 b 的中心退出來（放射模糊）
  c = TX.iris(a, b, u, cx, cy)              # 從物件位置開的圓：金色細邊（match cut 的強化版）
  c = TX.encounter(a, b, u)                 # 遊戲遇敵：白閃三下＋橫條交錯滑開（寶可夢題材專用，一支片一次）
  python transfx.py demo -o /tmp/tx.jpg
"""
import functools
import math
import os

import cv2
import numpy as np


# ───────── 雜訊 ─────────
@functools.lru_cache(maxsize=16)
def fbm(h, w, seed=0, scale=6.0, octaves=4):
    """平滑分形雜訊 0–1（低解析度產生再放大；同一個 seed 永遠相同）。"""
    rng = np.random.default_rng(seed)
    out = np.zeros((h, w), np.float32)
    amp, tot = 1.0, 0.0
    for o in range(octaves):
        s = scale * 2 ** o
        gh, gw = max(2, int(s * h / max(h, w)) + 2), max(2, int(s * w / max(h, w)) + 2)
        g = rng.random((gh, gw)).astype(np.float32)
        out += cv2.resize(g, (w, h), interpolation=cv2.INTER_CUBIC) * amp
        tot += amp
        amp *= 0.5
    out /= tot
    out = (out - out.min()) / (out.max() - out.min() + 1e-6)
    return out


def _screen(c, lay):
    return 1 - (1 - c) * (1 - np.clip(lay, 0, 1))


def _mix(a, b, m):
    m = m[..., None] if m.ndim == 2 else m
    return a * (1 - m) + b * m


# ───────── 火：燒過去 ─────────
def burn(a, b, u, seed=0, direction=(0.0, -1.0), width=0.05, col=(1.0, 0.50, 0.14), heat=10.0, embers=True, t=0.0):
    """燒開：雜訊＋方向梯度的門檻往前推，邊緣是橘白的火線，火線外側一圈焦黑，火線內側一點熱扭曲。"""
    h, w = a.shape[:2]
    n = fbm(h // 4, w // 4, seed, 5.0)
    yy, xx = np.mgrid[0:h // 4, 0:w // 4].astype(np.float32)
    dx, dy = direction
    gr = ((xx / (w // 4)) - 0.5) * dx + ((yy / (h // 4)) - 0.5) * dy
    gr = (gr - gr.min()) / (gr.max() - gr.min() + 1e-6)
    f = cv2.resize(0.55 * n + 0.45 * gr, (w, h), interpolation=cv2.INTER_CUBIC)
    th = -width + u * (1 + 2 * width)
    d = f - th                               # < 0：已燒開（看到 b）
    m = np.clip(0.5 - d / (width * 0.25), 0, 1)
    out = _mix(a, b, m)
    if heat > 0 and 0 < u < 1:
        band = np.exp(-(d / (width * 1.6)) ** 2).astype(np.float32)
        xx2, yy2 = np.mgrid[0:h, 0:w][::-1].astype(np.float32)
        wob = cv2.resize(fbm(h // 8, w // 8, seed + 7, 9.0), (w, h)) - 0.5
        out = cv2.remap(out, xx2, yy2 + wob * heat * band * 2, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
    char = np.clip(1 - np.abs(d - width * 0.9) / (width * 0.9), 0, 1) * (d > 0)
    out = out * (1 - 0.75 * char[..., None])
    edge = np.exp(-(d / (width * 0.22)) ** 2)
    lay = edge[..., None] * (np.float32(col) * 1.6 + 0.25) + cv2.GaussianBlur(edge, (0, 0), 18)[..., None] * np.float32(col) * 1.1
    out = _screen(out, lay * (1.0 if 0 < u < 1 else 0.0))
    if embers and 0.05 < u < 0.98:
        rng = np.random.default_rng(seed + 31)
        pts = rng.random((260, 2))
        ph = rng.random(260)
        S = 4
        e = np.zeros((h, w), np.float32)
        for (px, py), p in zip(pts, ph):
            x, y = int(px * w), int(py * h)
            if abs(d[min(y, h - 1), min(x, w - 1)]) < width * 1.5:
                life = (u * 9 + p) % 1.0
                yy_ = y - life * 160
                xx_ = x + math.sin(p * 20 + u * 12) * 18
                cv2.circle(e, (int(xx_ * S), int(yy_ * S)), int((2.4 - 1.6 * life) * S), float(1 - life), -1, cv2.LINE_AA, shift=2)
        lay = (e + cv2.GaussianBlur(e, (0, 0), 5) * 2)[..., None] * np.float32((1.0, 0.70, 0.30))
        out = _screen(out, lay)
    return out.astype(np.float32)


# ───────── 水：漣漪 ─────────
def ripple(a, b, u, cx=None, cy=None, rmax=None, band=90.0, amp=26.0, rings=3, col=(0.92, 0.98, 1.0)):
    """一滴水落下的圈往外擴：圈內是 b；圈邊（band 寬）折射位移＋一條細高光；b 裡面再有幾圈越來越淡的小波紋。"""
    h, w = a.shape[:2]
    cx = w / 2 if cx is None else cx
    cy = h / 2 if cy is None else cy
    rmax = rmax or math.hypot(max(cx, w - cx), max(cy, h - cy)) + band
    r = rmax * (1 - (1 - min(max(u, 0), 1)) ** 2.2)
    xx, yy = np.mgrid[0:h, 0:w][::-1].astype(np.float32)
    dx, dy = xx - cx, yy - cy
    rr = np.sqrt(dx * dx + dy * dy) + 1e-6
    d = rr - r
    m = np.clip(0.5 - d / 3.0, 0, 1)
    wave = np.exp(-(d / band) ** 2) * np.sin(d / band * math.pi * 2.0)
    for k in range(1, rings + 1):     # 圈內的小波紋（越裡越淡）
        dk = rr - r * (1 - 0.22 * k)
        wave += np.exp(-(dk / (band * 0.6)) ** 2) * np.sin(dk / (band * 0.6) * math.pi * 2) * 0.45 ** k * (rr < r)
    off = wave * amp * (1 - u * 0.6)
    mx, my = xx - dx / rr * off, yy - dy / rr * off
    A = cv2.remap(a, mx, my, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
    B = cv2.remap(b, mx, my, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
    out = _mix(A, B, m)
    hl = np.clip(np.exp(-((d + band * 0.18) / 5.0) ** 2) * 0.9 + np.maximum(wave, 0) * 0.18, 0, 1) * (1 - u ** 3)
    return _screen(out, hl[..., None] * np.float32(col)).astype(np.float32)


# ───────── 草：落葉掃過 ─────────
@functools.lru_cache(maxsize=64)
def leaf_sprite(r, seed=0):
    """寫實一點的葉子：不對稱葉形、葉脈（主脈＋側脈）、逆光透色（尖端黃綠、基部深綠）、上緣一條光澤、邊緣略暗。"""
    rng = np.random.default_rng(seed)
    S = 4
    L, Wd = r * 2.0, r * (0.62 + 0.25 * rng.random())
    pad = int(r * 0.3) + 4
    w, h = int(L + 2 * pad), int(Wd + 2 * pad)
    m = np.zeros((h * S, w * S), np.uint8)
    pts = []
    bend = (rng.random() - 0.5) * 0.25
    for i in range(61):
        u = i / 60
        y = math.sin(u * math.pi) ** 0.75 * (0.5 + 0.06 * math.sin(u * 7)) * Wd * 0.5
        pts.append(((pad + u * L) * S, (h / 2 - y + bend * Wd * math.sin(u * math.pi)) * S))
    for i in range(61):
        u = 1 - i / 60
        y = math.sin(u * math.pi) ** 0.85 * 0.46 * Wd
        pts.append(((pad + u * L) * S, (h / 2 + y + bend * Wd * math.sin(u * math.pi)) * S))
    cv2.fillPoly(m, [np.int32(pts)], 255, cv2.LINE_AA)
    a = cv2.resize(m, (w, h), interpolation=cv2.INTER_AREA).astype(np.float32) / 255
    xx, yy = np.mgrid[0:h, 0:w][::-1].astype(np.float32)
    u = np.clip((xx - pad) / L, 0, 1)
    mid = h / 2 + bend * Wd * np.sin(u * math.pi)
    v = (yy - mid) / (Wd * 0.5)
    hue = rng.random()
    tip = np.float32([0.78, 0.86, 0.30]) if hue < 0.7 else np.float32([0.92, 0.78, 0.30])
    base = np.float32([0.16, 0.38, 0.12]) if hue < 0.7 else np.float32([0.45, 0.42, 0.14])
    col = base + (tip - base) * (u ** 0.8)[..., None]
    vein = np.exp(-(v / 0.05) ** 2)
    side = np.exp(-(((u * 9 - np.abs(v) * 2.2) % 1.0 - 0.5) / 0.08) ** 2) * (np.abs(v) < 0.9) * 0.5
    sheen = np.exp(-((v + 0.45) / 0.22) ** 2) * 0.22
    rim = np.clip(1 - a, 0, 1)
    col = col * (1 + 0.35 * vein[..., None] + 0.18 * side[..., None]) + sheen[..., None]
    col = col * (1 - 0.35 * cv2.GaussianBlur(rim, (0, 0), 1.5)[..., None])
    out = np.zeros((h, w, 4), np.float32)
    out[..., :3] = np.clip(col, 0, 1)
    out[..., 3] = a
    return out


def _mblur_spr(spr, ang, length):
    """精靈沿 ang 方向的動態模糊（預乘 alpha 下做）。"""
    if length < 1.5:
        return spr
    n = int(length) | 1
    k = np.zeros((n, n), np.float32)
    c0 = n // 2
    for i in range(n):
        f = i / (n - 1) - 0.5
        k[int(round(c0 + math.sin(ang) * f * (n - 1))), int(round(c0 + math.cos(ang) * f * (n - 1)))] = 1
    k /= k.sum()
    p = int(length / 2) + 2
    s = np.pad(spr, ((p, p), (p, p), (0, 0)))
    s[..., :3] *= s[..., 3:4]
    s = cv2.filter2D(s, -1, k)
    s[..., :3] /= np.maximum(s[..., 3:4], 1e-6)
    return s


def leaves(a, b, u, t=0.0, seed=0, n=120, angle=-0.55, speed=1.0):
    """一陣葉子沿 angle 方向掃過（前緣最密），葉子後面換成 b。近的大、糊、動態模糊長；遠的小、清楚。"""
    from animepro import _rot
    from seekkit import blit
    h, w = a.shape[:2]
    ca, sa = math.cos(angle), math.sin(angle)
    xx, yy = np.mgrid[0:h, 0:w][::-1].astype(np.float32)
    proj = ((xx - w / 2) * ca + (yy - h / 2) * sa) / (abs(w * ca) + abs(h * sa)) + 0.5   # 0→1 沿掃的方向
    front = -0.25 + u * 1.5
    m = np.clip((front - proj) / 0.10 + 0.5, 0, 1)
    out = _mix(a, b, m)
    rng = np.random.default_rng(seed)
    P = rng.random((n, 6))
    L = abs(w * ca) + abs(h * sa)
    order = np.argsort(P[:, 2])                         # 遠的先畫
    for i in order:
        p0, lat, z, spin, sd, ph = P[i]
        along = front + (p0 - 0.75) * 0.55
        if along < -0.2 or along > 1.2:
            continue
        x = w / 2 + (along - 0.5) * L * ca - (lat - 0.5) * L * sa * 1.2 + math.sin(ph * 9 + u * 7) * 30
        y = h / 2 + (along - 0.5) * L * sa + (lat - 0.5) * L * ca * 1.2 + math.cos(ph * 7 + u * 5) * 30
        r = int(14 + 70 * z ** 2.2 * (w / 1080 + 0.25))
        spr = leaf_sprite(max(6, r), int(sd * 12))
        spr = _rot(spr, (spin * 360 + u * 400 * (1 if ph > 0.5 else -1)) % 360)
        if z > 0.8:
            spr = cv2.GaussianBlur(spr, (0, 0), (z - 0.8) * 30 * w / 1080 + 0.01)
        spr = _mblur_spr(spr, angle, (10 + 60 * z) * speed * w / 1080)
        shade = 0.75 + 0.25 * (1 - abs(lat - 0.5) * 2)
        s2 = spr.copy()
        s2[..., :3] *= shade
        blit(out, s2, x - s2.shape[1] / 2, y - s2.shape[0] / 2, 0.97)
    return out.astype(np.float32)


# ───────── 天空：雲穿過 ─────────
@functools.lru_cache(maxsize=4)
def _cloud_field(h, w, seed):
    """比畫面高 2.2 倍的雲場（低解析度）：大塊團狀＋細節，往上捲的「棉花」邊。"""
    H2 = int(h * 2.2)
    big = fbm(H2 // 6, w // 6, seed, 2.2, 3)
    det = fbm(H2 // 6, w // 6, seed + 1, 7.0, 4)
    n = big * 0.72 + det * 0.28
    return cv2.resize(n, (w // 2, H2 // 2), interpolation=cv2.INTER_CUBIC)


def clouds(a, b, u, t=0.0, seed=0, sun=(1.0, 0.97, 0.92), shadow=(0.62, 0.68, 0.80)):
    """穿雲：雲從下往上流過（像飛機爬升穿雲），u=0.5 最厚、在雲後面換鏡頭。雲有受光面（暖白）與背光面（灰藍），邊緣柔。"""
    h, w = a.shape[:2]
    F = _cloud_field(h, w, seed)
    H2 = F.shape[0]
    off = int((1 - u) * (H2 - h // 2))
    win = F[off:off + h // 2]
    if win.shape[0] < h // 2:
        win = np.pad(win, ((0, h // 2 - win.shape[0]), (0, 0)), mode='edge')
    cover = math.sin(math.pi * min(max(u, 0), 1)) ** 0.8
    th = 0.86 - cover * 0.84
    dens = np.clip((win - th) / 0.16, 0, 1)
    light = np.clip(0.5 + (win - np.roll(win, 6, 0)) * 9, 0, 1)        # 上方是太陽：往上變亮的面受光
    col = np.float32(shadow) + (np.float32(sun) - np.float32(shadow)) * light[..., None]
    dens = cv2.resize(cv2.GaussianBlur(dens, (0, 0), 2.0), (w, h), interpolation=cv2.INTER_CUBIC)
    col = cv2.resize(col, (w, h), interpolation=cv2.INTER_CUBIC)
    base = a if u < 0.5 else b
    haze = 0.25 * cover
    base = base * (1 - haze) + np.float32(sun) * haze
    return np.clip(base * (1 - dens[..., None]) + col * dens[..., None], 0, 1).astype(np.float32)


# ───────── 光帶 ─────────
def light_band(a, b, u, angle=0.35, width=0.10, col=(1.0, 0.93, 0.78), k=1.0):
    """一道斜光掃過：光帶前面是 a、後面是 b；光帶附近兩邊都過曝一點（像陽光掃過鏡頭）。"""
    h, w = a.shape[:2]
    xx, yy = np.mgrid[0:h, 0:w][::-1].astype(np.float32)
    ca, sa = math.cos(angle), math.sin(angle)
    proj = ((xx - w / 2) * ca + (yy - h / 2) * sa) / (abs(w * ca) + abs(h * sa)) + 0.5
    pos = -width * 2 + u * (1 + width * 4)
    d = proj - pos
    m = np.clip(0.5 - d / (width * 0.35), 0, 1)
    out = _mix(a, b, m)
    core = np.exp(-(d / (width * 0.35)) ** 2)
    glow = np.exp(-(d / (width * 1.8)) ** 2)
    lay = (core * 1.1 + glow * 0.45)[..., None] * np.float32(col) * k
    out = out * (1 + glow[..., None] * 0.25 * k)
    return _screen(np.clip(out, 0, 1), lay).astype(np.float32)


# ───────── 甩鏡 ─────────
def _dblur(img, dx, dy, n=9):
    if abs(dx) + abs(dy) < 1:
        return img
    acc = np.zeros_like(img)
    h, w = img.shape[:2]
    for i in range(n):
        f = (i / (n - 1) - 0.5)
        M = np.float32([[1, 0, dx * f], [0, 1, dy * f]])
        acc += cv2.warpAffine(img, M, (w, h), borderMode=cv2.BORDER_REFLECT)
    return acc / n


def whip(a, b, u, direction='left', blur=260.0):
    """甩鏡：前半 a 加速滑出、後半 b 減速滑入，中段方向性動態模糊最強（相機真的甩過去的樣子）。"""
    h, w = a.shape[:2]
    sx, sy = {'left': (-1, 0), 'right': (1, 0), 'up': (0, -1), 'down': (0, 1)}[direction]
    if u < 0.5:
        v = (u / 0.5) ** 2.2
        off = v * 0.55
        img, s = a, v
    else:
        v = (1 - (u - 0.5) / 0.5) ** 2.2
        off = -v * 0.55
        img, s = b, v
    M = np.float32([[1, 0, sx * off * w], [0, 1, sy * off * h]])
    moved = cv2.warpAffine(img, M, (w, h), borderMode=cv2.BORDER_REFLECT)
    return _dblur(moved, sx * blur * s, sy * blur * s).astype(np.float32)


# ───────── 衝進去 ─────────
def _rblur(img, cx, cy, amount, n=8):
    if amount < 0.004:
        return img
    h, w = img.shape[:2]
    acc = np.zeros_like(img)
    for i in range(n):
        s = 1 + amount * i / (n - 1)
        M = np.float32([[s, 0, cx * (1 - s)], [0, s, cy * (1 - s)]])
        acc += cv2.warpAffine(img, M, (w, h), borderMode=cv2.BORDER_REFLECT)
    return acc / n


def zoom_through(a, b, u, cx=None, cy=None, zmax=3.2, flash=0.6):
    """往 a 的 (cx, cy) 衝進去（放大＋放射模糊）→ 中點一下亮 → b 從稍微放大退回原位（模糊遞減）。"""
    h, w = a.shape[:2]
    cx = w / 2 if cx is None else cx
    cy = h / 2 if cy is None else cy
    if u < 0.5:
        v = (u / 0.5) ** 2.4
        s = 1 + (zmax - 1) * v
        M = np.float32([[s, 0, cx * (1 - s)], [0, s, cy * (1 - s)]])
        img = cv2.warpAffine(a, M, (w, h), borderMode=cv2.BORDER_REFLECT)
        img = _rblur(img, cx, cy, 0.25 * v)
    else:
        v = (1 - (u - 0.5) / 0.5) ** 2.4
        s = 1 + 0.6 * v
        M = np.float32([[s, 0, w / 2 * (1 - s)], [0, s, h / 2 * (1 - s)]])
        img = cv2.warpAffine(b, M, (w, h), borderMode=cv2.BORDER_REFLECT)
        img = _rblur(img, w / 2, h / 2, 0.22 * v)
    fk = flash * math.exp(-((u - 0.5) / 0.09) ** 2)
    return _screen(img, np.full_like(img, fk) * np.float32((1.0, 0.96, 0.88))).astype(np.float32)


# ───────── 圓 ─────────
def iris(a, b, u, cx=None, cy=None, col=(1.0, 0.84, 0.45), width=3.0, glow=10.0):
    """從物件位置開的圓（金色細邊＋光暈）：用在兩個鏡頭的主體在同一個位置時。"""
    h, w = a.shape[:2]
    cx = w / 2 if cx is None else cx
    cy = h / 2 if cy is None else cy
    rmax = math.hypot(max(cx, w - cx), max(cy, h - cy)) + 20
    r = rmax * (1 - (1 - min(max(u, 0), 1)) ** 3)
    xx, yy = np.mgrid[0:h, 0:w][::-1].astype(np.float32)
    d = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2) - r
    m = np.clip(0.5 - d / 1.5, 0, 1)
    out = _mix(a, b, m)
    ring = np.exp(-(d / width) ** 2) + cv2.GaussianBlur(np.exp(-(d / width) ** 2), (0, 0), glow) * 1.4
    return _screen(out, ring[..., None] * np.float32(col) * (1 - u ** 4)).astype(np.float32)


# ───────── 遊戲遇敵 ─────────
def encounter(a, b, u, bars=12, flashes=3, col=(1.0, 1.0, 1.0)):
    """遊戲裡「野生的○○出現了！」的進場：前 45% 畫面白閃 flashes 次（a 越閃越亮），後 55% 橫條從左右交錯滑開露出 b。
    跟題材有關才用（寶可夢、遊戲），一支片最多一次。"""
    h, w = a.shape[:2]
    if u < 0.45:
        v = u / 0.45
        k = (0.5 + 0.5 * math.cos(v * flashes * 2 * math.pi + math.pi)) * (0.55 + 0.45 * v)
        L = a @ np.float32([0.2126, 0.7152, 0.0722])
        hi = np.clip(a * 0.4 + L[..., None] * 0.6 + 0.35, 0, 1)
        return (a * (1 - k) + (hi * 0.3 + np.float32(col) * 0.7) * k).astype(np.float32)
    v = (u - 0.45) / 0.55
    out = np.empty_like(b)
    bh = h / bars
    for i in range(bars):
        y0, y1 = int(round(i * bh)), int(round((i + 1) * bh))
        d = 1 if i % 2 == 0 else -1
        e = min(1.0, max(0.0, v * 1.25 - i * 0.02))
        e = 1 - (1 - e) ** 3
        off = int(round(d * (1 - e) * w))
        row = np.full_like(b[y0:y1], 1.0) * np.float32(col)
        if off == 0:
            row = b[y0:y1]
        elif off > 0:
            row[:, off:] = b[y0:y1, :w - off]
        else:
            row[:, :w + off] = b[y0:y1, -off:]
        out[y0:y1] = row
    flash = max(0.0, 1 - v / 0.35) * 0.6
    return (out * (1 - flash) + np.float32(col) * flash).astype(np.float32)


# ───────── 自我測試 ─────────
def _demo(out):
    import glob
    h, w = 480, 270
    fs = sorted(glob.glob(os.path.expanduser('~/video-lab/cache/demo_*.jpg')))
    if len(fs) < 2:
        yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
        a = np.dstack([0.2 + 0.5 * xx / w, 0.35 + 0.0 * yy, 0.6 - 0.3 * yy / h]).astype(np.float32)
        b = np.dstack([0.85 - 0.3 * yy / h, 0.6 + 0.2 * xx / w, 0.25 + 0.0 * xx]).astype(np.float32)
    else:
        a, b = [cv2.resize(cv2.imread(f)[..., ::-1], (w, h), interpolation=cv2.INTER_AREA).astype(np.float32) / 255 for f in fs[:2]]
    rows = []
    fns = [lambda u: burn(a, b, u, 1), lambda u: ripple(a, b, u, 135, 300), lambda u: leaves(a, b, u, 0, 1, n=60),
           lambda u: clouds(a, b, u), lambda u: light_band(a, b, u), lambda u: whip(a, b, u, 'left', 120),
           lambda u: zoom_through(a, b, u, 135, 200), lambda u: iris(a, b, u, 135, 240)]
    for f in fns:
        rows.append(np.concatenate([f(u) for u in (0.2, 0.4, 0.5, 0.6, 0.8)], 1))
    sheet = np.concatenate([np.concatenate(rows[:4], 0), np.concatenate(rows[4:], 0)], 1)
    cv2.imwrite(out, (np.clip(sheet, 0, 1)[..., ::-1] * 255).astype(np.uint8))
    print(out)


if __name__ == '__main__':
    import sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    if len(sys.argv) > 1 and sys.argv[1] == 'demo':
        _demo(sys.argv[sys.argv.index('-o') + 1] if '-o' in sys.argv else '/tmp/tx.jpg')
