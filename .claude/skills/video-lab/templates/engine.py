"""seek(t) 影片引擎範本：複製到 projects/<案名>/work/engine.py 再改。

  python .claude/skills/video-lab/scripts/frames.py sheet projects/<案名>/work/engine.py -o projects/<案名>/qa/sheet.jpg
  python .claude/skills/video-lab/scripts/frames.py video projects/<案名>/work/engine.py -o projects/<案名>/deliver/master.mp4

約定：frame(t) 只由 t 決定。不要在 frame() 外累積狀態、不要用沒種子的亂數、不要讀「上一格」；
要隨機就 frame_rng(t, FPS)，要記住某個鏡頭的最後一格就直接 render_shot(那顆鏡頭, 它的結束時間 - 1e-3)。

這份範本沒有外部素材也能跑（有 BRAND 目錄就改用真的截圖與品牌色），示範三種不老套的做法：
  1. 開場不是「漸層＋置中標題」：真實頁面截圖當畫面，標題從基線遮罩升起、靠左對齊網格
  2. 進場不是全部淡入：rise（遮罩升起）、逐字、線條畫出，各有不同節奏
  3. 資訊字卡貼著內容（指向畫面裡的東西），不是角落小標

質感（references/finish.md）：
  - 網頁截圖、UI、logo 不調色（品牌色要準）；實拍鏡頭才走 look.py：face_safe（統一＋調色＋光＋臉）→ match 對齊代表鏡頭
  - 先跑 `look.py board` 選 MOOD；字一律 text_sprite＋blit／rise（次像素，不會抖）；快速運動包 mblur
  - 最後 grain／film → to_u8（預設抖色，漸層壓檔後不會一圈一圈）
"""
import json
import os

import cv2
import numpy as np

from seekkit import (CJK_B, CJK_R, CJK_TC, ease, ease_out, fit_text, glow_line, grain, hexrgb, image, kenburns, rise, wrap_text,
                     scroll_page, scrim, shade_rect, text_sprite, to_u8, vignette, window)

HERE = os.path.dirname(os.path.abspath(__file__))
W, H, FPS = 1080, 1920, 30
TOTAL = 9.0
AUDIO = None  # 例：os.path.join(HERE, 'music.wav')

# ───────── 品牌（brand.py 的輸出；沒有就用中性預設）─────────
BRAND = os.path.join(HERE, '..', 'brand')
B = json.load(open(os.path.join(BRAND, 'brand.json'))) if os.path.exists(os.path.join(BRAND, 'brand.json')) else {}
ACCENT = hexrgb(B['accents'][0]['hex']) if B.get('accents') else hexrgb('#F7BA0B')
INK = hexrgb(B['neutrals'][0]['hex']) if B.get('neutrals') else hexrgb('#0B0B0C')
PAPER = hexrgb('#F5F2EA')
MUTED = hexrgb('#8F8A7E')
MARGIN = 84  # 左側網格線：所有字對齊這條


def page_img(name):
    p = os.path.join(BRAND, name)
    if os.path.exists(p):
        return image(p)[..., :3]
    # 沒有品牌截圖時的替身：程式畫的假頁面只拿來測流程，正式片一律換成真截圖
    y = np.linspace(0, 1, 2400, dtype=np.float32)[:, None, None]
    img = np.ones((2400, 1080, 3), np.float32) * INK
    for k in range(6):
        img[300 + k * 360:520 + k * 360, 80:1000] = INK * 0.6 + ACCENT * 0.15 + 0.05
    return img * (0.9 + 0.1 * y)


# ───────── 這支片要改的地方（從 brand.md 的真實文案與截圖量出來）─────────
COPY = {
    'kicker': 'PRODUCT FILM',
    'headline': '一句話講清楚價值',
    'feature': '真實功能名稱',           # 例：網站上的按鈕或功能名
    'feature_sub': '一行說明，來自網站上的真實文案',
    'end_title': '品牌名',
    'end_cta': '網址或行動呼籲',
}
HERO_FOCUS = dict(z=(1.95, 1.85), c=(0.56, 0.39))   # mobile_hero 上主視覺的取景中心（比例），z 放到只剩主視覺、看不到網站自己的字
SCROLL_Y = (1640, 1840)                              # mobile_full 捲動起訖（原圖 px）
TARGET = (270, 2195)                                 # mobile_full 上被指的真實元素（原圖 px），callout 的線從這裡出發
LOGO = os.path.join(BRAND, 'logo', 'logo_0_src.png')  # brand.py 抓到的原檔；不存在就只放字

# ───────── 鏡頭表：(起, 迄, 種類, 參數) ─────────
SHOTS = [
    (0.0, 3.0, 'hero', dict(name='mobile_hero.png')),
    (3.0, 6.0, 'scroll', dict(name='mobile_full.png')),
    (6.0, TOTAL, 'end', dict()),
]
MARKS = [(0.4, '開場'), (1.5, '標題升起'), (3.4, '換鏡'), (4.5, '資訊卡'), (6.6, '收尾'), (8.5, '片尾')]


def shot_at(t):
    for s in SHOTS:
        if s[0] <= t < s[1]:
            return s
    return SHOTS[-1]


def scroll_y(t):
    s = SHOTS[1]
    return SCROLL_Y[0] + (SCROLL_Y[1] - SCROLL_Y[0]) * ease((t - s[0]) / (s[1] - s[0]))


