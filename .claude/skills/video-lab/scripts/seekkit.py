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


def mblur(fn, t, fps, n=5, shutter=0.5):
    """動態模糊：在快門時間內取 n 個子格平均（180° 快門＝0.5 格）。只包在快速運動的鏡頭（甩鏡、快推、物件飛入）：
    每格成本 ×n。fn(t) 回傳 float32 畫布；子格時間只由 t 決定，仍是純函式。
        c = mblur(lambda u: shot(u), t, FPS) if fast(t) else shot(t)"""
    if n <= 1 or shutter <= 0:
        return fn(t)
    acc = None
    for i in range(n):
        u = t + (i / (n - 1) - 0.5) * shutter / fps
        f = fn(u)
        acc = f.astype(np.float32) if acc is None else acc + f
    return acc / n


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
def image(path, max_side=None):
    """圖檔 → float32 RGB 0–1（含透明時回傳 RGBA）。max_side：長邊先縮到這麼多（手機原圖 5712 px 時省記憶體，
    建議 2×輸出長邊；縮圖用 INTER_AREA，不會鋸齒）。"""
    im = Image.open(path)
    im = im.convert('RGBA' if 'A' in im.getbands() or 'transparency' in im.info else 'RGB')
    a = np.asarray(im).astype(np.float32) / 255
    if max_side and max(a.shape[:2]) > max_side:
        k = max_side / max(a.shape[:2])
        a = cv2.resize(a, (round(a.shape[1] * k), round(a.shape[0] * k)), interpolation=cv2.INTER_AREA)
    return a


_MIP = {}


def _mip(img, k):
    """縮小倍率 k < 1 時，先用 INTER_AREA 縮到 2^(-n/4) 這一階（≥ k），剩下 1.00–1.19 倍的小縮放才交給 warpAffine。
    warpAffine 直接大比例縮小不做預濾波，細節（磚牆、招牌字、樹葉、網頁截圖）會鋸齒，緩推時一格一格閃。
    回傳 (縮好的圖, 剩下的倍率)。同一張圖的各階有快取（鍵含取樣指紋，影片每格是不同的圖，不會拿錯）。"""
    if k >= 0.999:
        return img, k
    n = math.floor(-4 * math.log2(k))
    L = 2 ** (-n / 4)
    key = (id(img), img.shape, float(img[::61, ::67].sum()), n)
    pre = _MIP.get(key)
    if pre is None:
        pre = cv2.resize(img, (max(1, round(img.shape[1] * L)), max(1, round(img.shape[0] * L))), interpolation=cv2.INTER_AREA)
        if len(_MIP) >= 6:
            _MIP.pop(next(iter(_MIP)))
        _MIP[key] = pre
    return pre, k * img.shape[1] / pre.shape[1]


def cover(img, w, h, z=1.0, cx=0.5, cy=0.5):
    """把圖填滿 w×h（像 CSS object-fit: cover），z 放大、(cx, cy) 為原圖上的取景中心比例。
    大圖縮小先走 _mip（不閃）；位置是浮點數（次像素），緩推不會一格一格跳。"""
    ih, iw = img.shape[:2]
    k = max(w / iw, h / ih) * z
    src_, k2 = _mip(img, k)
    sh, sw = src_.shape[:2]
    M = np.float32([[k2, 0, w / 2 - cx * sw * k2], [0, k2, h / 2 - cy * sh * k2]])
    return cv2.warpAffine(src_, M, (w, h), flags=cv2.INTER_CUBIC if k2 > 1.2 else cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)


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
    src_, k2 = _mip(page, k)  # warpAffine 不支援 INTER_AREA（會退回線性）：先縮再捲，網頁小字才不閃
    M = np.float32([[k2, 0, 0], [0, k2, -y * k]])
    return cv2.warpAffine(src_, M, (w, h), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)


# ───────── 字 ─────────
PUNCT = set('，。、；：！？「」『』（）《》〈〉【】')
OPEN_P, CLOSE_P = set('「『（《〈【'), set('，。、；：！？」』）》〉】')


