"""迷幻風卡點跳舞 MV（seek(t) 引擎範本，16:9）。配方、素材規格與分寸：references/dance-mv.md。

複製到 projects/<案名>/work/engine.py，只改「設定」那一段：
  python .claude/skills/video-lab/scripts/frames.py sheet projects/<案名>/work/engine.py -o projects/<案名>/qa/sheet.jpg
  python .claude/skills/video-lab/scripts/frames.py video projects/<案名>/work/engine.py -o projects/<案名>/deliver/master.mp4

規則（每一條都對應使用者給的規格，改之前先讀 dance-mv.md〈三〉〈四〉）：
  結構   歌先用 songcut.py 剪好（前奏／主歌／副歌／結尾，剪點在小節線），這裡吃剪後的 json；一切時間都從小節線算
  換人   每位角色停留 SEG_BARS（4）小節，換人落在小節線上：角色圖層「滑動＋交叉淡化」（小節線前後各 XFADE 拍），不硬切
  取景   同一位角色中間換一次取景：前兩小節全身 → 第三小節推到半身（平順推鏡）；每隔一位，最後兩拍接眼睛特寫
  副歌   開頭與結尾全員並排；中間穿插單人、雙人並排、五連排變色；整個畫面（連角色）慢慢轉色相
  閃白   只在小節線上：換人 0.30、副歌小節頭 0.18、其他小節 0.09（很淡），約 3 格消退
  背景   每小節換一個：資料夾圖片（色相流轉＋輕微扭曲）與彩虹同心圓、旋轉色環、融化彩虹、條紋、黑白棋盤輪流
  撕裂   畫面撕裂＋RGB 分離只在換人與副歌小節頭出現，下一拍前回到清楚
  萬花筒 前奏最後一小節、副歌每 8 小節的最後一小節、結尾；角色疊在萬花筒上面保持清楚
  大字   角色後面的日文大字：主歌每 2 小節一個、副歌每小節一個（WORDS；None＝不放字）；不是逐句歌詞字幕
"""
import glob
import math
import os
import sys

import cv2
import numpy as np


def _find_vl():
    d = os.path.dirname(os.path.abspath(__file__))
    while d != '/':
        p = os.path.join(d, '.claude', 'skills', 'video-lab', 'scripts')
        if os.path.isdir(p):
            return p
        d = os.path.dirname(d)
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'scripts')


sys.path.insert(0, _find_vl())
import psyfx as PX  # noqa: E402
from seekkit import ease, to_u8  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))

# ═════════ 設定（每支片改這裡）═════════
W, H, FPS = 1280, 720, 30
SONG_JSON = os.path.join(HERE, 'song90.json')          # songcut.py 的輸出（剪後時間軸）
AUDIO = os.path.join(HERE, 'song90.wav')
CHAR_DIR = os.path.join(HERE, 'chars')
# 角色：(來源, 免費律動風格)。來源＝keyloop.py key 的資料夾（生成的舞，風格不用）或 *_cut.png（免費律動 puppet）
CHARS = [(p, s) for p, s in zip(sorted(glob.glob(os.path.join(CHAR_DIR, '*_clip'))) or sorted(glob.glob(os.path.join(CHAR_DIR, '*_cut.png'))),
                                 ('bounce', 'sway', 'hop', 'groove', 'twist', 'robot') * 4)]
BG_DIR = os.path.join(HERE, 'bg')
BG_FILES = sorted(glob.glob(os.path.join(BG_DIR, '*.jpg')) + glob.glob(os.path.join(BG_DIR, '*.png')))
# 背景日文大字：從歌的主題挑關鍵字（例：スパークル的主題字），或用使用者指定的字；None＝不放字。不放逐句歌詞
WORDS = {'verse': ['夢', '光', '時', '星'], 'chorus': ['火花', '運命', '君', '永遠', '夢', '光', '煌めき', '奇跡']}
SEG_BARS = 4            # 每位角色停留幾小節
XFADE = 0.5             # 換人轉場：小節線前後各幾拍
PATTERNS = ('rings', 'wheel', 'melt', 'stripes', 'checker')
BG_ORDER = ('photo', 'photo', 'pattern')               # 每小節輪流：兩張圖片、一個程式圖樣
FLASH = dict(change=0.30, chorus=0.18, bar=0.09)
END_COL = (0.06, 0.02, 0.10)                            # 片尾收進的顏色（深紫）
# ═════════════════════════════════════

