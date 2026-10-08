"""seek(t) 引擎的共用零件（Python／numpy／OpenCV／PIL）。

一支片寫成一個 engine.py：定義 W、H、FPS、TOTAL 與 frame(t) -> uint8 RGB (H, W, 3)，
畫面只由 t 決定（同一個 t 永遠同一張），就能任意抽格、拼總覽、分段平行渲染（scripts/frames.py）。

這裡的零件全部不帶狀態：畫布是 float32 RGB 0–1，函式直接改畫布或回傳新陣列。
  from seekkit import *            # engine.py 開頭（frames.py 會把 scripts/ 加進 sys.path）
"""
import functools
import math
import os
import re

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

CJK_B = '/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc'
CJK_R = '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc'
CJK_TC = 3  # .ttc 內的繁中字面
SERIF_B = '/usr/share/fonts/opentype/noto/NotoSerifCJK-Bold.ttc'


# ───────── 時間與緩動 ─────────
def clamp01(u):
    return min(max(u, 0.0), 1.0)


def ease(u):
    u = clamp01(u)
    return u * u * (3 - 2 * u)


def ease_out(u, p=3):
    return 1 - (1 - clamp01(u)) ** p


def ease_in(u, p=3):
    return clamp01(u) ** p


def expo_out(u):
    u = clamp01(u)
    return 1.0 if u >= 1 else 1 - 2 ** (-10 * u)


def back_out(u, s=1.6):
    u = clamp01(u) - 1
    return 1 + u * u * ((s + 1) * u + s)


def spring(u, freq=3.2, damp=5.0):
    """0→1 帶一次回彈；u 以秒計較直覺（u = 經過秒數 / 時長）。"""
    u = max(u, 0.0)
    return 1 - math.exp(-damp * u) * math.cos(freq * 2 * math.pi * u)


def window(t, t0, t1, fade_in=0.3, fade_out=0.3, curve=ease):
    """t 在 [t0, t1] 內的出現量 0–1（進出各自有曲線，不是預設淡入淡出的替代品，是遮罩強度）。"""
    return curve((t - t0) / fade_in) * (1 - curve((t - (t1 - fade_out)) / fade_out))


def frame_rng(t, fps, salt=0):
    """每格固定的亂數（顆粒、抖動、閃爍）；同一格永遠相同。"""
    return np.random.default_rng(int(round(t * fps)) * 7919 + salt)


# ───────── 素材 ─────────
class Src:
    """可隨機存取的影片來源；at(t) 回傳 float32 RGB 0–1。grade=函式（uint8 BGR → uint8 RGB）可接調色。"""

    def __init__(self, path, grade=None, size=None):
        self.path, self.grade, self.size = path, grade, size
        self.cap = cv2.VideoCapture(path)
        self.n = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT))
        self.fps = self.cap.get(cv2.CAP_PROP_FPS) or 30
        self.dur = self.n / self.fps
        self.pos = -1
        self.cache = {}

    def frame(self, i):
        i = int(min(max(i, 0), self.n - 1))
        if i in self.cache:
            return self.cache[i]
        if i != self.pos + 1:
            self.cap.set(cv2.CAP_PROP_POS_FRAMES, i)
        ok, fr = self.cap.read()
        self.pos = i
        if not ok:
            fr = np.zeros((self.size[1], self.size[0], 3) if self.size else (16, 16, 3), np.uint8)
        if self.size and (fr.shape[1], fr.shape[0]) != tuple(self.size):
            fr = cv2.resize(fr, self.size, interpolation=cv2.INTER_AREA)
        fr = self.grade(fr) if self.grade else fr[..., ::-1].copy()
        if len(self.cache) > 8:
            self.cache.pop(min(self.cache))
        self.cache[i] = fr
        return fr

    def at(self, t, blend=False):
        """blend=True：兩格線性混合（慢動作更順、快轉帶一點動態模糊）。"""
        f = t * self.fps
        i = math.floor(f)
        if not blend:
            return self.frame(i + (f - i > 0.5)).astype(np.float32) / 255
        a = f - i
        return (self.frame(i).astype(np.float32) * (1 - a) + self.frame(i + 1).astype(np.float32) * a) / 255


_SRCS = {}


def src(path, **kw):
    """每個行程共用一個 Src（frames.py 平行渲染時每段各自開）。"""
    key = (path, tuple(sorted(kw.items(), key=lambda x: x[0])) if kw else ())
    if key not in _SRCS:
        _SRCS[key] = Src(path, **kw)
    return _SRCS[key]


@functools.lru_cache(maxsize=32)
def image(path):
    """圖檔 → float32 RGB 0–1（含透明時回傳 RGBA）。"""
    im = Image.open(path)
    im = im.convert('RGBA' if 'A' in im.getbands() or 'transparency' in im.info else 'RGB')
    return np.asarray(im).astype(np.float32) / 255


def cover(img, w, h, z=1.0, cx=0.5, cy=0.5):
    """把圖填滿 w×h（像 CSS object-fit: cover），z 放大、(cx, cy) 為原圖上的取景中心比例。"""
    ih, iw = img.shape[:2]
    k = max(w / iw, h / ih) * z
    M = np.float32([[k, 0, w / 2 - cx * iw * k], [0, k, h / 2 - cy * ih * k]])
    return cv2.warpAffine(img, M, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REFLECT)


