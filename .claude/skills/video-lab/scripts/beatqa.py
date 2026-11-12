#!/usr/bin/env python3
"""卡點片的輸出前檢查：閃白有沒有落在小節線上、聲音與畫面有沒有對齊拍子。

  python beatqa.py deliver/mv.mp4 --audio-json data/song90.json --song data/song90.wav -o qa/beat
  python beatqa.py deliver/mv.mp4 --audio-json data/song90.json --strong 22 --faint 7

量什麼：
  1. 閃白／亮度突升：逐格平均亮度（160×90 灰階），這一格比前兩格的較小值亮 ≥ --faint（0–255）就算一次；
     ≥ --strong 是「強閃」。每一次找最近的小節線與拍點，差幾格：
       強閃必須在小節線 ±1 格（規則：閃白只在小節線上，換人時稍強）；淡閃在小節線或拍點 ±1 格
     換背景的硬切也會被算成亮度突升（設計上也在小節線上，所以一起檢查）
  2. 聲音：給 --song（剪好的歌）時，成片音軌對歌本身做 onset 互相關 → 混音位移（ffmpeg 合音軌錯位、剪歌後換錯檔都會露出來），
     這一項才是判定；另外列「歌本身對拍格」與「成片音軌對拍格」的位移當參考：現場鼓、人聲很多的歌，常數拍格本來就會
     差幾十毫秒（Sparkle 實測 +65 ms），那是 analyze.py 的拍格問題，不是成片不同步
  3. 畫面對拍格：逐格畫面變化量（相鄰格差）在同樣 ±150 ms 平移下哪裡最強 → 畫面的「打點」比拍子早／晚幾格
  兩者都要在 ±1 格（30 fps＝±33 ms）內才算音畫同步
輸出：-o 資料夾的 report.md（表格＋不合格清單），終端機印摘要；任一項不合格時結束碼 1。
"""
import argparse
import json
import os
import subprocess
import sys

import numpy as np


def probe(path):
    r = subprocess.run(['ffprobe', '-v', 'error', '-select_streams', 'v:0', '-show_entries', 'stream=r_frame_rate', '-of', 'csv=p=0', path],
                       capture_output=True, text=True).stdout.strip().split(',')[0]
    a, b = r.split('/')
    return float(a) / float(b)


def video_curves(path, w=160, h=90):
    raw = subprocess.run(['ffmpeg', '-v', 'error', '-nostdin', '-i', path, '-vf', f'scale={w}:{h}:flags=area,format=gray', '-f', 'rawvideo', '-'],
                         capture_output=True, check=True).stdout
    f = np.frombuffer(raw, np.uint8).reshape(-1, h, w).astype(np.float32)
    L = f.mean((1, 2))
    D = np.zeros(len(f), np.float32)
    D[1:] = np.abs(f[1:] - f[:-1]).mean((1, 2))
    return L, D


def audio_onset(path, sr=22050, hop=128):
    import librosa
    raw = subprocess.run(['ffmpeg', '-v', 'error', '-nostdin', '-i', path, '-vn', '-ac', '1', '-ar', str(sr), '-f', 'f32le', '-'],
                         capture_output=True).stdout
    y = np.frombuffer(raw, np.float32)
    if len(y) < sr:
        return None, sr / hop
    o = librosa.onset.onset_strength(y=y, sr=sr, hop_length=hop)
    return o, sr / hop


def audio_onset_range(path, t0, dur, sr=22050, hop=128):
    import librosa
    raw = subprocess.run(['ffmpeg', '-v', 'error', '-nostdin', '-ss', str(t0), '-t', str(dur), '-i', path, '-ac', '1', '-ar', str(sr), '-f', 'f32le', '-'],
                         capture_output=True).stdout
    y = np.frombuffer(raw, np.float32)
    if len(y) < sr:
        return None, sr / hop
    return librosa.onset.onset_strength(y=y, sr=sr, hop_length=hop), sr / hop