G = PX.Grid(SONG_JSON)
TOTAL = G.dur
BEAT = G.beatlen
DANCERS = [PX.Dancer(p, style=s) for p, s in CHARS]
N = len(DANCERS)
_BG_CACHE = {}


def bg_img(k):
    if k not in _BG_CACHE:
        im = cv2.imread(BG_FILES[k])
        _BG_CACHE[k] = cv2.cvtColor(im, cv2.COLOR_BGR2RGB).astype(np.float32) / 255
        if len(_BG_CACHE) > 6:
            _BG_CACHE.pop(next(iter(_BG_CACHE)))
    return _BG_CACHE[k]


# ═════════ 依小節排的計畫（import 時算好，純資料）═════════
def _bars():
    first, last = G.bar(0.0)[0], G.bar(TOTAL - 1e-3)[0]
    if first < 0 and G.db[0] < 0.5 * G.barlen:          # 不到半小節的弱起併進第一小節（P() 會把它對到小節 0）
        first = 0
    return list(range(first, last + 1))


def _build():
    bars = _bars()
    roles = {i: G.role(max(0.0, G.bar_time(i)) + 0.02) for i in bars}
    plan = {}
    blocks = []            # (起小節, 迄小節, 模式, 角色們, 第幾個單人段)
    ci = 0
    solo_n = 0
    i = bars[0]
    while i <= bars[-1]:
        r = roles[i]
        j = i
        while j + 1 <= bars[-1] and roles[j + 1] == r:
            j += 1
        L = j - i + 1                                    # 這一段 [i, j]
        if r == 'chorus':
            ends = 2 if L >= 8 else 1
            k = i
            blocks.append((k, k + ends, 'all', list(range(N)), None))
            k += ends
            cyc = [('solo', SEG_BARS), ('duo', 2), ('solo', SEG_BARS), ('five', 2)]
            c = 0
            while j + 1 - ends - k >= 2:                    # 剩不到 2 小節就併進結尾的全員並排（1 小節的段太碎）
                mode, n = cyc[c % len(cyc)]
                n = min(n, j + 1 - ends - k)
                if mode == 'solo':
                    blocks.append((k, k + n, 'solo', [ci % N], solo_n))
                    solo_n += 1
                    ci += 1
                elif mode == 'duo':
                    blocks.append((k, k + n, 'duo', [ci % N, (ci + 1) % N], None))
                    ci += 2
                else:
                    blocks.append((k, k + n, 'five', [ci % N] * 5, None))
                    ci += 1
                k += n
                c += 1
            blocks.append((k, j + 1, 'all', list(range(N)), None))
        elif r == 'outro':
            blocks.append((i, j + 1, 'all', list(range(N)), None))
        else:                                            # intro、verse：單人，每 SEG_BARS 換人
            k = i
            while k <= j:
                n = min(SEG_BARS, j + 1 - k)
                blocks.append((k, k + n, 'solo', [ci % N], solo_n))
                solo_n += 1
                ci += 1
                k += n
        i = j + 1
    # 每小節的屬性
    word_i = {'verse': 0, 'chorus': 0}
    pat_i = photo_i = 0
    for b, (b0, b1, mode, who, sn) in enumerate(blocks):
        for i in range(b0, b1):
            r = roles[i]
            sec = G.section(max(0.0, G.bar_time(i)) + 0.02)
            in_sec = i - G.bar(sec['start'] + 0.02)[0]
            sec_len = round((sec['end'] - sec['start']) / G.barlen)
            kind = BG_ORDER[i % len(BG_ORDER)]
            if kind == 'pattern' or not BG_FILES:
                bg = ('pattern', PATTERNS[pat_i % len(PATTERNS)])
                pat_i += 1
            else:
                bg = ('photo', photo_i % len(BG_FILES))
                photo_i += 1
            kal = ((r == 'intro' and i == max(x for x in bars if roles[x] == 'intro'))
                   or (r == 'chorus' and ((in_sec + 1) % 8 == 0 or in_sec == sec_len - 1))
                   or r == 'outro' or i >= bars[-1] - 1)          # 結尾兩小節
            word = None
            if WORDS and r in WORDS:
                step = 2 if r == 'verse' else 1
                if in_sec % step == 0:
                    word = (WORDS[r][word_i[r] % len(WORDS[r])], i)
                    word_i[r] += 1
                elif i - 1 in plan and plan[i - 1]['word']:
                    word = plan[i - 1]['word']
            plan[i] = dict(block=b, mode=mode, who=who, solo=sn, b0=b0, b1=b1, role=r, bg=bg, kaleido=kal, word=word,
                           change=(i == b0 and b > 0), chorus_head=(r == 'chorus'))
    return plan, blocks