def kenburns(img, u, w, h, z=(1.0, 1.08), c0=(0.5, 0.5), c1=(0.5, 0.5), curve=ease):
    v = curve(u)
    return cover(img, w, h, z[0] + (z[1] - z[0]) * v, c0[0] + (c1[0] - c0[0]) * v, c0[1] + (c1[1] - c0[1]) * v)


def zoom(img, z, cx=0.5, cy=0.5):
    if abs(z - 1) < 1e-4:
        return img
    h, w = img.shape[:2]
    M = np.float32([[z, 0, w * cx * (1 - z)], [0, z, h * cy * (1 - z)]])
    return cv2.warpAffine(img, M, (w, h), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)


def scroll_page(page, u, w, h, y0=0.0, y1=None, curve=ease):
    """整頁截圖當底，從 y0 捲到 y1（px，原圖座標）；寬度縮放到 w。產品網站捲動鏡頭用。"""
    ph, pw = page.shape[:2]
    k = w / pw
    view = h / k
    y1 = ph - view if y1 is None else y1
    y = y0 + (y1 - y0) * curve(u)
    M = np.float32([[k, 0, 0], [0, k, -y * k]])
    return cv2.warpAffine(page, M, (w, h), flags=cv2.INTER_AREA, borderMode=cv2.BORDER_REPLICATE)


