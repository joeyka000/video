#!/usr/bin/env python3
"""調色與膠片質感（seek(t) 引擎用）：統一曝光白平衡 → 情緒調色（膚色保護、分離色調、高光柔肩）→ 光暈泛光 → 顆粒暗角。

來源：日田聖地巡禮 v2（使用者通過的 look engine）與峇里島 60 秒 v2（實拍升級的質感特效），整理成不綁專案的版本。
影像一律 float32 RGB 0–1；所有函式不帶狀態，同一個 t 永遠同一張（符合 CLAUDE.md 第一條）。

  from look import grade, face_safe, film, match, stats, MOODS     # engine.py（frames.py 已把 scripts/ 加進 sys.path）
  img = face_safe(src_frame, 'golden')        # 每個鏡頭：先統一、再調色、臉過亮自動降
  img = film(img, t, fps)                     # 每格最後：顆粒＋暗角（用 seekkit.to_u8 輸出，預設抖色）
  L = lock(代表格, 'golden', ref=REF)          # 會搖鏡、會換景的鏡頭：一個鏡頭量一次
  img = apply(src_frame, L)                   # 每格用同一組數字（不會像自動曝光一樣呼吸；finishtest F：0.169 → 0.000）

  python look.py board a.jpg b.jpg c.mp4@3.2 --moods clean,day,golden,aot,night -o qa/look_board.jpg
        → 每列一張素材、每欄一個 mood 的對照表（格頭寫 finish.py 的黑位／白位／飽和／膚色），先選 look 再寫引擎
  python look.py apply in.jpg --mood golden -o out.jpg

MOODS 參數：sat 飽和、contrast S 曲線強度、lift 黑位、teal／warm 暗部偏青與亮部偏暖、olive 綠往橄欖、
halation／bloom 高光外暈與泛光、expo 目標中間調（None＝不動曝光）、cool 整體冷暖。挑法見 references/finish.md〈三〉。
"""
import argparse
import functools
import math
import os
import sys

import cv2
import numpy as np

MOODS = {
    # 商品、品牌、空間：乾淨、膚色準、幾乎不偏色；高級感來自柔肩與乾淨的黑，不是濾鏡
    'clean':  dict(sat=0.90, contrast=0.38, lift=0.018, teal=0.020, warm=0.020, olive=0.25, halation=0.08, bloom=0.06, expo=0.42, cool=0.000),
    # 生活、美食、溫柔：低對比、黑位微抬、亮部柔
    'soft':   dict(sat=0.82, contrast=0.30, lift=0.050, teal=0.030, warm=0.050, olive=0.40, halation=0.16, bloom=0.14, expo=0.45, cool=-0.010),
    # 以下取自日田 v2（使用者通過）
    'day':    dict(sat=0.74, contrast=0.55, lift=0.040, teal=0.060, warm=0.070, olive=0.70, halation=0.22, bloom=0.12, expo=0.40, cool=0.000),
    'golden': dict(sat=0.80, contrast=0.60, lift=0.030, teal=0.060, warm=0.115, olive=0.60, halation=0.32, bloom=0.16, expo=0.38, cool=-0.025),
    'aot':    dict(sat=0.56, contrast=0.85, lift=0.030, teal=0.085, warm=0.030, olive=0.80, halation=0.25, bloom=0.10, expo=0.34, cool=0.025),
    'night':  dict(sat=0.85, contrast=0.70, lift=0.012, teal=0.090, warm=0.070, olive=0.05, halation=0.45, bloom=0.24, expo=None, cool=0.030),
    'bw':     dict(sat=0.00, contrast=0.90, lift=0.035, teal=0.000, warm=0.025, olive=0.00, halation=0.22, bloom=0.08, expo=0.38, cool=0.000),
}
YUNET = os.path.expanduser('~/video-lab/models/yunet.onnx')


def lum(img):
    return img[..., 0] * 0.2126 + img[..., 1] * 0.7152 + img[..., 2] * 0.0722


def screen(a, b):
    return 1 - (1 - a) * (1 - np.clip(b, 0, 1))


