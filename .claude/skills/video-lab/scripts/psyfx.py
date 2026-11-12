#!/usr/bin/env python3
"""迷幻卡點舞蹈 MV 零件庫（畫面只由 t 決定）。配方與分寸見 references/dance-mv.md。

拍格
  Grid(audio_json)              .bar(t) → (小節序, 小節起, 小節長, 小節內進度 0–1)；.beat(t) 同上（拍）；.bpos(t) 連續拍位置
                                .section(t) → 段落 dict（songcut.py 的 role：intro／verse／chorus／outro）；.hit(t, fps) 是否剛好在小節線那一格
背景（回傳 float32 RGB 0–1，w×h）
  rings 彩虹同心圓、wheel 旋轉色環（可加漩渦）、melt 融化彩虹、stripes 斜條紋、checker 黑白棋盤（旋轉＋扭曲）、
  photo_bg 資料夾圖片＋色相流轉＋輕微扭曲
畫面處理
  hue_shift（YIQ 旋轉，連角色一起變色也快）、warp 正弦扭曲、kaleido 萬花筒、tear 畫面撕裂＋RGB 分離、rgb_split、flash 閃白
角色
  key_rgba 綠幕／藍幕摳像＋去溢色、sticker 白色貼紙描邊（＋淡投影）、place 依腳底位置縮放旋轉傾斜貼上（次像素）、
  Dancer：keyloop.py 摳好的循環影片（跟歌的拍子同步播放）或靜態立繪＋免費律動（puppet，試片與省錢版）
字
  jp_sprite 日文大字精靈（Dela Gothic One／RocknRoll One／Rampart One，OFL）、big_text 角色後面的大字（在小節線上彈出）

  python psyfx.py demo -o out/psyfx_demo.jpg [--img 背景圖] [--char 立繪.png]   每個零件一格的對照表
"""
import functools
import glob
import json
import math
import os
import sys

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from seekkit import CJK_B, cover, ease  # noqa: E402

FONT_DIR = os.path.expanduser('~/.fonts')
FONTS = {
    'dela': (os.path.join(FONT_DIR, 'DelaGothicOne-Regular.ttf'), 0),     # 極粗黑體，迷幻海報感
    'rock': (os.path.join(FONT_DIR, 'RocknRollOne-Regular.ttf'), 0),      # 圓潤粗體，可愛
    'rampart': (os.path.join(FONT_DIR, 'RampartOne-Regular.ttf'), 0),     # 立體描邊字
    'noto': (CJK_B, 0),                                                   # Noto Sans CJK JP Bold（保底）
}


# ═════════ 拍格 ═════════
class Grid:
    """songcut.py／analyze.py 的 json。小節線之前與最後一個 downbeat 之後用小節長外插。"""

    def __init__(self, J):
        J = json.load(open(J)) if isinstance(J, str) else J
        self.J = J
        self.db = np.array(J['downbeats'], np.float64)
        self.beats = np.array(J['beats'], np.float64)
        self.barlen = float(np.median(np.diff(self.db)))
        self.beatlen = float(np.median(np.diff(self.beats)))
        self.meter = int(J.get('meter', 4))
        self.sections = J['sections']
        self.dur = float(J['duration'])

    def _at(self, arr, L, t):
        i = int(np.searchsorted(arr, t, 'right')) - 1
        if i < 0:
            k = math.floor((t - arr[0]) / L)
            t0 = arr[0] + k * L
            return k, t0, L, (t - t0) / L
        if i >= len(arr) - 1:
            k = math.floor((t - arr[-1]) / L)
            t0 = arr[-1] + k * L
            return len(arr) - 1 + k, t0, L, (t - t0) / L
        t0, t1 = arr[i], arr[i + 1]
        return i, t0, t1 - t0, (t - t0) / (t1 - t0)

    def bar(self, t):
        return self._at(self.db, self.barlen, t)

    def beat(self, t):
        return self._at(self.beats, self.beatlen, t)

    def bpos(self, t):
        i, _, _, u = self.beat(t)
        return i + u

    def bar_time(self, i):
        if 0 <= i < len(self.db):
            return float(self.db[i])
        return float(self.db[0] + i * self.barlen) if i < 0 else float(self.db[-1] + (i - len(self.db) + 1) * self.barlen)

    def section(self, t):
        cur = self.sections[0]
        for s in self.sections:
            if s['start'] <= t + 1e-6:
                cur = s
        return cur

    def role(self, t):
        s = self.section(t)
        return s.get('role') or s['name'].rstrip('0123456789')

    def hit(self, t, fps):
        """t 這一格是否就是小節線所在的格（小節線落在 [t − 半格, t + 半格)）。"""
        i, t0, _, _ = self.bar(t + 0.5 / fps)
        return abs(t - t0) < 0.5 / fps + 1e-6


def pulse(u, k=6.0):
    """拍頭最強、之後指數衰減（u = 拍內或小節內進度）。"""
    return math.exp(-k * max(0.0, u))