def render_shot(s, t):
    t0, t1, kind, p = s
    u = (t - t0) / (t1 - t0)
    if kind == 'hero':
        return kenburns(page_img(p['name']), u, W, H, HERO_FOCUS['z'], HERO_FOCUS['c'], HERO_FOCUS['c'])
    if kind == 'scroll':
        y = scroll_y(t)
        return scroll_page(page_img(p['name']), 0, W, H, y, y)
    return np.ones((H, W, 3), np.float32) * INK


# ───────── 實拍鏡頭（這份範本沒用到；有影片素材時照這個寫）─────────
# from look import face_safe, film, match, stats
# from seekkit import src, mblur
# MOOD = 'clean'                                     # look.py board 選出來的
# REF = stats(face_safe(src(V1).at(7.4), MOOD))      # 全片代表鏡頭：白天、有中性色（牆、衣服、桌面）
# def footage(path, t_src):
#     return match(face_safe(src(path).at(t_src, blend=True), MOOD), REF, 0.7)
# 會搖鏡的鏡頭改成整個鏡頭鎖一組參數（每格重量的話，畫面內容一變增益就跟著變，像自動曝光在呼吸）：
# from look import lock, apply
# @functools.lru_cache(maxsize=64)
# def shot_lock(path, t_rep):                      # t_rep：這個鏡頭最有代表性的那一格
#     return lock(src(path).at(t_rep), MOOD, ref=REF, strength=0.7)
# def footage(path, t_src, t_rep):
#     return apply(src(path).at(t_src, blend=True), shot_lock(path, t_rep))


# ───────── 疊層 ─────────
def title(c, t):
    e = t - 0.5
    if -0.1 < e < 2.6:
        scrim(c, 1150, 1700, 0.6 * window(t, 0.4, 3.0, 0.4, 0.4))
        rise(c, text_sprite(COPY['kicker'], 30, CJK_B, CJK_TC, 0.3, tuple(ACCENT)), MARGIN, 1300, e, 0.5, 2.1, 0.3)
        rise(c, fit_text(COPY['headline'], W - 2 * MARGIN, 84, CJK_B, CJK_TC, 0.06, tuple(PAPER)), MARGIN - 4, 1352, e - 0.1, 0.6, 2.0, 0.3)
        lu = ease_out((e - 0.4) / 0.6) * (1 - ease((e - 2.1) / 0.3))
        if lu > 0:
            c[1480:1483, MARGIN:MARGIN + int(260 * lu)] = ACCENT


def callout(c, t):
    """指向畫面裡真實元素的資訊卡：線從元素出發（跟著捲動走），字對齊左網格。"""
    e = t - 3.5
    if e < 0 or t > 6.0:
        return
    k = window(t, 3.5, 6.0, 0.3, 0.35)
    pw = page_img(SHOTS[1][3]['name']).shape[1]
    sc = W / pw
    tx, ty = TARGET[0] * sc, (TARGET[1] - scroll_y(t)) * sc + 70
    lx, ly = MARGIN + 40, int(ty + 70)   # 字緊貼在被指的元素下方，跟著它一起捲動
    u = ease_out(e / 0.5)
    glow_line(c, [(MARGIN + 8, ty - 10), (MARGIN + 8, ty - 10 + (ly + 150 - ty) * u)], ACCENT, 2, 8, k)
    if u > 0.6:
        rise(c, text_sprite(COPY['feature'], 64, CJK_B, CJK_TC, 0.05, tuple(PAPER)), lx, ly, e - 0.35, 0.5, 2.0, 0.3)
        rise(c, fit_text(COPY['feature_sub'], W - 2 * MARGIN, 36, CJK_R, CJK_TC, 0.04, tuple(PAPER * 0.85)), lx + 2, ly + 96, e - 0.45, 0.5, 1.9, 0.3)


def end_card(c, t):
    e = t - 6.0
    lines = wrap_text(COPY['end_title'], W - 2 * MARGIN, 92, CJK_B, CJK_TC, 0.02, tuple(PAPER))
    block = sum(ln.shape[0] + 14 for ln in lines) + 150
    y = int(H * 0.46 - block / 2)  # 整塊（logo 以下）垂直置中略偏上
    if os.path.exists(LOGO):
        lg = image(LOGO)
        lg = cv2.resize(lg, (150, int(150 * lg.shape[0] / lg.shape[1])), interpolation=cv2.INTER_AREA)
        if lg.shape[2] == 3:
            lg = np.dstack([lg, np.ones(lg.shape[:2], np.float32)])
        rise(c, lg, MARGIN, y - lg.shape[0] - 40, e, 0.6)
    # 所有字都要放得進安全區：寬度一律用 wrap_text／fit_text 量過，不寫死字級
    for i, ln in enumerate(lines):
        rise(c, ln, MARGIN, y, e - 0.2 - i * 0.12, 0.6)
        y += ln.shape[0] + 14
    rise(c, fit_text(COPY['end_cta'], W - 2 * MARGIN, 40, CJK_B, CJK_TC, 0.08, tuple(ACCENT)), MARGIN + 4, y + 30, e - 0.5, 0.5)
    lu = ease_out((e - 0.8) / 0.8)
    if lu > 0:
        shade_rect(c, MARGIN, y + 110, MARGIN + int(400 * lu), y + 113, 1.0, ACCENT)


def frame(t):
    s = shot_at(t)
    c = render_shot(s, t).copy()
    if s[2] != 'end':
        vignette(c)
    title(c, t)
    callout(c, t)
    if s[2] == 'end':
        end_card(c, t)
    if t > TOTAL - 0.6:  # 片尾收進品牌底色（只有最後這一下是淡出）
        f = ease((t - (TOTAL - 0.6)) / 0.6)
        c = c * (1 - f) + INK * f
    grain(c, t, FPS)
    return to_u8(c)
