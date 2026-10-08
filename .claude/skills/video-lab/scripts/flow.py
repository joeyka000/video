#!/usr/bin/env python3
"""剪接流暢度：鏡頭跟鏡頭怎麼接、每個鏡頭夠不夠看、入點好不好、整支片的節奏跟音樂走不走在一起。

縮圖總覽（review.py）看的是「一格好不好看」；這支看的是「兩格之間」：視線跳多遠、運動方向有沒有反、
明暗與色溫有沒有跳、是不是同景別同位置的跳接、入點是不是糊的、慢放有沒有重複格、實拍有沒有被縮小或蓋掉。

  python flow.py check out/final.mp4 -o out/flow                    # 成片或 10 秒試渲（自動偵測剪點）
  python flow.py check out/montage.mp4 --cuts out/montage.cuts.json  # 用剪點表的剪點（cutlist.py／render.py --dump-cuts／秒數清單）
  python flow.py check --engine work/engine.py -o qa/flow            # 正式渲染前：剪點取自 engine 的 SHOTS，只渲剪點前後各 7 格
  python flow.py pick media/a.mp4 --from 3 --to 14 --dur 2.4 --clean bottom -o qa/pick_a   # 幫一個鏡頭挑入點

check 產出（-o 目錄）：
  report.md          優先看的剪點（含改法）、鏡頭問題、節奏總覽、全部剪點表與鏡頭表
  cuts.jpg           要評分的剪點：左 A 末格｜右 B 首格；紅點＝A 的視線點、青點＝B 的視線點（B 上的空心紅圈是 A 的位置）、
                     黃箭頭＝畫面整體流向；格頭是剪點編號、秒數與標記
  cuts.review.json   剪點評分表（同 review.py 的格式）：依 references/review.md〈剪點評分〉逐刀打分，再 `review.py gate`
  flow.json          全部數字（給程式讀）
  pace.png           節奏圖：灰色＝音樂響度、線＝每秒剪幾刀（4 秒平滑）、直線＝剪點（紅＝優先看）

pick 產出：pick.jpg（每個候選入點的首格、中格、末格）＋終端機排名表；分數組成見 --help

量法與限制（細節與每個門檻的理由在 references/story.md〈八、量化門檻〉）：
  - 剪點偵測：HSV 直方圖距離＋畫素差，高於絕對門檻且高於前 0.5 秒中位數；溶接、慢擦、甩鏡會漏或多抓，
    有剪點表就用 --cuts。全白／全黑格（閃白、吸氣）與 1–2 格的過場格不算鏡頭，剪點拼圖取它們前後的實際畫面
  - 視線點：有人臉取最大的臉；沒有人臉取顯著度（spectral residual）＋局部運動＋輕微中心偏好的高點重心
  - 方向：鏡頭最後／最前 6 格的光流中位數，量的是「畫面整體往哪流」（鏡頭運動為主），主體方向看拼圖判斷
  - 景別：最大人臉高 ÷ 畫面短邊；沒有人臉記「無人臉」
  - 銳利度：畫面切成 8×14 區塊，取區塊拉普拉斯平均的中位數（字卡只佔幾格，不干擾）
  - 實拍覆蓋：整個畫面（黑邊也算）有紋理的區塊比例；< 50% 的時間逐格累計，全片 > 15% 在總覽警告
  - 色溫：只比兩邊「近中性色」像素的偏色（白平衡與調色），不比內容本身的顏色
  - 數字是提示，不是判決：每個標記都要看拼圖確認，刻意的（段落開頭的視線跳、衝擊用的明暗跳）在評分表寫理由
"""
import argparse
import json
import math
import os
import subprocess
import sys
from fractions import Fraction

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
FONT = '/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc'
YUNET = os.path.expanduser('~/video-lab/models/yunet.onnx')

# 門檻（理由見 references/story.md〈八、量化門檻〉；改數字時兩邊一起改）
TH = dict(
    cut=0.30,          # 剪點分數：0.55×直方圖距離 + 0.45×畫素差（40/255 封頂）
    cut_rise=0.15,     # 而且要比前 0.5 秒的中位數高這麼多
    min_frames=6,      # 最短可讀鏡頭（editing.md〈3. 剪輯密度表〉）
    eye_ok=0.15,       # 視線跳（佔對角線）≤ 0.15：眼睛不用移
    eye_jump=0.33,     # > 0.33：觀眾要重新找主體
    move=0.006,        # 每格位移 ≥ 畫面寬 0.6%（1080 寬約 200 px/秒，真的在搖或在走）才算有方向
    consistent=0.7,    # 而且 6 格的方向要一致（合向量長 ÷ 各格長度平均 ≥ 0.7），手持晃動不算
    reverse=120,       # 兩邊方向夾角 > 120° 算相反
    same_dir=45,       # < 45° 算延續
    dY=60,             # 亮度跳（0–255）
    dC=10,             # 色溫跳：兩邊「近中性色」像素的 Lab a／b 平均差（看調色與白平衡，不看內容本身的顏色）
    neutral=0.04,      # 近中性色像素少於 4% 的畫面不比（整片都是彩色內容時量不準）
    jump_corr=0.78,    # 剪點前後構圖相關係數 > 0.78：跳接感
    same_shot=0.90,    # 自動偵測時 ≥ 0.90（中間有過場格時 ≥ 0.78）：其實是同一個鏡頭被特效（閃光、漏光）切開，併回去
    blur_in=0.70,      # 入點前兩格銳利度 ÷ 第 4–8 格的中位數 < 0.70，而且要 ≥ 3 格才清楚：入點糊（區塊中位數，字卡進場不干擾）
    blur_long=5,       # 糊 ≥ 5 格（超過甩鏡 4 格的上限，craft.md）算嚴重
    repeat=0.30,       # 有動作的鏡頭裡，幾乎沒變的格 > 30%：重複格（慢放或低格率）
    cover=0.50,        # 有紋理的區塊 < 50%：實拍被縮小、蓋掉或換成圖卡（峇里島 60 秒 v1 被退的 3D 舞台）
    cover_time=0.15,   # 全片這種畫面 > 15% 的時間就在總覽警告
    read_busy=0.8,     # 無人臉、複雜度在全片前 25% 的鏡頭至少 0.8 秒
    read_face=0.3,     # 有臉的鏡頭至少 0.3 秒
)
SCALES = [(0.70, '大特寫'), (0.40, '特寫'), (0.20, '近景'), (0.09, '中景'), (0.035, '全景'), (0.0, '遠景')]
SCALE_ORDER = {n: i for i, (_, n) in enumerate(SCALES)}


# ───────────────────────── 讀檔 ─────────────────────────
def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode:
        sys.exit(f"失敗：{' '.join(cmd)}\n{r.stderr.strip()[-800:]}")
    return r.stdout


def probe(path):
    d = json.loads(run(['ffprobe', '-v', 'error', '-show_entries',
                        'stream=codec_type,width,height,r_frame_rate,avg_frame_rate:format=duration', '-of', 'json', path]))
    vs = [s for s in d['streams'] if s['codec_type'] == 'video']
    if not vs:
        sys.exit(f'{path} 沒有視訊軌')
    v = vs[0]
    fr = v.get('avg_frame_rate') if v.get('avg_frame_rate') not in (None, '0/0') else v['r_frame_rate']
    return dict(w=int(v['width']), h=int(v['height']), fps=float(Fraction(fr)), fr=fr,
                dur=float(d['format'].get('duration') or 0), audio=any(s['codec_type'] == 'audio' for s in d['streams']))


