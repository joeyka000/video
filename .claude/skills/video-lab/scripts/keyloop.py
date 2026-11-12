#!/usr/bin/env python3
"""舞蹈角色的前後處理：立繪 → 去背綠幕底（給影片生成當首尾幀）；生成的跳舞影片 → 摳像 RGBA 循環＋跟拍資訊。

  python keyloop.py plate 跳舞素材/*.png -o work/chars                 # 每張：去背、去地面陰影、決定綠幕或藍幕、9:16 底圖
  python keyloop.py key 生成/角色A.mp4 -o work/chars/A_clip --bpm 124    # 摳像 → f0000.png… RGBA ＋ clip.json
  python keyloop.py synth work/chars/A_cut.png -o test.mp4 --bpm 124      # 沒有生成影片時：用免費律動做一支綠幕測試片
  python keyloop.py matte 實拍.MOV -o work/chars/A_clip --from 1.0 --to 4.0 --bpm 128   # 實拍影片逐格去背 → 原地循環（來回播）
  python keyloop.py burst 連拍/*.JPG -o work/chars/B_clip                  # 連拍照片 → 每拍換一個姿勢的循環
  python keyloop.py marks work/chars/A_clip --beats 8                     # 重算落拍格（改一趟幾拍時）

plate 輸出（每張立繪）：
  <名>_cut.png    去背 RGBA（裁到主體），psyfx.Dancer 的靜態立繪來源（免費律動版）
  <名>_plate.png  1080×1920 純色底（綠 #00B040；衣服有綠色就換藍 #0047BB），主體高 78%、腳底在 92%：
                  頭上與兩側留空間給手臂與跳躍；這張同時當生成的首幀與尾幀（首尾同一張 → 影片可以無縫循環）
  <名>.json       {key, bbox（plate 上的主體框）, face, eyes（cut 上的比例座標，眼睛特寫用）, green_frac}
  去背：ISNet；白底／純色底的立繪會再去掉地面陰影（主體下緣 15% 內、顏色跟底色同色相但比較暗的像素）。
  綠藍判斷：主體上綠色像素（色相 70–170°、彩度 > 0.25）超過 0.5% 就用藍幕。
key 輸出：
  f0000.png…      RGBA（色差法摳像＋去溢色，裁到所有格主體聯集＋邊界；高度超過 --max-h 會縮）
  clip.json       {fps, n, n_loop（循環長度：尾格就是首格時少 1）, key, period（一拍幾格）, phase（第一個落拍格）,
                   seam（尾格→首格的差 ÷ 平常相鄰兩格的差：< 0.35 重複格、< 2 無縫、更大會頓）, size}
  跟拍：主體重心的上下位置做自相關，找 0.25–1.5 秒的週期；給 --bpm 時在 ×½、×1、×2 之中挑最接近歌的一拍。
  psyfx.Dancer 播放時把這段循環伸縮成剛好整數拍，落拍格對齊歌的拍點（跳舞跟拍點同步）。
matte／burst（不花錢的真人舞步：沒有生成影片時，用使用者自己的實拍當舞蹈來源）：
  每格：ISNet 去背（影片沿用上一格的範圍裁切後再去背，小的主體也有細節；照片用臉的位置挑對的那個人）
  正規化：把人固定在原地、同樣大小——影片用平滑過的身高與腳底位置（σ 0.5 秒：朝鏡頭走過來變成原地踏步，小跳與擺動留著）；
          照片估每張「站直時的身高」（輪廓高度與臉高換算差 10% 內用輪廓高度，否則用臉高）定大小、腳底貼地、重心置中。
          半身、腳出鏡的照片自動略過；蹲下、貼近鏡頭、去背失敗的要看過總覽後手動挑掉
  輸出 f0000.png…（含白色貼紙描邊，高 ≤ --h）＋ s0000.png…（小尺寸，並排用）＋ clip.json：
    mode "boomerang"（來回播，一趟 beats 拍；有量到腳步週期時一趟＝整數步，每一步落在拍上）或 "poses"（每 step 拍換一張）、
    eyes（每格兩眼中點的比例座標，眼睛特寫用）、src_h（來源身高 px：太小的不適合特寫）
"""
import argparse
import json
import math
import os
import subprocess
import sys

import cv2
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
KEYCOL = {'green': (0, 176, 64), 'blue': (0, 71, 187)}                   # RGB
KEYNAME = {'green': '綠幕', 'blue': '藍幕'}
YUNET = os.path.expanduser('~/video-lab/models/yunet.onnx')


def read_rgb(p):
    im = cv2.imread(p, cv2.IMREAD_UNCHANGED)
    if im is None:
        sys.exit(f'讀不到 {p}')
    if im.ndim == 2:
        im = cv2.cvtColor(im, cv2.COLOR_GRAY2BGR)
    alpha = None
    if im.shape[2] == 4:
        alpha = im[..., 3].astype(np.float32) / 255
        im = im[..., :3]
    return cv2.cvtColor(im, cv2.COLOR_BGR2RGB).astype(np.float32) / 255, alpha


