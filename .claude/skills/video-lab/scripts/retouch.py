#!/usr/bin/env python3
"""照片精修（旅行、人像）：曝光拉到日系的亮、臉部柔光補光、柔膚、膚色以外細銳化、自然飽和度。
釜山情侶片 v2 用的版本：使用者說「精修、打亮」時，每張照片先過這一層再進引擎調色（look.py 的 mood）。
  1. 曝光：中間調往 0.53 拉（只動中間調，高光柔肩、黑位微抬）；夜景、暗場不硬拉
  2. 臉部打亮：YuNet 找臉（~/video-lab/models/yunet.onnx），臉周圍柔和的橢圓補光（＋19%、微暖）
  3. 柔膚：只在臉與脖子的膚色區做保邊平滑（雙邊濾波 50%），留住五官邊緣
  4. 清晰度：膚色以外細銳化（頭髮、衣服、背景）
  5. 自然飽和度：低飽和處多加一點，已經鮮豔的不動
  python retouch.py in.jpg [in2.jpg ...] -o out_dir [--faces faces.json]
"""
import argparse
import json
import os
from concurrent.futures import ProcessPoolExecutor

import cv2
import numpy as np

YUNET = os.path.expanduser('~/video-lab/models/yunet.onnx')


def faces(bgr):
    h, w = bgr.shape[:2]
    s = 640 / max(h, w)
    sm = cv2.resize(bgr, (int(w * s), int(h * s)), interpolation=cv2.INTER_AREA)
    det = cv2.FaceDetectorYN.create(YUNET, '', (sm.shape[1], sm.shape[0]), 0.75, 0.3, 50)
    _, f = det.detect(sm)
    out = []
    for x in (f if f is not None else []):
        fx, fy, fw, fh = (float(v) / s for v in x[:4])
        if fw * fh > 0.0015 * w * h:
            out.append((fx, fy, fw, fh))
    return out


def lum(x):
    return x[..., 0] * 0.114 + x[..., 1] * 0.587 + x[..., 2] * 0.299        # BGR


def retouch(bgr):
    x = bgr.astype(np.float32) / 255
    h, w = x.shape[:2]
    # 1. 曝光（中間調 gamma，目標 0.50；夜景、暗場不硬拉）
    L = lum(x)
    med = float(np.median(L))
    g = np.clip(np.log(0.53) / np.log(max(min(med, 0.92), 0.08)), 0.68, 1.10)
    if med < 0.18:
        g = max(g, 0.88)
    Lg = np.clip(L, 1e-4, 1) ** g
    x = x * (Lg / np.clip(L, 1e-4, 1))[..., None]
    x = 1 - (1 - np.clip(x, 0, 1.6)) / (1 + np.clip(x - 1, 0, None) * 1.5)      # 柔肩：超過 1 的壓回來
    x = (np.clip(x, 0, 1) * 0.985 + 0.015).astype(np.float32)
    # 2. 臉部打亮＋3. 柔膚
    F = faces(bgr)
    if F:
        yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
        light = np.zeros((h, w), np.float32)
        region = np.zeros((h, w), np.float32)
        for fx, fy, fw, fh in F:
            cx, cy = fx + fw / 2, fy + fh * 0.55
            light = np.maximum(light, np.exp(-(((xx - cx) / (fw * 1.25)) ** 2 + ((yy - cy) / (fh * 1.35)) ** 2)))
            region = np.maximum(region, np.exp(-(((xx - cx) / (fw * 0.95)) ** 2 + ((yy - cy - fh * 0.25) / (fh * 1.25)) ** 2)))
        x = x * (1 + 0.19 * light[..., None] * np.float32([0.97, 1.0, 1.04]))      # BGR：微暖
        u8 = (np.clip(x, 0, 1) * 255).astype(np.uint8)
        ycc = cv2.cvtColor(u8, cv2.COLOR_BGR2YCrCb).astype(np.float32)
        skin = np.exp(-(((ycc[..., 1] - 152) / 14) ** 2 + ((ycc[..., 2] - 112) / 12) ** 2))
        skin = cv2.GaussianBlur(skin * region, (0, 0), 3)
        sm = cv2.bilateralFilter(np.clip(x, 0, 1).astype(np.float32), 0, 0.06, max(4, int(min(F[0][2], F[0][3]) * 0.03))).astype(np.float32)
        k = (0.50 * np.clip(skin * 1.4, 0, 1))[..., None]
        x = x * (1 - k) + sm * k
    else:
        skin = np.zeros((h, w), np.float32)
    # 4. 清晰度（膚色以外）
    bl = cv2.GaussianBlur(x, (0, 0), 1.4)
    sharp = x + (x - bl) * 0.45
    ks = (1 - np.clip(skin * 1.5, 0, 1))[..., None]
    x = x * (1 - ks) + sharp * ks
    # 5. 自然飽和度
    L = lum(x)[..., None]
    sat = np.abs(x - L).max(-1, keepdims=True)
    x = L + (x - L) * (1 + 0.14 * np.clip(1 - sat * 4, 0, 1))
    return (np.clip(x, 0, 1) * 255 + 0.5).astype(np.uint8), len(F)

def _one(args):
    path, out_dir = args
    bgr = cv2.imread(path)
    out = os.path.join(out_dir, os.path.basename(path))
    r, _ = retouch(bgr)
    cv2.imwrite(out, r, [cv2.IMWRITE_JPEG_QUALITY, 95])
    h, w = bgr.shape[:2]
    return os.path.basename(path), [(fx / w, fy / h, fw / w, fh / h) for fx, fy, fw, fh in faces(bgr)]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('inputs', nargs='+')
    ap.add_argument('-o', '--out', required=True)
    ap.add_argument('--faces', help='把每張的臉框（0–1 相對座標）存成 json，取景與摳圖用')
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    with ProcessPoolExecutor(4) as ex:
        res = list(ex.map(_one, [(p, a.out) for p in a.inputs]))
    if a.faces:
        json.dump(dict(res), open(a.faces, 'w'), ensure_ascii=False)
    print(f'精修 {len(res)} 張，{sum(1 for _, f in res if f)} 張有臉 → {a.out}')


if __name__ == '__main__':
    main()
