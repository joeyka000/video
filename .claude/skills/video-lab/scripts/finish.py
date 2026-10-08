#!/usr/bin/env python3
"""質感檢查：每個鏡頭的高光、暗部、黑白位與中性色是否全片統一、顏色爆掉、膚色、漸層色階（壓縮後）。

flow.py 管「兩格之間接得順不順」，這支管「每一格的影像品質夠不夠高級」。量的是成片（壓縮後的檔案），
因為色階、暗部糊成色塊這些問題只有壓完才看得到。

  python finish.py check deliver/final.mp4 -o qa/finish                       # 每 0.5 秒抽一格全解析度
  python finish.py check deliver/final.mp4 --flow qa/flow/flow.json -o qa/finish   # 用 flow.py 的鏡頭切分
  python finish.py check --engine work/engine.py -o qa/finish                 # 正式渲染前：每個鏡頭中間渲 1 格
  python finish.py still a.jpg b.png ...                                      # 單張圖（look board、海報、縮圖）

產出（-o 目錄）：
  report.md    總覽、要處理的鏡頭（含改法）、全片統一度、全部鏡頭的數字
  grade.jpg    每個鏡頭一格縮圖，格頭寫黑位／中間調／白位／偏色／彩度／膚色角；紅字＝要處理
  grade.png    全片曲線：黑位、中間調、白位、彩度 p95、偏色 a／b，一眼看出哪個鏡頭跳出去
  finish.json  全部數字

量法（門檻與理由在 references/finish.md〈七、量化門檻〉；改數字時兩邊一起改）：
  - 亮度 Y 用 Rec.709 權重、0–255；上下左右的黑邊不算
  - 高光硬切：Y ≥ 250 的像素 > 0.5%，而且比 235–249 這一段還多（沒有柔肩，一刀切白）
  - 死黑：Y ≤ 3 的像素 > 4%（暗部細節沒了）
  - 偏色：近中性色像素的 Lab a／b 平均（白平衡與調色），跟全片中位數比
  - 顏色爆掉：高彩度（C* > 40）又同時有通道撞 255、有通道撞 0，連成 5×5 以上的色塊；彩度 p95（Lab C*）只當參考
  - 字卡：有紋理的區塊 < 50%（跟 flow.py 實拍覆蓋同一個量法），不參與統一度、黑位、死黑、偏色
  - 膚色：YuNet 人臉中央 60% 的 Cb／Cr 向量角，跟示波器膚色線 123° 比
  - 色階：在「平滑但不是平的」區域量相同灰階連續多長（換算成 1080 短邊的像素）；抖色或顆粒約 1–3，
    一圈一圈看得出來的色階 > 8
"""
import argparse
import json
import math
import os
import subprocess
import sys

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
FONT = '/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc'
YUNET = os.path.expanduser('~/video-lab/models/yunet.onnx')

TH = dict(
    clip=0.005,        # Y ≥ 250 超過 0.5% 才看是不是硬切
    crush=0.04,        # Y ≤ 3 超過 4%：死黑
    black_dev=14,      # 黑位（Y 第 1 百分位）跟全片中位數差 > 14：這個鏡頭的黑跟別人不一樣
    cast_dev=6,        # 中性色偏色跟全片中位數差 > 6（Lab a／b）：調色沒統一
    gamut=0.005,       # 高彩度（C* > 40）又同時有通道撞 255、有通道撞 0，而且連成 5×5 以上的色塊，佔畫面 > 0.5%：顏色爆掉
    card=0.5,          # 有紋理的區塊 < 50% 的鏡頭當字卡／圖卡：不參與統一度、黑位、死黑、偏色判斷
    short=0.5,         # 短於 0.5 秒的鏡頭（閃白、過場格）也不參與
    skin_line=123,     # 示波器膚色線（度）
    skin_dev=12,       # 膚色向量角偏 > 12°：偏洋紅（> 135）或偏綠黃（< 111）
    band=8.0,          # 色階長度 > 8 px：看得到一圈一圈
    band_area=0.03,    # 平滑漸層區要佔畫面 3% 以上才量
)