# ───────── 字 ─────────
@functools.lru_cache(maxsize=256)
def text_sprite(text, size, font=CJK_B, index=CJK_TC, tracking=0.0, col=(1, 1, 1), spans=None):
    """單行字 → RGBA float32（已裁邊）；tracking 以字級倍數計；spans=((起, 迄, (r,g,b)), ...) 局部換色。"""
    f = ImageFont.truetype(font, size, index=index)
    widths = [f.getlength(ch) for ch in text]
    tw = int(sum(widths) + tracking * size * max(0, len(text) - 1) + size)
    th = int(size * 1.8)
    im = Image.new('RGBA', (tw, th), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    x = size * 0.3
    for i, (ch, wd) in enumerate(zip(text, widths)):
        c = col
        for a, b, cc in spans or ():
            if a <= i < b:
                c = cc
        d.text((x, th * 0.52), ch, font=f, fill=tuple(int(v * 255) for v in c) + (255,), anchor='lm')
        x += wd + tracking * size
    a = np.asarray(im).astype(np.float32) / 255
    ys, xs = np.nonzero(a[..., 3] > 0.01)
    if len(xs):
        a = a[max(0, ys.min() - 4):ys.max() + 5, max(0, xs.min() - 4):xs.max() + 5]
    return a


def fit_text(text, max_w, size, font=CJK_B, index=CJK_TC, tracking=0.0, col=(1, 1, 1), min_size=24):
    """單行字縮到 max_w 以內（字級每次 -4）；縮到 min_size 還放不下就丟錯，提醒改文案或換行。"""
    while size >= min_size:
        spr = text_sprite(text, size, font, index, tracking, col)
        if spr.shape[1] <= max_w:
            return spr
        size -= 4
    raise ValueError(f'「{text}」在 {max_w}px 內放不下：改短或用 wrap_text 換行')


def wrap_text(text, max_w, size, font=CJK_B, index=CJK_TC, tracking=0.0, col=(1, 1, 1)):
    """在標點後換行（，。、！？：；／ 與空白），每行都不超過 max_w；回傳精靈清單。"""
    parts = re.split(r'(?<=[，。、！？：；／\s])', text)
    lines, cur = [], ''
    for ptxt in parts:
        trial = cur + ptxt
        if cur and text_sprite(trial, size, font, index, tracking, col).shape[1] > max_w:
            lines.append(cur)
            cur = ptxt
        else:
            cur = trial
    if cur:
        lines.append(cur)
    return [fit_text(ln.strip(), max_w, size, font, index, tracking, col) for ln in lines]


def missing_glyphs(text, font=CJK_B, index=CJK_TC):
    """回傳字型裡沒有的字（避免豆腐字）。"""
    f = ImageFont.truetype(font, 40, index=index)
    tofu = f.getmask('￿').getbbox()
    return [ch for ch in set(text) if not ch.isspace() and f.getmask(ch).getbbox() in (None, tofu)]


def blit(c, spr, x, y, op=1.0, anchor='lt'):
    """RGBA 精靈貼到畫布；anchor: lt 左上、c 中心、rt 右上、lb 左下。"""
    if op <= 0.004:
        return
    h, w = spr.shape[:2]
    if anchor == 'c':
        x, y = x - w / 2, y - h / 2
    elif anchor == 'rt':
        x = x - w
    elif anchor == 'lb':
        y = y - h
    x, y = int(round(x)), int(round(y))
    x0, y0, x1, y1 = max(0, x), max(0, y), min(c.shape[1], x + w), min(c.shape[0], y + h)
    if x1 <= x0 or y1 <= y0:
        return
    s = spr[y0 - y:y1 - y, x0 - x:x1 - x]
    a = s[..., 3:4] * op
    c[y0:y1, x0:x1] = c[y0:y1, x0:x1] * (1 - a) + s[..., :3] * a


def rise(c, spr, x, y, e, dur_in=0.55, hold=None, out=0.35):
    """字從自己的基線遮罩裡升起（不是淡入）；e = 進場後經過秒數；hold 後淡出並微上移。"""
    if e < 0:
        return
    u = expo_out(e / dur_in)
    op = 1.0
    if hold is not None and e > hold:
        v = ease((e - hold) / out)
        op, y = 1 - v, y - v * 10
    if op <= 0:
        return
    sh = spr.shape[0]
    y0 = int(y)
    sub = c[y0:y0 + sh + 2]
    if sub.shape[0] == 0:
        return
    tmp = sub.copy()
    blit(tmp, spr, x, y + (1 - u) * sh * 0.9 - y0, op)
    c[y0:y0 + tmp.shape[0]] = tmp


def type_on(c, text, x, y, e, size, cps=18, **kw):
    """逐字出現（每字自己升起），cps = 每秒字數。"""
    xx = x
    for i, ch in enumerate(text):
        spr = text_sprite(ch, size, **kw)
        rise(c, spr, xx, y, e - i / cps, 0.35)
        xx += spr.shape[1] - size * 0.08


# ───────── 合成 ─────────
def screen(c, add):
    c[:] = 1 - (1 - c) * (1 - np.clip(add, 0, 1))


def shade_rect(c, x0, y0, x1, y1, alpha, col=(0, 0, 0), r=0):
    x0, y0, x1, y1 = int(x0), int(y0), int(x1), int(y1)
    col = np.float32(col)
    if r:
        m = np.zeros((y1 - y0, x1 - x0), np.uint8)
        cv2.rectangle(m, (r, 0), (x1 - x0 - r, y1 - y0), 255, -1)
        cv2.rectangle(m, (0, r), (x1 - x0, y1 - y0 - r), 255, -1)
        for cx, cy in ((r, r), (x1 - x0 - r - 1, r), (r, y1 - y0 - r - 1), (x1 - x0 - r - 1, y1 - y0 - r - 1)):
            cv2.circle(m, (cx, cy), r, 255, -1, cv2.LINE_AA)
        a = m.astype(np.float32)[..., None] / 255 * alpha
    else:
        a = alpha
    c[y0:y1, x0:x1] = c[y0:y1, x0:x1] * (1 - a) + col * a


def scrim(c, y0, y1, strength=0.55):
    """字底下的垂直漸層壓暗（不用色塊），讓字在亮處也讀得清楚。"""
    yy = np.arange(c.shape[0], dtype=np.float32)
    m = np.clip(np.sin(np.clip((yy - y0) / (y1 - y0), 0, 1) * np.pi), 0, 1) ** 1.2 * strength
    c *= (1 - m)[:, None, None]


def glow_line(c, pts, col, width=2, glow=10, k=1.0):
    h, w = c.shape[:2]
    m = np.zeros((h // 2, w // 2), np.float32)
    p = np.round(np.array(pts, np.float32) / 2).astype(np.int32)
    cv2.polylines(m, [p], False, 1.0, max(1, int(width / 2)), cv2.LINE_AA)
    core = cv2.resize(m, (w, h))
    g = cv2.resize(cv2.GaussianBlur(m, (0, 0), glow / 2), (w, h))
    screen(c, (core[..., None] + g[..., None] * 2.2) * np.float32(col) * k)


@functools.lru_cache(maxsize=4)
def _vignette(w, h, k):
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    r = np.sqrt(((xx - w / 2) / (w * 0.75)) ** 2 + ((yy - h / 2) / (h * 0.68)) ** 2)
    return np.clip(1 - k * r ** 2.2, 0.45, 1)[..., None]


def vignette(c, k=0.32):
    c *= _vignette(c.shape[1], c.shape[0], k)


def grain(c, t, fps, amt=0.016):
    h, w = c.shape[:2]
    n = frame_rng(t, fps, 5).normal(0, 1, (h // 2, w // 2)).astype(np.float32)
    n = cv2.resize(n, (w, h), interpolation=cv2.INTER_LINEAR)
    c += n[..., None] * amt * (0.5 + c.mean(2, keepdims=True))


def halation(c, thr=0.78, k=0.18, col=(1.0, 0.55, 0.35)):
    """亮部外暈（膠片感），只動高光。"""
    h, w = c.shape[:2]
    lum = c.mean(2)
    m = cv2.resize(np.clip((lum - thr) / (1 - thr), 0, 1), (w // 4, h // 4))
    g = cv2.resize(cv2.GaussianBlur(m, (0, 0), 6), (w, h))
    screen(c, g[..., None] * np.float32(col) * k)


def to_u8(c):
    return (np.clip(c, 0, 1) * 255 + 0.5).astype(np.uint8)


def hexrgb(s):
    s = s.lstrip('#')
    return np.float32([int(s[i:i + 2], 16) for i in (0, 2, 4)]) / 255
