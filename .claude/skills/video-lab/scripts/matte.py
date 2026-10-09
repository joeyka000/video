"""遮罩與深度：去背（ISNet）、單張深度（Depth-Anything-V2-Small）、照片 2.5D 視差運鏡、主體輪廓光。

結果都存進磁碟快取（~/video-lab/cache/matte/），平行渲染的每個行程不用重算；鍵＝(來源鍵, 尺寸)。
  import matte as MT
  m = MT.isnet(img, key='4037@3.4')            # 0–1 主體遮罩（同尺寸）
  d = MT.depth(img, key='P4110')               # 0＝遠、1＝近
  out = MT.parallax(img, d, dx=0.02, dz=0.04)  # 鏡頭往右平移 2% 寬、往前推 4%：近的動得多，遠的動得少
  MT.rim(c, m, col, k)                         # 沿遮罩邊緣的輪廓光（掃描、登場用）
模型：~/video-lab/models/isnet.onnx；Depth-Anything 走 transformers（session-start 已下載到 HF 快取）。
"""
import functools
import hashlib
import os

import cv2
import numpy as np

CACHE = os.path.expanduser('~/video-lab/cache/matte')
_S = {}


def _cache(kind, key, shape):
    if key is None:
        return None
    h = hashlib.md5(f'{kind}|{key}|{shape[0]}x{shape[1]}'.encode()).hexdigest()[:16]
    return os.path.join(CACHE, f'{kind}_{h}.npy')


def _load(p):
    if p and os.path.exists(p):
        try:
            return np.load(p)
        except Exception:  # noqa: BLE001
            return None
    return None


def _save(p, a):
    if p:
        os.makedirs(CACHE, exist_ok=True)
        tmp = f'{p}.{os.getpid()}.tmp.npy'
        np.save(tmp, a)
        os.replace(tmp, p)


def isnet(img, key=None, keep=0.15, lo=0.3, hi=0.7):
    """通用顯著物體去背（ISNet）。img float32 RGB 0–1。回傳同尺寸 0–1 遮罩（保留面積 ≥ 最大塊 keep 倍的連通塊）。"""
    p = _cache('isnet', key, img.shape)
    m = _load(p)
    if m is not None:
        return m
    import onnxruntime as ort
    if 'isnet' not in _S:
        o = ort.SessionOptions()
        o.intra_op_num_threads = 4
        _S['isnet'] = ort.InferenceSession(os.path.expanduser('~/video-lab/models/isnet.onnx'), o, providers=['CPUExecutionProvider'])
    s = _S['isnet']
    h, w = img.shape[:2]
    x = cv2.resize(img, (1024, 1024), interpolation=cv2.INTER_AREA) - 0.5
    out = s.run(None, {s.get_inputs()[0].name: x.transpose(2, 0, 1)[None].astype(np.float32)})[0][0, 0]
    out = (out - out.min()) / (out.max() - out.min() + 1e-6)
    m = cv2.resize(out, (w, h), interpolation=cv2.INTER_CUBIC).astype(np.float32)
    try:
        m = cv2.ximgproc.guidedFilter(cv2.cvtColor(img.astype(np.float32), cv2.COLOR_RGB2GRAY), m, 6, 1e-3)
    except Exception:  # noqa: BLE001
        pass
    m = np.clip((m - lo) / (hi - lo), 0, 1)
    bw = (m > 0.5).astype(np.uint8)
    n, lab, st, _ = cv2.connectedComponentsWithStats(bw, 8)
    if n > 1:
        big = st[1:, cv2.CC_STAT_AREA].max()
        ok = np.zeros(n, bool)
        ok[1:] = st[1:, cv2.CC_STAT_AREA] > big * keep
        m = m * cv2.dilate(ok[lab].astype(np.uint8), np.ones((9, 9), np.uint8))
    m = m.astype(np.float32)
    _save(p, m)
    return m