def border_stats(img):
    b = np.concatenate([img[:8].reshape(-1, 3), img[-8:].reshape(-1, 3), img[:, :8].reshape(-1, 3), img[:, -8:].reshape(-1, 3)])
    return np.median(b, 0), float(b.std(0).mean())


def remove_ground_shadow(img, a):
    """純色底立繪：主體下緣 15% 內，色相接近底色、比底色暗的低彩度像素 → 透明（地面陰影）。"""
    bg, sd = border_stats(img)
    if sd > 0.06:                                      # 底不是純色（實拍照片）：不動，只把下緣的半透明清掉
        ys = np.nonzero(a.max(1) > 0.5)[0]
        if len(ys):
            y1 = ys.max()
            band = slice(int(y1 - 0.06 * (y1 - ys.min())), y1 + 1)
            a[band] = np.where(a[band] < 0.6, 0, a[band])
        return a, 0
    ys = np.nonzero(a.max(1) > 0.5)[0]
    if not len(ys):
        return a, 0
    y0, y1 = ys.min(), ys.max()
    top = int(y1 - 0.15 * (y1 - y0))
    reg = img[top:y1 + 1]
    # 陰影＝底色變暗（每個通道約同一個倍數 s，0.45–0.985）、平滑（5×5 標準差小），而且 ISNet 不確定（alpha < 0.9）。
    # 實測 ISNet 本身幾乎不收陰影（合成白底＋灰色橢圓陰影：主體外 alpha > 0.5 的只有 201 px，都在腳邊），
    # 所以只清不確定的部分；黑裙、白襪這種 alpha≈1 的主體不能動（第一版只看顏色，把它們一起刪了）
    s = (reg / np.maximum(bg, 1e-3)).mean(-1)
    dev = np.abs(reg - bg * s[..., None]).max(-1)
    g = cv2.cvtColor(reg, cv2.COLOR_RGB2GRAY)
    sd = np.sqrt(np.maximum(cv2.blur(g * g, (5, 5)) - cv2.blur(g, (5, 5)) ** 2, 0))
    sub = a[top:y1 + 1]
    shadow = (s > 0.45) & (s < 0.985) & (dev < 0.05) & (sd < 0.02) & (sub < 0.9)
    n = int((shadow & (sub > 0.05)).sum())
    sub = np.where(shadow, 0, sub).astype(np.float32)
    a[top:y1 + 1] = sub
    return a, n


def green_fraction(img, a):
    hsv = cv2.cvtColor((img * 255).astype(np.uint8), cv2.COLOR_RGB2HSV)
    m = a > 0.6
    hue = hsv[..., 0].astype(np.float32) * 2
    g = m & (hue > 70) & (hue < 170) & (hsv[..., 1] > 64) & (hsv[..., 2] > 40)
    return float(g.sum() / max(1, m.sum()))


def face_eyes(rgba):
    """YuNet：臉框與兩眼（cut 上的比例座標）。"""
    if not os.path.exists(YUNET):
        return None, None
    a = rgba[..., 3:4]
    comp = rgba[..., :3] * a + 0.5 * (1 - a)
    bgr = cv2.cvtColor((comp * 255).astype(np.uint8), cv2.COLOR_RGB2BGR)
    h, w = bgr.shape[:2]
    s = 640 / max(h, w)
    sm = cv2.resize(bgr, (max(1, int(w * s)), max(1, int(h * s))), interpolation=cv2.INTER_AREA)
    det = cv2.FaceDetectorYN.create(YUNET, '', (sm.shape[1], sm.shape[0]), 0.6, 0.3, 20)
    _, f = det.detect(sm)
    if f is None or not len(f):
        return None, None
    f = f[np.argmax(f[:, 2] * f[:, 3])]
    face = [float(f[0] / s / w), float(f[1] / s / h), float(f[2] / s / w), float(f[3] / s / h)]
    eyes = [[float(f[4] / s / w), float(f[5] / s / h)], [float(f[6] / s / w), float(f[7] / s / h)]]
    return face, eyes