# ───────────────────────── 量測 ─────────────────────────
def luma(rgb):
    f = rgb.astype(np.float32)
    return f[..., 0] * 0.2126 + f[..., 1] * 0.7152 + f[..., 2] * 0.0722


def active_mask(Y):
    """去掉 letterbox／pillarbox：從畫面邊緣往內連續、幾乎全黑的列／欄（黑邊裡有字幕或標題也算黑邊：
    一列的中位數 ≤ 2、第 75 百分位 ≤ 4 就算；夜空有顆粒與雜訊，中位數不會到 2）。"""
    h, w = Y.shape
    m = np.ones((h, w), bool)
    for axis, n in ((0, h), (1, w)):
        q = np.percentile(Y, [50, 75], axis=1 - axis)
        bar = (q[0] <= 2) & (q[1] <= 4)
        a = 0
        while a < n // 2 and bar[a]:
            a += 1
        b = 0
        while b < n // 2 and bar[n - 1 - b]:
            b += 1
        if axis == 0:
            m[:a] = False
            m[n - b:] = False
        else:
            m[:, :a] = False
            m[:, n - b:] = False
    return m


def banding(g):
    """漸層色階長度（px，換算成 1080 短邊）；沒有夠大的平滑漸層區回 None。"""
    if g.ndim == 3:
        g = cv2.cvtColor(g, cv2.COLOR_RGB2GRAY)
    f = g.astype(np.float32)
    b = cv2.GaussianBlur(f, (0, 0), 3)
    m1 = cv2.blur(b, (15, 15))
    sd = np.sqrt(np.maximum(cv2.blur(b * b, (15, 15)) - m1 * m1, 0))  # 小尺度起伏：紋理（磚、樹葉、皮膚）排除
    big = cv2.GaussianBlur(f, (0, 0), 12)  # 大尺度坡度：寬達 40 px 的色階也會被抹成一道坡
    gr = np.hypot(cv2.Sobel(big, cv2.CV_32F, 1, 0, ksize=3), cv2.Sobel(big, cv2.CV_32F, 0, 1, ksize=3)) / 8
    mask = (sd < 3.0) & (gr > 0.006) & (gr < 0.6) & (b > 6) & (b < 249) & active_mask(f)  # 死黑、死白另外量
    if mask.mean() < TH['band_area']:
        return None
    # 分 64 px 區塊各量一次，取第 90 百分位：壓檔常常只在某一段把抖色抹平成一條色帶，平均會把它稀釋掉
    ex = (g[:, 1:] == g[:, :-1]) & mask[:, 1:]
    ey = (g[1:, :] == g[:-1, :]) & mask[1:, :]
    mx, my = mask[:, 1:], mask[1:, :]
    T = 64
    runs = []
    for y0 in range(0, g.shape[0] - T + 1, T):
        for x0 in range(0, g.shape[1] - T + 1, T):
            nx, ny = mx[y0:y0 + T, x0:x0 + T].sum(), my[y0:y0 + T, x0:x0 + T].sum()
            if nx < T * T * 0.5 or ny < T * T * 0.5:
                continue
            px, py = ex[y0:y0 + T, x0:x0 + T].sum() / nx, ey[y0:y0 + T, x0:x0 + T].sum() / ny
            runs.append(min(1 / (1 - min(px, 0.995)), 1 / (1 - min(py, 0.995))))
    if len(runs) < 4:
        return None
    return round(float(np.percentile(runs, 90) * 1080 / min(g.shape)), 2)


_det = None


