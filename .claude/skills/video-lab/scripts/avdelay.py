"""光到了、聲音晚到：從一支影片量閃光與聲音的時間差，換算成距離（煙火、雷、遠處的爆破）。
做法：畫面上半部（天空）平均亮度的上升 vs 聲音能量的上升（onset），兩條都取正向變化、標準化後做互相關，
找 0–lag_max 秒內最像的位移；整支一個數，再每 2 分鐘分段算一次看穩不穩（煙火每一發高度不同，分段會在 ±0.2 秒內跳）。

  python avdelay.py IMG_6061.MOV                 # → 整支時間差、分段時間差、距離（音速預設 340 m/s ≈ 15°C）
  python avdelay.py IMG_6061.MOV --sky 0.6 --c 343

以整支的數字為準：分段的相關很弱（煙火連發、人聲、風切），只拿來看有沒有一段特別離譜。
釜山煙火節 2026（民樂洞看廣安里）：IMG_6061 整支 1.01 秒、IMG_6051 整支 1.12 秒 → 約 340–380 公尺；
61 秒的長焦連發近景（IMG_6050）量不準（0.9–2.1 秒），要用有單發、有空檔的長片。
手機錄影的影音同步誤差約 ±1 格，距離只寫「約」，並寫出音速用的溫度。
"""
import argparse
import subprocess
import sys

import numpy as np


def sky_curve(path, sky=0.6, w=54, h=96):
    """解碼成 54×96 灰階（自動轉正），回傳 (每格時間, 上半部亮度)。"""
    pts = subprocess.run(['ffprobe', '-v', 'error', '-select_streams', 'v:0', '-show_entries', 'packet=pts_time', '-of', 'csv=p=0', path],
                         capture_output=True, text=True).stdout.split()
    pts = np.sort(np.array([float(x) for x in pts if x not in ('', 'N/A')]))
    raw = subprocess.run(['ffmpeg', '-v', 'error', '-threads', '4', '-i', path, '-map', '0:v:0', '-vf', f'scale={w}:{h}:flags=area,format=gray',
                          '-fps_mode', 'passthrough', '-f', 'rawvideo', '-'], capture_output=True).stdout
    fr = np.frombuffer(raw, np.uint8).reshape(-1, h, w).astype(np.float32)
    n = min(len(fr), len(pts))
    return pts[:n], fr[:n, :int(h * sky), :].mean(axis=(1, 2))


def audio_curve(path, sr=16000, hop=160):
    raw = subprocess.run(['ffmpeg', '-v', 'error', '-i', path, '-map', '0:a:0', '-ac', '1', '-ar', str(sr), '-f', 'f32le', '-'],
                         capture_output=True).stdout
    y = np.frombuffer(raw, np.float32)
    n = len(y) // hop
    e = np.sqrt((y[:n * hop].reshape(n, hop) ** 2).mean(1))
    return np.arange(n) * hop / sr, np.log(e + 1e-6)


def lag(db, da, lmax):
    """畫面窗固定（前 n 格），聲音窗往後滑 L：每個 L 的重疊長度一樣，大位移不會因為樣本少而被雜訊放大。"""
    n = min(len(db), len(da)) - lmax
    z = [(x - x.mean()) / (x.std() + 1e-9) for x in (db, da)]
    sc = [float(np.dot(z[0][:n], z[1][L:L + n])) / n for L in range(lmax)]
    k = int(np.argmax(sc))
    return k, sc[k]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('video')
    ap.add_argument('--sky', type=float, default=0.6, help='畫面上方幾成算天空')
    ap.add_argument('--max', type=float, default=10.0, help='最多找幾秒的延遲')
    ap.add_argument('--c', type=float, default=340.0, help='音速 m/s（15°C≈340、20°C≈343）')
    ap.add_argument('--seg', type=float, default=120.0, help='分段長度（秒）')
    a = ap.parse_args()
    pts, sky = sky_curve(a.video, a.sky)
    ta, le = audio_curve(a.video)
    T = np.arange(0, min(pts[-1], ta[-1]), 0.01)
    db = np.clip(np.diff(np.interp(T, pts, sky), prepend=sky[0]), 0, None)
    da = np.clip(np.diff(np.interp(T, ta, le), prepend=le[0]), 0, None)
    L, s = lag(db, da, int(a.max * 100))
    print(f'整支：聲音晚 {L / 100:.2f} 秒（相關 {s:.3f}）→ 約 {L / 100 * a.c:.0f} 公尺（音速 {a.c:.0f} m/s）')
    seg = int(a.seg * 100)
    lags = []
    lm = int(a.max * 100)
    for i0 in range(0, len(T) - seg - lm, seg):
        k, sc = lag(db[i0:i0 + seg + lm], da[i0:i0 + seg + lm], lm)
        lags.append(k / 100)
        print(f'  {i0 // 6000:02d}:{i0 // 100 % 60:02d} 起 {k / 100:.2f} 秒（相關 {sc:.3f}）')
    if lags:
        q = np.percentile(lags, [25, 50, 75])
        print(f'分段中位數 {q[1]:.2f} 秒（四分位 {q[0]:.2f}–{q[2]:.2f}）；跟整支差太多就看哪一段有雜音（人聲、風切）')


if __name__ == '__main__':
    sys.exit(main())