PLAN, BLOCKS = _build()


def P(i):
    if i in PLAN:
        return PLAN[i]
    return PLAN[min(PLAN)] if i < min(PLAN) else PLAN[max(PLAN)]


# ═════════ 畫面 ═════════
def background(i, t):
    p = P(i)
    kind, k = p['bg']
    if kind == 'photo':
        c = PX.photo_bg(bg_img(k), t, W, H, hue0=i * 47.0)
    else:
        c = {'rings': lambda: PX.rings(t, W, H, bands=7, wobble=0.06),
             'wheel': lambda: PX.wheel(t, W, H, twist=1.1, sectors=12),
             'melt': lambda: PX.melt(t, W, H),
             'stripes': lambda: PX.stripes(t, W, H, angle=0.55 if i % 2 else -0.55),
             'checker': lambda: PX.checker(t, W, H, warp_amp=0.22)}[k]()
    if p['kaleido']:
        c = PX.kaleido(c, t, n=8, spin=0.35)
    return c


def framing(i, t):
    """回傳 (z, 焦點 x, 焦點 y)：焦點是角色身上要放到畫面中心的點（畫面比例）。"""
    p = P(i)
    if p['mode'] != 'solo':
        return 1.0, 0.5, 0.5
    nb = p['b1'] - p['b0']
    k = i - p['b0']
    u = (t - G.bar_time(i)) / G.barlen
    half = (1.75, 0.5, 0.36)
    if nb >= 3:
        push_bar = nb - 2
    else:
        push_bar = nb - 1
    if k < push_bar:
        z, fx, fy = 1.0, 0.5, 0.5
    elif k == push_bar:
        e = ease(min(1.0, u / 0.6))                      # 前 60% 小節平順推到半身
        z, fx, fy = 1 + (half[0] - 1) * e, 0.5, 0.5 + (half[2] - 0.5) * e
    else:
        z, fx, fy = half
    # 每隔一位：最後兩拍接眼睛特寫（拍頭硬切，是剪接不是推鏡）；焦點在 char_layer 依此刻的眼睛位置算
    if p['solo'] is not None and p['solo'] % 2 == 1 and k == nb - 1 and nb >= 2 and t >= beat_in_bar(i, 2):
        return EYE_Z, None, None
    return z, fx, fy


SOLO_H, SOLO_FOOT = H * 0.86, H * 0.975


def beat_in_bar(i, k):
    """小節 i 的第 k 拍（0 起）的實際時間：拍格鎖到鼓之後每小節長度略有不同，用「半小節」會差 1 格以上。"""
    t0, t1 = G.bar_time(i), G.bar_time(i + 1)
    bb = G.beats[(G.beats >= t0 - 1e-3) & (G.beats < t1 - 1e-3)]
    return float(bb[k]) if len(bb) > k else t0 + k / G.meter * (t1 - t0)
EYE_Z = 3.6