def _res(img):
    """模糊半徑以 1920 長邊為基準縮放，4K 與直式畫面的光暈大小才一致。"""
    return max(img.shape[:2]) / 1920


# ───────────────────────── 1. 統一 ─────────────────────────
def normalize(img, mood, gmul=1.0, wb=0.35):
    """不同素材的曝光與白平衡先拉近，再交給調色（手機自動白平衡忽冷忽熱、每張曝光不同）。
    wb：往灰世界拉的比例（0.35；夕陽、霓虹這種顏色本身就是主角的畫面降到 0.15）。"""
    m = MOODS[mood]
    small = cv2.resize(img, (96, 96), interpolation=cv2.INTER_AREA)
    means = small.reshape(-1, 3).mean(0) + 1e-4
    gain_wb = (means.mean() / means) ** wb
    img = img * gain_wb
    if m['expo']:
        L = lum(np.clip(small * gain_wb, 0, 1))
        mid = float(np.exp(np.log(L + 1e-3).mean()))                # 幾何平均＝中間調
        gain = np.clip(m['expo'] / max(mid, 1e-3), 0.75, 1.5) ** 0.6
        p98 = float(np.percentile(L, 98))
        gain = min(gain, max(1.0, 0.93 / max(p98, 1e-3)))           # 不把臉和亮部推過曝
        img = img * gain * gmul
    return img


# ───────────────────────── 2. 調色 ─────────────────────────
def tone(x, contrast, lift, shoulder=0.72):
    """高光柔肩（從 shoulder 起 tanh 壓縮，亮部不會一刀切白）＋ S 曲線＋黑位。高級感最重要的一條曲線。"""
    x = np.maximum(x, 0)
    k = shoulder
    x = np.where(x > k, k + (1 - k) * np.tanh((x - k) / (1 - k)), x)
    s = x * x * (3 - 2 * x)
    x = x + contrast * (s - x)
    return lift + (1 - lift) * x


def color(img, mood):
    """綠往橄欖、降飽和但保護膚色、分離色調（暗部青、亮部暖，皮膚不被推走）。"""
    m = MOODS[mood]
    img = np.clip(img, 0, 4).astype(np.float32)
    hsv = cv2.cvtColor(np.clip(img, 0, 1), cv2.COLOR_RGB2HSV)       # float：H 0–360
    h, s, v = hsv[..., 0], hsv[..., 1], hsv[..., 2]
    green = np.clip(1 - np.abs(h - 115) / 55, 0, 1)
    h = h + (48 - h) * green * m['olive'] * 0.6
    s = s * (1 - green * m['olive'] * 0.35)
    skin = np.clip(1 - np.abs(h - 28) / 30, 0, 1)                   # 橘色區間＝皮膚候選
    s = s * (m['sat'] + (1 - m['sat']) * skin * 0.85)
    base = cv2.cvtColor(np.dstack([h, np.clip(s, 0, 1), v]), cv2.COLOR_HSV2RGB)
    img = base + np.maximum(img - 1, 0)                             # 超過 1 的亮部留給光暈
    L = np.clip(lum(img), 0, 1)[..., None]
    img = tone(img, m['contrast'], 0)
    skin_m = skin[..., None] * np.clip(hsv[..., 1:2] * 3, 0, 1)     # 只有夠飽和的橘色才算皮膚
    img = img + (1 - L) ** 2 * np.float32([-m['teal'] * 0.6, m['teal'] * 0.15, m['teal']]) * (1 - 0.95 * skin_m)
    img = img + skin_m * np.float32([0.028, 0.010, -0.016])         # 皮膚一點點暖
    img = img + L ** 2 * np.float32([m['warm'], m['warm'] * 0.35, -m['warm'] * 0.7])
    img = img + np.float32([-m['cool'], 0, m['cool']])
    return m['lift'] + (1 - m['lift']) * np.clip(img, 0, 1)