def sizes(w, h, long_side):
    k = long_side / max(w, h)
    return max(2, int(round(w * k / 2)) * 2), max(2, int(round(h * k / 2)) * 2)


def decode(path, fr, w, h, t0=None, dur=None):
    """逐格讀成 RGB（先 fps 濾鏡統一成固定格率，格序 i 對應時間 t0 + i/fps）。"""
    cmd = ['ffmpeg', '-v', 'error']
    if t0:
        cmd += ['-ss', f'{t0:.3f}']
    cmd += ['-i', path]
    if dur:
        cmd += ['-t', f'{dur:.3f}']
    cmd += ['-vf', f'fps={fr},scale={w}:{h}:flags=area', '-an', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-']
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE)
    n = w * h * 3
    while True:
        b = p.stdout.read(n)
        if len(b) < n:
            break
        yield np.frombuffer(b, np.uint8).reshape(h, w, 3)
    p.stdout.close()
    p.wait()


def audio_rms(path, step=0.25):
    """音樂能量：響度（dBFS 換 0..1）與頻譜通量（打擊與變化的密度）各半，每 step 秒一個值。沒有音軌回 None。"""
    r = subprocess.run(['ffmpeg', '-v', 'error', '-i', path, '-vn', '-ac', '1', '-ar', '8000', '-f', 's16le', '-'],
                       capture_output=True)
    if r.returncode or not r.stdout:
        return None
    x = np.frombuffer(r.stdout, np.int16).astype(np.float32) / 32768
    n = int(8000 * step)
    m = len(x) // n
    if m < 4:
        return None
    rms = np.sqrt((x[:m * n].reshape(m, n) ** 2).mean(1) + 1e-12)
    loud = np.clip((20 * np.log10(rms) + 50) / 50, 0, 1)
    hop, win = 256, 512
    k = (len(x) - win) // hop
    fr = np.lib.stride_tricks.as_strided(x, (k, win), (x.strides[0] * hop, x.strides[0])) * np.hanning(win)
    mag = np.log1p(np.abs(np.fft.rfft(fr, axis=1)) * 10)
    flux = np.maximum(np.diff(mag, axis=0), 0).sum(1)
    per = n // hop
    fl = np.array([flux[i * per:(i + 1) * per].mean() if (i + 1) * per <= len(flux) else 0 for i in range(m)])
    fl = fl / (np.percentile(fl, 95) + 1e-9)
    return 0.5 * loud + 0.5 * np.clip(fl, 0, 1)


# ───────────────────────── 每格特徵 ─────────────────────────
def bars_mask(g):
    """上下（或左右）全黑的 letterbox 列／欄：True = 畫面有效區。"""
    rows = (g.mean(1) > 18) | (g.std(1) > 4)
    cols = (g.mean(0) > 18) | (g.std(0) > 4)
    return rows[:, None] & cols[None, :]


def cells(m, r, c):
    """把 2D 圖切成 r×c 個區塊取平均。"""
    H, W = m.shape
    return m[:H // r * r, :W // c * c].reshape(r, H // r, c, W // c).mean((1, 3))


def dhash(g):
    s = cv2.resize(g, (9, 8), interpolation=cv2.INTER_AREA).astype(np.int16)
    bits = (s[:, 1:] > s[:, :-1]).flatten()
    return int(''.join('1' if b else '0' for b in bits), 2)


class Feat:
    """一格的特徵；prev 是上一格的 Feat（剪點分數與光流要用）。"""

    def __init__(self, rgb, prev=None):
        g = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
        lab = cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB).astype(np.float32)
        valid = bars_mask(g)
        self.g = g
        self.Y = float(g[valid].mean()) if valid.any() else float(g.mean())
        self.A = float(lab[..., 1][valid].mean() - 128) if valid.any() else 0.0
        self.B = float(lab[..., 2][valid].mean() - 128) if valid.any() else 0.0
        self.std = float(g.std())
        r, c = (14, 8) if g.shape[0] > g.shape[1] else (8, 14)
        ok = cells(valid.astype(np.float32), r, c) > 0.5
        hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
        self.hist = cv2.calcHist([hsv], [0, 1, 2], None, [12, 4, 4], [0, 180, 0, 256, 0, 256])
        cv2.normalize(self.hist, self.hist, 1, 0, cv2.NORM_L1)
        # 銳利度：每個區塊的拉普拉斯平均，取中位數（字卡只佔幾格，不會把整格拉高）
        lap = cells(np.abs(cv2.Laplacian(g, cv2.CV_32F)), r, c)
        self.sharp = float(np.median(lap[ok])) if ok.any() else 0.0
        self.edge = float((cv2.Canny(g, 80, 160) > 0).mean())
        # 實拍覆蓋率：整個畫面有紋理的區塊佔多少（深色舞台上一張小卡、整片圖卡、直式畫面塞橫式素材時都會很低；
        # 黑邊也算在分母裡，觀眾看到的就是那麼小）
        gb = cv2.GaussianBlur(g, (5, 5), 0).astype(np.float32)
        m1 = cv2.blur(gb, (7, 7))
        sd = np.sqrt(np.maximum(cv2.blur(gb * gb, (7, 7)) - m1 * m1, 0))
        self.cover = float((cells(sd, r, c) > 3.0).mean())
        self.hash = dhash(g)
        if prev is None:
            self.score, self.dpix, self.flow = 0.0, 0.0, (0.0, 0.0)
        else:
            dh = cv2.compareHist(prev.hist, self.hist, cv2.HISTCMP_BHATTACHARYYA)
            self.dpix = float(cv2.absdiff(g, prev.g).mean())
            self.score = 0.55 * dh + 0.45 * min(self.dpix / 40, 1)
            fl = cv2.calcOpticalFlowFarneback(prev.g, g, None, 0.5, 2, 11, 2, 5, 1.1, 0)
            w = g.shape[1]
            self.flow = (float(np.median(fl[..., 0])) / w, float(np.median(fl[..., 1])) / w)

    @property
    def uniform(self):
        """閃白、黑場、純色過場格。"""
        return self.std < 7 and (self.Y > 222 or self.Y < 26)


# ───────────────────────── 視線點與景別 ─────────────────────────
_det = None


def faces(rgb):
    global _det
    if not os.path.exists(YUNET):
        return []
    h, w = rgb.shape[:2]
    if _det is None:
        _det = cv2.FaceDetectorYN.create(YUNET, '', (w, h), 0.72)
    _det.setInputSize((w, h))
    _, f = _det.detect(cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR))
    if f is None:
        return []
    return [((x + fw / 2) / w, (y + fh / 2) / h, fw / w, fh / h) for x, y, fw, fh in f[:, :4]]


def scale_of(fs, w, h):
    if not fs:
        return '無人臉', 0.0
    s = max(f[3] * h for f in fs) / min(w, h)
    return next(n for t, n in SCALES if s >= t), float(s)