# ═════════ 色彩 ═════════
def hue_rgb(h, s=1.0, v=1.0):
    """色相陣列（0–1）→ RGB float32（標準 HSV 公式，向量化）。"""
    h = np.asarray(h, np.float32)
    out = np.empty(h.shape + (3,), np.float32)
    for i, n in enumerate((5.0, 3.0, 1.0)):
        k = np.mod(n + h * 6.0, 6.0)
        out[..., i] = v - v * s * np.clip(np.minimum(k, 4.0 - k), 0, 1)
    return out


@functools.lru_cache(maxsize=1024)
def _hue_m(q):
    th = math.radians(q / 2.0)
    T = np.float32([[0.299, 0.587, 0.114], [0.596, -0.274, -0.322], [0.211, -0.523, 0.312]])
    c, s = math.cos(th), math.sin(th)
    R = np.float32([[1, 0, 0], [0, c, -s], [0, s, c]])
    return (np.linalg.inv(T) @ R @ T).astype(np.float32)


def hue_shift(img, deg):
    """整張圖轉色相（YIQ 平面旋轉，亮度不變；0.5° 一階快取矩陣）。RGBA 只轉 RGB。"""
    if abs(deg % 360) < 0.25:
        return img
    M = _hue_m(int(round((deg % 360) * 2)))
    if img.shape[-1] == 4:
        rgb = np.clip(cv2.transform(np.ascontiguousarray(img[..., :3]), M), 0, 1)
        return np.dstack([rgb, img[..., 3]])
    return np.clip(cv2.transform(img, M), 0, 1)


def saturate(img, k):
    L = img[..., :3] @ np.float32([0.299, 0.587, 0.114])
    rgb = np.clip(L[..., None] + (img[..., :3] - L[..., None]) * k, 0, 1)
    return np.dstack([rgb, img[..., 3]]) if img.shape[-1] == 4 else rgb


# ═════════ 座標快取 ═════════
@functools.lru_cache(maxsize=8)
def _xy(w, h):
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    return xx, yy


@functools.lru_cache(maxsize=16)
def _polar(w, h, cx, cy):
    xx, yy = _xy(w, h)
    dx, dy = xx - cx * w, yy - cy * h
    return np.hypot(dx, dy) / h, np.arctan2(dy, dx).astype(np.float32)


def _smooth_bands(x, n, soft=0.08):
    """x（0–1 循環）量化成 n 階，階與階之間留 soft 寬的柔邊（不鋸齒、仍是色塊感）。"""
    y = x * n
    f = y - np.floor(y)
    e = np.clip((f - (1 - soft)) / soft, 0, 1)
    e = e * e * (3 - 2 * e)
    return (np.floor(y) + e) / n


# ═════════ 背景 ═════════
def rings(t, w, h, cx=0.5, cy=0.5, period=0.14, speed=0.55, bands=7, sat=0.85, wobble=0.0):
    """彩虹同心圓：從中心一圈圈往外流。bands=0 是連續漸層，7 是七色色塊。"""
    r, th = _polar(w, h, cx, cy)
    if wobble:
        r = r * (1 + wobble * np.sin(th * 5 + t * 1.7))
    x = np.mod(r / period - t * speed, 1.0)
    if bands:
        x = _smooth_bands(x, bands)
    return hue_rgb(x, sat)


def wheel(t, w, h, cx=0.5, cy=0.5, spin=0.12, twist=0.0, sectors=12, sat=0.85):
    """旋轉色環；twist > 0 變成漩渦（越外圈色相轉越多）；sectors=0 連續。"""
    r, th = _polar(w, h, cx, cy)
    x = np.mod(th / (2 * np.pi) + t * spin + twist * r, 1.0)
    if sectors:
        x = _smooth_bands(x, sectors, 0.04)
    return hue_rgb(x, sat)


def melt(t, w, h, speed=0.07, drip=0.10, bands=8, sat=0.88):
    """融化彩虹：水平色帶，越往下越被往下拉長、像顏料往下流。"""
    xx, yy = _xy(w, h)
    x, y = xx / w, yy / h
    d = drip * (0.6 * np.sin(x * 9.0 + t * 0.8) + 0.4 * np.sin(x * 23.0 - t * 1.4) + 0.25 * np.sin(x * 51.0 + t * 0.5)) * (0.25 + y)
    v = np.mod(y * 1.15 - d - t * speed, 1.0)
    if bands:
        v = _smooth_bands(v, bands, 0.10)
    return hue_rgb(v, sat)