# ───────────────────────── 3. 光 ─────────────────────────
def glow(img, mood, scale=1.0):
    """光暈（紅橘、貼著高光邊緣）＋泛光（大範圍柔光）；1/4 解析度算。"""
    m = MOODS[mood]
    h, w = img.shape[:2]
    r = _res(img) * scale
    small = cv2.resize(img, (w // 4, h // 4), interpolation=cv2.INTER_AREA)
    hi = np.clip((lum(small) - 0.78) / 0.22, 0, 1)[..., None] ** 1.5 * small
    hal = cv2.GaussianBlur(hi, (0, 0), 3.5 * r) * np.float32([1.0, 0.38, 0.18])
    blo = cv2.GaussianBlur(hi, (0, 0), 14 * r)
    add = cv2.resize(hal * m['halation'] * 1.3 + blo * m['bloom'], (w, h), interpolation=cv2.INTER_LINEAR)
    return screen(img, add)


def anamorphic(img, strength=0.5, thresh=0.86):
    """變形鏡頭的橫向藍色光斑：只給煙火、太陽、路燈這種點光源；一支片一兩次。"""
    h, w = img.shape[:2]
    small = cv2.resize(img, (w // 4, h // 4), interpolation=cv2.INTER_AREA)
    spot = np.clip((lum(small) - thresh) / (1 - thresh), 0, 1) ** 2
    n = int(161 * _res(img)) | 1
    streak = cv2.filter2D(spot, -1, cv2.getGaussianKernel(n, 45 * _res(img)).T * 3.0)
    return screen(img, cv2.resize(streak, (w, h))[..., None] * np.float32([0.35, 0.6, 1.0]) * strength)


# ───────────────────────── 4. 一次調好 ─────────────────────────
def grade(img, mood='clean', flare=0.0, gmul=1.0, wb=0.35):
    img = normalize(img, mood, gmul, wb)
    img = color(img, mood)
    img = glow(img, mood)
    if flare > 0:
        img = anamorphic(img, flare)
    return np.clip(img, 0, 1)


_FD = None


def face_lum(img):
    """最亮那張臉中央的亮度（0–1）；沒有臉回 None。"""
    global _FD
    if not os.path.exists(YUNET):
        return None
    h, w = img.shape[:2]
    s = 800 / max(h, w)
    sm = cv2.resize((np.clip(img, 0, 1) * 255).astype(np.uint8)[..., ::-1], (int(w * s), int(h * s)))
    if _FD is None:
        _FD = cv2.FaceDetectorYN.create(YUNET, '', (sm.shape[1], sm.shape[0]), 0.7)
    _FD.setInputSize((sm.shape[1], sm.shape[0]))
    _, f = _FD.detect(sm)
    if f is None:
        return None
    vals = []
    for x, y, fw, fh in f[:, :4] / s:
        if fw < w * 0.04:
            continue
        x0, y0, x1, y1 = int(x + fw * 0.2), int(y + fh * 0.25), int(x + fw * 0.8), int(y + fh * 0.75)
        if x1 > x0 and y1 > y0:
            vals.append(float(lum(img[max(0, y0):y1, max(0, x0):x1]).mean()))
    return max(vals) if vals else None


def face_safe(img, mood='clean', flare=0.0, limit=0.60, wb=0.35):
    """調色後臉太亮（閃光自拍、逆光提亮）會白成一片、像過度美顏：量臉亮度，超過 limit 就降曝光重調（最多 3 次）。"""
    g = grade(img, mood, flare, 1.0, wb)
    k = 1.0
    for _ in range(3):
        fl = face_lum(g)
        if fl is None or fl <= limit:
            break
        k *= (limit / fl) ** 1.3
        g = grade(img, mood, flare, k, wb)
    return g


# ───────────────────────── 5. 鏡頭之間對齊 ─────────────────────────
def stats(img):
    """黑位（第 1 百分位）、白位（第 99）、中間調、近中性色偏色（Lab a／b，0–1 尺度的 RGB 也可）。"""
    u8 = (np.clip(img, 0, 1) * 255).astype(np.uint8)
    L = lum(img) * 255
    lab = cv2.cvtColor(u8, cv2.COLOR_RGB2LAB).astype(np.float32)
    A, B = lab[..., 1] - 128, lab[..., 2] - 128
    neu = (np.hypot(A, B) < 14) & (lab[..., 0] > 50) & (lab[..., 0] < 230)
    cast = (float(A[neu].mean()), float(B[neu].mean())) if neu.mean() > 0.04 else None
    return dict(black=float(np.percentile(L, 1)), white=float(np.percentile(L, 99)), mid=float(np.exp(np.log(L + 1).mean()) - 1), cast=cast)


def match(img, ref, strength=1.0):
    """把這個鏡頭的黑位、白位、近中性色偏色對到 ref（stats() 的結果，通常取全片代表鏡頭）。
    不動中間調（那是場景本身的亮暗），只讓「黑一樣黑、白一樣白、灰一樣灰」。"""
    st = stats(img)
    b0, w0 = st['black'] / 255, st['white'] / 255
    b1, w1 = ref['black'] / 255, ref['white'] / 255
    out = img
    if w0 - b0 > 0.2:
        lin = (img - b0) / (w0 - b0) * (w1 - b1) + b1
        out = img + (lin - img) * strength
    st = stats(np.clip(out, 0, 1))  # 黑白位對齊後再量一次偏色（拉伸會改變哪些像素算「中性色」）
    if st['cast'] and ref.get('cast'):
        da, db = (ref['cast'][0] - st['cast'][0]) * strength, (ref['cast'][1] - st['cast'][1]) * strength
        u8 = (np.clip(out, 0, 1) * 255).astype(np.uint8)
        lab = cv2.cvtColor(u8, cv2.COLOR_RGB2LAB).astype(np.float32)
        delta = np.zeros_like(lab)
        delta[..., 1], delta[..., 2] = da, db
        moved = cv2.cvtColor(np.clip(lab + delta, 0, 255).astype(np.uint8), cv2.COLOR_LAB2RGB).astype(np.float32) / 255
        out = out + (moved - np.clip(out, 0, 1))  # 只加位移量，不吃掉超過 1 的亮部與浮點精度
    return np.clip(out, 0, 1)


# ───────────────────────── 5b. 整個鏡頭鎖同一組參數 ─────────────────────────
def _gains(img, mood, wb):
    m = MOODS[mood]
    small = cv2.resize(img, (96, 96), interpolation=cv2.INTER_AREA)
    means = small.reshape(-1, 3).mean(0) + 1e-4
    gain_wb = (means.mean() / means) ** wb
    gain = 1.0
    if m['expo']:
        L = lum(np.clip(small * gain_wb, 0, 1))
        mid = float(np.exp(np.log(L + 1e-3).mean()))
        gain = float(np.clip(m['expo'] / max(mid, 1e-3), 0.75, 1.5) ** 0.6)
        gain = min(gain, max(1.0, 0.93 / max(float(np.percentile(L, 98)), 1e-3)))
    return gain_wb.astype(np.float32), gain


def lock(img, mood='clean', ref=None, strength=0.7, flare=0.0, limit=0.60, wb=0.35):
    """一個鏡頭量一次（拿這個鏡頭最有代表性的一格）：白平衡、曝光、臉的降光、對齊 ref 的黑白位與偏色。
    face_safe／match 每格重量，搖鏡時畫面內容一變，增益就跟著變，看起來像手機自動曝光在呼吸；
    整個鏡頭用同一組數字（apply）才穩。lock 的結果只由那一格決定，仍符合 seek(t)。"""
    gw, g = _gains(img, mood, wb)
    k = 1.0
    out = None
    for _ in range(4):
        out = color(img * gw * (g * k), mood)
        out = np.clip(glow(out, mood), 0, 1)
        fl = face_lum(out)
        if fl is None or fl <= limit:
            break
        k *= (limit / fl) ** 1.3
    L = dict(mood=mood, gw=gw, g=g * k, flare=flare, lin=None, dab=None)
    if ref is not None:
        st = stats(out)
        b0, w0, b1, w1 = st['black'] / 255, st['white'] / 255, ref['black'] / 255, ref['white'] / 255
        if w0 - b0 > 0.2:
            L['lin'] = (b0, w0, b1, w1, strength)
            out = out + ((out - b0) / (w0 - b0) * (w1 - b1) + b1 - out) * strength
        st = stats(np.clip(out, 0, 1))
        if st['cast'] and ref.get('cast'):
            L['dab'] = ((ref['cast'][0] - st['cast'][0]) * strength, (ref['cast'][1] - st['cast'][1]) * strength)
    return L


def apply(img, L):
    """用 lock() 的參數調色：normalize → color → glow →（flare）→ match，數字全鏡頭一樣。"""
    out = color(img * L['gw'] * L['g'], L['mood'])
    out = glow(out, L['mood'])
    if L['flare'] > 0:
        out = anamorphic(out, L['flare'])
    out = np.clip(out, 0, 1)
    if L['lin']:
        b0, w0, b1, w1, s = L['lin']
        out = out + ((out - b0) / (w0 - b0) * (w1 - b1) + b1 - out) * s
    if L['dab']:
        u8 = (np.clip(out, 0, 1) * 255).astype(np.uint8)
        lab = cv2.cvtColor(u8, cv2.COLOR_RGB2LAB).astype(np.float32)
        lab[..., 1] += L['dab'][0]
        lab[..., 2] += L['dab'][1]
        moved = cv2.cvtColor(np.clip(lab, 0, 255).astype(np.uint8), cv2.COLOR_LAB2RGB).astype(np.float32) / 255
        out = out + (moved - np.clip(out, 0, 1))
    return np.clip(out, 0, 1)


# ───────────────────────── 6. 膠片 ─────────────────────────
@functools.lru_cache(maxsize=4)
def _grain_bank(h, w, n=8, seed=5):
    r = np.random.default_rng(seed)
    bank = []
    for _ in range(n):
        g = cv2.GaussianBlur(r.normal(0, 1, (h // 2, w // 2)).astype(np.float32), (0, 0), 0.6)
        bank.append(cv2.resize(g, (w, h), interpolation=cv2.INTER_LINEAR))
    return bank


@functools.lru_cache(maxsize=4)
def _vig(h, w, k):
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    r = np.sqrt(((xx - w / 2) / (w / 2)) ** 2 + ((yy - h / 2) / (h / 1.6)) ** 2) / math.sqrt(2)
    return (1 - k * np.clip(r, 0, 1.2) ** 2.2)[..., None].astype(np.float32)


def film(img, t, fps=30, grain=0.03, vignette=0.32):
    """顆粒（中間調最明顯，24 格一換的節奏）＋暗角。grain 0.02–0.04；交付前壓檔要留 0.012 以上才擋得住色階。"""
    h, w = img.shape[:2]
    L = lum(img)[..., None]
    amt = grain * (0.35 + 2.6 * L * (1 - L))
    img = img + _grain_bank(h, w)[int(t * 24) % 8][..., None] * amt
    if vignette:
        img = img * _vig(h, w, vignette)
    return np.clip(img, 0, 1)


def weave(t, k=1.0):
    """片門晃動的位移（px，以 1080p 計）：低頻、肉眼幾乎看不出，但讓畫面「活著」。"""
    return k * (0.5 * math.sin(t * 1.7) + 0.3 * math.sin(t * 5.3 + 1)), k * 0.35 * math.sin(t * 2.3 + 2)


def light_leak(h, w, u, seed=0, tint=(1.0, 0.55, 0.20)):
    """漏光層（screen 疊上去）：幾團暖光從邊緣掃過，u 0–1 為轉場進度，中段最亮。"""
    r = np.random.default_rng(seed)
    hs, ws = h // 4, w // 4
    yy, xx = np.mgrid[0:hs, 0:ws].astype(np.float32)
    out = np.zeros((hs, ws, 3), np.float32)
    for k in range(3):
        cx = (r.random() * 0.4 + (0.1 if k % 2 else 0.6)) * ws + (u - 0.5) * ws * (0.8 + r.random())
        cy = r.random() * hs
        rad = (0.25 + r.random() * 0.35) * ws
        col = np.float32(tint) * np.float32([1, 0.8 + r.random() * 0.4, 0.6 + r.random() * 0.8])
        out += np.exp(-(((xx - cx) ** 2 + (yy - cy) ** 2) / rad ** 2))[..., None] * col
    return cv2.resize(out, (w, h)) * math.sin(math.pi * min(max(u, 0), 1)) ** 1.3


def holo_sweep(img, u, k=0.22):
    """彩虹箔光：一道柔和斜光帶掃過（卡牌、包裝、金屬題材），只掃一次，k ≤ 0.25。"""
    if k <= 0.01 or u < -0.2 or u > 1.2:
        return img
    h, w = img.shape[:2]
    hs, ws = h // 4, w // 4
    yy, xx = np.mgrid[0:hs, 0:ws].astype(np.float32)
    g, yn = xx / ws * 0.75 + yy / hs * 0.55, yy / hs
    p = -0.2 + u * 1.7
    band = np.exp(-((g - p) / 0.09) ** 2) * 0.8 + np.exp(-((g - p) / 0.03) ** 2) * 0.6
    hue = (g * 3.0 + yn * 1.5) % 1.0
    rgb = np.stack([0.5 + 0.5 * np.cos(2 * np.pi * (hue + o)) for o in (0.0, 0.33, 0.66)], -1).astype(np.float32) * 0.55 + 0.45
    return screen(img, cv2.resize(band[..., None] * rgb, (w, h)) * k)


def glints(img, t, n=4, size=None, k=1.0, thr=0.82):
    """實拍高光處長出四芒星（玻璃、金屬、水面反光）；閃爍節奏由 t 決定。只放在本來就亮的地方。"""
    h, w = img.shape[:2]
    size = size or int(26 * _res(img))
    s = cv2.GaussianBlur(cv2.resize(lum(img), (w // 6, h // 6), interpolation=cv2.INTER_AREA), (0, 0), 1.2)
    mx = cv2.dilate(s, np.ones((9, 9), np.uint8))
    ys, xs = np.nonzero((s >= mx) & (s > thr))
    pts = []
    for v, x, y in sorted(zip(s[ys, xs], xs * 6 + 3, ys * 6 + 3), reverse=True):
        if all((x - a) ** 2 + (y - b) ** 2 > (size * 6) ** 2 for a, b in pts):
            pts.append((x, y))
        if len(pts) >= n:
            break
    if not pts:
        return img
    lay = np.zeros((h, w), np.float32)
    for i, (x, y) in enumerate(pts):
        tw = max(0.0, math.sin(t * 3.1 + i * 2.3 + x * 0.01)) ** 4 * k
        if tw < 0.02:
            continue
        for (dx, dy), L in (((1, 0), size * 2.2), ((0, 1), size * 2.2), ((0.7, 0.7), size * 0.9), ((0.7, -0.7), size * 0.9)):
            p0 = (int((x - dx * L) * 16), int((y - dy * L) * 16))
            p1 = (int((x + dx * L) * 16), int((y + dy * L) * 16))
            cv2.line(lay, p0, p1, tw, 1, cv2.LINE_AA, shift=4)
    lay = cv2.GaussianBlur(lay, (0, 0), 1.2) * 1.6 + cv2.GaussianBlur(lay, (0, 0), size * 0.25) * 2.5
    return screen(img, lay[..., None] * np.float32([1.0, 0.97, 0.9]))


# ───────────────────────── 指令：look board ─────────────────────────
def _load(spec):
    """a.jpg 或 clip.mp4@秒數 → float32 RGB 0–1。"""
    if '@' in spec and spec.rsplit('@', 1)[1].replace('.', '', 1).isdigit():
        path, t = spec.rsplit('@', 1)
        cap = cv2.VideoCapture(path)
        cap.set(cv2.CAP_PROP_POS_MSEC, float(t) * 1000)
        ok, fr = cap.read()
        if not ok:
            sys.exit(f'讀不到 {spec}')
        return fr[..., ::-1].astype(np.float32) / 255
    im = cv2.imread(spec, cv2.IMREAD_COLOR)
    if im is None:
        sys.exit(f'讀不到 {spec}')
    return im[..., ::-1].astype(np.float32) / 255


def cmd_board(a):
    from PIL import Image, ImageDraw, ImageFont
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from finish import measure
    moods = ['原片'] + a.moods.split(',')
    tile = a.tile
    rows = []
    for spec in a.inputs:
        img = _load(spec)
        k = tile * 2 / max(img.shape[:2])
        img = cv2.resize(img, (int(img.shape[1] * k), int(img.shape[0] * k)), interpolation=cv2.INTER_AREA) if k < 1 else img
        row = []
        for m in moods:
            out = img if m == '原片' else film(face_safe(img, m), 0.5, vignette=0.25, grain=0.02)
            u8 = (np.clip(out, 0, 1) * 255 + 0.5).astype(np.uint8)
            q = measure(u8)
            row.append((m, u8, q))
        rows.append((os.path.basename(spec), row))
    th0, tw0 = rows[0][1][0][1].shape[:2]
    kk = tile / max(th0, tw0)
    tw, th = int(tw0 * kk), int(th0 * kk)
    bar, pad = 44, 6
    sheet = Image.new('RGB', (pad + len(moods) * (tw + pad), pad + len(rows) * (th + bar + pad)), (16, 16, 18))
    d = ImageDraw.Draw(sheet)
    f1 = ImageFont.truetype('/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc', 15, index=3)
    f2 = ImageFont.truetype('/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc', 12, index=3)
    for r, (name, row) in enumerate(rows):
        for c, (m, u8, q) in enumerate(row):
            x, y = pad + c * (tw + pad), pad + r * (th + bar + pad)
            sheet.paste(Image.fromarray(u8).resize((tw, th), Image.LANCZOS), (x, y + bar))
            d.text((x + 2, y + 1), f"{m}" + (f"　{name[:10]}" if c == 0 else ''), font=f1, fill=(240, 210, 90))
            skin = f" 膚{q['skin'][0]:.0f}°" if q['skin'] else ''
            d.text((x + 2, y + 22), f"黑{q['black']:.0f} 白{q['white']:.0f} 彩{q['sat']:.0f} 硬切{q['clip']:.1%}{skin}", font=f2,
                   fill=(255, 120, 110) if q['clip'] > 0.005 or q['sat'] > 60 or (q['skin'] and abs(q['skin'][0] - 123) > 12) else (215, 215, 215))
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    sheet.save(a.out, quality=90)
    print(a.out)


def cmd_apply(a):
    img = _load(a.input)
    out = film(face_safe(img, a.mood), 0.5) if a.film else face_safe(img, a.mood)
    cv2.imwrite(a.out, ((np.clip(out, 0, 1) * 255 + 0.5).astype(np.uint8))[..., ::-1])
    print(a.out)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = p.add_subparsers(dest='cmd', required=True)
    s = sp.add_parser('board', help='同一批素材套不同 mood 的對照表')
    s.add_argument('inputs', nargs='+', help='圖檔，或 影片@秒數')
    s.add_argument('--moods', default='clean,soft,day,golden,aot')
    s.add_argument('--tile', type=int, default=300, help='每格長邊（px）')
    s.add_argument('-o', '--out', default='out/look_board.jpg')
    s = sp.add_parser('apply', help='一張圖套一個 mood')
    s.add_argument('input')
    s.add_argument('--mood', default='clean', choices=sorted(MOODS))
    s.add_argument('--film', action='store_true')
    s.add_argument('-o', '--out', required=True)
    a = p.parse_args()
    {'board': cmd_board, 'apply': cmd_apply}[a.cmd](a)


if __name__ == '__main__':
    main()