@functools.lru_cache(maxsize=512)
def _ink_gaps(font, index, ch, S):
    """全形標點在 1 em 裡左右各空多少 px（繁中字型的，。置中、「」偏一側，實測 Noto TC 逗號左右各 0.38 em）。"""
    f = ImageFont.truetype(font, S, index=index)
    im = Image.new('L', (S * 3, S * 2))
    ImageDraw.Draw(im).text((S, int(S * 1.5)), ch, font=f, fill=255, anchor='ls')
    xs = np.nonzero(np.asarray(im).max(0) > 20)[0]
    if not len(xs):
        return 0.0, 0.0
    return float(xs.min() - S), float(S + f.getlength(ch) - xs.max() - 1)


@functools.lru_cache(maxsize=256)
def text_sprite(text, size, font=CJK_B, index=CJK_TC, tracking=0.0, col=(1, 1, 1), spans=None, palt=None):
    """單行字 → RGBA float32（已裁邊）；tracking 以字級倍數計；spans=((起, 迄, (r,g,b)), ...) 局部換色。
    palt：標點擠壓（連續標點「」，」「。」」之間的雙重空白收掉、行首開引號貼齊網格；單獨的標點維持全形置中）；
    None＝字級 ≥ 40 自動開（標題），內文維持全形。"""
    palt = size >= 40 if palt is None else palt
    ss = 2  # 兩倍大畫再縮小：字距（tracking）的小數位置不會被四捨五入吃掉，筆畫邊緣更細緻
    S = size * ss
    f = ImageFont.truetype(font, S, index=index)
    widths = [f.getlength(ch) for ch in text]
    tw = int(sum(widths) + tracking * S * max(0, len(text) - 1) + S)
    th = int(S * 1.8)
    tw, th = tw + tw % 2, th + th % 2
    im = Image.new('RGBA', (tw, th), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    x = S * 0.3
    for i, (ch, wd) in enumerate(zip(text, widths)):
        c = col
        for a, b, cc in spans or ():
            if a <= i < b:
                c = cc
        lt = rt = 0.0
        if palt and ch in PUNCT:
            # 臺灣排版的標點是全形置中；只擠「連續標點」（」，、。」、），）之間的雙重空白，和行首開引號的外側空白，
            # 單獨的逗號、冒號維持全形（全部擠成半形會像英文標點）
            lg, rg = _ink_gaps(font, index, ch, S)
            if i == 0 and ch in OPEN_P:
                lt = lg
            if i > 0 and text[i - 1] in PUNCT:
                lt = max(lt, lg - 0.06 * S)
            if i + 1 < len(text) and text[i + 1] in PUNCT:
                rt = max(0.0, rg - 0.06 * S)
        x -= lt
        d.text((x, th * 0.52), ch, font=f, fill=tuple(int(v * 255) for v in c) + (255,), anchor='lm')
        x += wd - rt + tracking * S
    a = np.asarray(im).astype(np.float32) / 255
    a[..., :3] *= a[..., 3:4]  # 預乘 alpha 再縮，邊緣不會黑一圈
    a = cv2.resize(a, (tw // ss, th // ss), interpolation=cv2.INTER_AREA)
    a[..., :3] /= np.maximum(a[..., 3:4], 1e-6)
    a[..., :3] = np.where(a[..., 3:4] > 1e-6, a[..., :3], 0)
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
    # 避頭尾：行首不能是收尾標點、行尾不能是開引號
    for i in range(1, len(lines)):
        while lines[i] and lines[i][0] in CLOSE_P:
            lines[i - 1], lines[i] = lines[i - 1] + lines[i][0], lines[i][1:]
        while lines[i - 1] and lines[i - 1][-1] in OPEN_P:
            lines[i - 1], lines[i] = lines[i - 1][:-1], lines[i - 1][-1] + lines[i]
    return [fit_text(ln.strip(), max_w, size, font, index, tracking, col) for ln in lines if ln.strip()]


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
    ix, iy = math.floor(x), math.floor(y)
    fx, fy = x - ix, y - iy
    pm = np.concatenate([spr[..., :3] * spr[..., 3:4], spr[..., 3:4]], -1)  # 預乘 alpha
    if fx > 1e-3 or fy > 1e-3:
        # 次像素位置：字慢慢移動時不會每隔幾格跳 1 px（整數取位的抖動）
        pm = cv2.copyMakeBorder(pm, 0, 1, 0, 1, cv2.BORDER_CONSTANT, value=0)
        pm = cv2.warpAffine(pm, np.float32([[1, 0, fx], [0, 1, fy]]), (w + 1, h + 1), flags=cv2.INTER_LINEAR,
                            borderMode=cv2.BORDER_CONSTANT, borderValue=0)
        h, w = h + 1, w + 1
    x, y = ix, iy
    x0, y0, x1, y1 = max(0, x), max(0, y), min(c.shape[1], x + w), min(c.shape[0], y + h)
    if x1 <= x0 or y1 <= y0:
        return
    s = pm[y0 - y:y1 - y, x0 - x:x1 - x]
    c[y0:y1, x0:x1] = c[y0:y1, x0:x1] * (1 - s[..., 3:4] * op) + s[..., :3] * op


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
    y0 = math.floor(y)
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



def rounded_rect_path(x0, y0, x1, y1, r, u=1.0, n=160):
    """圓角矩形外框的點列（從右上角順時針），u 0–1 只取前段，用來把 glow_line「畫」出一圈。
    產品片用法：圈住真實截圖上的按鈕（座標用截圖原圖 px 經同一個 cover／zoom 轉換算出）。"""
    pts = []
    for cx, cy, a0 in ((x1 - r, y0 + r, -90), (x1 - r, y1 - r, 0), (x0 + r, y1 - r, 90), (x0 + r, y0 + r, 180)):
        for a in np.linspace(a0, a0 + 90, n // 4):
            pts.append((cx + r * math.cos(math.radians(a)), cy + r * math.sin(math.radians(a))))
    pts.append(pts[0])
    return np.array(pts[:max(2, int(len(pts) * u))], np.float32)

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
    pts = np.array(pts, np.float32)
    # 線芯：全解析度、次像素座標（shift=4 → 1/16 px），不再是半解析度放大的糊線
    core = np.zeros((h, w), np.float32)
    cv2.polylines(core, [np.round(pts * 16).astype(np.int32)], False, 1.0, max(1, int(round(width))), cv2.LINE_AA, shift=4)
    m = np.zeros((h // 2, w // 2), np.float32)
    cv2.polylines(m, [np.round(pts * 8).astype(np.int32)], False, 1.0, max(1, int(width / 2)), cv2.LINE_AA, shift=4)
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
    """底片顆粒：中間調最明顯、純黑純白幾乎沒有（真的底片也是這樣）；每格種子固定。"""
    h, w = c.shape[:2]
    n = frame_rng(t, fps, 5).normal(0, 1, (h // 2, w // 2)).astype(np.float32)
    n = cv2.resize(n, (w, h), interpolation=cv2.INTER_LINEAR)
    L = np.clip(c.mean(2, keepdims=True), 0, 1)
    c += n[..., None] * amt * (0.35 + 2.6 * L * (1 - L))


def halation(c, thr=0.78, k=0.18, col=(1.0, 0.55, 0.35)):
    """亮部外暈（膠片感），只動高光。"""
    h, w = c.shape[:2]
    lum = c.mean(2)
    m = cv2.resize(np.clip((lum - thr) / (1 - thr), 0, 1), (w // 4, h // 4))
    g = cv2.resize(cv2.GaussianBlur(m, (0, 0), 6), (w, h))
    screen(c, g[..., None] * np.float32(col) * k)


@functools.lru_cache(maxsize=2)
def _tpdf(h, w):
    """三角分布抖色（±1 階），固定圖樣：每格一樣，編碼器不用多花位元。"""
    r = np.random.default_rng(11)
    return (r.random((h, w, 1), np.float32) - r.random((h, w, 1), np.float32))


def to_u8(c, dither=True):
    """0–1 浮點 → uint8。dither=True 加 ±1 階的三角抖色：暗部漸層、scrim、暈影、天空在 8-bit 不會一圈一圈。"""
    if dither:
        c = c * 255 + 0.5 + _tpdf(c.shape[0], c.shape[1])
        return np.clip(c, 0, 255).astype(np.uint8)
    return (np.clip(c, 0, 1) * 255 + 0.5).astype(np.uint8)


def hexrgb(s):
    s = s.lstrip('#')
    return np.float32([int(s[i:i + 2], 16) for i in (0, 2, 4)]) / 255