def stripes(t, w, h, angle=0.55, period=0.085, speed=0.6, cols=None, aa=1.2):
    """斜條紋往一側流；cols=顏色列表（預設彩虹六色），邊緣抗鋸齒 aa px。"""
    cols = np.float32(cols if cols is not None else [hue_rgb(i / 6, 0.85) for i in range(6)])
    xx, yy = _xy(w, h)
    p = (xx * math.cos(angle) + yy * math.sin(angle)) / (period * h) - t * speed
    i = np.floor(p).astype(np.int64)
    f = p - np.floor(p)
    a = cols[np.mod(i, len(cols))]
    b = cols[np.mod(i + 1, len(cols))]
    e = np.clip((f - 1 + aa / (period * h)) / (aa / (period * h)), 0, 1)[..., None]
    return a * (1 - e) + b * e


def checker(t, w, h, size=0.10, rot=0.18, zoom=0.0, warp_amp=0.0, cols=((0.02, 0.02, 0.02), (0.97, 0.97, 0.95))):
    """黑白棋盤：慢慢旋轉、可隨時間縮放（zoom 為每秒倍率變化）、warp_amp 給它扭曲（歐普藝術）。"""
    xx, yy = _xy(w, h)
    x, y = (xx - w / 2) / h, (yy - h / 2) / h
    if warp_amp:
        r = np.hypot(x, y)
        k = 1 + warp_amp * np.sin(r * 9 - t * 2.2)
        x, y = x * k, y * k
    a = t * rot
    s = size * (1 + zoom * math.sin(t * 0.7))
    u = (x * math.cos(a) - y * math.sin(a)) / s
    v = (x * math.sin(a) + y * math.cos(a)) / s
    m = np.sin(np.pi * u) * np.sin(np.pi * v)
    # 抗鋸齒：用 m 在畫面上的實際變化率（相鄰像素差，含扭曲）當過渡寬度，邊緣剛好 1 px 柔，扭曲處也不糊
    gx = np.abs(np.diff(m, axis=1, append=m[:, -1:]))
    gy = np.abs(np.diff(m, axis=0, append=m[-1:, :]))
    e = np.clip(0.5 + m / (2 * (gx + gy) + 1e-4), 0, 1)
    c0, c1 = np.float32(cols[0]), np.float32(cols[1])
    return c0 + (c1 - c0) * e[..., None]


def warp(img, t, amp=7.0, freq=1.0, speed=1.0):
    """輕微正弦扭曲（像熱浪、液體）。amp = px（以 720p 為準等比）。"""
    h, w = img.shape[:2]
    xx, yy = _xy(w, h)
    a = amp * h / 720
    f = freq * 2 * np.pi / h
    mx = xx + a * np.sin(yy * f * 1.3 + t * 1.9 * speed) + a * 0.5 * np.sin((xx + yy) * f * 2.1 - t * 1.1 * speed)
    my = yy + a * np.sin(xx * f * 1.1 - t * 1.5 * speed) + a * 0.5 * np.sin((xx - yy) * f * 1.7 + t * 0.9 * speed)
    return cv2.remap(img, mx, my, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)


def photo_bg(img, t, w, h, hue_speed=36.0, flow=110.0, warp_amp=6.0, z=1.10, sat=1.15, hue0=0.0):
    """資料夾的背景圖：填滿畫面、色相隨時間流轉（同一張圖上色相還會像波一樣流動 flow 度）、輕微扭曲。"""
    base = cover(img, w, h, z=z + 0.03 * math.sin(t * 0.45), cx=0.5 + 0.02 * math.sin(t * 0.3), cy=0.5)
    if warp_amp:
        base = warp(base, t, warp_amp)
    th = hue0 + t * hue_speed
    if flow:
        a, b = hue_shift(base, th), hue_shift(base, th + flow)
        xx, yy = _xy(w, h)
        m = (0.5 + 0.5 * np.sin((xx / w * 2.2 + yy / h * 1.3) * np.pi - t * 1.3))[..., None]
        out = a * (1 - m) + b * m
    else:
        out = hue_shift(base, th)
    return saturate(out, sat) if sat != 1 else out


# ═════════ 畫面處理 ═════════
def kaleido(img, t, n=6, cx=0.5, cy=0.5, spin=0.25, zoom=0.85, src_spin=0.1):
    """萬花筒：把畫面摺成 n 等分的鏡射扇形，整體旋轉。角色要疊在萬花筒「上面」保持清楚（先做背景萬花筒再貼角色）。"""
    h, w = img.shape[:2]
    r, th = _polar(w, h, cx, cy)
    seg = 2 * np.pi / n
    a = np.mod(th + t * spin, seg)
    a = np.where(a > seg / 2, seg - a, a) + t * src_spin
    rr = r * h * zoom
    mx = (w * 0.5 + rr * np.cos(a)).astype(np.float32)
    my = (h * 0.5 + rr * np.sin(a)).astype(np.float32)
    return cv2.remap(img, mx, my, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT_101)