def faces(rgb):
    global _det
    if not os.path.exists(YUNET):
        return []
    h, w = rgb.shape[:2]
    k = 640 / max(h, w)
    sm = cv2.resize(rgb, (int(w * k), int(h * k)), interpolation=cv2.INTER_AREA)
    if _det is None:
        _det = cv2.FaceDetectorYN.create(YUNET, '', (sm.shape[1], sm.shape[0]), 0.9)  # 高門檻：卡牌、海報上的動漫臉不要算
    _det.setInputSize((sm.shape[1], sm.shape[0]))
    _, f = _det.detect(cv2.cvtColor(sm, cv2.COLOR_RGB2BGR))
    if f is None:
        return []
    return [(x / k, y / k, fw / k, fh / k) for x, y, fw, fh in f[:, :4] if fw / k > min(h, w) * 0.05]


def skin(rgb):
    """最大人臉中央 60% 的膚色：(向量角度, 亮度)；沒有臉回 None。"""
    fs = faces(rgb)
    if not fs:
        return None
    x, y, fw, fh = max(fs, key=lambda f: f[2] * f[3])
    x0, y0, x1, y1 = int(x + fw * 0.2), int(y + fh * 0.25), int(x + fw * 0.8), int(y + fh * 0.8)
    roi = rgb[max(0, y0):y1, max(0, x0):x1]
    if roi.size < 300:
        return None
    ycc = cv2.cvtColor(roi, cv2.COLOR_RGB2YCrCb).astype(np.float32)
    Yv, cr, cb = ycc[..., 0], ycc[..., 1] - 128, ycc[..., 2] - 128
    ok = (Yv > 40) & (Yv < 235)  # 排除眼睛、頭髮、反光
    # 真的人臉中央大半是膚色（YCrCb 經典膚色框放寬）；卡通臉、食物、玩偶過不了
    skinish = ok & (cr > 2) & (cr < 50) & (cb > -50) & (cb < 2)
    if ok.mean() < 0.3 or skinish.mean() < 0.4:
        return None
    ok = skinish
    ang = math.degrees(math.atan2(float(cr[ok].mean()), float(cb[ok].mean()))) % 360
    return round(ang, 1), round(float(Yv[ok].mean()), 1)


