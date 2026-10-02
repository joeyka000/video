#!/usr/bin/env python3
"""分析歌曲 → data/audio.json（拍格、downbeat、段落、包絡線、鼓點）。只用 librosa／scipy，不跑 Demucs。

  python analyze.py song.mp3 -o data/audio.json
  python analyze.py song.mp3 -o data/audio.json --bpm 128 --first-beat 0.42
  python analyze.py song.mp3 -o data/audio.json --sections "intro:0,verse1:4,chorus1:12,verse2:20,chorus2:28"
  python analyze.py song.mp3 -o data/audio.json --plot out/audio.png    # 需要 matplotlib（選用）

做法：
  1. onset envelope（librosa.onset.onset_strength，混音＋低頻帶）→ tempo（librosa.feature.tempo；--bpm 可覆寫）
  2. 擬合常數拍格：對 tempo（±7%）與相位做網格搜尋，最大化拍點上的 onset 強度，再用 kick 攻擊點的中位殘差修正相位
     （--first-beat 秒 可覆寫：拍格從這個時間開始，而且它就是 bar 0 的 downbeat）
  3. downbeat：在 meter 個相位中，選「低頻 onset（kick）＋混音 onset＋和弦變化（chroma 差異）」最強的相位
  4. sections：--sections 給「名稱:小節序」（bar 0 = 第一個 downbeat，每段到下一段開始為止，最後一段到曲末）；
     沒給就用 librosa.segment.agglomerative 在小節同步的 chroma＋MFCC＋RMS 上自動分 6–10 段，命名 S1、S2…
  5. env：100 fps 的 rms／low(<150 Hz)／mid(150–2000)／high(>4000)，fast-attack(10 ms)/slow-release(90 ms) follower，
     各自除以 99 百分位後裁到 0..1
  6. onsets：kick（<120 Hz 帶的攻擊點）、snare（1.5–5 kHz 攻擊點且 40–120 ms 後有 0.5–5 kHz 雜訊尾巴；
     kick 的敲擊聲沒有尾巴所以被排除）、hat（>7 kHz 攻擊點，排除 snare ±40 ms 內的）

輸出格式：
  { "duration", "sr": 44100, "tempo", "meter", "beats": [秒,...], "downbeats": [秒,...],
    "sections": [{"name","start","end","bar"}, ...],
    "env": {"fps": 100, "rms": [...], "low": [...], "mid": [...], "high": [...]},
    "onsets": {"kick": [秒,...], "snare": [...], "hat": [...]} }
"""
import argparse
import json
import math
import os
import sys

import numpy as np

SR = 44100
FPS = 100
OSR = 22050          # onset envelope 用的取樣率
OHOP = 64            # onset envelope 的 hop（344.5 fps）


# ---------------------------------------------------------------- 工具
def band_sos(lo, hi, sr):
    from scipy.signal import butter
    if lo and hi:
        return butter(4, [lo, hi], btype="band", fs=sr, output="sos")
    if hi:
        return butter(4, hi, btype="low", fs=sr, output="sos")
    return butter(4, lo, btype="high", fs=sr, output="sos")


