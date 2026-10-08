#!/usr/bin/env python3
"""看不見的精度回歸測試：改過 seekkit.py／look.py／finish.py 之後跑一次，確認高級質感的保證還在。

  python finishtest.py          # 全部（約 30 秒）；任一項沒過 exit 1

不靠任何專案素材（全部合成）：
  A 緩推不閃：細節密的大圖 1.00→1.06 緩推，cover() 的時間閃爍要比「直接 warpAffine」低 30% 以上
  B 字不抖：字 3 秒移 24 px，blit() 每格都要動（停住的格 = 0），位置誤差 < 0.01 px
  C 漸層沒色階：暗部漸層 to_u8()＋grain 0.018 用 deliver 的 x265 參數壓 3.8 Mbps 後，finish.banding() ≤ 5；不抖色時要 > 8（量法還分得出來）
  D 標點：「」，連續標點有擠壓、單獨逗號維持全形；wrap_text 行首沒有收尾標點
  E 調色：look.match 把黑位對到參考 ±2；look.tone 的高光柔肩讓 235–249 這段多於 ≥ 250（finish.measure 量得到）
"""
import os
import subprocess
import sys
import tempfile

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import seekkit as sk  # noqa: E402
import look  # noqa: E402
from finish import banding, measure  # noqa: E402

W, H = 1080, 1920
results = []


def check(name, ok, detail):
    results.append(ok)
    print(f"{'通過' if ok else '沒過'}  {name}：{detail}")


def flicker(frames):
    L = [cv2.Laplacian(cv2.cvtColor((np.clip(f, 0, 1) * 255).astype(np.uint8), cv2.COLOR_RGB2GRAY).astype(np.float32), cv2.CV_32F)
         for f in frames]
    return float(np.mean([np.abs(L[i] - 0.5 * (L[i - 1] + L[i + 1])).mean() for i in range(1, len(L) - 1)]))


# A
r = np.random.default_rng(3)
big = (r.random((3000, 4000), np.float32) * 0.25 + 0.4)
big[:, ::7] = 0.1
big[::11, :] = 0.9
big = np.dstack([big, big * 0.95, big * 0.9])
naive, ours = [], []
for i in range(24):
    z = 1.0 + 0.06 * i / 23
    k = max(W / 4000, H / 3000) * z
    M = np.float32([[k, 0, W / 2 - 0.5 * 4000 * k], [0, k, H / 2 - 0.5 * 3000 * k]])
    naive.append(cv2.warpAffine(big, M, (W, H), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REFLECT))
    ours.append(sk.cover(big, W, H, z))
fn, fo = flicker(naive), flicker(ours)
check('A 緩推不閃', fo < fn * 0.7, f'時間閃爍 直接 warp {fn:.3f} → cover {fo:.3f}（{(1 - fo / fn) * 100:.0f}% 降）')

# B
spr = sk.text_sprite('質感 Premium', 56, tracking=0.04)
xs = []
for i in range(90):
    c = np.zeros((200, 900, 3), np.float32)
    sk.blit(c, spr, 100 + 24 * i / 89, 60)
    col = c.mean(2).sum(0)
    xs.append(float((col * np.arange(len(col))).sum() / col.sum()))
xs = np.array(xs)
stalls = int((np.abs(np.diff(xs)) < 0.02).sum())
err = float(np.sqrt(np.mean((xs - np.polyval(np.polyfit(np.arange(90), xs, 1), np.arange(90))) ** 2)))
check('B 字不抖', stalls == 0 and err < 0.01, f'停住的格 {stalls}、位置誤差 {err:.4f} px')

# C
yy = np.linspace(0, 1, H, dtype=np.float32)[:, None, None]
base = (0.03 + 0.17 * yy) * np.ones((H, W, 3), np.float32) * np.float32([1.0, 0.97, 0.92])
tmp = tempfile.mkdtemp()