def rgb_split(img, px, angle=0.0):
    """R 往一邊、B 往另一邊位移 px（次像素）。"""
    if px < 0.05:
        return img
    h, w = img.shape[:2]
    dx, dy = px * math.cos(angle), px * math.sin(angle)
    out = img.copy()
    for ch, s in ((0, 1), (2, -1)):
        M = np.float32([[1, 0, s * dx], [0, 1, s * dy]])
        out[..., ch] = cv2.warpAffine(np.ascontiguousarray(img[..., ch]), M, (w, h), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
    return out


def tear(img, k, seed, bands=8, shift=0.07, rgb=14.0):
    """畫面撕裂：幾條水平帶左右錯開＋RGB 分離；k 0–1（換人與副歌小節頭給 0.6–1，下一拍前回到 0）。"""
    if k <= 0.01:
        return img
    h, w = img.shape[:2]
    rng = np.random.default_rng(seed)
    out = img.copy()
    for _ in range(bands):
        y0 = int(rng.integers(0, h))
        hh = int(rng.integers(max(2, h // 90), max(3, h // 9)))
        dx = int(round((rng.random() * 2 - 1) * shift * w * k))
        if dx:
            out[y0:y0 + hh] = np.roll(img[y0:y0 + hh], dx, axis=1)
    return rgb_split(out, rgb * k * h / 720, angle=float(rng.random() * 0.3))


def flash(c, k, col=(1.0, 1.0, 1.0)):
    """閃白（screen 疊色）：k 0–1。"""
    if k <= 0.003:
        return c
    lay = np.float32(col) * k
    return 1 - (1 - c) * (1 - lay)


def over(c, rgba, op=1.0):
    a = rgba[..., 3:4] * op
    return c * (1 - a) + rgba[..., :3] * a


# ═════════ 角色 ═════════
KEY = {'green': (0.0, 0.69, 0.25), 'blue': (0.0, 0.28, 0.73)}


def key_rgba(rgb, key='green', lo=0.06, hi=0.22, despill=1.0):
    """綠幕／藍幕摳像（色差法）＋去溢色；回傳 RGBA float32。生成影片的背景不一定純，lo／hi 依實際畫面調。"""
    R, G, B = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    if key == 'green':
        d = G - np.maximum(R, B)
    else:
        d = B - np.maximum(R, G)
    a = 1 - np.clip((d - lo) / (hi - lo), 0, 1)
    a = cv2.morphologyEx(a.astype(np.float32), cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    a = cv2.GaussianBlur(a, (0, 0), 0.7)
    out = rgb.copy()
    if despill:
        if key == 'green':
            out[..., 1] = np.minimum(G, np.maximum(R, B) + (1 - despill) * (G - np.maximum(R, B)))
        else:
            out[..., 2] = np.minimum(B, np.maximum(R, G) + (1 - despill) * (B - np.maximum(R, G)))
    return np.dstack([out, a]).astype(np.float32)


def sticker(rgba, px=10, col=(1.0, 1.0, 1.0), shadow=0.30, shadow_off=(0.25, 0.45), pad=None):
    """白色貼紙描邊（＋往右下的柔投影）。px＝描邊寬（輸出尺寸下約 0.8–1.2% 畫面高）。回傳加了邊界的新 RGBA。"""
    pad = int(px * 2.5) if pad is None else pad
    a = rgba[..., 3]
    A = cv2.copyMakeBorder(a, pad, pad, pad, pad, cv2.BORDER_CONSTANT, value=0)
    RGB = cv2.copyMakeBorder(rgba[..., :3], pad, pad, pad, pad, cv2.BORDER_CONSTANT, value=0)
    dist = cv2.distanceTransform((A < 0.5).astype(np.uint8), cv2.DIST_L2, 5)
    ring = np.clip(px + 0.5 - dist, 0, 1).astype(np.float32)
    ring = cv2.GaussianBlur(ring, (0, 0), 0.6)
    out_a = np.maximum(A, ring)
    rgb = np.float32(col) * (1 - A[..., None]) + RGB * A[..., None]
    rgb = np.where(out_a[..., None] > 1e-4, rgb * 1.0, 0)
    if shadow:
        sx, sy = shadow_off[0] * px, shadow_off[1] * px
        sh = cv2.warpAffine(out_a, np.float32([[1, 0, sx], [0, 1, sy]]), (A.shape[1], A.shape[0]))
        sh = cv2.GaussianBlur(sh, (0, 0), px * 0.5) * shadow
        tot = out_a + sh * (1 - out_a)
        rgb = rgb * (out_a / np.maximum(tot, 1e-6))[..., None]
        out_a = tot
    return np.dstack([rgb, out_a]).astype(np.float32)


def place_matrix(ww, hh, x, y, height, angle=0.0, sx=1.0, sy=1.0, shear=0.0, anchor=(0.5, 1.0), flip=False):
    """place() 用的 2×3 仿射矩陣：精靈座標（px）→ 畫面座標。拿來算角色身上某一點（眼睛）此刻在畫面哪裡。"""
    k = height / hh
    ax, ay = anchor[0] * ww, anchor[1] * hh
    ca, sa = math.cos(math.radians(angle)), math.sin(math.radians(angle))
    S = np.array([[k * sx * (-1 if flip else 1), -shear * k * sy], [0, k * sy]], np.float64)
    A2 = np.array([[ca, -sa], [sa, ca]]) @ S
    tvec = np.array([x, y]) - A2 @ np.array([ax, ay])
    return np.hstack([A2, tvec[:, None]])


def place(c, rgba, x, y, height, op=1.0, angle=0.0, sx=1.0, sy=1.0, shear=0.0, anchor=(0.5, 1.0), flip=False):
    """把角色貼到畫布：anchor 點（預設腳底中央）放在 (x, y)，高度 height px；angle 度（繞 anchor）、sx/sy 壓扁拉長、
    shear 上半身往右傾（比例）。次像素位置、預乘 alpha，只在角色範圍內運算。就地修改 c。"""
    if op <= 0.004:
        return c
    hh, ww = rgba.shape[:2]
    k = height / hh
    M = place_matrix(ww, hh, x, y, height, angle, sx, sy, shear, anchor, flip)
    corners = np.array([[0, 0], [ww, 0], [0, hh], [ww, hh]], np.float64)
    pts = corners @ M[:, :2].T + M[:, 2]
    H, W = c.shape[:2]
    x0, y0 = max(0, int(math.floor(pts[:, 0].min())) - 1), max(0, int(math.floor(pts[:, 1].min())) - 1)
    x1, y1 = min(W, int(math.ceil(pts[:, 0].max())) + 1), min(H, int(math.ceil(pts[:, 1].max())) + 1)
    if x1 <= x0 or y1 <= y0:
        return c
    M2 = M.copy()
    M2[:, 2] -= (x0, y0)
    f = 1
    if k < 0.5:                                           # 大縮小先縮階（不閃），縮好的版本快取起來
        f = 2 ** int(math.floor(math.log2(1 / k / 1.4)))
        f = max(1, f)
    pm = _premul(rgba, f)
    if f > 1:
        M2[:, :2] *= hh / pm.shape[0]                     # 縮小版的座標換回原圖座標
    warped = cv2.warpAffine(pm, M2.astype(np.float32), (x1 - x0, y1 - y0), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT,
                            borderValue=0)
    a = warped[..., 3:4] * op
    roi = c[y0:y1, x0:x1]
    if c.shape[2] == 4:                                   # 透明圖層（預乘）：RGB 與 alpha 都疊上去
        c[y0:y1, x0:x1] = roi * (1 - a) + warped * op
    else:
        c[y0:y1, x0:x1] = roi[..., :3] * (1 - a) + warped[..., :3] * op
    return c


_PM = {}


def _premul(rgba, f):
    """預乘 alpha 的 RGBA，f > 1 時是縮小 f 倍的版本；以陣列身分＋縮階快取（角色精靈在 Dancer 裡常駐，身分不變）。"""
    key = (id(rgba), rgba.shape, f)
    v = _PM.get(key)
    if v is not None and v[0] is rgba:
        return v[1]
    pm = np.dstack([rgba[..., :3] * rgba[..., 3:4], rgba[..., 3]])
    if f > 1:
        pm = cv2.resize(pm, (max(1, rgba.shape[1] // f), max(1, rgba.shape[0] // f)), interpolation=cv2.INTER_AREA)
    if len(_PM) > 256:
        _PM.pop(next(iter(_PM)))
    _PM[key] = (rgba, pm)
    return pm


def over_layer(c, layer, op=1.0):
    """預乘的 RGBA 圖層疊到 RGB 畫布。"""
    a = layer[..., 3:4] * op
    return c * (1 - a) + layer[..., :3] * op


class Dancer:
    """一位角色。兩種來源：
       clip：keyloop.py key 產出的資料夾（f0000.png… RGBA＋clip.json：fps、n、period 每拍幾格、phase 第一個拍點的格）
             → at(t, grid) 依歌的拍位置取格：循環裡剛好塞整數拍，動作的落點對齊歌的拍子（跳舞跟拍點同步）
       still：一張去背立繪（RGBA png）＋ style 免費律動（puppet）：bounce／sway／hop／groove／twist／robot。
             這是試片與不花點數的版本，品質不能跟生成的舞蹈比，交付時要講清楚。
    sticker_px：描邊寬（以角色原圖高度的比例，0.012 ≈ 1.2%）。"""

    STYLES = ('bounce', 'sway', 'hop', 'groove', 'twist', 'robot')

    def __init__(self, src, style='bounce', sticker_px=0.012, name=None, meta=None):
        self.src = src
        self.name = name or os.path.splitext(os.path.basename(src.rstrip('/')))[0]
        self.style = style
        self.sp = sticker_px
        self.meta = meta or {}
        if os.path.isdir(src):
            self.kind = 'clip'
            self.info = json.load(open(os.path.join(src, 'clip.json')))
            self.files = sorted(glob.glob(os.path.join(src, 'f*.png')))
            self.n = len(self.files)
        else:
            self.kind = 'still'
            im = cv2.imread(src, cv2.IMREAD_UNCHANGED)
            if im is None or im.shape[2] != 4:
                raise ValueError(f'{src} 不是 RGBA png（先用 keyloop.py plate 去背）')
            rgba = cv2.cvtColor(im, cv2.COLOR_BGRA2RGBA).astype(np.float32) / 255
            px = max(2, int(rgba.shape[0] * self.sp))
            self._still = sticker(rgba, px=px)
            self._pad = int(px * 2.5)
            self._cut_hw = rgba.shape[:2]
        # 眼睛位置（keyloop.py plate 的 <名>.json；精靈比例座標）：眼睛特寫的焦點
        self.eyes = None
        mp = self.meta.get('json') or self._meta_path(src)
        if mp and os.path.exists(mp):
            m = json.load(open(mp))
            if m.get('eyes'):
                ex = sum(e[0] for e in m['eyes']) / 2
                ey = sum(e[1] for e in m['eyes']) / 2
                if self.kind == 'still':
                    (h0, w0), pd = self._cut_hw, self._pad
                    ex, ey = (ex * w0 + pd) / (w0 + 2 * pd), (ey * h0 + pd) / (h0 + 2 * pd)
                self.eyes = (ex, ey)

    @staticmethod
    def _meta_path(src):
        s = src.rstrip('/')
        for suf in ('_cut.png', '_clip'):
            if s.endswith(suf):
                return s[: -len(suf)] + '.json'
        return None

    def eye_xy(self, rgba, mv, x, foot_y, height):
        """此刻（含律動）眼睛在畫面上的位置；沒有眼睛資料時用頭頂下方 13%。"""
        ex, ey = self.eyes or (0.5, 0.13)
        hh, ww = rgba.shape[:2]
        M = place_matrix(ww, hh, x, foot_y - mv['dy'] * height, height, mv['angle'], mv['sx'], mv['sy'], mv['shear'])
        return M @ np.array([ex * ww, ey * hh, 1.0])

    @functools.lru_cache(maxsize=48)
    def _frame(self, i):
        im = cv2.imread(self.files[i], cv2.IMREAD_UNCHANGED)
        rgba = cv2.cvtColor(im, cv2.COLOR_BGRA2RGBA).astype(np.float32) / 255
        return sticker(rgba, px=max(2, int(rgba.shape[0] * self.sp)))

    def at(self, t, grid):
        """回傳 (RGBA, 律動參數 dict：dy 往上跳比例、sx、sy、angle、shear)。"""
        b = grid.bpos(t)
        if self.kind == 'clip':
            n, P, ph = self.info.get('n_loop', self.n), self.info['period'], self.info.get('phase', 0.0)
            K = max(1, round(n / P))                      # 這段循環塞幾拍
            f = (ph + b * n / K) % n
            i0 = int(math.floor(f)) % n
            return self._frame(i0), dict(dy=0, sx=1, sy=1, angle=0, shear=0)
        return self._still, puppet(b, self.style)


def puppet(b, style):
    """免費律動：b = 連續拍位置。回傳 place() 的參數。動作都在拍頭最強（落拍），兩拍一個左右循環。"""
    i = math.floor(b)
    u = b - i
    side = 1 if i % 2 == 0 else -1
    hitk = math.exp(-7 * u)                               # 拍頭壓下去
    rise = math.sin(math.pi * u)                          # 拍與拍之間彈起來
    if style == 'bounce':
        return dict(dy=0.035 * rise, sx=1 + 0.05 * hitk, sy=1 - 0.06 * hitk, angle=1.5 * side * rise, shear=0.02 * side * rise)
    if style == 'sway':
        s = math.sin(math.pi * (b % 2))
        return dict(dy=0.012 * abs(s), sx=1, sy=1 - 0.025 * hitk, angle=7 * s, shear=0.06 * s)
    if style == 'hop':
        return dict(dy=0.09 * (1 - (2 * u - 1) ** 2), sx=1 + 0.07 * hitk, sy=1 - 0.09 * hitk + 0.03 * rise, angle=0, shear=0)
    if style == 'groove':                                 # 反拍點頭：上半身前後傾
        off = math.exp(-7 * ((b + 0.5) % 1))
        return dict(dy=0.015 * rise, sx=1 + 0.03 * off, sy=1 - 0.05 * off, angle=0, shear=-0.10 * off + 0.03 * side)
    if style == 'twist':
        s = math.sin(2 * math.pi * b / 2)
        return dict(dy=0.01 * rise, sx=1 - 0.10 * abs(s), sy=1, angle=3 * s, shear=0.12 * s)
    if style == 'robot':                                  # 八分音符一格一格停住
        q = math.floor(b * 2) / 2
        return dict(dy=0.0, sx=1, sy=1 - 0.03 * (q % 1 == 0), angle=[-6, 0, 6, 0][int(q * 2) % 4], shear=[0.06, 0, -0.06, 0][int(q * 2) % 4])
    return dict(dy=0, sx=1, sy=1, angle=0, shear=0)


def put_dancer(c, rgba, mv, x, foot_y, height, op=1.0, flip=False):
    """依律動參數貼角色（腳底在 foot_y，跳起來時往上移）。"""
    return place(c, rgba, x, foot_y - mv['dy'] * height, height, op=op, angle=mv['angle'], sx=mv['sx'], sy=mv['sy'],
                 shear=mv['shear'], flip=flip)


def lineup(c, items, y, height, x0=0.12, x1=0.88, hues=None, op=1.0):
    """並排：items = [(RGBA, 律動參數), ...]，在畫面寬度 x0–x1 之間等距；hues＝每位轉幾度（五連排變色）。"""
    W = c.shape[1]
    n = len(items)
    for k, (rgba, mv) in enumerate(items):
        x = W * (x0 + (x1 - x0) * (k + 0.5) / n)
        if hues:
            rgba = hue_shift(rgba, hues[k])
        put_dancer(c, rgba, mv, x, y, height, op=op)
    return c


# ═════════ 字 ═════════
@functools.lru_cache(maxsize=128)
def jp_sprite(text, size, font='dela', col=(1.0, 1.0, 1.0), stroke=0.0, stroke_col=(0.0, 0.0, 0.0), vertical=False, tracking=0.0):
    """日文大字精靈 RGBA float32（兩倍大畫再縮）。stroke＝描邊寬（字級比例）；vertical＝直排。"""
    path, idx = FONTS.get(font, FONTS['noto'])
    if not os.path.exists(path):
        path, idx = FONTS['noto']
    ss = 2
    S = size * ss
    f = ImageFont.truetype(path, S, index=idx)
    sw = int(round(stroke * S))
    chars = list(text)
    if vertical:
        cw = int(S * 1.15)
        W, H = cw + 2 * sw + S // 4, int(len(chars) * S * (1.0 + tracking) + 2 * sw + S // 2)
    else:
        W = int(sum(f.getlength(ch) for ch in chars) + tracking * S * len(chars) + 2 * sw + S // 2)
        H = int(S * 1.45 + 2 * sw)
    im = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    fill = tuple(int(v * 255) for v in col) + (255,)
    sfill = tuple(int(v * 255) for v in stroke_col) + (255,)
    if vertical:
        y = sw + S // 4
        for ch in chars:
            d.text((W / 2, y + S / 2), ch, font=f, fill=fill, anchor='mm', stroke_width=sw, stroke_fill=sfill)
            y += S * (1.0 + tracking)
    else:
        x = sw + S // 4
        for ch in chars:
            d.text((x, H / 2), ch, font=f, fill=fill, anchor='lm', stroke_width=sw, stroke_fill=sfill)
            x += f.getlength(ch) + tracking * S
    a = np.asarray(im).astype(np.float32) / 255
    ys, xs = np.nonzero(a[..., 3] > 0.01)
    a = a[max(0, ys.min() - 2):ys.max() + 3, max(0, xs.min() - 2):xs.max() + 3]
    return cv2.resize(a, (max(1, a.shape[1] // ss), max(1, a.shape[0] // ss)), interpolation=cv2.INTER_AREA)


def big_text(c, text, u, cx=0.5, cy=0.46, height=0.62, font='dela', col=(1, 1, 1), stroke=0.0, stroke_col=(0, 0, 0),
             vertical=False, op=1.0, pop=0.10, hue=0.0, max_w=0.94):
    """角色後面的日文大字：u＝這個字出現以來的小節進度（0 在小節線上），前 pop 小節從 1.22 倍彈到 1.0、不淡入（硬出）。
    height＝字高佔畫面比例（直排時是整串高度）。先貼背景、再貼大字、最後貼角色。"""
    if op <= 0:
        return c
    H, W = c.shape[:2]
    base = 96
    spr = jp_sprite(text, base, font, tuple(col), stroke, tuple(stroke_col), vertical)
    k = (H * height) / spr.shape[0]
    k = min(k, W * max_w / spr.shape[1])
    s = 1.0 + 0.22 * (1 - ease(min(1.0, u / pop))) if pop else 1.0
    s *= 1.0 + 0.015 * u                                  # 之後慢慢放大一點（活著）
    spr2 = spr if not hue else hue_shift(spr, hue)
    return place(c, spr2, W * cx, H * cy, spr.shape[0] * k * s, op=op, anchor=(0.5, 0.5))


# ═════════ 鏡頭 ═════════
def camera(c, z=1.0, cx=0.5, cy=0.5, angle=0.0):
    """對整張合成畫面推鏡（全身 → 半身 → 眼睛特寫）：z 倍放大，(cx, cy) 為畫面上的取景中心比例。"""
    if abs(z - 1) < 1e-4 and abs(angle) < 1e-3 and abs(cx - 0.5) < 1e-4 and abs(cy - 0.5) < 1e-4:
        return c
    h, w = c.shape[:2]
    M = cv2.getRotationMatrix2D((cx * w, cy * h), angle, z)
    M[0, 2] += w * 0.5 - cx * w
    M[1, 2] += h * 0.5 - cy * h
    return cv2.warpAffine(c, M, (w, h), flags=cv2.INTER_CUBIC if z > 1.3 else cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)


def slide_x(a, b, u, direction=1, blur=0.0):
    """滑動＋交叉淡化（絲滑換人）：a 往外滑、b 從另一側滑進，同時交叉。u 0–1（用 ease 後的值）。"""
    h, w = a.shape[:2]
    e = ease(u)
    off = direction * w * 0.18
    A = cv2.warpAffine(a, np.float32([[1, 0, -off * e]]  + [[0, 1, 0]]), (w, h), borderMode=cv2.BORDER_REFLECT)
    B = cv2.warpAffine(b, np.float32([[1, 0, off * (1 - e)]] + [[0, 1, 0]]), (w, h), borderMode=cv2.BORDER_REFLECT)
    return A * (1 - e) + B * e


# ═════════ demo ═════════
def _demo(a):
    from seekkit import to_u8
    W, H = 640, 360
    t = 2.3
    img = None
    if a.img:
        img = cv2.cvtColor(cv2.imread(a.img), cv2.COLOR_BGR2RGB).astype(np.float32) / 255
    else:
        img = rings(0.4, W, H, bands=0)
    char = None
    if a.char:
        im = cv2.imread(a.char, cv2.IMREAD_UNCHANGED)
        char = cv2.cvtColor(im, cv2.COLOR_BGRA2RGBA).astype(np.float32) / 255
        char = sticker(char, px=max(2, int(char.shape[0] * 0.012)))
    tiles = [
        ('rings 彩虹同心圓', rings(t, W, H)),
        ('wheel 旋轉色環＋漩渦', wheel(t, W, H, twist=1.2)),
        ('melt 融化彩虹', melt(t, W, H)),
        ('stripes 斜條紋', stripes(t, W, H)),
        ('checker 棋盤＋扭曲', checker(t, W, H, warp_amp=0.25)),
        ('photo_bg 色相流轉＋扭曲', photo_bg(img, t, W, H)),
        ('kaleido 萬花筒', kaleido(photo_bg(img, t, W, H), t, n=8)),
        ('tear 撕裂＋RGB', tear(photo_bg(img, t, W, H), 0.9, 7)),
    ]
    big = rings(t, W, H, bands=7)
    big = big_text(big, '夢', 0.05, font='dela', col=(1, 1, 1), stroke=0.06, stroke_col=(0.1, 0.05, 0.2))
    if char is not None:
        put_dancer(big, char, puppet(0.3, 'bounce'), W * 0.5, H * 0.96, H * 0.86)
    tiles.append(('大字＋貼紙角色', big))
    lu = checker(t, W, H)
    if char is not None:
        lineup(lu, [(char, puppet(0.2 + k * 0.25, s)) for k, s in enumerate(('bounce', 'sway', 'hop', 'groove', 'twist'))],
               H * 0.95, H * 0.6, hues=[0, 72, 144, 216, 288])
    tiles.append(('五連排變色', lu))
    tiles.append(('閃白 0.5', flash(wheel(t, W, H), 0.5)))
    tiles.append(('hue_shift 120°', hue_shift(photo_bg(img, t, W, H, flow=0), 120)))
    rows = []
    for r in range(0, len(tiles), 4):
        row = []
        for name, im in tiles[r:r + 4]:
            u8 = cv2.cvtColor(to_u8(im), cv2.COLOR_RGB2BGR)
            lab = Image.fromarray(np.zeros((34, W, 3), np.uint8))
            ImageDraw.Draw(lab).text((10, 5), name, font=ImageFont.truetype(CJK_B, 20, index=3), fill=(255, 255, 255))
            row.append(np.vstack([u8, np.asarray(lab)[..., ::-1]]))
        while len(row) < 4:
            row.append(np.zeros_like(row[0]))
        rows.append(np.hstack(row))
    cv2.imwrite(a.o, np.vstack(rows), [cv2.IMWRITE_JPEG_QUALITY, 90])
    print('寫入', a.o)


if __name__ == '__main__':
    import argparse
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('cmd', choices=['demo'])
    p.add_argument('-o', default='out/psyfx_demo.jpg')
    p.add_argument('--img')
    p.add_argument('--char')
    a = p.parse_args()
    os.makedirs(os.path.dirname(os.path.abspath(a.o)), exist_ok=True)
    _demo(a)