def cmd_plate(a):
    import matte as MT
    os.makedirs(a.o, exist_ok=True)
    W, H = (int(v) for v in a.size.split('x'))
    for p in a.inputs:
        name = os.path.splitext(os.path.basename(p))[0]
        img, alpha = read_rgb(p)
        if alpha is not None and alpha.min() < 0.5:
            m = alpha                                       # 已經是去背 png
        else:
            m = MT.isnet(img, key=None)
        m, nshadow = remove_ground_shadow(img, m.copy())
        ys, xs = np.nonzero(m > 0.05)
        if not len(ys):
            print(f'{name}：找不到主體，略過')
            continue
        y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
        pad = 6
        y0, x0 = max(0, y0 - pad), max(0, x0 - pad)
        y1, x1 = min(img.shape[0], y1 + pad), min(img.shape[1], x1 + pad)
        cut = np.dstack([img[y0:y1, x0:x1], m[y0:y1, x0:x1]])
        if cut.shape[0] > a.max_h:
            k = a.max_h / cut.shape[0]
            cut = cv2.resize(cut, (int(cut.shape[1] * k), a.max_h), interpolation=cv2.INTER_AREA)
        gf = green_fraction(cut[..., :3], cut[..., 3])
        key = a.key if a.key != 'auto' else ('blue' if gf > 0.005 else 'green')
        out_cut = os.path.join(a.o, f'{name}_cut.png')
        cv2.imwrite(out_cut, cv2.cvtColor((np.clip(cut, 0, 1) * 255 + 0.5).astype(np.uint8), cv2.COLOR_RGBA2BGRA))
        # 9:16 純色底
        ch, cw = cut.shape[:2]
        k = min(H * a.h / ch, W * 0.80 / cw)
        sw, sh = int(cw * k), int(ch * k)
        spr = np.clip(cv2.resize(cut, (sw, sh), interpolation=cv2.INTER_AREA if k < 1 else cv2.INTER_CUBIC), 0, 1)   # 放大的立方插值會超出 0–1
        plate = np.ones((H, W, 3), np.float32) * np.float32(KEYCOL[key]) / 255
        px, py = int(W / 2 - sw / 2), int(H * a.foot - sh)
        al = spr[..., 3:4]
        plate[py:py + sh, px:px + sw] = plate[py:py + sh, px:px + sw] * (1 - al) + spr[..., :3] * al
        cv2.imwrite(os.path.join(a.o, f'{name}_plate.png'), cv2.cvtColor((np.clip(plate, 0, 1) * 255 + 0.5).astype(np.uint8), cv2.COLOR_RGB2BGR))
        face, eyes = face_eyes(cut)
        meta = dict(key=key, green_frac=round(gf, 4), shadow_px=nshadow, size=[W, H], bbox=[px, py, sw, sh], cut=out_cut,
                    face=face, eyes=eyes)
        json.dump(meta, open(os.path.join(a.o, f'{name}.json'), 'w'), ensure_ascii=False)
        print(f'{name}：{KEYNAME[key]}（綠色像素 {gf:.1%}）、地面陰影去掉 {nshadow} px、臉 {"有" if face else "沒找到"} → {name}_plate.png')


def frames_of(path, max_side=1280):
    cap = cv2.VideoCapture(path)
    fps = cap.get(cv2.CAP_PROP_FPS) or 24
    out = []
    while True:
        ok, f = cap.read()
        if not ok:
            break
        out.append(cv2.cvtColor(f, cv2.COLOR_BGR2RGB).astype(np.float32) / 255)
    return out, fps


