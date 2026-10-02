#!/usr/bin/env python3
"""分析歌曲 → data/audio.json（拍格、downbeat、段落、包絡線、鼓點）。只用 librosa／scipy，不跑 Demucs。

  python analyze.py song.mp3 -o data/audio.json
  python analyze.py song.mp3 -o data/audio.json --bpm 128 --first-beat 0.42
  python analyze.py song.mp3 -o data/audio.json --sections "intro:0,verse1:4,chorus1:12,verse2:20,chorus2:28"
  python analyze.py song.mp3 -o data/audio.json --plot out/audio.png    # 分析圖（numpy 畫、ffmpeg 編碼，不需 matplotlib）
  python analyze.py song.mp3 -o data/audio.json --kick-on-grid          # onsets.kick 只留拍格 ±60 ms 內的

做法：
  1. onset envelope（librosa.onset.onset_strength，混音＋低頻帶）→ tempo（librosa.feature.tempo；--bpm 可覆寫）
  2. 擬合常數拍格：對 tempo（±7%）與相位做網格搜尋，最大化拍點上的 onset 強度，再用 kick 攻擊點的中位殘差修正相位，
     最後對拍格 ±60 ms 內的 kick 做「拍序→時間」線性回歸修 tempo（斜率 = 拍長；要 ≥ 8 個 kick、跨 ≥ 8 拍、
     修正量 ≤ 0.5% 才採用；--bpm 固定時不做）。摘要會印修正前後的 max 殘差
     （--first-beat 秒 可覆寫：拍格從這個時間開始，而且它就是 bar 0 的 downbeat）
  3. downbeat：在 meter 個相位中，選「低頻 onset（kick）＋混音 onset＋和絃變化（chroma 差異）」最強的相位
  4. sections：--sections 給「名稱:小節序」（bar 0 = 第一個 downbeat，每段到下一段開始為止，最後一段到曲末；
     第一段不是 bar 0 時印警告並自動補一段 intro（名稱已被用掉就叫 S0）從 bar 0 起，讓每個時間都落在某段裡）；
     沒給就自動分段：小節同步的 MFCC＋log RMS＋spectral contrast → 小節自相似矩陣（self-similarity matrix）
     → 棋盤核（checkerboard kernel，半寬 4 小節）novelty 曲線取峰值 → 邊界離 4 小節樂句格 1 小節內就吸附過去
     → 段落最短 4 小節、最多 10 段，命名 S1、S2…。自動分段僅供參考（2 小節的前奏會被併掉、
     同編制只換和絃的段落分不出來），正式請用 --sections
  5. env：100 fps 的 rms／low(<150 Hz)／mid(150–2000)／high(>4000)，fast-attack(10 ms)/slow-release(90 ms) follower，
     各自除以 99 百分位後裁到 0..1
  6. onsets：kick（<120 Hz 帶的攻擊點，再過形狀條件：攻擊後 5–45 ms 與 85–125 ms 的低頻（30–250 Hz）頻譜重心比
     ≥ 1.03，也就是音高往下掃（測試歌 kick 1.09–1.81、bass 0.77–0.90）；或 20–120 ms 內 <80 Hz 能量佔 <400 Hz 的 ≥ 75%，也就是 sub 為主。
     bass 的攻擊音高不變、諧波多，兩條都不過就剔除。真實歌曲裡 sub-bass 合成器仍可能混進來，
     要乾淨的拍點用 --kick-on-grid 只留拍格 ±60 ms 內的）、
     snare（1.5–5 kHz 攻擊點且 40–120 ms 後有 0.5–5 kHz 雜訊尾巴；kick 的敲擊聲沒有尾巴所以被排除）、
     hat（>7 kHz 攻擊點，排除 snare ±40 ms 內的）

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
    """用拍格 ±60 ms 內的 kick 攻擊點的中位殘差修正相位。回傳 (off, 殘差 sd)。"""
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


def refine_tempo_on_kicks(kick_t, P, off, tol=0.060, min_n=8, min_span=8, max_change=0.005):
    """網格搜尋的 tempo 步進有限（最細 0.0002 BPM），短歌也會有 0.1% 的誤差、累積到曲末偏一格；
    對拍格 ±tol 內的 kick 做「拍序 n → kick 時間」的最小平方線性回歸：斜率 = 拍長 P、截距 = 相位。
    要 ≥ min_n 個 kick、跨 ≥ min_span 拍，且修正量 |ΔP/P| ≤ max_change（避免被 bass 攻擊或錯拍帶走）才採用。
    回傳 (P, off, 修正前 max 殘差, 修正後 max 殘差, 採用的 kick 數)；沒採用時 P、off 原樣回傳。"""
    if len(kick_t) < min_n:
        return P, off, 0.0, 0.0, 0
    n = np.round((kick_t - off) / P)
    res = kick_t - (off + n * P)
    keep = np.abs(res) < tol
    if keep.sum() < min_n or (n[keep].max() - n[keep].min()) < min_span:
        return P, off, 0.0, 0.0, 0
    before = float(np.abs(res[keep]).max())
    slope, icept = np.polyfit(n[keep], kick_t[keep], 1)
    if abs(slope - P) / P > max_change:
        return P, off, before, before, 0
    P2, off2 = float(slope), float(icept)
    res2 = kick_t[keep] - (off2 + n[keep] * P2)
    off2 = off2 - P2 * math.floor(off2 / P2)
    return P2, off2, before, float(np.abs(res2).max()), int(keep.sum())


def beat_sync(F, times, fps):
    """把特徵矩陣 F（列=特徵、欄=格）依 times（秒）切成每個區間一欄：第 i 欄 = 第 i 個時間到第 i+1 個時間（最後一個到結尾）
    的平均。兩個時間落在同一格（例如第一拍在 0.02 秒內、或拍比格密）時取該格本身，欄數永遠等於 len(times)。
    不用 librosa.util.sync：它會把邊界 0 與 frames[0]==0 合併、少回一欄，下游指派時 shape 不符。"""
    n = F.shape[1]
    b = np.clip(np.round(np.asarray(times) * fps).astype(int), 0, n - 1)
    ends = np.append(b[1:], n)
    out = np.empty((F.shape[0], len(b)))
    for i, (s, e) in enumerate(zip(b, ends)):
        out[:, i] = F[:, s:e].mean(1) if e > s else F[:, s]
    return out


def pick_downbeat_phase(beats, meter, o_mix, o_low, ofps, y, sr):
    """在 meter 個相位中選 kick＋onset＋和絃變化最強者。回傳 (相位 k, 各相位分數)。"""
    import librosa
    def at(o, ts):
        idx = np.clip(np.round(ts * ofps).astype(int), 1, len(o) - 2)
        return np.maximum.reduce([o[idx - 1], o[idx], o[idx + 1]])
    mix = at(o_mix, beats)
    low = at(o_low, beats)
    mix = mix / (mix.mean() + 1e-9)
    low = low / (low.mean() + 1e-9)
    # 和絃變化：每拍的 chroma 與前一拍的 cos 距離
    y22 = librosa.resample(y, orig_sr=sr, target_sr=OSR)
    chroma = librosa.feature.chroma_stft(y=y22, sr=OSR, hop_length=512)
    bc = beat_sync(chroma, beats, OSR / 512)
    bc = bc / (np.linalg.norm(bc, axis=0, keepdims=True) + 1e-9)
    nov = np.zeros(bc.shape[1])
    nov[1:] = 1 - np.sum(bc[:, 1:] * bc[:, :-1], axis=0)
    nov = nov / (nov.mean() + 1e-9)
    scores = []
    for k in range(meter):
        sel = np.arange(k, len(beats), meter)
        scores.append(float(mix[sel].mean() + low[sel].mean() + 1.5 * nov[sel].mean()))
    return int(np.argmax(scores)), scores


# ---------------------------------------------------------------- 段落
def bar_features(y, sr, downbeats):
    """每小節一欄：MFCC(1–12)＋log RMS（×3 權重）＋spectral contrast，各特徵跨小節標準化。"""
    import librosa
    y22 = librosa.resample(y, orig_sr=sr, target_sr=OSR)
    hop = 512
    mfcc = librosa.feature.mfcc(y=y22, sr=OSR, hop_length=hop, n_mfcc=13)[1:]
    rms = np.log(librosa.feature.rms(y=y22, hop_length=hop) + 1e-6)
    contrast = librosa.feature.spectral_contrast(y=y22, sr=OSR, hop_length=hop)
    feats = []
    for F, rep in ((mfcc, 1), (rms, 3), (contrast, 1)):
        S = beat_sync(F, downbeats, OSR / hop)   # 每小節一欄（nb 欄；第一個 downbeat 在第 0 格也不會少欄）
        S = (S - S.mean(1, keepdims=True)) / (S.std(1, keepdims=True) + 1e-9)
        feats.append(np.repeat(S, rep, axis=0))   # RMS 加權（段落最明顯的差別是音量與編制）
    return np.vstack(feats)


def novelty_curve(X, L):
    """小節自相似矩陣（高斯核）上套棋盤核（半寬 L 小節），回傳每個小節邊界的 novelty（長度 nb，索引 i = 第 i 小節開頭）。"""
    nb = X.shape[1]
    d = np.linalg.norm(X[:, :, None] - X[:, None, :], axis=0)      # 歐氏距離矩陣
    sigma = np.median(d[d > 0]) if np.any(d > 0) else 1.0
    S = np.exp(-(d ** 2) / (2 * sigma ** 2))
    # 棋盤核：左上／右下 +1、右上／左下 −1，乘高斯錐
    g = np.exp(-0.5 * ((np.arange(2 * L) - (L - 0.5)) / (L / 2)) ** 2)
    sign = np.r_[-np.ones(L), np.ones(L)]
    K = np.outer(sign * g, sign * g)
    Sp = np.pad(S, L, mode="reflect")
    nov = np.zeros(nb)
    for i in range(1, nb):
        blk = Sp[i: i + 2 * L, i: i + 2 * L]        # 以邊界 i 為中心（pad 後索引 i+L 對應原本的 i）
        nov[i] = float((blk * K).sum())
    nov = np.maximum(nov, 0)
    return nov / (nov.max() + 1e-9)


def auto_sections(y, sr, downbeats, duration, min_len=4, phrase=4, max_segments=10):
    """小節級 novelty 分段：峰值 → 吸附到 phrase 小節樂句格（差 1 小節內）→ 最短 min_len 小節 → 最多 max_segments 段。
    回傳 [(名稱, 起始小節), ...]，第一段一定從 0 開始。"""
    from scipy.signal import find_peaks
    nb = len(downbeats)
    if nb < 2 * min_len:
        return [("S1", 0)]
    X = bar_features(y, sr, downbeats)
    L = min(4, nb // 4)
    nov = novelty_curve(X, L)
    pk, prop = find_peaks(nov, height=0.15, distance=max(1, min_len - 1))
    cands = sorted(zip(prop["peak_heights"], pk), reverse=True)
    bounds = []
    for h, b in cands:
        b = int(b)
        snapped = int(round(b / phrase)) * phrase          # 吸附到樂句格
        if abs(snapped - b) <= 1 and 0 < snapped < nb:
            b = snapped
        if b <= 0 or b >= nb:
            continue
        # 與已接受的邊界（含 0 與曲末）至少隔 min_len 小節；強的先佔位
        if all(abs(b - q) >= min_len for q in bounds + [0, nb]):
            bounds.append(b)
        if len(bounds) >= max_segments - 1:
            break
    bounds = sorted(set(bounds) | {0})
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


def low_centroid(y, sr, t0, dur=0.040, lo=30.0, hi=250.0, nfft=32768):
    """t0 起 dur 秒的低頻（lo–hi Hz）功率頻譜重心；零補到 nfft 讓 40 ms 視窗也有 1.3 Hz 的格點。"""
    a = int(t0 * sr)
    n = int(dur * sr)
    seg = y[a:a + n]
    if len(seg) < n:
        return None
    mag2 = np.abs(np.fft.rfft(seg * np.hanning(n), nfft)) ** 2
    f = np.fft.rfftfreq(nfft, 1 / sr)
    m = (f >= lo) & (f <= hi)
    w = mag2[m]
    return float((f[m] * w).sum() / (w.sum() + 1e-12))


def sub_share(y, sr, t0, dur=0.100, nfft=32768):
    """t0 起 dur 秒：20–80 Hz 能量佔 20–400 Hz 的比例。"""
    a = int(t0 * sr)
    n = int(dur * sr)
    seg = y[a:a + n]
    if len(seg) < n:
        return None
    mag2 = np.abs(np.fft.rfft(seg * np.hanning(n), nfft)) ** 2
    f = np.fft.rfftfreq(nfft, 1 / sr)
    lo = mag2[(f >= 20) & (f < 80)].sum()
    all_ = mag2[(f >= 20) & (f < 400)].sum()
    return float(lo / (all_ + 1e-12))


def kick_shape(y, sr, t):
    """回傳 (重心比, sub 佔比)：重心比 = 攻擊後 5–45 ms 的低頻重心 ÷ 85–125 ms 的低頻重心（kick 的音高往下掃 → >1；
    bass 音高不變 → ≈1）；sub 佔比 = 20–120 ms 內 <80 Hz 能量佔 <400 Hz 的比例（純 sub 的 kick 接近 1，bass 諧波多則低）。"""
    c1 = low_centroid(y, sr, t + 0.005)
    c2 = low_centroid(y, sr, t + 0.085)
    sh = sub_share(y, sr, t + 0.020)
    ratio = (c1 / c2) if (c1 and c2) else 0.0
    return ratio, (sh if sh is not None else 0.0)


def is_kick(y, sr, t, min_ratio=1.03, min_share=0.75):
    ratio, share = kick_shape(y, sr, t)
    return ratio >= min_ratio or share >= min_share


def drum_onsets(y, sr):
    from scipy.signal import sosfiltfilt
    kt, _ = band_onsets(y, sr, None, 120, win=0.012, min_gap=0.15, rel_db=12)
    if len(kt):
        kt = np.array([t for t in kt if is_kick(y, sr, t)])   # 形狀條件：剔除 bass 攻擊
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
        st = st[(rel > -8) & (tail > thr) & (fl >= 0.5)]
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
    ap.add_argument("--plot", help="輸出分析圖 PNG（numpy 畫、ffmpeg 編碼）")
    ap.add_argument("--kick-on-grid", dest="kick_on_grid", action="store_true",
                    help="onsets.kick 只留離拍格 ±60 ms 內的（bass 攻擊混進來時用）")
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
    tempo_note = ""
    if not a.bpm:
        # 相位修好後再用 kick 回歸修 tempo（--bpm 固定時不動）
        P, off, r_before, r_after, n_fit = refine_tempo_on_kicks(kt, P, off)
        bpm = 60 / P
        if n_fit:
            tempo_note = f"  kick 回歸修正 tempo（{n_fit} 個 kick，max 殘差 {r_before * 1000:.1f} → {r_after * 1000:.1f} ms）"
            _, kick_sd = refine_phase_on_kicks(kt, P, off)
    if a.first_beat is not None:
        off = a.first_beat - P * math.floor(a.first_beat / P)
        t_first = a.first_beat
    else:
        t_first = off
    beats = t_first + P * np.arange(int((duration - t_first) / P) + 1)
    beats = beats[beats < duration]
    if len(beats) < a.meter:
        sys.exit("拍數太少，無法分析")
    n_kick_raw = len(kt)
    if a.kick_on_grid and len(kt):
        kt = kt[np.min(np.abs(kt[:, None] - beats[None, :]), axis=1) <= 0.060]
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
        if spec[0][1] != 0:
            # 第一段不從 bar 0 起：前面的小節沒有段落，下游 MV.sectionAt(t) 會拿不到；自動補一段
            fill = "intro" if all(n != "intro" for n, _ in spec) else "S0"
            print(f"警告：--sections 第一段 {spec[0][0]} 從 bar {spec[0][1]} 開始，bar 0–{spec[0][1] - 1} 自動補成段落 {fill}；"
                  f"要自己命名請加 名稱:0", file=sys.stderr)
            spec.insert(0, (fill, 0))
    else:
        spec = auto_sections(y, SR, downbeats, duration)
    # start／end 直接用 downbeats 四捨五入後的值（4 位），讓 section.start == downbeats[section.bar]
    db4 = [round(float(t), 4) for t in downbeats]
    dur3 = round(duration, 3)
    sections = []
    for i, (name, b) in enumerate(spec):
        end = dur3 if i == len(spec) - 1 else db4[spec[i + 1][1]]
        sections.append({"name": name, "start": db4[b], "end": end, "bar": int(b)})
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
        "duration": dur3, "sr": SR, "tempo": round(bpm, 3), "meter": a.meter,
        "beats": [round(float(t), 4) for t in beats],
        "downbeats": db4,
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
          f"kick 殘差 sd {kick_sd * 1000:.1f} ms{tempo_note}")
    print(f"第一拍 {beats[0]:.3f} 秒  拍數 {len(beats)}  downbeat 相位 {k0}/{a.meter}  小節數 {len(downbeats)}  "
          f"第一個 downbeat {downbeats[0]:.3f} 秒")
    if phase_scores:
        print("downbeat 相位分數：" + "  ".join(f"{i}:{s:.2f}" for i, s in enumerate(phase_scores)))
    print(f"鼓點 kick {len(kt)}" + (f"（拍格外剔除 {n_kick_raw - len(kt)}）" if a.kick_on_grid else "") +
          f"  snare {len(st)}  hat {len(ht)}")
    if not a.sections:
        print("段落：自動分段僅供參考（小節 novelty 峰值、吸附 4 小節樂句格、最短 4 小節），正式請用 --sections 指定")
    print(f"{'段落':<10}{'起(秒)':>9}{'迄(秒)':>9}{'小節':>6}{'長(小節)':>9}")
    for i, s in enumerate(sections):
        nbars = (spec[i + 1][1] - s["bar"]) if i + 1 < len(spec) else (len(downbeats) - s["bar"])
        print(f"{s['name']:<10}{s['start']:>9.3f}{s['end']:>9.3f}{s['bar']:>6}{nbars:>9}")
    print(f"寫入 {a.out}")

    if a.plot:
        write_plot(a.plot, o_mix, ofps, beats, downbeats, env, sections, duration)
        print(f"寫入 {a.plot}")


# ---------------------------------------------------------------- 分析圖（不用 matplotlib）
def _vlines(img, xs, color, width=1):
    H, W, _ = img.shape
    for x in xs:
        x = int(x)
        if 0 <= x < W:
            img[:, max(0, x - width // 2): x - width // 2 + width] = color


def _curve(img, y0, y1, values, vfps, duration, color):
    """把 values（vfps 格／秒、0..1）畫在 y0..y1 列：每個 x 欄取該時段的 min/max 填垂直線段。"""
    H, W, _ = img.shape
    n = len(values)
    v = np.asarray(values, dtype=np.float64)
    for x in range(W):
        i0 = int(x / W * duration * vfps)
        i1 = max(i0 + 1, int((x + 1) / W * duration * vfps))
        if i0 >= n:
            break
        seg = v[i0: min(i1, n)]
        lo, hi = float(seg.min()), float(seg.max())
        ya = int(y1 - hi * (y1 - y0))
        yb = int(y1 - lo * (y1 - y0))
        img[max(y0, ya): min(y1, yb) + 1, x] = color


def write_plot(path, o_mix, ofps, beats, downbeats, env, sections, duration):
    """上：onset 強度＋拍線（灰）＋downbeat（青）＋段落（紅）；下：env 的 rms／low／mid／high。
    numpy 畫 RGB 點陣，餵給 ffmpeg 加段落名與秒數刻度後存 PNG。"""
    import subprocess
    W = int(min(6000, max(1600, duration * 24)))
    H = 700
    top = (24, 330)
    bot = (370, 690)
    img = np.full((H, W, 3), 255, np.uint8)
    img[top[0]:top[1], :] = (247, 247, 247)
    img[bot[0]:bot[1], :] = (247, 247, 247)
    px = lambda t: t / duration * W
    _vlines(img, [px(b) for b in beats], (210, 210, 210), 1)
    _vlines(img, [px(b) for b in downbeats], (0, 170, 190), 2)
    o = np.asarray(o_mix, dtype=np.float64)
    _curve(img, top[0], top[1], o / (o.max() + 1e-9), ofps, duration, (20, 20, 20))
    for name, color in (("rms", (20, 20, 20)), ("low", (214, 39, 40)), ("mid", (44, 160, 44)), ("high", (31, 119, 180))):
        _curve(img, bot[0], bot[1], env[name], env["fps"], duration, color)
    _vlines(img, [px(s["start"]) for s in sections], (214, 39, 40), 3)
    # 文字（段落名、秒數刻度）交給 ffmpeg drawtext
    font = ""
    try:
        f = subprocess.run(["fc-match", "-f", "%{file}", "Noto Sans CJK TC"], capture_output=True, text=True).stdout.strip()
        if f and os.path.exists(f):
            font = f":fontfile={f}"
    except OSError:
        pass
    safe = lambda t: "".join(ch if ch not in "'\\\";:,[]%" else " " for ch in str(t))
    draws = []
    for s in sections:
        draws.append(f"drawtext=text='{safe(s['name'])}':x={int(px(s['start'])) + 4}:y=4:fontsize=18:fontcolor=0xd62728{font}")
    step = 5 if duration <= 90 else (10 if duration <= 300 else 30)
    for t in range(0, int(duration) + 1, step):
        draws.append(f"drawtext=text='{t}s':x={int(px(t)) + 3}:y={top[1] + 6}:fontsize=14:fontcolor=0x555555{font}")
    draws.append(f"drawtext=text='onset  灰線=拍  青線=downbeat  紅線=段落':x=6:y={top[0] + 4}:fontsize=16:fontcolor=0x333333{font}")
    draws.append(f"drawtext=text='env  黑=rms 紅=low 綠=mid 藍=high':x=6:y={bot[0] + 4}:fontsize=16:fontcolor=0x333333{font}")
    cmd = ["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-i", "-",
           "-vf", ",".join(draws), "-frames:v", "1", path]
    r = subprocess.run(cmd, input=img.tobytes(), capture_output=True)
    if r.returncode:
        sys.exit(f"--plot 失敗：\n{' '.join(cmd)}\n{r.stderr.decode(errors='replace').strip()}")


if __name__ == "__main__":
    main()