def frame_rms(x, sr, fps=FPS, win=2048):
    """每 1/fps 秒取一個 RMS（視窗 win 個樣本、置中）。"""
    hop = sr / fps
    n = int(math.ceil(len(x) / sr * fps))
    pad = np.pad(x, (win // 2, win // 2 + int(hop) + 2))
    idx = (np.arange(n) * hop).astype(int)
    c = np.concatenate([[0.0], np.cumsum(pad.astype(np.float64) ** 2)])
    e = (c[idx + win] - c[idx]) / win
    return np.sqrt(np.maximum(e, 0))


def follower(x, fps=FPS, attack=0.010, release=0.090):
    """一階 follower：攻擊快、釋放慢（畫面用）。"""
    aa = math.exp(-1 / (attack * fps))
    ar = math.exp(-1 / (release * fps))
    y = np.empty_like(x)
    s = 0.0
    for i, v in enumerate(x):
        a = aa if v > s else ar
        s = a * s + (1 - a) * v
        y[i] = s
    return y


def norm01(x, pct=99.0):
    ref = np.percentile(x, pct)
    return np.clip(x / (ref + 1e-12), 0, 1)


def moving_mean(x, w):
    """置中的移動平均（cumsum，O(N)）。"""
    c = np.concatenate([[0.0], np.cumsum(np.pad(x.astype(np.float64), (w // 2, w - w // 2)))])
    return (c[w:] - c[:-w])[: len(x)] / w


def band_onsets(x, sr, lo, hi, win=0.010, hop_s=0.002, min_gap=0.08, rel_db=10.0, min_db=-55.0):
    """某頻帶的攻擊點：帶通 → 能量 dB → 20 ms 內上升量的峰值；回傳 (時間, 峰值 dB)。
    峰值低於 min_db（dBFS）的略過，免得在幾乎無聲的頻帶抓到別的樂器漏進來的殘響。"""
    from scipy.ndimage import median_filter, uniform_filter1d
    from scipy.signal import find_peaks, sosfiltfilt
    xb = sosfiltfilt(band_sos(lo, hi, sr), x)
    h = int(hop_s * sr)
    w = int(win * sr)
    e = moving_mean(xb ** 2, w)[::h]
    db = 10 * np.log10(e + 1e-10)
    fps = sr / h
    d = uniform_filter1d(np.diff(db, prepend=db[0]), 3)
    lag = int(0.02 * fps)
    rise = db - np.concatenate([np.full(lag, db[0]), db[:-lag]])
    floor = median_filter(db, int(1.0 * fps) | 1)
    pk, _ = find_peaks(rise, height=rel_db, distance=max(1, int(min_gap * fps)))
    times, strength = [], []
    for p in pk:
        a = max(0, p - lag)
        q = a + int(np.argmax(d[a:p + 1]))          # 攻擊時間：上升最陡處
        peak_db = db[p:p + int(0.03 * fps)].max()
        if peak_db < floor[p] + 3 or peak_db < min_db:   # 沒有明顯高過底噪、或太小聲就略過
            continue
        times.append(q / fps)
        strength.append(peak_db)
    return np.array(times), np.array(strength)


# ---------------------------------------------------------------- 拍格
def onset_curves(y, sr):
    """回傳 (混音 onset envelope, 低頻 onset envelope, 每秒格數)。"""
    import librosa
    from scipy.signal import sosfiltfilt
    y22 = librosa.resample(y, orig_sr=sr, target_sr=OSR)
    o_mix = librosa.onset.onset_strength(y=y22, sr=OSR, hop_length=OHOP)
    low = sosfiltfilt(band_sos(None, 150, OSR), y22)
    o_low = librosa.onset.onset_strength(y=low, sr=OSR, hop_length=OHOP, n_mels=8, fmax=300)
    return o_mix, o_low, OSR / OHOP


def grid_score(o, ofps, duration, P, offs, tol):
    """對一組相位 offs（陣列）計算拍點上 onset 強度（±tol 格取最大）的平均。"""
    n = np.arange(int(duration / P) + 1)
    ts = offs[:, None] + P * n[None, :]
    idx = np.round(ts * ofps).astype(int)
    valid = (idx > tol) & (idx < len(o) - tol - 1)
    idc = np.clip(idx, tol + 1, len(o) - tol - 2)
    v = np.maximum.reduce([o[idc + k] for k in range(-tol, tol + 1)])
    v = np.where(valid, v, 0.0)
    return v.sum(1) / np.maximum(valid.sum(1), 1)


def fit_grid(o, ofps, duration, bpm0, fixed_bpm=False):
    """常數拍格：tempo＋相位的網格搜尋（粗→細→更細）。回傳 (bpm, off)。"""
    def search(bpms, off_lo, off_hi, off_step, tol):
        best = (-1.0, None, None)
        for bpm in bpms:
            P = 60 / bpm
            offs = np.arange(off_lo, off_hi, off_step)
            offs = offs[(offs >= 0) & (offs < P + 1e-9)] if off_lo == 0 else offs
            if len(offs) == 0:
                continue
            s = grid_score(o, ofps, duration, P, offs, tol)
            i = int(np.argmax(s))
            if s[i] > best[0]:
                best = (float(s[i]), float(bpm), float(offs[i]))
        return best

    if fixed_bpm:
        bpms = np.array([bpm0])
    else:
        bpms = np.arange(bpm0 * 0.93, bpm0 * 1.07, 0.02)
    _, bpm, off = search(bpms, 0.0, 60 / bpm0 * 1.08, 0.004, 2)
    if not fixed_bpm:
        _, bpm, off = search(np.arange(bpm - 0.03, bpm + 0.03, 0.002), off - 0.012, off + 0.012, 0.001, 1)
        _, bpm, off = search(np.arange(bpm - 0.003, bpm + 0.003, 0.0002), off - 0.002, off + 0.002, 0.0002, 1)
    else:
        _, bpm, off = search(bpms, off - 0.012, off + 0.012, 0.0005, 1)
    P = 60 / bpm
    off = off - P * math.floor(off / P)
    return bpm, off


def refine_phase_on_kicks(kick_t, P, off):
    if len(kick_t) < 4:
        return off, 0.0
    n = np.round((kick_t - off) / P)
    res = kick_t - (off + n * P)
    res = res[np.abs(res) < 0.06]
    if len(res) < 4:
        return off, 0.0
    off = off + float(np.median(res))
    off = off - P * math.floor(off / P)
    return off, float(res.std())


def pick_downbeat_phase(beats, meter, o_mix, o_low, ofps, y, sr):
    """在 meter 個相位中選 kick＋onset＋和弦變化最強者。回傳 (相位 k, 各相位分數)。"""
    import librosa
    def at(o, ts):
        idx = np.clip(np.round(ts * ofps).astype(int), 1, len(o) - 2)
        return np.maximum.reduce([o[idx - 1], o[idx], o[idx + 1]])
    mix = at(o_mix, beats)
    low = at(o_low, beats)
    mix = mix / (mix.mean() + 1e-9)
    low = low / (low.mean() + 1e-9)
    # 和弦變化：每拍的 chroma 與前一拍的 cos 距離
    y22 = librosa.resample(y, orig_sr=sr, target_sr=OSR)
    chroma = librosa.feature.chroma_stft(y=y22, sr=OSR, hop_length=512)
    frames = librosa.time_to_frames(beats, sr=OSR, hop_length=512)
    frames = np.clip(frames, 0, chroma.shape[1] - 1)
    # sync 的第 0 欄是第一個邊界之前的片段，第 i+1 欄才是第 i 拍
    bc = librosa.util.sync(chroma, frames, aggregate=np.mean)[:, 1: len(beats) + 1]
    bc = bc / (np.linalg.norm(bc, axis=0, keepdims=True) + 1e-9)
    nov = np.zeros(len(beats))
    nov[1:] = 1 - np.sum(bc[:, 1:] * bc[:, :-1], axis=0)
    nov = nov / (nov.mean() + 1e-9)
    scores = []
    for k in range(meter):
        sel = np.arange(k, len(beats), meter)
        scores.append(float(mix[sel].mean() + low[sel].mean() + 1.5 * nov[sel].mean()))
    return int(np.argmax(scores)), scores


# ---------------------------------------------------------------- 段落
def auto_sections(y, sr, downbeats, duration):
    """小節同步的 chroma＋MFCC＋RMS 上做 agglomerative 分段（6–10 段），起點對齊 downbeat。"""
    import librosa
    nb = len(downbeats)
    if nb < 2:
        return [("S1", 0)]
    k = int(min(10, max(6, round(nb / 8))))
    k = min(k, nb)
    y22 = librosa.resample(y, orig_sr=sr, target_sr=OSR)
    hop = 512
    chroma = librosa.feature.chroma_stft(y=y22, sr=OSR, hop_length=hop)
    mfcc = librosa.feature.mfcc(y=y22, sr=OSR, hop_length=hop, n_mfcc=13)[1:]
    rms = librosa.feature.rms(y=y22, hop_length=hop)
    rms = np.log(rms + 1e-6)
    frames = librosa.time_to_frames(downbeats, sr=OSR, hop_length=hop)
    frames = np.clip(frames, 0, chroma.shape[1] - 1)
    feats = []
    for F in (chroma, mfcc, rms):
        S = librosa.util.sync(F, frames, aggregate=np.mean)[:, 1: nb + 1]   # 第 0 欄是第一個 downbeat 之前
        S = (S - S.mean(1, keepdims=True)) / (S.std(1, keepdims=True) + 1e-9)
        feats.append(S)
    X = np.vstack(feats)
    bounds = librosa.segment.agglomerative(X, k)
    bounds = sorted(set(int(b) for b in bounds) | {0})
    return [(f"S{i + 1}", b) for i, b in enumerate(bounds)]


def parse_sections(spec):
    out = []
    for item in spec.split(","):
        item = item.strip()
        if not item:
            continue
        if ":" not in item:
            sys.exit(f"--sections 格式錯誤：{item!r}（要寫 名稱:小節序）")
        name, bar = item.rsplit(":", 1)
        try:
            out.append((name.strip(), int(bar)))
        except ValueError:
            sys.exit(f"--sections 小節序不是整數：{item!r}")
    out.sort(key=lambda x: x[1])
    return out


# ---------------------------------------------------------------- 鼓點
def flatness(y, sr, t, n=2048):
    """t 秒起 n 個樣本在 1–8 kHz 的頻譜平坦度（幾何平均／算術平均）：雜訊接近 1，純音接近 0。"""
    a = max(0, int(t * sr))
    seg = y[a:a + n]
    if len(seg) < n:
        return 0.0
    mag = np.abs(np.fft.rfft(seg * np.hanning(n)))
    f = np.fft.rfftfreq(n, 1 / sr)
    m = mag[(f >= 1000) & (f <= 8000)] + 1e-12
    return float(np.exp(np.mean(np.log(m))) / np.mean(m))


def drum_onsets(y, sr):
    from scipy.signal import sosfiltfilt
    kt, _ = band_onsets(y, sr, None, 120, win=0.012, min_gap=0.15, rel_db=12)
    st, _ = band_onsets(y, sr, 1500, 5000, win=0.010, min_gap=0.15, rel_db=10)
    if len(st):
        # 雜訊尾巴：攻擊後 40–120 ms 的 0.5–5 kHz 能量要在附近 2.5 秒內最響的 8 dB 之內
        xb = sosfiltfilt(band_sos(500, 5000, sr), y)
        e = np.sqrt(moving_mean(xb ** 2, 441))
        tail = []
        for t in st:
            a, b = int((t + 0.04) * sr), int((t + 0.12) * sr)
            tail.append(20 * np.log10(e[a:b].mean() + 1e-9) if b <= len(e) and b > a else -120.0)
        tail = np.array(tail)
        rel = np.array([tail[i] - tail[np.abs(st - st[i]) < 2.5].max() for i in range(len(st))])
        thr = np.percentile(tail, 95) - 25
        # 尾巴要像雜訊（頻譜平坦度），排除 bass／人聲／吉他這類有諧波的攻擊
        fl = np.array([max(flatness(y, sr, t + 0.005), flatness(y, sr, t + 0.03)) for t in st])
        st = st[(rel > -8) & (tail > thr) & (fl >= 0.35)]
    ht, _ = band_onsets(y, sr, 7000, None, win=0.006, min_gap=0.06, rel_db=9)
    if len(st) and len(ht):
        dist = np.min(np.abs(ht[:, None] - st[None, :]), axis=1)
        ht = ht[dist > 0.04]
    return kt, st, ht


# ---------------------------------------------------------------- 主程式
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("song")
    ap.add_argument("-o", "--out", required=True, help="輸出 audio.json")
    ap.add_argument("--bpm", type=float, help="固定 tempo（不搜尋）")
    ap.add_argument("--meter", type=int, default=4, help="每小節拍數（預設 4）")
    ap.add_argument("--first-beat", dest="first_beat", type=float, help="第一拍（也是 bar 0 的 downbeat）的秒數")
    ap.add_argument("--sections", help='段落小節序，例如 "intro:0,verse1:4,chorus1:12"')
    ap.add_argument("--plot", help="輸出分析圖 PNG（需要 matplotlib）")
    a = ap.parse_args()
    if a.meter < 1:
        ap.error("--meter 至少 1")
    if not os.path.exists(a.song):
        sys.exit(f"找不到歌曲檔：{a.song}")

    import librosa
    y, _ = librosa.load(a.song, sr=SR, mono=True)
    if len(y) < SR:
        sys.exit("歌曲太短（不到 1 秒）")
    duration = len(y) / SR

    # 1. onset 與 tempo
    o_mix, o_low, ofps = onset_curves(y, SR)
    o = o_mix / (np.percentile(o_mix, 99) + 1e-9) + o_low / (np.percentile(o_low, 99) + 1e-9)
    if a.bpm:
        bpm0 = a.bpm
    else:
        bpm0 = float(librosa.feature.tempo(onset_envelope=o_mix, sr=OSR, hop_length=OHOP, start_bpm=120)[0])
        while bpm0 < 60:
            bpm0 *= 2
        while bpm0 >= 200:
            bpm0 /= 2
    # 2. 拍格
    bpm, off = fit_grid(o, ofps, duration, bpm0, fixed_bpm=bool(a.bpm))
    P = 60 / bpm
    kt, st, ht = drum_onsets(y, SR)
    off, kick_sd = refine_phase_on_kicks(kt, P, off)
    if a.first_beat is not None:
        off = a.first_beat - P * math.floor(a.first_beat / P)
        t_first = a.first_beat
    else:
        t_first = off
    beats = t_first + P * np.arange(int((duration - t_first) / P) + 1)
    beats = beats[beats < duration]
    if len(beats) < a.meter:
        sys.exit("拍數太少，無法分析")
    # 3. downbeat 相位
    if a.first_beat is not None:
        k0, phase_scores = 0, None
    else:
        k0, phase_scores = pick_downbeat_phase(beats, a.meter, o_mix, o_low, ofps, y, SR)
    downbeats = beats[k0::a.meter]
    # 4. 段落
    if a.sections:
        spec = parse_sections(a.sections)
        for name, b in spec:
            if b < 0 or b >= len(downbeats):
                sys.exit(f"--sections 的小節序 {b}（{name}）超出範圍，共 {len(downbeats)} 小節（0–{len(downbeats) - 1}）")
    else:
        spec = auto_sections(y, SR, downbeats, duration)
    sections = []
    for i, (name, b) in enumerate(spec):
        start = float(downbeats[b])
        end = duration if i == len(spec) - 1 else float(downbeats[spec[i + 1][1]])
        sections.append({"name": name, "start": round(start, 3), "end": round(end, 3), "bar": int(b)})
    # 5. 包絡線
    from scipy.signal import sosfiltfilt
    n_env = int(math.ceil(duration * FPS))
    env = {"fps": FPS}
    raw = {"rms": frame_rms(y, SR)[:n_env]}
    for name, (lo, hi) in {"low": (None, 150), "mid": (150, 2000), "high": (4000, None)}.items():
        raw[name] = frame_rms(sosfiltfilt(band_sos(lo, hi, SR), y), SR)[:n_env]
    for k, v in raw.items():
        env[k] = [round(float(x), 3) for x in norm01(follower(v))]

    doc = {
        "duration": round(duration, 3), "sr": SR, "tempo": round(bpm, 3), "meter": a.meter,
        "beats": [round(float(t), 4) for t in beats],
        "downbeats": [round(float(t), 4) for t in downbeats],
        "sections": sections, "env": env,
        "onsets": {"kick": [round(float(t), 3) for t in kt],
                   "snare": [round(float(t), 3) for t in st],
                   "hat": [round(float(t), 3) for t in ht]},
    }
    os.makedirs(os.path.dirname(os.path.abspath(a.out)) or ".", exist_ok=True)
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, separators=(",", ":"))

    # 摘要
    print(f"檔案 {a.song}  長度 {duration:.2f} 秒")
    print(f"tempo {bpm:.3f} BPM（初估 {bpm0:.1f}{'，--bpm 固定' if a.bpm else ''}）  拍長 {P:.5f} 秒  "
          f"kick 殘差 sd {kick_sd * 1000:.1f} ms")
    print(f"第一拍 {beats[0]:.3f} 秒  拍數 {len(beats)}  downbeat 相位 {k0}/{a.meter}  小節數 {len(downbeats)}  "
          f"第一個 downbeat {downbeats[0]:.3f} 秒")
    if phase_scores:
        print("downbeat 相位分數：" + "  ".join(f"{i}:{s:.2f}" for i, s in enumerate(phase_scores)))
    print(f"鼓點 kick {len(kt)}  snare {len(st)}  hat {len(ht)}")
    print(f"{'段落':<10}{'起(秒)':>9}{'迄(秒)':>9}{'小節':>6}{'長(小節)':>9}")
    for i, s in enumerate(sections):
        nbars = (spec[i + 1][1] - s["bar"]) if i + 1 < len(spec) else (len(downbeats) - s["bar"])
        print(f"{s['name']:<10}{s['start']:>9.3f}{s['end']:>9.3f}{s['bar']:>6}{nbars:>9}")
    print(f"寫入 {a.out}")

    if a.plot:
        try:
            import matplotlib
            matplotlib.use("Agg")
            import matplotlib.pyplot as plt
        except ImportError:
            print("未安裝 matplotlib，略過 --plot（在 venv 裝 matplotlib 後再跑）")
            return
        t_o = np.arange(len(o_mix)) / ofps
        t_e = np.arange(n_env) / FPS
        fig, ax = plt.subplots(2, 1, figsize=(24, 7), sharex=True)
        ax[0].plot(t_o, o_mix / (o_mix.max() + 1e-9), lw=0.5, color="k", label="onset")
        for b in beats:
            ax[0].axvline(b, color="gray", lw=0.4)
        for b in downbeats:
            ax[0].axvline(b, color="c", lw=1.2)
        for name, c in [("rms", "k"), ("low", "tab:red"), ("mid", "tab:green"), ("high", "tab:blue")]:
            ax[1].plot(t_e, env[name], lw=0.6, color=c, label=name)
        for s in sections:
            for a_ in ax:
                a_.axvline(s["start"], color="tab:red", lw=1.5)
            ax[0].text(s["start"], 1.02, s["name"], color="tab:red")
        for a_ in ax:
            a_.legend(loc="upper right", fontsize=8)
        fig.tight_layout()
        fig.savefig(a.plot, dpi=65)
        print(f"寫入 {a.plot}")


if __name__ == "__main__":
    main()