def saliency(rgb, prev=None):
    """spectral residual 顯著度 ＋ 扣掉鏡頭運動後的局部運動 ＋ 輕微中心偏好；回傳正規化的圖。"""
    h, w = rgb.shape[:2]
    sw, sh = sizes(w, h, 96)
    g = cv2.resize(cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY), (sw, sh), interpolation=cv2.INTER_AREA).astype(np.float32)
    F = np.fft.fft2(g)
    la = np.log(np.abs(F) + 1e-6)
    sr = la - cv2.blur(la, (3, 3))
    sal = np.abs(np.fft.ifft2(np.exp(sr + 1j * np.angle(F)))) ** 2
    sal = cv2.GaussianBlur(sal, (0, 0), 2.5)
    sal = (sal - sal.min()) / (np.ptp(sal) + 1e-9)
    m = sal
    if prev is not None:
        gp = cv2.resize(cv2.cvtColor(prev, cv2.COLOR_RGB2GRAY), (sw, sh), interpolation=cv2.INTER_AREA)
        fl = cv2.calcOpticalFlowFarneback(gp, g.astype(np.uint8), None, 0.5, 2, 9, 2, 5, 1.1, 0)
        loc = np.hypot(fl[..., 0] - np.median(fl[..., 0]), fl[..., 1] - np.median(fl[..., 1]))
        if loc.max() > 0.6:  # 有東西在動才算
            loc = cv2.GaussianBlur(loc, (0, 0), 2)
            m = 0.55 * sal + 0.45 * loc / (loc.max() + 1e-9)
    yy, xx = np.mgrid[0:sh, 0:sw]
    prior = np.exp(-(((xx / sw - 0.5) / 0.38) ** 2 + ((yy / sh - 0.5) / 0.38) ** 2) / 2)
    m = m * (0.55 + 0.45 * prior)
    m[~bars_mask(g.astype(np.uint8))] = 0
    return m


def eye_point(rgb, prev=None):
    """(x, y) 正規化座標、來源（'臉'／'顯著'）、景別、臉高比。"""
    h, w = rgb.shape[:2]
    fs = faces(rgb)
    sc, sv = scale_of(fs, w, h)
    if fs:
        x, y, fw, fh = max(fs, key=lambda f: f[2] * f[3])
        return (float(x), float(y)), '臉', sc, sv
    m = saliency(rgb, prev)
    thr = np.percentile(m, 96)
    ys, xs = np.nonzero(m >= thr)
    wt = m[ys, xs]
    return (float((xs * wt).sum() / wt.sum() / m.shape[1]), float((ys * wt).sum() / wt.sum() / m.shape[0])), '顯著', sc, sv


def eye_dist(a, b, w, h):
    diag = math.hypot(w, h)
    return math.hypot((a[0] - b[0]) * w, (a[1] - b[1]) * h) / diag


def mean_flow(feats):
    """6 格光流的方向與量；方向不一致（手持晃動）時量記 0。"""
    if not feats:
        return (0.0, 0.0), 0.0
    v = np.array([f.flow for f in feats])
    mx, my = float(v[:, 0].mean()), float(v[:, 1].mean())
    m = math.hypot(mx, my)
    each = float(np.hypot(v[:, 0], v[:, 1]).mean())
    if each == 0 or m / each < TH['consistent']:
        return (mx, my), 0.0
    return (mx, my), m


def angle_between(a, b):
    na, nb = math.hypot(*a), math.hypot(*b)
    if na == 0 or nb == 0:
        return None
    c = max(-1, min(1, (a[0] * b[0] + a[1] * b[1]) / (na * nb)))
    return math.degrees(math.acos(c))


def neutral_cast(rgb):
    """近中性色（低彩度、不太暗不太亮）像素的 Lab a／b 平均；太少時回 None。"""
    lab = cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB).astype(np.float32)
    L, A, B = lab[..., 0], lab[..., 1] - 128, lab[..., 2] - 128
    m = (np.hypot(A, B) < 14) & (L > 50) & (L < 230)
    if m.mean() < TH['neutral']:
        return None
    return float(A[m].mean()), float(B[m].mean())


def corr_small(a, b):
    sa = cv2.resize(cv2.cvtColor(a, cv2.COLOR_RGB2GRAY), (24, 24), interpolation=cv2.INTER_AREA).astype(np.float32).ravel()
    sb = cv2.resize(cv2.cvtColor(b, cv2.COLOR_RGB2GRAY), (24, 24), interpolation=cv2.INTER_AREA).astype(np.float32).ravel()
    if sa.std() < 1 or sb.std() < 1:
        return 0.0
    return float(np.corrcoef(sa, sb)[0, 1])


# ───────────────────────── 剪點與鏡頭 ─────────────────────────
DIRS = ['→', '↘', '↓', '↙', '←', '↖', '↑', '↗']