def encode(fn, name):
    out = os.path.join(tmp, name + '.mp4')
    p = subprocess.Popen(['ffmpeg', '-v', 'error', '-y', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', f'{W}x{H}', '-r', '30', '-i', '-',
                          '-c:v', 'libx265', '-preset', 'medium', '-b:v', '3800k', '-pix_fmt', 'yuv420p',
                          '-x265-params', 'aq-mode=3:aq-strength=1.2:psy-rdoq=2:log-level=error', out],  # 同 frames.py deliver
                         stdin=subprocess.PIPE)
    for i in range(30):
        p.stdin.write(fn(i / 30).tobytes())
    p.stdin.close()
    p.wait()
    rr = subprocess.run(['ffmpeg', '-v', 'error', '-ss', '0.5', '-i', out, '-frames:v', '1', '-f', 'rawvideo', '-pix_fmt', 'gray', '-'],
                        capture_output=True)
    return banding(np.frombuffer(rr.stdout, np.uint8).reshape(H, W))


def with_grain(t):
    c = base.copy()
    sk.grain(c, t, 30, 0.018)
    return sk.to_u8(c)


b_good = encode(with_grain, 'good')
b_bad = encode(lambda t: sk.to_u8(base, dither=False), 'bad')
check('C 漸層沒色階', b_good is not None and b_good <= 5 and b_bad is not None and b_bad > 8,
      f'抖色＋顆粒壓檔後 {b_good} px（≤ 5）；不抖色 {b_bad} px（> 8，量法分得出來）')

# D
a_full = sk.text_sprite('質感」，從', 72, palt=False).shape[1]
a_palt = sk.text_sprite('質感」，從', 72).shape[1]
b_full = sk.text_sprite('質感，從', 72, palt=False).shape[1]
b_palt = sk.text_sprite('質感，從', 72).shape[1]
ws = sk.wrap_text('他說「好。」然後我們一起去了那間店，吃了很久。', 420, 48)
check('D 標點', a_palt < a_full - 50 and abs(b_palt - b_full) <= 2,
      f'「」，」擠壓 {a_full}→{a_palt} px；單獨逗號 {b_full}→{b_palt} px（維持全形）；換行 {len(ws)} 行')

# E
img = np.linspace(0, 1.15, W, dtype=np.float32)[None, :, None] * np.ones((H, W, 3), np.float32)  # 亮部超過 1（天空、窗）
img[600:900, 300:800] = (0.75, 0.55, 0.45)
ref = dict(black=10.0, white=235.0, mid=100.0, cast=(0.0, 3.0))
m = look.match(np.clip(img * 0.8 + 0.08, 0, 1), ref)
st = look.stats(m)
u8 = lambda x: (np.clip(x, 0, 1) * 255 + 0.5).astype(np.uint8)
hard, soft = measure(u8(img)), measure(u8(look.tone(img, 0.4, 0.0)))
check('E 調色', abs(st['black'] - 10) <= 2 and soft['clip'] < hard['clip'] * 0.5 and soft['shoulder'] > hard['shoulder'],
      f"match 後黑位 {st['black']:.1f}（參考 10）；高光 ≥250：直接切 {hard['clip']:.1%} → 柔肩 {soft['clip']:.1%}，"
      f"235–249 過渡 {hard['shoulder']:.1%} → {soft['shoulder']:.1%}")

# F：搖鏡時調色不能呼吸（畫面從亮窗搖到暗室，每格重量增益會跟著變）
pano = np.ones((H, W * 3, 3), np.float32) * np.float32([0.18, 0.15, 0.12])   # 暗室
pano[:, :W] = np.float32([0.85, 0.88, 0.92])                                  # 亮窗
pano[300:700, :] = np.float32([0.45, 0.32, 0.25])                             # 一路都在的木桌（實際亮度不變）
pano = cv2.GaussianBlur(pano, (0, 0), 25)
views = [pano[:, int(i * W * 2 / 23):int(i * W * 2 / 23) + W] for i in range(24)]
table = lambda f: float(f[420:580].mean())
per = [table(look.face_safe(v, 'day')) for v in views]
L = look.lock(views[12], 'day')
lk = [table(look.apply(v, L)) for v in views]
d_per, d_lock = max(per) - min(per), max(lk) - min(lk)
check('F 搖鏡', d_lock < 0.01 and d_per > 0.03,
      f'同一張木桌在 24 格搖鏡裡的亮度變化：每格重量 {d_per:.3f} → 整個鏡頭鎖參數 {d_lock:.3f}')

print('全部通過' if all(results) else f'{results.count(False)} 項沒過')
sys.exit(0 if all(results) else 1)