def char_layer(i, t):
    """這一小節所屬區塊的角色圖層（預乘 RGBA）＋大字。取景（推鏡）直接折進角色的貼圖參數，特寫也清楚。"""
    p = P(i)
    lay = np.zeros((H, W, 4), np.float32)
    z, fx, fy = framing(i, t)
    if fx is None:                                       # 眼睛特寫：跟著此刻（含律動）的眼睛位置
        d = DANCERS[p['who'][0]]
        rgba, mv = d.at(t, G)
        ex, ey = d.eye_xy(rgba, mv, 0.5 * W, SOLO_FOOT, SOLO_H)
        fx, fy = ex / W, ey / H
    cam = lambda x, y: (W / 2 + (x - fx * W) * z, H / 2 + (y - fy * H) * z)   # noqa: E731
    hues = None
    if p['mode'] == 'solo':
        slots = [(0.5, SOLO_FOOT, SOLO_H)]
    elif p['mode'] == 'duo':
        slots = [(0.32, H * 0.97, H * 0.80), (0.68, H * 0.97, H * 0.80)]
    elif p['mode'] == 'five':
        slots = [((k + 0.5) / 5 * 0.9 + 0.05, H * 0.97, H * 0.62) for k in range(5)]
        hues = [k * 72 + (t - G.bar_time(p['b0'])) * 60 for k in range(5)]
    else:
        n = len(p['who'])
        slots = [((k + 0.5) / n * 0.92 + 0.04, H * 0.97, H * (0.66 if n <= 4 else 0.58)) for k in range(n)]
    for k, (who, (sx, foot, hh)) in enumerate(zip(p['who'], slots)):
        rgba, mv = DANCERS[who].at(t, G)                 # 全員都踩同一個拍（不錯開，錯開就不卡點）
        if hues:                                         # 五連排：先縮到要用的大小再轉色相（全尺寸轉色太慢）
            f = hh * z * 1.2 / rgba.shape[0]
            if f < 1:
                rgba = _small(rgba, f)
            rgba = PX.hue_shift(rgba, hues[k])
        x, y = cam(sx * W, foot - mv['dy'] * hh)
        PX.place(lay, rgba, x, y, hh * z, angle=mv['angle'], sx=mv['sx'], sy=mv['sy'], shear=mv['shear'])
    return lay, z


def word_layer(c, i, t, z):
    p = P(i)
    if not p['word']:
        return c
    text, b0 = p['word']
    u = (t - G.bar_time(b0)) / G.barlen
    fonts = ('dela', 'rock', 'dela', 'rampart')
    cols = ((1, 1, 1), (1.0, 0.93, 0.25), (1.0, 0.45, 0.78), (0.45, 0.95, 1.0))
    k = b0 % 4
    zz = 1 + (z - 1) * 0.35                              # 大字在角色後面：推鏡時跟著動一點（視差）
    return PX.big_text(c, text, u, cy=0.45, height=0.46 * zz, font=fonts[k], col=cols[k], stroke=0.05,
                       stroke_col=(0.08, 0.03, 0.16), op=0.88, max_w=0.78)


def compose(i, t):
    """小節 i 的畫面（不含閃白與撕裂）：背景 → 大字 → 角色。"""
    lay, z = char_layer(i, t)
    c = background(i, t)
    if z > 1.001:
        c = PX.camera(c, 1 + (z - 1) * 0.25)              # 背景跟著推一點（視差）
    c = word_layer(c, i, t, z)
    return c, lay


I0 = min(PLAN)


def frame(t):
    i, t0, L, u = G.bar(t)
    i = max(i, I0)                                       # 弱起併進第一小節（背景、計畫都用第一小節的；閃白照實際小節線）
    if t < G.bar_time(I0):
        t0 = G.bar_time(I0) - G.barlen
    c, lay = compose(i, t)
    # 換人：小節線前後各 XFADE 拍，角色圖層滑動＋交叉淡化（背景照小節線換）
    nxt = G.bar(t + XFADE * BEAT)[0]
    prv = G.bar(t - XFADE * BEAT)[0]
    if nxt != i and P(nxt)['change'] and P(nxt)['block'] != P(i)['block']:
        T = G.bar_time(nxt)
        e = (t - (T - XFADE * BEAT)) / (2 * XFADE * BEAT)
        lay = _slide(lay, char_layer(nxt, t)[0], e)
    elif prv != i and P(i)['change']:
        T = G.bar_time(i)
        e = (t - (T - XFADE * BEAT)) / (2 * XFADE * BEAT)
        lay = _slide(char_layer(prv, t)[0], lay, e)
    c = PX.over_layer(c, lay)
    p = P(i)
    # 副歌：整個畫面連角色一起慢慢轉色相
    if p['role'] == 'chorus':
        sec = G.section(t)
        c = PX.hue_shift(c, (t - sec['start']) * 22.0)
    # 閃白：只在小節線上
    dt = t - t0
    k = FLASH['change'] if p['change'] else FLASH['chorus'] if p['chorus_head'] else FLASH['bar']
    c = PX.flash(c, k * math.exp(-dt / 0.045))
    # 撕裂＋RGB：換人與副歌小節頭，下一拍前恢復
    if p['change'] or p['chorus_head']:
        kk = (0.35 if p['change'] else 0.2) * max(0.0, 1 - dt / (0.8 * BEAT)) ** 2     # 「輕輕出現」
        c = PX.tear(c, kk, seed=int(round(t * FPS)))
    # 片尾：最後 1 秒收進深色
    if t > TOTAL - 1.0:
        e = ease((t - (TOTAL - 1.0)) / 1.0)
        c = c * (1 - e) + np.float32(END_COL) * e
    return to_u8(c)