def measure(rgb):
    """一格的質感數字。rgb：uint8 (H, W, 3)。"""
    Y = luma(rgb)
    act = active_mask(Y)
    if act.mean() < 0.05:  # 整格黑（片頭黑場）：整格都算
        act[:] = True
    y = Y[act]
    n = max(1, y.size)
    hi, sh = (y >= 250).sum() / n, ((y >= 235) & (y < 250)).sum() / n
    lab = cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB).astype(np.float32)
    L, A, B = lab[..., 0], lab[..., 1] - 128, lab[..., 2] - 128
    neu = act & (np.hypot(A, B) < 14) & (L > 50) & (L < 230)
    Cm = np.hypot(A, B)
    C = Cm[act & (L > 20)]  # Lab 彩度（暗部不會像 HSV 飽和度那樣虛高）
    sat = float(np.percentile(C, 95)) if C.size else 0.0
    # 顏色爆掉：最高亮度的純色（一個通道 255、一個通道 0）連成色塊，紋理沒了。
    # 只撞一邊不算（黃色的藍通道本來就接近 0）；峇里島 v2 的調色是 0，彩度拉 1.4 倍才出現 0.1–1.5%
    pinned = (act & (Cm > 40) & (rgb.max(2) >= 253) & (rgb.min(2) <= 2)).astype(np.uint8)
    gamut = float(cv2.erode(pinned, np.ones((5, 5), np.uint8)).sum() / max(1, act.sum()))
    g256 = cv2.resize(cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY), None, fx=256 / max(rgb.shape[:2]), fy=256 / max(rgb.shape[:2]),
                      interpolation=cv2.INTER_AREA).astype(np.float32)
    gb = cv2.GaussianBlur(g256, (5, 5), 0)
    m1 = cv2.blur(gb, (7, 7))
    sdm = np.sqrt(np.maximum(cv2.blur(gb * gb, (7, 7)) - m1 * m1, 0))
    r, c = (14, 8) if g256.shape[0] > g256.shape[1] else (8, 14)
    hh, ww = sdm.shape
    cells = sdm[:hh // r * r, :ww // c * c].reshape(r, hh // r, c, ww // c).mean((1, 3))
    cover = float((cells > 3.0).mean())  # 跟 flow.py 的實拍覆蓋率同一個量法
    m = dict(black=round(float(np.percentile(y, 1)), 1), mid=round(float(np.exp(np.log(y + 1).mean()) - 1), 1),
             white=round(float(np.percentile(y, 99)), 1), clip=round(float(hi), 4), shoulder=round(float(sh), 4),
             crush=round(float((y <= 3).sum() / n), 4), sat=round(sat, 1), gamut=round(gamut, 4), cover=round(cover, 2),
             cast=None if neu.mean() < 0.04 else (round(float(A[neu].mean()), 1), round(float(B[neu].mean()), 1)),
             band=banding(rgb), skin=skin(rgb), active=round(float(act.mean()), 3))
    return m


# ───────────────────────── 讀片與分鏡頭 ─────────────────────────
def probe(path):
    r = subprocess.run(['ffprobe', '-v', 'error', '-select_streams', 'v:0', '-show_entries', 'stream=width,height:format=duration',
                        '-of', 'json', path], capture_output=True, text=True)
    d = json.loads(r.stdout)
    return int(d['streams'][0]['width']), int(d['streams'][0]['height']), float(d['format']['duration'])


def samples(path, every):
    w, h, dur = probe(path)
    p = subprocess.Popen(['ffmpeg', '-v', 'error', '-i', path, '-vf', f'fps=1/{every}', '-an', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-'],
                         stdout=subprocess.PIPE)
    n, i = w * h * 3, 0
    while True:
        b = p.stdout.read(n)
        if len(b) < n:
            break
        yield i * every, np.frombuffer(b, np.uint8).reshape(h, w, 3)  # fps 濾鏡取的是 i×every 附近那一格
        i += 1
    p.wait()


def group(times, frames_small, flow_json=None):
    """把抽樣格分到鏡頭：有 flow.json 用它的鏡頭；沒有就看相鄰抽樣格的直方圖差。"""
    if flow_json:
        S = json.load(open(flow_json))['shots']
        out = []
        for t in times:
            k = next((s['i'] for s in S if s['t0'] <= t < s['t1']), S[-1]['i'])
            out.append(k)
        return out, {s['i']: (s['t0'], s['t1']) for s in S}
    out, k, prev = [], 1, None
    for t, sm in zip(times, frames_small):
        hsv = cv2.cvtColor(sm, cv2.COLOR_RGB2HSV)
        hist = cv2.calcHist([hsv], [0, 1, 2], None, [12, 4, 4], [0, 180, 0, 256, 0, 256])
        cv2.normalize(hist, hist, 1, 0, cv2.NORM_L1)
        if prev is not None and cv2.compareHist(prev, hist, cv2.HISTCMP_BHATTACHARYYA) > 0.35:
            k += 1
        out.append(k)
        prev = hist
    spans = {}
    for t, s in zip(times, out):
        a, b = spans.get(s, (t, t))
        spans[s] = (min(a, t), max(b, t))
    return out, spans


# ───────────────────────── 判斷 ─────────────────────────
def shot_summary(ms):
    lit = [m for m in ms if m['mid'] >= 12]  # 淡入淡出、黑場的格不代表這個鏡頭
    ms = lit or ms

    def med(key):
        v = [m[key] for m in ms if m[key] is not None]
        return float(np.median(v)) if v else None
    casts = [m['cast'] for m in ms if m['cast']]
    skins = [m['skin'] for m in ms if m['skin']]
    bands = sorted(m['band'] for m in ms if m['band'] is not None)
    if len(bands) >= 3:  # 鏡頭頭尾的抽樣常落在轉場格上：取第二高，不讓單一過場格決定整個鏡頭
        bands = bands[:-1]
    return dict(black=med('black'), mid=med('mid'), white=med('white'), clip=max(m['clip'] for m in ms),
                shoulder=float(np.median([m['shoulder'] for m in ms])), crush=med('crush'), sat=med('sat'),
                gamut=max(m['gamut'] for m in ms), cover=med('cover'),
                cast=(float(np.median([c[0] for c in casts])), float(np.median([c[1] for c in casts]))) if casts else None,
                skin=(float(np.median([s[0] for s in skins])), float(np.median([s[1] for s in skins]))) if skins else None,
                band=max(bands) if bands else None, active=med('active'))


def judge(S):
    """S：[{i, t0, t1, ...summary}]；加上 flags／fixes，回傳全片統一度。"""
    for s in S:  # 字卡、圖卡、黑場、閃白過場格不參與統一度與黑位／偏色判斷
        s['card'] = bool((s['cover'] is not None and s['cover'] < TH['card']) or (s['t1'] - s['t0']) < TH['short']
                         or not s['mid'] or s['mid'] < 20 or (s['active'] or 0) < 0.5)
    real = [s for s in S if not s['card']]
    ref_black = float(np.median([s['black'] for s in real])) if real else 0
    casts = [s['cast'] for s in real if s['cast']]
    ref_cast = (float(np.median([c[0] for c in casts])), float(np.median([c[1] for c in casts]))) if casts else None
    for s in S:
        f, x = [], []
        if s['clip'] > TH['clip'] and s['clip'] > s['shoulder']:
            f.append(f"高光硬切 {s['clip']:.1%}")
            x.append('高光沒有柔肩：用 look.py 的 tone()（0.72 起肩部壓縮）或降曝光；天空與窗外先拉回來再調色')
        if s['crush'] > TH['crush'] and not s['card']:
            f.append(f"死黑 {s['crush']:.1%}")
            x.append('暗部被壓死：抬黑位（lift 0.02–0.04）或降對比；夜景刻意的話在評分表寫明')
        if s in real and abs(s['black'] - ref_black) > TH['black_dev']:
            f.append(f"黑位跳 {s['black'] - ref_black:+.0f}")
            x.append(f'這個鏡頭的黑位 {s["black"]:.0f}，全片是 {ref_black:.0f}：用 look.py match 對齊，或同一個 mood 重調')
        if s in real and ref_cast and s['cast']:
            d = math.hypot(s['cast'][0] - ref_cast[0], s['cast'][1] - ref_cast[1])
            if d > TH['cast_dev']:
                f.append(f"偏色 {d:.0f}")
                x.append('中性色的顏色跟全片不同（白平衡或調色沒統一）：look.py normalize／match')
        if s['gamut'] > TH['gamut']:
            f.append(f"顏色爆掉 {s['gamut']:.1%}")
            x.append('高彩度的地方撞到 0／255、紋理不見（霓虹、紅色包裝、藍天常見）：mood 的 sat 降到 0.6–0.8，或先降曝光再調色')
        if s['skin']:
            dv = s['skin'][0] - TH['skin_line']
            if abs(dv) > TH['skin_dev']:
                f.append(f"膚色{'偏洋紅' if dv > 0 else '偏綠黃'} {dv:+.0f}°")
                x.append('膚色離示波器膚色線太遠：調色時膚色保護區（look.py color 的 skin）不要被分離色調推走')
        if s['band'] is not None and s['band'] > TH['band']:
            f.append(f"色階 {s['band']:.0f}px")
            x.append('漸層一圈一圈：to_u8(dither=True)＋grain（0.012–0.02）再壓檔；暗部大面積漸層別用純色 scrim')
        s['flags'], s['fixes'] = f, x
    def spread(key):
        v = [s[key] for s in real if s[key] is not None]
        return round(float(np.std(v)), 1) if len(v) > 1 else None
    cast_sd = None
    if len(casts) > 1:
        cast_sd = round(float(np.sqrt(np.var([c[0] for c in casts]) + np.var([c[1] for c in casts]))), 1)
    return dict(black_ref=round(ref_black, 1), cast_ref=ref_cast, black_sd=spread('black'), white_sd=spread('white'), mid_sd=spread('mid'),
                cast_sd=cast_sd, sat_med=round(float(np.median([s['sat'] for s in real])), 1) if real else None,
                band_max=max([s['band'] for s in S if s['band'] is not None], default=None), shots=len(S), graded=len(real))


# ───────────────────────── 輸出 ─────────────────────────
def font(n):
    return ImageFont.truetype(FONT, n, index=3)


def draw_strip(path, S, thumbs):
    if not S:
        return
    h0, w0 = thumbs[S[0]['i']].shape[:2]
    tw = 150 if w0 < h0 else 240
    th = int(tw * h0 / w0)
    cols = 8 if w0 < h0 else 5
    bar, pad = 58, 6
    rows = (len(S) + cols - 1) // cols
    im = Image.new('RGB', (pad + cols * (tw + pad), pad + rows * (th + bar + pad)), (16, 16, 18))
    d = ImageDraw.Draw(im)
    f1, f2 = font(14), font(12)
    for k, s in enumerate(S):
        x = pad + (k % cols) * (tw + pad)
        y = pad + (k // cols) * (th + bar + pad)
        im.paste(Image.fromarray(thumbs[s['i']]).resize((tw, th), Image.LANCZOS), (x, y + bar))
        col = (235, 80, 70) if s['flags'] else (120, 220, 160)
        d.text((x + 2, y + 1), f"#{s['i']} {s['t0']:.1f}s", font=f1, fill=col)
        cast = '—' if not s['cast'] else f"{s['cast'][0]:+.0f}/{s['cast'][1]:+.0f}"
        d.text((x + 2, y + 19), f"黑{s['black']:.0f} 中{s['mid']:.0f} 白{s['white']:.0f}", font=f2, fill=(220, 220, 220))
        d.text((x + 2, y + 35), f"偏{cast} 彩{s['sat']:.0f}" + (f" 膚{s['skin'][0]:.0f}°" if s['skin'] else ''), font=f2, fill=(220, 220, 220))
        if s['flags']:
            d.rectangle([x, y + bar, x + tw - 1, y + bar + th - 1], outline=(235, 80, 70), width=2)
            d.text((x + 4, y + bar + th - 18), s['flags'][0][:12], font=f2, fill=(255, 120, 110))
    im.save(path, quality=88)


def draw_chart(path, S, U):
    Wd, Hd, pad = 1400, 360, 46
    im = Image.new('RGB', (Wd, Hd), (16, 16, 18))
    d = ImageDraw.Draw(im)
    n = len(S)
    X = lambda k: pad + (Wd - 2 * pad) * (k + 0.5) / max(1, n)
    Yv = lambda v: Hd - pad - (Hd - 2 * pad) * v / 255
    for v in (0, 64, 128, 192, 255):
        d.line([(pad, Yv(v)), (Wd - pad, Yv(v))], fill=(40, 40, 46))
    for key, col in (('black', (120, 160, 255)), ('mid', (200, 200, 200)), ('white', (255, 230, 140))):
        pts = [(X(k), Yv(s[key])) for k, s in enumerate(S) if s[key] is not None]
        if len(pts) > 1:
            d.line(pts, fill=col, width=2)
        for p in pts:
            d.ellipse([p[0] - 3, p[1] - 3, p[0] + 3, p[1] + 3], fill=col)
    sp = [(X(k), Yv(s['sat'] * 2)) for k, s in enumerate(S) if s['sat'] is not None]
    if len(sp) > 1:
        d.line(sp, fill=(230, 110, 200), width=1)
    for k, s in enumerate(S):
        if s['cast']:  # 偏色：從中線往上下畫 a（紅綠）與 b（黃藍）
            d.line([(X(k) - 2, Hd / 2), (X(k) - 2, Hd / 2 - s['cast'][0] * 6)], fill=(240, 90, 90), width=3)
            d.line([(X(k) + 2, Hd / 2), (X(k) + 2, Hd / 2 - s['cast'][1] * 6)], fill=(240, 200, 60), width=3)
        if s['flags']:
            d.text((X(k) - 4, Hd - pad + 6), '!', font=font(16), fill=(235, 80, 70))
    d.text((pad, 10), '藍＝黑位　灰＝中間調　黃＝白位（0–255）　粉＝彩度 p95（×2）　紅／黃短棒＝偏色 a／b（中線為 0）　! ＝要處理',
           font=font(15), fill=(220, 220, 220))
    im.save(path)


def report(path, meta, S, U):
    bad = [s for s in S if s['flags']]
    L = ['# 質感檢查', '', f"來源：`{meta['source']}`（{meta['mode']}；{len(S)} 個鏡頭、{meta['n']} 格抽樣）", '',
         '數字是提示：每個標記看 `grade.jpg` 那一格確認；刻意的（夜景死黑、復古偏色）在評分表寫理由。門檻與做法見 `references/finish.md`。', '',
         '## 全片統一度（字卡、黑場不算）', '', '| 項目 | 數值 | 怎麼看 |', '|---|---|---|',
         f"| 黑位（Y 第 1 百分位）中位數／標準差 | {U['black_ref']}／{U['black_sd']} | 標準差 ≤ 6 算一套調色；> 10 看得出鏡頭之間黑不一樣 |",
         f"| 白位標準差 | {U['white_sd']} | ≤ 12 |",
         f"| 中間調標準差 | {U['mid_sd']} | 曝光本來就會隨場景變；> 35 時看是不是有鏡頭特別暗或亮 |",
         f"| 偏色（中性色 Lab a／b）中位數／分散 | {U['cast_ref']}／{U['cast_sd']} | 分散 ≤ 4 算統一；> 6 看得出白平衡各自為政 |",
         f"| 彩度 p95（Lab C*）中位數 | {U['sat_med']} | 參考值：辦公室導覽 20、峇里島卡牌 53（素材本身鮮豔）；同一支片前後差太多才要看 |",
         f"| 最嚴重的色階 | {U['band_max']} px | ≤ 4 看不出來；> 8 看得到一圈一圈 |", '',
         f"## 要處理的鏡頭（{len(bad)} 個）", '']
    if bad:
        L += ['| 鏡頭 | 起訖 | 標記 | 改法 |', '|---|---|---|---|']
        for s in bad:
            L.append(f"| {s['i']} | {s['t0']:.1f}–{s['t1']:.1f} | {'、'.join(s['flags'])} | {'；'.join(s['fixes'])} |")
    else:
        L.append('沒有。')
    L += ['', '## 全部鏡頭', '', '| # | 起訖 | 黑 | 中 | 白 | 高光 ≥250 | 死黑 ≤3 | 偏色 a/b | 彩度 | 膚色角／亮 | 色階 |',
          '|---|---|---|---|---|---|---|---|---|---|---|']
    for s in S:
        cast = '—' if not s['cast'] else f"{s['cast'][0]:+.1f}/{s['cast'][1]:+.1f}"
        sk = '—' if not s['skin'] else f"{s['skin'][0]:.0f}°／{s['skin'][1]:.0f}"
        L.append(f"| {s['i']}{'（卡）' if s.get('card') else ''} | {s['t0']:.1f}–{s['t1']:.1f} | {s['black']:.0f} | {s['mid']:.0f} | {s['white']:.0f} | {s['clip']:.1%} | "
                 f"{s['crush']:.1%} | {cast} | {s['sat']:.0f} | {sk} | {'—' if s['band'] is None else s['band']} |")
    open(path, 'w').write('\n'.join(L) + '\n')


def finish(a, meta, S, thumbs):
    os.makedirs(a.out, exist_ok=True)
    U = judge(S)
    draw_strip(os.path.join(a.out, 'grade.jpg'), S, thumbs)
    draw_chart(os.path.join(a.out, 'grade.png'), S, U)
    json.dump(dict(meta=meta, th=TH, unity=U, shots=S), open(os.path.join(a.out, 'finish.json'), 'w'), ensure_ascii=False, indent=1)
    report(os.path.join(a.out, 'report.md'), meta, S, U)
    print(f"{a.out}/report.md\n{a.out}/grade.jpg\n{a.out}/grade.png")
    print(f"{len(S)} 個鏡頭、要處理 {sum(1 for s in S if s['flags'])} 個；黑位標準差 {U['black_sd']}、偏色分散 {U['cast_sd']}、"
          f"彩度 p95 中位數 {U['sat_med']}、最嚴重色階 {U['band_max']} px")


# ───────────────────────── 指令 ─────────────────────────
def cmd_check(a):
    if a.engine:
        import frames as FR
        m = FR.load(a.engine)
        shots = sorted([(float(s[0]), float(s[1])) for s in getattr(m, 'SHOTS', [])]) or \
            [(i * 2.0, min(m.TOTAL, (i + 1) * 2.0)) for i in range(int(math.ceil(m.TOTAL / 2)))]
        S, thumbs = [], {}
        for k, (t0, t1) in enumerate(shots):
            im = np.ascontiguousarray(m.frame((t0 + t1) / 2)[..., :3])
            if im.dtype != np.uint8:
                im = (np.clip(im, 0, 1) * 255 + 0.5).astype(np.uint8)
            s = dict(i=k + 1, t0=t0, t1=t1, **shot_summary([measure(im)]))
            S.append(s)
            thumbs[k + 1] = cv2.resize(im, (im.shape[1] // 4, im.shape[0] // 4), interpolation=cv2.INTER_AREA)
        finish(a, dict(source=os.path.abspath(a.engine), mode='engine：每個鏡頭中間 1 格（未壓縮，色階看不出壓檔後的樣子）', n=len(S)), S, thumbs)
        return
    times, ms, small, thumbs_all = [], [], [], []
    print(f'讀 {a.video}（每 {a.every} 秒抽一格全解析度）…', file=sys.stderr)
    for t, im in samples(a.video, a.every):
        times.append(t)
        ms.append(measure(im))
        sm = cv2.resize(im, (im.shape[1] // 4, im.shape[0] // 4), interpolation=cv2.INTER_AREA)
        small.append(sm)
    ids, spans = group(times, small, a.flow)
    S, thumbs = [], {}
    for k in sorted(set(ids)):
        idx = [j for j, s in enumerate(ids) if s == k]
        t0, t1 = spans[k]
        S.append(dict(i=k, t0=round(t0, 2), t1=round(t1, 2), **shot_summary([ms[j] for j in idx])))
        thumbs[k] = small[idx[len(idx) // 2]]
    finish(a, dict(source=os.path.abspath(a.video), mode='成片抽樣（含壓縮）', n=len(times)), S, thumbs)


def cmd_still(a):
    for p in a.images:
        im = np.asarray(Image.open(p).convert('RGB'))
        m = measure(im)
        print(p, json.dumps(m, ensure_ascii=False))


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = p.add_subparsers(dest='cmd', required=True)
    s = sp.add_parser('check')
    s.add_argument('video', nargs='?')
    s.add_argument('--engine')
    s.add_argument('--flow', help='flow.py 的 flow.json：用它的鏡頭切分')
    s.add_argument('--every', type=float, default=0.5, help='每幾秒抽一格（預設 0.5）')
    s.add_argument('-o', '--out', default='out/finish')
    s = sp.add_parser('still')
    s.add_argument('images', nargs='+')
    a = p.parse_args()
    if a.cmd == 'still':
        cmd_still(a)
    elif a.video or a.engine:
        cmd_check(a)
    else:
        sys.exit('給影片路徑或 --engine engine.py')


if __name__ == '__main__':
    main()