def arrow(v, mag):
    if mag < TH['move']:
        return '·'
    a = math.degrees(math.atan2(v[1], v[0])) % 360
    return DIRS[int((a + 22.5) // 45) % 8]


def judge_cut(c, fps):
    """依門檻給標記、嚴重度與改法。c 已含量測值。"""
    flags, fixes, sev = [], [], 0
    trans = c['trans']
    if c['eye'] > TH['eye_jump']:
        flags.append(f"視線跳 {c['eye']:.2f}")
        fixes.append('把 B 的主體移到 A 的視線點附近（cover／zoom 的中心、或換入點）；要刻意跳就放在段落第一拍')
        sev += 2
    if c['dir'] == '相反':
        flags.append('方向相反' + ('（甩鏡兩邊要同向）' if trans != '硬切' else ''))
        fixes.append('換同方向的 take、B 沒有字時水平翻轉，或中間插一個正面／靜止鏡頭')
        sev += 2 if trans != '硬切' else 1
    if abs(c['dY']) > TH['dY'] and trans == '硬切':
        flags.append(f"明暗跳 {c['dY']:+.0f}")
        fixes.append('footage.py match 把 B 對到 A，或把這刀移到段落邊界讓明暗變化有理由')
        sev += 1
    if c['dC'] is not None and c['dC'] > TH['dC']:
        flags.append(f"色溫跳 {c['dC']:.0f}")
        fixes.append('中性色的偏色不一樣（白平衡或調色沒統一）：footage.py match，或全片套同一個調色再比')
        sev += 2
    if c['corr'] >= TH['same_shot']:
        c['flags'], c['fixes'], c['sev'], c['good'] = [], [], 0, ['同一畫面（只換字或特效，不是剪點）']
        return c
    if c['corr'] > TH['jump_corr']:
        flags.append(f"跳接感 {c['corr']:.2f}")
        fixes.append('構圖幾乎一樣：換景別（至少差兩級）或角度 > 30°；要跳接就連跳 3 刀以上讓它變成風格')
        sev += 2
    elif c['scaleA'] == c['scaleB'] and c['scaleA'] != '無人臉' and c['eye'] < 0.08:
        flags.append('同景別同位置')
        fixes.append('同一個人同景別同位置：換景別或換角度（30° 規則）')
        sev += 1
    if c.get('blurB'):
        k = c['blurB']
        flags.append(f'B 入點糊 {k} 格')
        fixes.append(f'入點往後 {k} 格（+{k / fps:.2f} 秒）從清楚的那一格開始；甩鏡進場的糊不要超過 4 格')
        sev += 2 if k >= TH['blur_long'] else 1
    good = []
    if c['eye'] <= TH['eye_ok']:
        good.append('視線順')
    if c['dir'] == '延續':
        good.append('動作延續')
    c['flags'], c['fixes'], c['sev'], c['good'] = flags, fixes, sev, good
    return c


def build_cut(i, t, trans, a_prev, a_last, b_first, b_next, featsA, featsB, fps, cont=False):
    w, h = a_last.shape[1], a_last.shape[0]
    pa, srcA, scA, svA = eye_point(a_last, a_prev)  # A 的局部運動用最後兩格算
    pb, srcB, scB, svB = eye_point(b_first)
    if b_next is not None and srcB == '顯著':  # B 沒有臉時，局部運動用前兩格算
        pb = eye_point(b_next, b_first)[0]
    va, ma = mean_flow(featsA[-6:])
    vb, mb = mean_flow(featsB[1:7])
    ang = angle_between(va, vb) if ma >= TH['move'] and mb >= TH['move'] else None
    d = '—' if ang is None else ('相反' if ang > TH['reverse'] else '延續' if ang < TH['same_dir'] else '轉向')
    if ang is None and (ma >= TH['move']) != (mb >= TH['move']):
        d = '動接靜' if ma >= TH['move'] else '靜接動'
    fa, fb = Feat(a_last), Feat(b_first)
    na, nb = neutral_cast(a_last), neutral_cast(b_first)
    c = dict(i=i, t=round(t, 3), trans=trans, eye=round(eye_dist(pa, pb, w, h), 3), eyeA=pa, eyeB=pb, srcA=srcA, srcB=srcB,
             scaleA=scA, scaleB=scB, flowA=(va, ma), flowB=(vb, mb), dir=d, angle=None if ang is None else round(ang),
             dY=round(fb.Y - fa.Y, 1), dC=None if na is None or nb is None else round(math.hypot(nb[0] - na[0], nb[1] - na[1]), 1),
             corr=round(corr_small(a_last, b_first), 3))
    sh = [f.sharp for f in featsB[:12]]
    if len(sh) >= 9:
        ref = float(np.median(sh[4:9])) or 1.0
        head = float(np.mean(sh[:2]))
        k = next((j for j, s in enumerate(sh) if s >= 0.8 * ref), len(sh))
        if head / ref < TH['blur_in'] and k >= 3:
            c['blurB'] = k
        c['sharpB'] = round(head / ref, 2)
    if cont:  # 剪點表上有、畫面上其實連續（同一段素材換速度、只換字卡）
        c['flags'], c['fixes'], c['sev'], c['good'] = [], [], 0, ['畫面連續（換速度或字卡，不是剪點）']
        return c
    return judge_cut(c, fps)


def shot_flags(s, busy_edge, fps):
    flags, fixes = [], []
    if s['frames'] < TH['min_frames']:
        flags.append(f"太短 {s['frames']} 格")
        fixes.append('至少 6 格；要閃就改成刻意的三連 stutter（editing.md 配方 6）')
    elif s['scale'] == '無人臉' and s['edge'] >= busy_edge and s['dur'] < TH['read_busy']:
        flags.append(f"資訊多只給 {s['dur']:.2f} 秒")
        fixes.append('遠景或細節多的畫面延長到 0.8 秒以上，或換成近景')
    elif s['scale'] != '無人臉' and s['dur'] < TH['read_face']:
        flags.append(f"人臉只給 {s['dur']:.2f} 秒")
        fixes.append('有臉的鏡頭至少 0.3 秒，觀眾才認得出表情')
    if s.get('repeat') is not None and s['repeat'] > TH['repeat']:
        flags.append(f"重複格 {s['repeat']:.0%}")
        fixes.append('慢放或低格率造成：換本身清楚的素材、footage.py slowmo 補格；不要 < 0.7 倍硬放')
    if s['cover'] < TH['cover']:
        flags.append(f"實拍只佔 {s['cover']:.0%}")
        fixes.append('實拍被縮小、蓋掉或換成圖卡：關掉特效還看得到主體嗎（masters.md〈零〉第 1 條）；片頭片尾字卡可以例外')
    s['flags'], s['fixes'] = flags, fixes
    return s


# ───────────────────────── check：成片 ─────────────────────────
def segment(feats, fps, given=None):
    """回傳鏡頭清單 [(起格, 迄格)] 與每刀的轉場說明；閃白黑場格與 1–2 格的過場格不算鏡頭。"""
    n = len(feats)
    sc = np.array([f.score for f in feats])
    win = max(3, int(fps * 0.5))
    if given is not None:
        bounds = sorted({b for b in given if 0 < b < n})
    else:
        bounds = []
        for i in range(1, n):
            local = np.median(sc[max(0, i - win):i]) if i > 1 else 0
            if sc[i] > TH['cut'] and sc[i] > local + TH['cut_rise']:
                bounds.append(i)
    uni = [f.uniform for f in feats]
    for i in range(1, n):
        if uni[i] != uni[i - 1]:
            bounds.append(i)
    bounds = sorted(set(bounds))
    segs, prev = [], 0
    for b in bounds + [n]:
        if b > prev:
            segs.append([prev, b])
        prev = b
    shots, trans, pending = [], [], []
    for a, b in segs:
        is_uni = all(uni[a:b])
        if is_uni or (b - a <= 2 and given is None):
            pending.append((a, b, is_uni))
            continue
        if shots:
            if pending:
                k = sum(e - s for s, e, _ in pending)
                kinds = {('白' if feats[s].Y > 128 else '黑') if u else '過場' for s, e, u in pending}
                trans.append(f"{'／'.join(sorted(kinds))} {k} 格")
            else:
                trans.append('硬切')
        shots.append([a, b])
        pending = []
    if shots and pending:  # 片尾的黑場併進最後一個鏡頭
        shots[-1][1] = pending[-1][1]
    return shots, trans


def load_given_cuts(path, fps):
    d = json.load(open(path))
    if isinstance(d, list):
        return [int(round(float(t) * fps)) for t in d]
    off = float(d.get('offset', 0))
    if d.get('rows') and d.get('fps'):
        k = fps / float(d['fps'])
        return [int(round(r['f'] * k)) for r in d['rows'] if r.get('f')]
    return [int(round((float(t) - off) * fps)) for t in d.get('cuts', [])]


def check_video(a):
    P = probe(a.video)
    fps = P['fps']
    pw, ph = sizes(P['w'], P['h'], a.pair)
    aw, ah = sizes(P['w'], P['h'], 256)
    feats, keep, ring = [], {}, []
    every = max(1, int(round(fps * 0.5)))
    want, prev = -1, None
    print(f'讀 {a.video}（{P["w"]}×{P["h"]}，{fps:.3f} fps，{P["dur"]:.1f} 秒）…', file=sys.stderr)
    for i, rgb in enumerate(decode(a.video, P['fr'], pw, ph)):
        f = Feat(cv2.resize(rgb, (aw, ah), interpolation=cv2.INTER_AREA), prev)
        if prev is not None:
            prev.g = prev.hist = None  # 只有下一格要用；放掉省記憶體
        feats.append(f)
        ring = (ring + [(i, rgb)])[-3:]
        # 可能是剪點：留下前兩格、這格、下一格的大圖（之後才決定哪些是真的剪點）；另外每 0.5 秒留一張給景別用
        if f.score > TH['cut'] * 0.8 or (prev is not None and f.uniform != prev.uniform):
            keep.update(dict(ring))
            want = i + 1
        elif i == want or i % every == 0:
            keep[i] = rgb
        prev = f
    n = len(feats)
    if n < 2:
        sys.exit('影片太短')
    lead = next((i for i, f in enumerate(feats) if not f.uniform), n)
    low_s = sum(1 for f in feats if f.cover < TH['cover']) / fps  # 逐格算（同一個鏡頭裡卡片飛進來、字卡蓋上去都算得到）
    given = load_given_cuts(a.cuts, fps) if a.cuts else None
    if given:
        # 剪點表給的格，前後的大圖可能沒留：補讀
        need = sorted({j for b in given for j in (b - 2, b - 1, b, b + 1) if 0 <= j < n} - set(keep))
        if need:
            for i, rgb in enumerate(decode(a.video, P['fr'], pw, ph)):
                if i in need:
                    keep[i] = rgb
                if i > need[-1]:
                    break
    shots, trans = segment(feats, fps, given)
    # 中間格（景別）也要大圖：取最近留下的格
    kept = np.array(sorted(keep))

    def near(j):
        return keep[int(kept[np.argmin(np.abs(kept - j))])]

    if given is None:  # 前後幾乎一樣的「剪點」是特效（閃光、漏光）切開同一個鏡頭：併回去
        k = 0
        while k < len(shots) - 1:
            cc = corr_small(near(shots[k][1] - 1), near(shots[k + 1][0]))
            if cc >= TH['same_shot'] or (trans[k] != '硬切' and cc >= TH['jump_corr']):
                shots[k][1] = shots[k + 1][1]
                del shots[k + 1], trans[k]
            else:
                k += 1

    S = []
    for k, (s0, s1) in enumerate(shots):
        fs = feats[s0:s1]
        mid = near((s0 + s1) // 2)
        sc, sv = scale_of(faces(mid), mid.shape[1], mid.shape[0])
        d = np.array([f.dpix for f in fs[1:]])
        rep = None
        if len(d) >= 8 and np.median(d) > 1.5:
            rep = float((d < 0.2 * np.median(d)).mean())
        v, m = mean_flow(fs[1:])
        S.append(dict(i=k + 1, t0=round(s0 / fps, 3), t1=round(s1 / fps, 3), frames=s1 - s0, dur=round((s1 - s0) / fps, 3),
                      scale=sc, face=round(sv, 3), edge=float(np.mean([f.edge for f in fs])), cover=float(np.mean([f.cover for f in fs])),
                      motion=round(m, 4), dirn=arrow(v, m), repeat=rep, hash=fs[len(fs) // 2].hash, thumb=mid, Y=float(np.mean([f.Y for f in fs]))))
    busy = float(np.percentile([s['edge'] for s in S], 75)) if S else 1
    for s in S:
        shot_flags(s, busy, fps)
    C = []
    for k in range(len(shots) - 1):
        a_end, b_start = shots[k][1], shots[k + 1][0]
        cont = False
        if given is not None and trans[k] == '硬切':  # 剪點表給的剪點：交界的變化跟前後幾格差不多就是連續畫面
            win = [feats[j].score for j in range(max(1, b_start - 6), min(n, b_start + 7)) if j != b_start]
            cont = bool(win) and feats[b_start].score < max(TH['cut'], 1.5 * float(np.median(win)) + 0.05)
        C.append(build_cut(k + 1, b_start / fps, trans[k], near(a_end - 2), near(a_end - 1), near(b_start), near(b_start + 1) if b_start + 1 < n else None,
                           feats[shots[k][0]:a_end], feats[b_start:shots[k + 1][1]], fps, cont))
    rms = audio_rms(a.video) if P['audio'] else None
    finish(a, dict(source=os.path.abspath(a.video), mode='video', w=P['w'], h=P['h'], fps=fps, dur=n / fps, lead=lead, low_cover=low_s), S, C, rms,
           {c['i']: (near(shots[c['i'] - 1][1] - 1), near(shots[c['i']][0])) for c in C})


# ───────────────────────── check：engine（正式渲染前） ─────────────────────────
def check_engine(a):
    sys.path.insert(0, HERE)
    import frames as FR
    m = FR.load(a.engine)
    if not getattr(m, 'SHOTS', None):
        sys.exit(f'{a.engine} 沒有 SHOTS（[(起, 迄, 種類, 參數), ...]）：改用成片或 10 秒試渲檢查')
    fps = float(m.FPS)
    pw, ph = sizes(m.W, m.H, a.pair)
    aw, ah = sizes(m.W, m.H, 256)

    def render(t):
        im = m.frame(min(max(t, 0), m.TOTAL - 1e-3))
        return cv2.resize(np.ascontiguousarray(im[..., :3]), (pw, ph), interpolation=cv2.INTER_AREA)

    shots = sorted([(float(s[0]), float(s[1])) for s in m.SHOTS])
    # 剪點落在拍子上（2.14 秒）不一定剛好是整格：frames.py 第 i 格在 t = i/fps，B 的第一格是 t ≥ s0 的那一格（無條件進位），
    # 用四捨五入會把 A 的最後一格當成 B 的第一格，整刀被誤判成「畫面連續」
    cuts = sorted({math.ceil(s0 * fps - 1e-6) for s0, _ in shots if s0 > 1e-6})
    print(f'{a.engine}：{len(shots)} 個鏡頭、{len(cuts)} 個剪點，每刀渲 14 格…', file=sys.stderr)
    S, C, pairs = [], [], {}
    win = {}
    for fc in cuts:
        ims = [render((fc + k) / fps) for k in range(-7, 7)]
        fs, prev = [], None
        for im in ims:
            f = Feat(cv2.resize(im, (aw, ah), interpolation=cv2.INTER_AREA), prev)
            fs.append(f)
            prev = f
        win[fc] = (ims, fs)
    for k, (t0, t1) in enumerate(shots):
        mid = render((t0 + t1) / 2)
        sc, sv = scale_of(faces(mid), mid.shape[1], mid.shape[0])
        f = Feat(cv2.resize(mid, (aw, ah), interpolation=cv2.INTER_AREA))
        S.append(dict(i=k + 1, t0=round(t0, 3), t1=round(t1, 3), frames=int(round((t1 - t0) * fps)), dur=round(t1 - t0, 3), scale=sc,
                      face=round(sv, 3), edge=f.edge, cover=f.cover, motion=None, dirn='', repeat=None, hash=f.hash, thumb=mid, Y=f.Y))
    busy = float(np.percentile([s['edge'] for s in S], 75)) if S else 1
    for s in S:
        shot_flags(s, busy, fps)
    for k, fc in enumerate(cuts):
        ims, fs = win[fc]
        trans = '硬切'
        others = [fs[j].score for j in range(1, 14) if j != 7]
        cont = fs[7].score < max(TH['cut'], 1.5 * float(np.median(others)) + 0.05)
        c = build_cut(k + 1, fc / fps, trans, ims[5], ims[6], ims[7], ims[8], fs[1:7], fs[7:], fps, cont)
        C.append(c)
        pairs[c['i']] = (ims[6], ims[7])
    rms = None
    au = getattr(m, 'AUDIO', None)
    if au and os.path.exists(au):
        rms = audio_rms(au)
    finish(a, dict(source=os.path.abspath(a.engine), mode='engine', w=m.W, h=m.H, fps=fps, dur=float(m.TOTAL)), S, C, rms, pairs)


# ───────────────────────── 節奏、報告、拼圖 ─────────────────────────
def pace(meta, C, rms, step=0.25):
    dur = meta['dur']
    n = int(dur / step) + 1
    cut = np.zeros(n)
    for c in C:
        cut[min(n - 1, int(c['t'] / step))] += 1
    k = int(4 / step)
    ker = np.ones(k) / (k * step)
    rate = np.convolve(cut, ker, mode='same')  # 每秒幾刀（4 秒平滑）
    out = dict(rate=rate.tolist(), step=step)
    if rms is not None:
        r = np.interp(np.arange(n) * step, np.arange(len(rms)) * step, rms)
        r4 = np.convolve(r, np.ones(k) / k, mode='same')
        out['rms'] = r4.tolist()
        if rate.std() > 0 and r4.std() > 0:
            out['corr'] = round(float(np.corrcoef(rate, r4)[0, 1]), 2)
        out['peak_audio'] = round(float(np.argmax(r4) * step), 1)
    third = max(1, n // 3)
    out['first'] = round(float(rate[:third].mean()), 2)
    out['last'] = round(float(rate[-third:].mean()), 2)
    out['peak_cut'] = round(float(np.argmax(rate) * step), 1)
    return out


def font(size):
    return ImageFont.truetype(FONT, size, index=3)


def draw_pace(path, meta, C, P):
    W, H, pad = 1400, 300, 40
    im = Image.new('RGB', (W, H), (16, 16, 18))
    d = ImageDraw.Draw(im)
    n = len(P['rate'])
    X = lambda i: pad + (W - 2 * pad) * i / max(1, n - 1)
    if 'rms' in P:
        pts = [(X(i), H - pad - (H - 2 * pad) * v) for i, v in enumerate(P['rms'])]
        d.polygon([(pad, H - pad)] + pts + [(W - pad, H - pad)], fill=(58, 58, 64))
    top = max(max(P['rate']), 1e-6)
    for c in C:
        x = pad + (W - 2 * pad) * c['t'] / meta['dur']
        col = (235, 80, 70) if c['sev'] >= 3 else (240, 200, 80) if c['sev'] >= 1 else (120, 120, 128)
        d.line([(x, pad), (x, H - pad)], fill=col, width=1)
    d.line([(X(i), H - pad - (H - 2 * pad) * v / top) for i, v in enumerate(P['rate'])], fill=(90, 210, 190), width=3)
    f = font(16)
    d.text((pad, 10), f"灰＝音樂能量　綠線＝每秒剪幾刀（4 秒平滑，最高 {top:.1f}）　直線＝剪點（紅＝優先看、黃＝有標記）", font=f, fill=(220, 220, 220))
    for s in range(0, int(meta['dur']) + 1, 5 if meta['dur'] <= 90 else 15):
        x = pad + (W - 2 * pad) * s / meta['dur']
        d.text((x - 8, H - pad + 6), f'{s}s', font=f, fill=(150, 150, 150))
    im.save(path)


def draw_cuts(path, C, pairs, cols):
    if not C:
        return
    a0, _ = pairs[C[0]['i']]
    h0, w0 = a0.shape[:2]
    tw = 300 if w0 >= h0 else 170
    th = int(tw * h0 / w0)
    bar, gap, pad = 52, 4, 10
    cw = tw * 2 + gap
    rows = (len(C) + cols - 1) // cols
    sheet = Image.new('RGB', (pad + cols * (cw + pad), pad + rows * (th + bar + pad)), (16, 16, 18))
    d = ImageDraw.Draw(sheet)
    f1, f2 = font(17), font(14)
    for k, c in enumerate(C):
        x = pad + (k % cols) * (cw + pad)
        y = pad + (k // cols) * (th + bar + pad)
        A, B = pairs[c['i']]
        sheet.paste(Image.fromarray(A).resize((tw, th), Image.LANCZOS), (x, y + bar))
        sheet.paste(Image.fromarray(B).resize((tw, th), Image.LANCZOS), (x + tw + gap, y + bar))
        col = (235, 80, 70) if c['sev'] >= 3 else (240, 200, 80) if c['sev'] >= 1 else (110, 220, 160)
        d.text((x + 2, y + 2), f"#{c['i']}  {c['t']:.2f}s  {c['scaleA']}→{c['scaleB']}  {c['trans']}", font=f1, fill=col)
        tag = '　'.join(c['flags']) or '　'.join(c['good']) or '—'
        d.text((x + 2, y + 26), tag[:34], font=f2, fill=(225, 225, 225))
        ax, ay = x + c['eyeA'][0] * tw, y + bar + c['eyeA'][1] * th
        bx, by = x + tw + gap + c['eyeB'][0] * tw, y + bar + c['eyeB'][1] * th
        gx, gy = x + tw + gap + c['eyeA'][0] * tw, y + bar + c['eyeA'][1] * th
        r = 7
        d.ellipse([ax - r, ay - r, ax + r, ay + r], fill=(235, 70, 60), outline=(255, 255, 255))
        d.ellipse([gx - r, gy - r, gx + r, gy + r], outline=(235, 70, 60), width=2)
        d.line([(gx, gy), (bx, by)], fill=(255, 255, 255), width=1)
        d.ellipse([bx - r, by - r, bx + r, by + r], fill=(60, 210, 230), outline=(255, 255, 255))
        for (v, mg), ox in ((c['flowA'], x), (c['flowB'], x + tw + gap)):
            if mg >= TH['move']:
                cx, cy = ox + tw / 2, y + bar + th - 22
                L = 18 + min(40, mg * 4000)
                ex, ey = cx + v[0] / mg * L, cy + v[1] / mg * L
                d.line([(cx, cy), (ex, ey)], fill=(250, 220, 60), width=3)
                d.ellipse([ex - 4, ey - 4, ex + 4, ey + 4], fill=(250, 220, 60))
    sheet.save(path, quality=88)


def write_review(path, C, source):
    old = json.load(open(path)) if os.path.exists(path) else None
    if old:
        json.dump(old, open(os.path.splitext(path)[0] + f'.r{old.get("round", 1)}.json', 'w'), ensure_ascii=False, indent=1)
    cells = [dict(i=c['i'], t=c['t'], label='　'.join(c['flags']) or '抽查', score=None, why='', fix='') for c in C]
    rnd = (old.get('round', 1) + 1) if old else 1
    json.dump(dict(source=source, kind='cuts', round=rnd, min=8, cells=cells), open(path, 'w'), ensure_ascii=False, indent=1)
    return rnd


def finish(a, meta, S, C, rms, pairs):
    os.makedirs(a.out, exist_ok=True)
    fps = meta['fps']
    # 重複使用的畫面（不相鄰的鏡頭 dHash 漢明距離 ≤ 6）
    for i in range(len(S)):
        for j in range(i + 2, len(S)):
            same = bin(S[i]['hash'] ^ S[j]['hash']).count('1') <= 10
            if same and S[i]['cover'] >= 0.5 and S[i].get('thumb') is not None and corr_small(S[i]['thumb'], S[j]['thumb']) > 0.9:
                S[j]['flags'].append(f"跟 #{S[i]['i']} 同一個畫面")
                S[j]['fixes'].append('同一個畫面出現兩次：首尾呼應以外換一個鏡頭')
    for s in S:
        s.pop('hash', None)
        s.pop('thumb', None)
    P = pace(meta, C, rms)
    durs = np.array([s['dur'] for s in S]) if S else np.array([meta['dur']])
    low = meta['low_cover'] if 'low_cover' in meta else sum(s['dur'] for s in S if s['cover'] < TH['cover'])
    seq = dict(shots=len(S), cuts=len(C), low_cover=round(low, 1), low_cover_pct=round(low / max(meta['dur'], 1e-6), 3), asl=round(float(durs.mean()), 2), median=round(float(np.median(durs)), 2),
               cv=round(float(durs.std() / max(durs.mean(), 1e-6)), 2), shortest=round(float(durs.min()), 2), longest=round(float(durs.max()), 2),
               first_cut=round(C[0]['t'], 2) if C else None, last_hold=round(float(S[-1]['dur']), 2) if S else None,
               pace=P, flagged=sum(1 for c in C if c['sev'] >= 2))
    # 評分集：嚴重度 ≥ 2 的全部（最多 30），不夠 8 刀就均勻補抽查
    rv = sorted([c for c in C if c['sev'] >= 2], key=lambda c: -c['sev'])[:30]
    if len(rv) < 8:
        rest = [c for c in C if c not in rv]
        if rest:
            idx = np.linspace(0, len(rest) - 1, min(len(rest), 8 - len(rv))).round().astype(int)
            rv += [rest[i] for i in sorted(set(idx))]
    rv = sorted(rv, key=lambda c: c['t'])
    cols = 2 if meta['w'] >= meta['h'] else 3
    draw_cuts(os.path.join(a.out, 'cuts.jpg'), rv, pairs, cols)
    if a.all:
        draw_cuts(os.path.join(a.out, 'cuts_all.jpg'), C, pairs, cols + 1)
    draw_pace(os.path.join(a.out, 'pace.png'), meta, C, P)
    rnd = write_review(os.path.join(a.out, 'cuts.review.json'), rv, meta['source'])

    def js(o):
        if isinstance(o, (np.floating,)):
            return float(o)
        if isinstance(o, (np.integer,)):
            return int(o)
        if isinstance(o, tuple):
            return list(o)
        raise TypeError(type(o))

    json.dump(dict(meta=meta, th=TH, seq=seq, cuts=C, shots=S), open(os.path.join(a.out, 'flow.json'), 'w'),
              ensure_ascii=False, indent=1, default=js)
    report(os.path.join(a.out, 'report.md'), meta, seq, S, C, rv, rnd)
    print(f"{a.out}/report.md\n{a.out}/cuts.jpg（{len(rv)} 刀待評分，第 {rnd} 輪）\n{a.out}/pace.png")
    print(f"鏡頭 {len(S)}、剪點 {len(C)}、平均鏡頭 {seq['asl']} 秒；優先看 {seq['flagged']} 刀" +
          (f"；剪輯速度跟音樂能量 r = {P['corr']}" if 'corr' in P else ''))


def report(path, meta, seq, S, C, rv, rnd):
    P = seq['pace']
    L = [f"# 剪接流暢度報告", '', f"來源：`{meta['source']}`（{'engine 剪點前後渲染' if meta['mode'] == 'engine' else '成片'}；"
         f"{meta['w']}×{meta['h']}、{meta['fps']:.3f} fps、{meta['dur']:.1f} 秒）", '',
         '數字是提示：每個標記都要對 `cuts.jpg` 確認；刻意的在 `cuts.review.json` 的 why 寫理由。規則與門檻見 `references/story.md`。', '',
         '## 總覽', '', '| 項目 | 數值 | 怎麼看 |', '|---|---|---|',
         f"| 鏡頭／剪點 | {seq['shots']}／{seq['cuts']} | |",
         f"| 平均鏡頭長（ASL）／中位數 | {seq['asl']} 秒／{seq['median']} 秒 | 口播與導覽 2–4 秒、vlog 1–2.5 秒、MV 副歌 0.3–1 秒 |",
         f"| 鏡頭長變異係數 | {seq['cv']} | < 0.3 太均勻像節拍器；0.4–0.9 有緩急 |",
         f"| 最短／最長 | {seq['shortest']}／{seq['longest']} 秒 | 最短 ≥ 0.2 秒（6 格） |",
         f"| 第一個剪點 | {seq['first_cut']} 秒 | 短影音 ≤ 1.5 秒內要有第一個變化（鉤子） |",
         f"| 開場黑／白格 | {meta.get('lead', 0)} 格 | 短影音第一格就要有畫面；> 0 表示從黑場或白場開始 |",
         f"| 片尾停留 | {seq['last_hold']} 秒 | 收尾鏡頭 ≥ 1 秒，讓觀眾讀得到最後一句或 logo |",
         f"| 實拍不到半個畫面的時間 | {seq['low_cover']} 秒（{seq['low_cover_pct']:.0%}）{'　⚠ 超過 15%' if seq['low_cover_pct'] > TH['cover_time'] else ''} | "
         f"片頭片尾字卡以外應接近 0；峇里島 60 秒 v1（被退）17%、v2 1% |",
         f"| 前三分之一／後三分之一剪輯速度 | {P['first']}／{P['last']} 刀/秒 | 一般後段 ≥ 前段（遞進）；刻意慢收要說得出理由 |",
         f"| 剪輯最密處／音樂能量最高處 | {P['peak_cut']} 秒／{P.get('peak_audio', '—')} 秒 | 兩者應落在同一段 |"]
    if 'corr' in P:
        L.append(f"| 剪輯速度 vs 音樂能量 | r = {P['corr']} | ≥ 0.4 貼著音樂走；< 0.2 節奏跟音樂各走各的（能量＝響度＋打擊密度） |")
    L += ['', f"## 優先看的剪點（嚴重度 ≥ 2，共 {seq['flagged']} 刀）", '']
    top = sorted([c for c in C if c['sev'] >= 2], key=lambda c: (-c['sev'], c['t']))
    if not top:
        L.append('沒有。照常抽查 `cuts.jpg`。')
    else:
        L += ['| # | 秒 | 景別 | 標記 | 改法 |', '|---|---|---|---|---|']
        for c in top[:30]:
            L.append(f"| {c['i']} | {c['t']:.2f} | {c['scaleA']}→{c['scaleB']} | {'、'.join(c['flags'])} | {'；'.join(c['fixes'])} |")
    bad = [s for s in S if s['flags']]
    L += ['', f"## 鏡頭問題（{len(bad)} 個）", '']
    if not bad:
        L.append('沒有。')
    else:
        L += ['| 鏡頭 | 起訖 | 長度 | 景別 | 標記 | 改法 |', '|---|---|---|---|---|---|']
        for s in bad:
            L.append(f"| {s['i']} | {s['t0']:.2f}–{s['t1']:.2f} | {s['dur']:.2f} | {s['scale']} | {'、'.join(s['flags'])} | {'；'.join(s['fixes'])} |")
    good = [c for c in C if c['good'] and not c['flags']]
    L += ['', f"## 接得好的（{len(good)} 刀）", '', '、'.join(f"#{c['i']}（{'、'.join(c['good'])}）" for c in good[:40]) or '—']
    L += ['', '## 全部剪點', '', '| # | 秒 | 轉場 | 景別 | 視線跳 | 流向 A→B | 方向 | ΔY | 色偏 | 構圖相關 | B 入點銳利 |',
          '|---|---|---|---|---|---|---|---|---|---|---|']
    for c in C:
        (va, ma), (vb, mb) = c['flowA'], c['flowB']
        dc = '—' if c['dC'] is None else f"{c['dC']:.0f}"
        L.append(f"| {c['i']} | {c['t']:.2f} | {c['trans']} | {c['scaleA']}→{c['scaleB']} | {c['eye']:.2f} | {arrow(va, ma)}→{arrow(vb, mb)} | "
                 f"{c['dir']} | {c['dY']:+.0f} | {dc} | {c['corr']:.2f} | {c.get('sharpB', '—')} |")
    L += ['', '## 全部鏡頭', '', '| # | 起訖 | 長度 | 景別 | 流向 | 複雜度 | 實拍覆蓋 | 重複格 |', '|---|---|---|---|---|---|---|---|']
    for s in S:
        rep = '—' if s['repeat'] is None else f"{s['repeat']:.0%}"
        L.append(f"| {s['i']} | {s['t0']:.2f}–{s['t1']:.2f} | {s['dur']:.2f} | {s['scale']} | {s['dirn'] or '—'} | {s['edge']:.3f} | {s['cover']:.0%} | {rep} |")
    L += ['', '## 下一步', '',
          f"1. 看 `cuts.jpg`（{len(rv)} 刀），依 `references/review.md`〈剪點評分〉逐刀把 score／why／fix 填進 `cuts.review.json`（第 {rnd} 輪）",
          '2. `python review.py gate cuts.review.json`：沒過就修最差的 3 刀、重跑 flow.py（round 自動 +1）',
          '3. 看 `pace.png`：剪輯最密處要落在音樂最大的段落；breakdown 有沒有真的慢下來']
    open(path, 'w').write('\n'.join(L) + '\n')


# ───────────────────────── pick：挑入點 ─────────────────────────
def cmd_pick(a):
    P = probe(a.video)
    fps = P['fps']
    t0, t1 = a.t_from, a.to if a.to else P['dur'] - a.dur
    span = t1 - t0 + a.dur
    pw, ph = sizes(P['w'], P['h'], a.pair)
    aw, ah = sizes(P['w'], P['h'], 256)
    feats, eyes, face_on, big = [], [], [], {}
    prev, prev_rgb = None, None
    for i, rgb in enumerate(decode(a.video, P['fr'], pw, ph, t0, span)):
        small = cv2.resize(rgb, (aw, ah), interpolation=cv2.INTER_AREA)
        f = Feat(small, prev)
        if prev is not None:
            prev.g = prev.hist = None
        feats.append(f)
        if i % 2 == 0:
            p, src, sc, sv = eye_point(rgb, prev_rgb)
            eyes.append(p)
            face_on.append(src == '臉')
        else:
            eyes.append(eyes[-1])
            face_on.append(face_on[-1])
        if i % max(1, int(fps / 10)) == 0:
            big[i] = rgb
        prev, prev_rgb = f, rgb
    n = len(feats)
    W = int(round(a.dur * fps))
    if n < W + 1:
        sys.exit('範圍太短：--to 減 --from 至少要比 --dur 長')
    sh = np.array([f.sharp for f in feats])
    ref = float(np.percentile(sh, 90)) or 1
    fl = np.array([f.flow for f in feats])
    dp = np.array([f.dpix for f in feats])
    any_face = any(face_on)
    clean = {'top': lambda p: p[1] > 0.35, 'bottom': lambda p: p[1] < 0.65, 'left': lambda p: p[0] > 0.35,
             'right': lambda p: p[0] < 0.65, 'none': lambda p: True}[a.clean]
    cands = []
    step = max(1, int(round(a.step * fps)))
    for s in range(0, n - W, step):
        w = slice(s, s + W)
        c = dict(t=round(t0 + s / fps, 3))
        c['sharp_in'] = min(1, sh[s:s + 2].mean() / ref)
        c['sharp'] = min(1, sh[w].mean() / ref)
        v = fl[s + 1:s + W]
        sm = cv2.GaussianBlur(v.astype(np.float32), (1, 9), 0) if len(v) >= 9 else v
        jit = float(np.abs(v - sm).mean()) if len(v) else 0
        c['stable'] = float(np.clip(1 - jit / 0.006, 0, 1))
        d = dp[s + 1:s + W]
        c['clear'] = 1 - (float((d < 0.2 * np.median(d)).mean()) if np.median(d) > 1.5 else 0)
        c['subject'] = float(np.mean(face_on[w])) if any_face else 1.0
        c['clean'] = float(np.mean([clean(p) for p in eyes[s:s + W]]))
        mag = np.hypot(v[:, 0], v[:, 1]) if len(v) else np.zeros(1)
        pk = int(np.argmax(mag)) / max(1, len(mag) - 1)
        c['action'] = 1.0 if 0.15 <= pk <= 0.85 else 0.4
        wts = dict(sharp_in=0.25, sharp=0.15, stable=0.15, clear=0.15, subject=0.15 if any_face else 0, clean=0.15 if a.clean != 'none' else 0,
                   action=0.1 if a.action else 0)
        c['score'] = round(sum(c[k] * v_ for k, v_ in wts.items()) / sum(wts.values()), 3)
        c['_s'] = s
        cands.append(c)
    cands.sort(key=lambda c: -c['score'])
    pick = []
    for c in cands:
        if all(abs(c['t'] - p['t']) >= a.dur / 2 for p in pick):
            pick.append(c)
        if len(pick) >= a.n:
            break
    os.makedirs(a.out, exist_ok=True)
    kb = np.array(sorted(big))
    nb = lambda j: big[int(kb[np.argmin(np.abs(kb - j))])]
    h0, w0 = ph, pw
    tw = 220 if w0 >= h0 else 130
    th = int(tw * h0 / w0)
    bar, pad = 40, 8
    sheet = Image.new('RGB', (pad + 3 * (tw + 4) + pad, pad + len(pick) * (th + bar + pad)), (16, 16, 18))
    d = ImageDraw.Draw(sheet)
    f1 = font(15)
    print(f"{'名次':<4}{'入點':>8}  {'總分':>5}  入點清楚 全段清楚 穩定 不重複 有主體 字區乾淨 動作在中段")
    for r, c in enumerate(pick):
        s = c['_s']
        y = pad + r * (th + bar + pad)
        for k, j in enumerate((s, s + W // 2, s + W - 1)):
            sheet.paste(Image.fromarray(nb(j)).resize((tw, th), Image.LANCZOS), (pad + k * (tw + 4), y + bar))
        d.text((pad + 2, y + 4), f"#{r + 1}  {c['t']:.2f}s 起 {a.dur:.1f} 秒  分數 {c['score']:.2f}", font=f1, fill=(240, 210, 90))
        d.text((pad + 2, y + 21), f"清楚 {c['sharp_in']:.2f}/{c['sharp']:.2f} 穩 {c['stable']:.2f} 主體 {c['subject']:.2f} 字區 {c['clean']:.2f}",
               font=font(12), fill=(210, 210, 210))
        print(f"#{r + 1:<3}{c['t']:>8.2f}  {c['score']:>5.2f}  {c['sharp_in']:>8.2f} {c['sharp']:>8.2f} {c['stable']:>4.2f} {c['clear']:>6.2f} "
              f"{c['subject']:>6.2f} {c['clean']:>8.2f} {c['action']:>10.2f}")
    out = os.path.join(a.out, 'pick.jpg')
    sheet.save(out, quality=88)
    json.dump([{k: v for k, v in c.items() if k != '_s'} for c in pick], open(os.path.join(a.out, 'pick.json'), 'w'), indent=1)
    print(out)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = p.add_subparsers(dest='cmd', required=True)
    s = sp.add_parser('check', help='剪點與鏡頭檢查')
    s.add_argument('video', nargs='?')
    s.add_argument('--engine', help='seek(t) engine.py：剪點取自 SHOTS，正式渲染前用')
    s.add_argument('--cuts', help='剪點表：秒數清單或 cutlist.py／render.py --dump-cuts 的 cuts.json')
    s.add_argument('-o', '--out', default='out/flow')
    s.add_argument('--pair', type=int, default=480, help='拼圖與視線點用的長邊畫素（預設 480）')
    s.add_argument('--all', action='store_true', help='另出 cuts_all.jpg（全部剪點）')
    s = sp.add_parser('pick', help='幫一個鏡頭挑入點')
    s.add_argument('video')
    s.add_argument('--from', dest='t_from', type=float, default=0.0)
    s.add_argument('--to', type=float, help='入點最晚到幾秒（預設片長 − dur）')
    s.add_argument('--dur', type=float, required=True, help='這個鏡頭要用幾秒')
    s.add_argument('--step', type=float, default=0.1)
    s.add_argument('--clean', choices=['none', 'top', 'bottom', 'left', 'right'], default='none', help='要留給字的區域：主體不要在那裡')
    s.add_argument('--action', action='store_true', help='偏好動作高峰落在鏡頭中段（動作接）')
    s.add_argument('--n', type=int, default=5)
    s.add_argument('--pair', type=int, default=360)
    s.add_argument('-o', '--out', default='out/pick')
    a = p.parse_args()
    if a.cmd == 'pick':
        cmd_pick(a)
    elif a.engine:
        check_engine(a)
    elif a.video:
        check_video(a)
    else:
        sys.exit('給影片路徑或 --engine engine.py')


if __name__ == '__main__':
    main()