def best_lag(curve, cfps, beats, max_lag=0.15):
    """curve 在 beats＋lag 的平均值最大的 lag（秒，正＝curve 比拍格晚）。"""
    lags = np.arange(-max_lag, max_lag + 1e-9, 1 / cfps)
    sc = []
    for L in lags:
        idx = np.round((beats + L) * cfps).astype(int)
        idx = idx[(idx >= 0) & (idx < len(curve))]
        sc.append(curve[idx].mean() if len(idx) else 0)
    sc = np.array(sc)
    i = int(np.argmax(sc))
    contrast = float(sc[i] / (np.median(sc) + 1e-9))
    return float(lags[i]), contrast


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('video')
    p.add_argument('--audio-json', required=True)
    p.add_argument('-o', default='out/beatqa')
    p.add_argument('--strong', type=float, default=22.0)
    p.add_argument('--faint', type=float, default=7.0)
    p.add_argument('--offset', type=float, default=0.0, help='影片 0 秒對應 json 的第幾秒')
    p.add_argument('--song', help='剪好的歌（songcut.py 輸出）：量成片音軌的混音位移')
    a = p.parse_args()

    J = json.load(open(a.audio_json))
    db = np.array(J['downbeats']) - a.offset
    beats = np.array(J['beats']) - a.offset
    fps = probe(a.video)
    L, D = video_curves(a.video)
    n = len(L)
    # 1. 亮度突升
    prev = np.minimum(np.r_[L[0], L[:-1]], np.r_[L[0], L[0], L[:-2]])
    rise = L - prev
    ev = []
    f = 1
    while f < n:
        if rise[f] >= a.faint:
            g = f
            while g + 1 < n and rise[g + 1] >= a.faint:      # 連續幾格算同一次，取最大那格
                g += 1
            k = f + int(np.argmax(rise[f:g + 1]))
            t = k / fps
            dbar = (t - db[np.argmin(np.abs(db - t))]) * fps
            dbeat = (t - beats[np.argmin(np.abs(beats - t))]) * fps
            strong = rise[k] >= a.strong
            ok = abs(dbar) <= 1.01 if strong else (abs(dbar) <= 1.01 or abs(dbeat) <= 1.01)
            ev.append(dict(t=round(t, 3), frame=k, rise=round(float(rise[k]), 1), strong=bool(strong), d_bar=round(float(dbar), 2),
                           d_beat=round(float(dbeat), 2), ok=bool(ok)))
            f = g + 1
        else:
            f += 1
    bad = [e for e in ev if not e['ok']]
    strong = [e for e in ev if e['strong']]
    on_bar = sum(abs(e['d_bar']) <= 1.01 for e in strong)
    # 2. 聲音
    o, ofps = audio_onset(a.video)
    a_lag = a_con = None
    if o is not None:
        a_lag, a_con = best_lag(o / (o.max() + 1e-9), ofps, beats[(beats > 0) & (beats < n / fps)])
    mux = s_lag = None
    if a.song and o is not None:
        so, _ = audio_onset_range(a.song, a.offset, n / fps)
        if so is not None:
            m = min(len(so), len(o))
            x, y = o[:m] - o[:m].mean(), so[:m] - so[:m].mean()
            R = int(0.2 * ofps)
            cc = [float(np.dot(x[max(0, L):m + min(0, L)], y[max(0, -L):m - max(0, L)])) for L in range(-R, R + 1)]
            mux = (int(np.argmax(cc)) - R) / ofps
            s_lag, _ = best_lag(so / (so.max() + 1e-9), ofps, beats[(beats > 0) & (beats < n / fps)])
    # 3. 畫面
    v_lag, v_con = best_lag(D / (D.max() + 1e-9), fps, beats[(beats > 0) & (beats < n / fps)])
    tol = 1.01 / fps
    sync_ok = (abs(mux) <= tol if mux is not None else (a_lag is None or abs(a_lag) <= tol)) and abs(v_lag) <= tol
    passed = not bad and sync_ok

    os.makedirs(a.o, exist_ok=True)
    lines = [f'# 卡點檢查：{os.path.basename(a.video)}', '',
             f'- 影片 {n} 格、{fps:g} fps、{n / fps:.2f} 秒；拍格 {J.get("tempo", 0):.2f} BPM、{len(db)} 條小節線',
             f'- 亮度突升 {len(ev)} 次（強閃 ≥ {a.strong:g}：{len(strong)} 次，落在小節線 ±1 格 {on_bar}/{len(strong)}）；不合格 {len(bad)} 次',
             (f'- 混音位移（成片音軌 vs 歌）：{mux * 1000:+.0f} ms；參考：歌本身對拍格 {s_lag * 1000:+.0f} ms、成片音軌對拍格 {a_lag * 1000:+.0f} ms'
               '（onset 強度峰值本來就比鼓的攻擊點晚 30–50 ms，拍格鎖在鼓上時這裡約 +30～+60 是正常的）'
              if mux is not None else
              f'- 聲音對拍格：{"沒有音軌" if a_lag is None else f"{a_lag * 1000:+.0f} ms（對比 {a_con:.2f}）"}（沒給 --song，這項含歌本身的拍格誤差）'),
             f'- 畫面打點對拍格：{v_lag * 1000:+.0f} ms ＝ {v_lag * fps:+.1f} 格（對比 {v_con:.2f}；對比 < 1.15 表示畫面變化跟拍子關係很弱）',
             f'- 結論：**{"通過" if passed else "不通過"}**', '']
    if bad:
        lines += ['## 不合格', '', '| 秒 | 格 | 亮度升 | 強閃 | 離小節線（格） | 離拍點（格） |', '|---|---|---|---|---|---|']
        lines += [f'| {e["t"]:.3f} | {e["frame"]} | {e["rise"]} | {"是" if e["strong"] else ""} | {e["d_bar"]:+.2f} | {e["d_beat"]:+.2f} |' for e in bad]
        lines.append('')
    lines += ['## 全部亮度突升', '', '| 秒 | 亮度升 | 強閃 | 離小節線（格） | 離拍點（格） | 合格 |', '|---|---|---|---|---|---|']
    lines += [f'| {e["t"]:.3f} | {e["rise"]} | {"是" if e["strong"] else ""} | {e["d_bar"]:+.2f} | {e["d_beat"]:+.2f} | {"✓" if e["ok"] else "✗"} |' for e in ev]
    open(os.path.join(a.o, 'report.md'), 'w').write('\n'.join(lines) + '\n')
    json.dump(dict(events=ev, audio_lag=a_lag, video_lag=v_lag, passed=passed), open(os.path.join(a.o, 'beatqa.json'), 'w'))
    for l in lines[2:7]:
        print(l)
    sys.exit(0 if passed else 1)


if __name__ == '__main__':
    main()