def depth(img, key=None, size=(384, 672)):
    """單張深度（相對值）：0＝最遠、1＝最近；邊緣用導向濾波貼回原圖，視差時才不會撕裂。"""
    p = _cache('depth', key, img.shape)
    d = _load(p)
    if d is not None:
        return d
    if 'depth' not in _S:
        import torch
        from transformers import pipeline
        torch.set_num_threads(2)
        _S['depth'] = pipeline('depth-estimation', model='depth-anything/Depth-Anything-V2-Small-hf', device='cpu')
    from PIL import Image
    h, w = img.shape[:2]
    sw, sh = size if h >= w else size[::-1]
    pil = Image.fromarray((np.clip(img, 0, 1) * 255).astype(np.uint8)).resize((sw, sh), Image.BILINEAR)
    d = _S['depth'](pil)['predicted_depth'].squeeze().numpy().astype(np.float32)
    d = (d - np.percentile(d, 1)) / (np.percentile(d, 99.5) - np.percentile(d, 1) + 1e-6)
    d = cv2.resize(np.clip(d, 0, 1), (w, h), interpolation=cv2.INTER_CUBIC)
    try:
        d = cv2.ximgproc.guidedFilter(cv2.cvtColor(img.astype(np.float32), cv2.COLOR_RGB2GRAY), d, 8, 1e-3)
    except Exception:  # noqa: BLE001
        d = cv2.GaussianBlur(d, (0, 0), 2)
    d = np.clip(d, 0, 1).astype(np.float32)
    _save(p, d)
    return d


@functools.lru_cache(maxsize=8)
def _grid(h, w):
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    return xx, yy


def _spread(d, r):
    """近景邊緣往外擴一點（最大值濾波＋柔化）：位移時前景邊上的背景跟著走，不會被拉成一條條。"""
    if r <= 0:
        return d
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r + 1, 2 * r + 1))
    return cv2.GaussianBlur(cv2.dilate(d, k), (0, 0), r * 0.6)


def parallax(img, d, dx=0.0, dy=0.0, dz=0.0, focus=0.0, cx=0.5, cy=0.5, spread=6, gamma=1.0):
    """2.5D 視差：鏡頭平移 (dx, dy)（以寬的比例）＋往前推 dz。每個像素的位移 ∝ (深度 − focus)。
    focus＝不動的那個深度（0＝背景不動、前景動；0.5＝中景不動，前後反向）。位移量建議 ≤ 3% 寬，超過會看到拉扯。"""
    h, w = img.shape[:2]
    dd = _spread(d, spread) ** gamma - focus
    xx, yy = _grid(h, w)
    px, py = cx * w, cy * h
    ox = dx * w * dd + (xx - px) * dz * dd
    oy = dy * w * dd + (yy - py) * dz * dd
    return cv2.remap(img, xx - ox, yy - oy, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)


def edge(m, width=3.0):
    """遮罩的邊緣帶（0–1）：輪廓光、掃描線碰到主體邊緣時用。"""
    g = cv2.morphologyEx(m, cv2.MORPH_GRADIENT, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3)))
    return np.clip(cv2.GaussianBlur(g, (0, 0), width) * 3.0, 0, 1)


def rim(c, m, col=(1.0, 0.92, 0.70), k=1.0, width=3.0, glow=14.0):
    """沿主體輪廓的光（加光合成）：細邊＋寬光暈。m 跟畫布同尺寸。"""
    if k <= 0:
        return
    e = edge(m, width)
    g = cv2.GaussianBlur(e, (0, 0), glow)
    lay = (e * 0.9 + g * 1.4)[..., None] * np.float32(col) * k
    c[:] = 1 - (1 - c) * (1 - np.clip(lay, 0, 1))


def bbox(m, thr=0.5, pad=0):
    ys, xs = np.nonzero(m > thr)
    if len(xs) == 0:
        return None
    return max(0, xs.min() - pad), max(0, ys.min() - pad), xs.max() + pad, ys.max() + pad
