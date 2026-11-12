#!/usr/bin/env python3
"""舞蹈角色的前後處理：立繪 → 去背綠幕底（給影片生成當首尾幀）；生成的跳舞影片 → 摳像 RGBA 循環＋跟拍資訊。

  python keyloop.py plate 跳舞素材/*.png -o work/chars                 # 每張：去背、去地面陰影、決定綠幕或藍幕、9:16 底圖
  python keyloop.py key 生成/角色A.mp4 -o work/chars/A_clip --bpm 124    # 摳像 → f0000.png… RGBA ＋ clip.json
  python keyloop.py synth work/chars/A_cut.png -o test.mp4 --bpm 124      # 沒有生成影片時：用免費律動做一支綠幕測試片

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
    a = p.parse_args()
    {'plate': cmd_plate, 'key': cmd_key, 'synth': cmd_synth}[a.cmd](a)


if __name__ == '__main__':
    main()