_SMALL = {}


def _small(rgba, f):
    key = (id(rgba), round(f, 2))
    v = _SMALL.get(key)
    if v is None or v[0] is not rgba:
        v = (rgba, cv2.resize(rgba, (max(1, int(rgba.shape[1] * f)), max(1, int(rgba.shape[0] * f))), interpolation=cv2.INTER_AREA))
        if len(_SMALL) > 64:
            _SMALL.pop(next(iter(_SMALL)))
        _SMALL[key] = v
    return v[1]


def _slide(a, b, e):
    """角色圖層：a 往左滑出、b 從右滑入，同時交叉淡化。"""
    e = ease(min(1.0, max(0.0, e)))
    off = W * 0.22
    A = cv2.warpAffine(a, np.float32([[1, 0, -off * e], [0, 1, 0]]), (W, H), borderMode=cv2.BORDER_CONSTANT, borderValue=0)
    B = cv2.warpAffine(b, np.float32([[1, 0, off * (1 - e)], [0, 1, 0]]), (W, H), borderMode=cv2.BORDER_CONSTANT, borderValue=0)
    return A * (1 - e) + B * e


# ═════════ 給 flow.py／frames.py sheet ═════════
# 每小節換背景＝每小節一刀（換人只是其中幾刀）；flow.py 的平均鏡頭長、節奏 vs 音樂才算得對
def _shots():
    out = []
    for i in sorted(PLAN):
        a, b = (0.0 if i == I0 else G.bar_time(i)), min(TOTAL, G.bar_time(i + 1))
        p = PLAN[i]
        cuts = [a]
        if p['mode'] == 'solo' and framing(i, G.bar_time(i) + 0.75 * G.barlen)[1] is None:
            cuts.append(beat_in_bar(i, 2))               # 眼睛特寫在第三拍硬切
        cuts.append(b)
        for x, y in zip(cuts, cuts[1:]):
            if y > x:
                out.append((x, y, p['mode'], dict(change=p['change'] and x == a, bg=p['bg'])))
    return out


SHOTS = _shots()


def _marks():
    m = []
    for s in G.sections:
        m.append((s['start'] + 0.25 * BEAT, f'{s["name"]} 開頭'))
    for b0, b1, mode, who, sn in BLOCKS:
        T = G.bar_time(b0)
        if 0 < T < TOTAL:
            m.append((T + XFADE * BEAT + 0.07, f'換人後 {mode}'))     # 轉場與閃白都結束的第一個清楚畫面
            if b0 in (BLOCKS[1][0], BLOCKS[len(BLOCKS) // 2][0]):
                m.append((T, '轉場正中'))
        if mode == 'solo' and b1 - b0 >= 3:
            m.append((G.bar_time(b1 - 1) + 0.25 * BEAT, '半身'))
            if sn is not None and sn % 2 == 1:
                m.append((G.bar_time(b1 - 1) + 0.75 * G.barlen, '眼睛特寫'))
        if mode == 'five':
            m.append((T + 0.5 * G.barlen, '五連排變色'))
    for i, p in PLAN.items():
        if p['kaleido'] and 0 < G.bar_time(i) < TOTAL:
            m.append((G.bar_time(i) + 0.5 * G.barlen, '萬花筒'))
    m.append((TOTAL - 0.5, '片尾'))
    m = sorted({round(min(max(t, 0.0), TOTAL - 0.05), 2): lab for t, lab in m}.items())
    if len(m) > 48:                                      # 總覽最多 48 格：均勻抽
        m = [m[int(round(k * (len(m) - 1) / 47))] for k in range(48)]
    return m


MARKS = _marks()