def motion_period(cy, fps, beat_s=None):
    """主體重心上下位置 → (一拍幾格, 第一個落拍格)。"""
    x = np.asarray(cy, np.float64)
    if len(x) < 8:
        return float(len(x)), 0.0
    k = max(3, int(fps * 0.6)) | 1
    x = x - np.convolve(np.pad(x, k // 2, mode='edge'), np.ones(k) / k, 'valid')     # 去掉慢漂移
    x = (x - x.mean()) / (x.std() + 1e-9)
    n = len(x)
    ac = np.array([np.dot(x[:n - L], x[L:]) / (n - L) for L in range(n // 2)])
    lo, hi = max(2, int(0.25 * fps)), min(len(ac) - 1, int(1.5 * fps))
    if hi <= lo:
        return float(n), 0.0
    L = lo + int(np.argmax(ac[lo:hi]))
    # 拋物線內插讓週期有小數
    if 1 <= L < len(ac) - 1:
        y0, y1, y2 = ac[L - 1], ac[L], ac[L + 1]
        d = (y0 - y2) / (2 * (y0 - 2 * y1 + y2) + 1e-12)
        P = L + float(np.clip(d, -0.5, 0.5))
    else:
        P = float(L)
    if beat_s:
        target = beat_s * fps
        P = min((P * m for m in (0.5, 1.0, 2.0)), key=lambda q: abs(math.log(q / target)))
    # 落拍＝重心最低（y 最大）：把每格的位置摺到一個週期內求平均曲線
    ph = np.mod(np.arange(n), P)
    bins = max(4, int(round(P)))
    prof = np.array([x[(ph >= P * i / bins) & (ph < P * (i + 1) / bins)].mean() if np.any((ph >= P * i / bins) & (ph < P * (i + 1) / bins)) else 0
                     for i in range(bins)])
    phase = (np.argmax(prof) + 0.5) * P / bins
    return float(P), float(phase)


def cmd_key(a):
    from psyfx import key_rgba
    fr, fps = frames_of(a.clip)
    if not fr:
        sys.exit('影片讀不到任何格')
    bg, _ = border_stats(fr[0])
    key = a.key
    if key == 'auto':
        key = 'green' if bg[1] >= bg[2] else 'blue'
    rg = [key_rgba(f, key, a.lo, a.hi) for f in fr]
    A = np.max([r[..., 3] for r in rg], 0)
    ys, xs = np.nonzero(A > 0.1)
    pad = 12
    y0, y1 = max(0, ys.min() - pad), min(A.shape[0], ys.max() + pad)
    x0, x1 = max(0, xs.min() - pad), min(A.shape[1], xs.max() + pad)
    os.makedirs(a.o, exist_ok=True)
    cy = []
    k = min(1.0, a.max_h / (y1 - y0))
    for i, r in enumerate(rg):
        c = r[y0:y1, x0:x1]
        if k < 1:
            c = cv2.resize(c, (int(c.shape[1] * k), int(c.shape[0] * k)), interpolation=cv2.INTER_AREA)
        al = c[..., 3]
        yy = np.arange(al.shape[0], dtype=np.float32)[:, None]
        cy.append(float((al * yy).sum() / max(1e-6, al.sum())))
        cv2.imwrite(os.path.join(a.o, f'f{i:04d}.png'), cv2.cvtColor((np.clip(c, 0, 1) * 255 + 0.5).astype(np.uint8), cv2.COLOR_RGBA2BGRA))
    P, phase = motion_period(cy, fps, 60 / a.bpm if a.bpm else None)
    pm = lambda r: r[..., :3] * r[..., 3:]                                   # noqa: E731
    step = float(np.median([np.abs(pm(rg[i]) - pm(rg[i + 1])).mean() for i in range(0, len(rg) - 1, max(1, len(rg) // 24))]))
    seam_d = float(np.abs(pm(rg[-1]) - pm(rg[0])).mean())
    ratio = seam_d / max(step, 1e-6)                    # 尾格→首格的差 ÷ 平常相鄰兩格的差
    n_loop = len(rg) - 1 if ratio < 0.35 else len(rg)   # 尾格就是首格（首尾幀同一張）：循環時跳過重複的那格
    info = dict(fps=fps, n=len(rg), n_loop=n_loop, key=key, period=round(P, 3), phase=round(phase, 3), seam=round(ratio, 2),
                size=[int((x1 - x0) * k), int((y1 - y0) * k)], src=os.path.basename(a.clip), bpm_dance=round(60 * fps / P, 1))
    json.dump(info, open(os.path.join(a.o, 'clip.json'), 'w'))
    seam = ('尾格＝首格，循環時略過尾格' if ratio < 0.35 else '無縫（接點跟平常換格一樣）' if ratio < 2.0
            else f'接點跳動是平常的 {ratio:.1f} 倍：循環會頓一下，重生或換一段循環區間')
    print( f'{len(rg)} 格、{fps:g} fps、{KEYNAME[key]} → 舞步一拍 {P:.2f} 格（約 {info["bpm_dance"]} BPM）、落拍相位 {phase:.1f} 格、'
          f'循環接點 {seam}')


def cmd_synth(a):
    """沒有生成影片時的測試片：去背立繪在綠幕上用免費律動跳 --sec 秒（首尾同格），給 key 指令驗證流程。"""
    import psyfx as PX
    im = cv2.imread(a.cut, cv2.IMREAD_UNCHANGED)
    rgba = cv2.cvtColor(im, cv2.COLOR_BGRA2RGBA).astype(np.float32) / 255
    W, H, fps = 480, 854, 24
    beat = 60 / a.bpm
    n = int(round(a.sec * fps))
    nb = max(1, round(a.sec / beat))                       # 讓整段剛好整數拍（首尾同格）
    cmd = ['ffmpeg', '-v', 'error', '-y', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', f'{W}x{H}', '-r', str(fps), '-i', '-',
           '-c:v', 'libx264', '-crf', '14', '-pix_fmt', 'yuv420p', a.o]
    pr = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    for i in range(n):
        b = i / n * nb
        c = np.ones((H, W, 3), np.float32) * np.float32(KEYCOL['green']) / 255
        PX.put_dancer(c, rgba, PX.puppet(b, a.style), W / 2, H * 0.92, H * 0.78)
        pr.stdin.write((np.clip(c, 0, 1) * 255 + 0.5).astype(np.uint8).tobytes())
    pr.stdin.close()
    pr.wait()
    print(f'寫入 {a.o}（{n} 格、{nb} 拍、{a.style}）')


# ═════════ 實拍 → 舞步循環 ═════════
def _isnet_person(img, face=None, box=None):
    """img float32 RGB。box=(x0,y0,x1,y1) 時只在那個範圍去背。face=(cx, cy) 時挑含臉（或離臉最近）的連通塊，否則挑最大塊。"""
    import matte as MT
    H, W = img.shape[:2]
    if box is None:
        box = (0, 0, W, H)
    x0, y0, x1, y1 = [int(v) for v in box]
    m = MT.isnet(np.ascontiguousarray(img[y0:y1, x0:x1]), key=None, keep=0.02)
    bw = (m > 0.5).astype(np.uint8)
    n, lab, st, cen = cv2.connectedComponentsWithStats(bw, 8)
    if n <= 1:
        return np.zeros((H, W), np.float32)
    if face is not None:
        fx, fy = face[0] - x0, face[1] - y0
        best, bd = 1, 1e18
        for k in range(1, n):
            if st[k, cv2.CC_STAT_AREA] < 0.2 * st[1:, cv2.CC_STAT_AREA].max():
                continue
            bx, by, bw_, bh = st[k, :4]
            dx = max(bx - fx, 0, fx - (bx + bw_))
            dy = max(by - fy, 0, fy - (by + bh))
            d = dx * dx + dy * dy
            if d < bd:
                best, bd = k, d
    else:
        best = 1 + int(np.argmax(st[1:, cv2.CC_STAT_AREA]))
    keep = cv2.dilate((lab == best).astype(np.uint8), np.ones((9, 9), np.uint8))
    out = np.zeros((H, W), np.float32)
    out[y0:y1, x0:x1] = m * keep
    return out


def _bbox(a, thr=0.5):
    ys, xs = np.nonzero(a > thr)
    if not len(ys):
        return None
    return int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1


def _expand(b, W, H, m=0.18):
    x0, y0, x1, y1 = b
    dx, dy = (x1 - x0) * m, (y1 - y0) * m
    return max(0, int(x0 - dx)), max(0, int(y0 - dy)), min(W, int(x1 + dx)), min(H, int(y1 + dy))


def _face(bgr_u8, thr=0.6):
    """最大的一張臉 → (x, y, w, h, 兩眼中點 x, y)；沒有回 None。"""
    if not os.path.exists(YUNET):
        return None
    h, w = bgr_u8.shape[:2]
    s = 640 / max(h, w)
    sm = cv2.resize(bgr_u8, (max(1, int(w * s)), max(1, int(h * s))), interpolation=cv2.INTER_AREA)
    det = cv2.FaceDetectorYN.create(YUNET, '', (sm.shape[1], sm.shape[0]), thr, 0.3, 50)
    _, f = det.detect(sm)
    if f is None or not len(f):
        return None
    f = f[np.argmax(f[:, 2] * f[:, 3])] / s
    return float(f[0]), float(f[1]), float(f[2]), float(f[3]), float((f[4] + f[6]) / 2), float((f[5] + f[7]) / 2)


def _gauss(x, sigma):
    x = np.asarray(x, np.float64)
    if sigma <= 0.3 or len(x) < 3:
        return x
    r = int(max(1, round(3 * sigma)))
    k = np.exp(-0.5 * (np.arange(-r, r + 1) / sigma) ** 2)
    k /= k.sum()
    return np.convolve(np.pad(x, r, mode='edge'), k, 'valid')


def _write_clip(out, items, info, body_h, small_h=560, sticker_frac=0.012):
    """items = [(rgb float32 裁好的圖, alpha, 縮放 k, 腳底錨點 (ax, ay)（裁圖座標）, 眼睛 (ex, ey) 或 None)]。
    每格縮放後貼到同一張畫布（腳底錨點在畫布底部中央），加貼紙描邊，存大小兩種尺寸。"""
    from psyfx import sticker
    os.makedirs(out, exist_ok=True)
    for f in os.listdir(out):
        if f.endswith('.png'):
            os.remove(os.path.join(out, f))
    L = R = T = 0.0
    for rgb, a, k, (ax, ay), _ in items:
        b = _bbox(a, 0.1)
        if b is None:
            continue
        L, R = max(L, (ax - b[0]) * k), max(R, (b[2] - ax) * k)
        T = max(T, (ay - b[1]) * k)
    half = int(math.ceil(max(L, R))) + 4
    Wc, Hc = 2 * half, int(math.ceil(T)) + 6
    px = max(2, int(round(body_h * sticker_frac)))
    eyes = []
    for i, (rgb, a, k, (ax, ay), eye) in enumerate(items):
        M = np.float32([[k, 0, half - ax * k], [0, k, Hc - 2 - ay * k]])
        interp = cv2.INTER_AREA if k < 0.8 else cv2.INTER_CUBIC
        pm = np.dstack([rgb * a[..., None], a])
        if k < 0.5:                                         # 大縮小先縮階
            f = int(1 / k / 1.4)
            if f > 1:
                pm = cv2.resize(pm, (pm.shape[1] // f, pm.shape[0] // f), interpolation=cv2.INTER_AREA)
                M[:, :2] *= f
            interp = cv2.INTER_LINEAR
        w = np.clip(cv2.warpAffine(pm, M, (Wc, Hc), flags=interp, borderMode=cv2.BORDER_CONSTANT, borderValue=0), 0, 1)
        al = w[..., 3]
        rgba = np.dstack([w[..., :3] / np.maximum(al[..., None], 1e-4) * (al[..., None] > 1e-3), al]).astype(np.float32)
        st = sticker(np.clip(rgba, 0, 1), px=px)
        pad = (st.shape[0] - Hc) // 2
        if i == 0:
            info['size'] = [st.shape[1], st.shape[0]]
            info['anchor'] = [0.5, round((Hc - 2 + pad) / st.shape[0], 4)]
        cv2.imwrite(os.path.join(out, f'f{i:04d}.png'), cv2.cvtColor((np.clip(st, 0, 1) * 255 + 0.5).astype(np.uint8), cv2.COLOR_RGBA2BGRA),
                    [cv2.IMWRITE_PNG_COMPRESSION, 1])
        ks = small_h / st.shape[0]
        if ks < 1:
            sm = cv2.resize(np.dstack([st[..., :3] * st[..., 3:], st[..., 3]]), (max(1, int(st.shape[1] * ks)), small_h), interpolation=cv2.INTER_AREA)
            sm = np.dstack([sm[..., :3] / np.maximum(sm[..., 3:], 1e-4) * (sm[..., 3:] > 1e-3), sm[..., 3]])
        else:
            sm = st
        cv2.imwrite(os.path.join(out, f's{i:04d}.png'), cv2.cvtColor((np.clip(sm, 0, 1) * 255 + 0.5).astype(np.uint8), cv2.COLOR_RGBA2BGRA),
                    [cv2.IMWRITE_PNG_COMPRESSION, 1])
        if eye is not None:
            ex, ey = M @ np.array([eye[0], eye[1], 1.0])
            eyes.append([round(float((ex + pad) / st.shape[1]), 4), round(float((ey + pad) / st.shape[0]), 4)])
        else:
            eyes.append(None)
    info.update(n=len(items), stickered=True, eyes=eyes, body_h=int(body_h))
    json.dump(info, open(os.path.join(out, 'clip.json'), 'w'), ensure_ascii=False)


def beat_marks(d, beats):
    """把「姿勢停住、手腳伸得最開」的格對到每一拍：回傳 beats＋1 個格序（頭尾固定）。
    每格的分數 = 伸展（輪廓寬÷高的 z 分數）− 0.7×動作量（跟前一格輪廓差的 z 分數）；每一拍在理想位置 ±38% 拍長內挑分數最高的格。"""
    files = sorted(f for f in os.listdir(d) if f.startswith('s') and f.endswith('.png'))
    A = []
    for f in files:
        a_ = cv2.imread(os.path.join(d, f), cv2.IMREAD_UNCHANGED)[..., 3]
        A.append(cv2.resize(a_, (max(1, a_.shape[1] * 140 // a_.shape[0]), 140), interpolation=cv2.INTER_AREA).astype(np.float32) / 255)
    n = len(A)
    ext, mot = np.zeros(n), np.zeros(n)
    for i, a_ in enumerate(A):
        ys, xs = np.nonzero(a_ > 0.5)
        ext[i] = (xs.max() - xs.min()) / max(1, ys.max() - ys.min()) if len(xs) else 0
        if i:
            mot[i] = float(np.abs(a_ - A[i - 1]).mean())
    mot[0] = mot[1] if n > 1 else 0
    z = lambda x: (x - x.mean()) / (x.std() + 1e-9)                      # noqa: E731
    score = z(_gauss(ext, 1.0)) - 0.7 * z(_gauss(mot, 1.0))
    step = (n - 1) / beats
    marks = [0]
    for j in range(1, beats):
        lo = max(marks[-1] + int(0.45 * step), int(round(j * step - 0.38 * step)))
        hi = min(n - 1 - int(0.45 * step) * (beats - j), int(round(j * step + 0.38 * step)))
        marks.append(lo + int(np.argmax(score[lo:hi + 1])) if hi > lo else int(round(j * step)))
    return marks + [n - 1]


def cmd_marks(a):
    p = os.path.join(a.dir, 'clip.json')
    J = json.load(open(p))
    if a.beats:
        J['beats'] = a.beats
    J['marks'] = beat_marks(a.dir, int(J['beats']))
    json.dump(J, open(p, 'w'), ensure_ascii=False)
    even = [round(k * (J['n'] - 1) / J['beats']) for k in range(J['beats'] + 1)]
    print(f'{a.dir}：一趟 {J["beats"]} 拍，落拍格 {J["marks"]}（等距會是 {even}）')


def cmd_matte(a):
    """實拍影片 → 原地循環。"""
    pr = subprocess.run(['ffprobe', '-v', 'error', '-select_streams', 'v:0', '-show_entries', 'stream=width,height,r_frame_rate:stream_side_data=rotation',
                         '-of', 'json', a.clip], capture_output=True, text=True).stdout
    st = json.loads(pr)['streams'][0]
    w, h = st['width'], st['height']
    rot = abs(int((st.get('side_data_list') or [{}])[0].get('rotation', 0) or 0))
    if rot in (90, 270):
        w, h = h, w
    k0 = min(1.0, a.max_side / max(w, h))
    W, H = int(w * k0) // 2 * 2, int(h * k0) // 2 * 2
    cmd = ['ffmpeg', '-v', 'error', '-nostdin', '-ss', str(a.t0), '-t', str(a.t1 - a.t0), '-i', a.clip,
           '-vf', f'fps={a.fps},scale={W}:{H}:flags=area', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-']
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE)
    crops, met = [], []
    box = None
    i = 0
    while True:
        raw = p.stdout.read(W * H * 3)
        if len(raw) < W * H * 3:
            break
        img = np.frombuffer(raw, np.uint8).reshape(H, W, 3).astype(np.float32) / 255
        if box is None:
            al = _isnet_person(img)
            b = _bbox(al)
            if b is None:
                sys.exit('第一格找不到人')
        for _ in range(2):                                  # 沿用上一格的範圍；主體碰到裁切邊就放大再做一次
            bx = _expand(box or b, W, H, 0.22)
            al = _isnet_person(img, box=bx)
            b = _bbox(al)
            if b is None:
                break
            touch = (b[0] <= bx[0] + 1 and bx[0] > 0) or (b[2] >= bx[2] - 1 and bx[2] < W) or (b[1] <= bx[1] + 1 and bx[1] > 0) or (b[3] >= bx[3] - 1 and bx[3] < H)
            box = b
            if not touch:
                break
        if b is None:
            print(f'第 {i} 格找不到人，略過')
            i += 1
            continue
        c = _expand(b, W, H, 0.04)
        ys, xs = np.nonzero(al[c[1]:c[3], c[0]:c[2]] > 0.5)
        cx = float(xs.mean()) + c[0]
        fc = _face((img[c[1]:c[3], c[0]:c[2], ::-1] * 255).astype(np.uint8), 0.5)
        eye = (fc[4], fc[5]) if fc else None
        crops.append(((img[c[1]:c[3], c[0]:c[2]] * 255).astype(np.uint8), (al[c[1]:c[3], c[0]:c[2]] * 255).astype(np.uint8), c, eye))
        met.append((b[1], b[3], cx, float(ys.mean()) + c[1]))
        i += 1
        if i % 20 == 0:
            print(f'  去背 {i} 格', flush=True)
    p.wait()
    if len(crops) < 4:
        sys.exit('可用的格太少')
    met = np.array(met, np.float64)
    hgt = met[:, 1] - met[:, 0]
    sg = a.smooth * a.fps
    hs = np.exp(_gauss(np.log(hgt), sg))
    ys_ = _gauss(met[:, 1], sg)
    xs_ = _gauss(met[:, 2], sg)
    body = min(a.h, float(np.median(hgt)) * 1.3)
    cy_rel = (met[:, 3] - ys_) / hs                        # 重心相對腳底的高度（身高比例）：腳步的上下起伏
    P, phase = motion_period(cy_rel, a.fps, 60 / a.bpm if a.bpm else None)
    items = []
    for (rgb, al, c, eye), hh, yb, xc in zip(crops, hs, ys_, xs_):
        items.append((rgb.astype(np.float32) / 255, al.astype(np.float32) / 255, body / hh, (xc - c[0], yb - c[1]), eye))
    n = len(items)
    beat = 60 / a.bpm if a.bpm else 0.5
    beats = a.beats or max(1, int(round((n / a.fps) / beat / a.speed)))
    info = dict(mode='boomerang', fps=a.fps, beats=beats, src=os.path.basename(a.clip), t0=a.t0, t1=a.t1, src_h=int(np.median(hgt)),
                step_period=round(P, 2), step_phase=round(phase, 2))
    _write_clip(a.o, items, info, body)
    J = json.load(open(os.path.join(a.o, 'clip.json')))
    J['marks'] = beat_marks(a.o, beats)
    json.dump(J, open(os.path.join(a.o, 'clip.json'), 'w'), ensure_ascii=False)
    print(f'{n} 格、來源身高約 {int(np.median(hgt))} px → 輸出身高 {int(body)} px；身高變化 {hgt.min():.0f}–{hgt.max():.0f} px（已正規化）；'
          f'腳步週期 {P:.1f} 格（{a.fps / P:.2f} 步/秒）；來回播一趟 {beats} 拍')


def cmd_burst(a):
    """連拍照片 → 姿勢循環。"""
    from PIL import Image, ImageOps
    rows = []
    for pth in a.inputs:
        im = Image.open(pth)
        im.draft('RGB', (a.max_side, a.max_side))
        im = ImageOps.exif_transpose(im).convert('RGB')
        if max(im.size) > a.max_side:
            k = a.max_side / max(im.size)
            im = im.resize((int(im.size[0] * k), int(im.size[1] * k)), Image.LANCZOS)
        img = np.asarray(im).astype(np.float32) / 255
        H, W = img.shape[:2]
        fc = _face((img[..., ::-1] * 255).astype(np.uint8), 0.7)
        name = os.path.basename(pth)
        if fc is None:
            print(f'  {name}：沒找到臉，略過')
            continue
        al = _isnet_person(img, face=(fc[0] + fc[2] / 2, fc[1] + fc[3] / 2))
        b = _bbox(al)
        if b is None:
            continue
        bh = b[3] - b[1]
        if b[3] >= H - 3 or b[1] <= 2 or bh / fc[3] < a.min_heads:
            print(f'  {name}：不是全身（身高／臉高 {bh / fc[3]:.1f}、腳{"出鏡" if b[3] >= H - 3 else "在"}），略過')
            continue
        c = _expand(b, W, H, 0.03)
        ys, xs = np.nonzero(al[c[1]:c[3], c[0]:c[2]] > 0.5)
        rows.append(dict(name=name, rgb=img[c[1]:c[3], c[0]:c[2]].copy(), al=al[c[1]:c[3], c[0]:c[2]].copy(), c=c, face_h=fc[3],
                         eye=(fc[4] - c[0], fc[5] - c[1]), foot=(float(xs.mean()), float(b[3] - c[1])), bh=bh))
        print(f'  {name}：身高 {bh} px、臉高 {fc[3]:.0f} px')
    if len(rows) < 2:
        sys.exit('可用的全身照不到 2 張')
    # 大小：每張照片估「站直時的身高」。站姿的輪廓高度最準（±2%），但踢腿、彎腰、舉手時輪廓高度會變；
    # 臉高×頭身比不受姿勢影響，但 YuNet 的臉框有 ±8% 雜訊。兩者差 10% 以內就信輪廓高度，否則用臉高換算。
    # 試過的另外兩種：全部用臉高（拍得遠的那幾張整組小 12%）；依相鄰身高差分組取中位數（攝影者慢慢後退時組內大小不一）
    fh = np.array([r['face_h'] for r in rows])
    bh = np.array([r['bh'] for r in rows], np.float64)
    heads = float(np.median(bh / fh))
    stand = np.where(np.abs(bh / (fh * heads) - 1) < 0.10, bh, fh * heads)
    n_face = int((stand != bh).sum())
    body = min(a.h, float(np.median(bh)) * 1.1)
    items = [(r['rgb'], r['al'], body / st_, r['foot'], r['eye']) for r, st_ in zip(rows, stand)]
    info = dict(mode='poses', step=a.step, names=[r['name'] for r in rows], src_h=int(np.median([r['bh'] for r in rows])))
    _write_clip(a.o, items, info, body)
    print(f'{len(items)} 個姿勢（{n_face} 張姿勢特殊、改用臉高定大小）、來源身高約 {info["src_h"]} px → 輸出 {int(body)} px；每 {a.step} 拍換一張')


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = p.add_subparsers(dest='cmd', required=True)
    q = sp.add_parser('plate')
    q.add_argument('inputs', nargs='+')
    q.add_argument('-o', required=True)
    q.add_argument('--size', default='1080x1920')
    q.add_argument('--h', type=float, default=0.78, help='主體高佔畫面比例')
    q.add_argument('--foot', type=float, default=0.92, help='腳底位置（畫面高比例）')
    q.add_argument('--key', choices=['auto', 'green', 'blue'], default='auto')
    q.add_argument('--max-h', type=int, default=1600)
    q = sp.add_parser('key')
    q.add_argument('clip')
    q.add_argument('-o', required=True)
    q.add_argument('--key', choices=['auto', 'green', 'blue'], default='auto')
    q.add_argument('--lo', type=float, default=0.06)
    q.add_argument('--hi', type=float, default=0.22)
    q.add_argument('--bpm', type=float)
    q.add_argument('--max-h', type=int, default=900)
    q = sp.add_parser('synth')
    q.add_argument('cut')
    q.add_argument('-o', required=True)
    q.add_argument('--bpm', type=float, default=120)
    q.add_argument('--sec', type=float, default=5.0)
    q.add_argument('--style', default='bounce')
    q = sp.add_parser('matte')
    q.add_argument('clip')
    q.add_argument('-o', required=True)
    q.add_argument('--from', dest='t0', type=float, default=0.0)
    q.add_argument('--to', dest='t1', type=float, default=3.0)
    q.add_argument('--fps', type=float, default=30.0)
    q.add_argument('--bpm', type=float)
    q.add_argument('--beats', type=int, help='來回播一趟幾拍（預設依原速與 --speed 算）')
    q.add_argument('--speed', type=float, default=1.0, help='比原速快幾倍（算一趟幾拍用）')
    q.add_argument('--smooth', type=float, default=0.5, help='身高與位置的平滑秒數（越大保留越多跳動）')
    q.add_argument('--h', type=int, default=1200, help='輸出身高上限 px')
    q.add_argument('--max-side', type=int, default=2880, help='解碼時長邊上限')
    q = sp.add_parser('burst')
    q.add_argument('inputs', nargs='+')
    q.add_argument('-o', required=True)
    q.add_argument('--step', type=float, default=1.0, help='每幾拍換一個姿勢')
    q.add_argument('--h', type=int, default=1200)
    q.add_argument('--max-side', type=int, default=3000)
    q.add_argument('--min-heads', type=float, default=4.6, help='身高／臉高低於這個值當成半身照略過')
    q = sp.add_parser('marks')
    q.add_argument('dir')
    q.add_argument('--beats', type=int, help='改一趟幾拍')
    a = p.parse_args()
    {'plate': cmd_plate, 'key': cmd_key, 'synth': cmd_synth, 'matte': cmd_matte, 'burst': cmd_burst, 'marks': cmd_marks}[a.cmd](a)


if __name__ == '__main__':
    main()
