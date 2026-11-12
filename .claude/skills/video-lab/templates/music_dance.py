"""原創舞曲範本（合成、沒有版權問題）：卡點跳舞 MV 用。128 BPM、48 小節＝剛好 90 秒；同時輸出精確拍格 json。

  python music_dance.py out.wav        → out.wav（48 kHz 立體聲）＋ out.json（psyfx.Grid／beatqa.py 直接吃，不用再做拍點偵測）

風格：future funk／nu-disco（四拍底鼓、反拍開鈸、八度跳的 disco 貝斯、旁鏈壓縮的和弦刺、主旋律鉤子、濾波器打開的前奏）。
調：降 E 大調。副歌 IV–V–iii–vi（A♭maj7–B♭–Gm7–Cm7），主歌 vi–IV–I–V，結尾落在 I。
段落（改 SECTIONS 就能換長度；小節長 = 240 / BPM 秒）：
  intro 4（低通慢慢打開）→ verse 8（最後一小節小鼓滾奏＋上升噪音）→ chorus 16（鉤子兩遍，第二遍加高八度與琶音）
  → verse 8（前 4 小節抽掉底鼓）→ chorus 8 → outro 4（最後一小節一記主和弦＋殘響自然收）
SWISH_BARS：畫面換人的小節，在小節線前半拍放一聲很輕的咻（聲音跟畫面的轉場綁在一起）。
寫歌不能用耳朵聽，靠量：build() 結尾印各軌 RMS、低／中／高頻比例、峰值；整體響度用 ffmpeg ebur128 量（目標 −14 LUFS 上下）。
"""
import json
import os
import sys

import numpy as np
from scipy import signal

SR = 48000
BPM = 128
BEAT = 60 / BPM
BAR = BEAT * 4
SECTIONS = [(0, 'intro'), (4, 'verse'), (12, 'chorus'), (28, 'verse'), (36, 'chorus'), (44, 'outro')]
BARS = 48
DUR = BARS * BAR
N = int(round(DUR * SR))
SWISH_BARS = [4, 8, 12, 14, 18, 20, 24, 26, 28, 32, 36, 38, 42, 44]
rng = np.random.default_rng(128)

CH = {  # 和弦音（MIDI）、根音
    'IV': ([56, 60, 63, 67], 32), 'V': ([58, 62, 65, 72], 34), 'iii': ([55, 58, 62, 65], 31), 'vi': ([60, 63, 67, 70], 36),
    'I': ([58, 63, 67, 70], 27), 'ii': ([53, 56, 60, 63], 29),
}
PROG = {'chorus': ['IV', 'V', 'iii', 'vi'], 'verse': ['vi', 'IV', 'I', 'V'], 'intro': ['vi', 'IV', 'I', 'V'], 'outro': ['IV', 'V', 'vi', 'I']}
# 主旋律鉤子：8 小節，(小節內第幾拍, MIDI, 幾拍長)
HOOK = [
    [(0, 67, .5), (.75, 70, .5), (1.5, 72, .75), (2.5, 70, .5), (3, 67, .5), (3.5, 70, .5)],
    [(0, 65, .75), (.75, 70, .5), (1.5, 74, 1.25), (3, 72, .5), (3.5, 70, .5)],
    [(0, 74, .5), (.75, 72, .5), (1.5, 70, .75), (2.5, 67, .5), (3, 70, .5), (3.5, 72, .5)],
    [(0, 75, 1.75), (2, 74, .5), (2.5, 72, .5), (3, 67, 1.0)],
    [(0, 67, .5), (.75, 70, .5), (1.5, 72, .75), (2.5, 70, .5), (3, 67, .5), (3.5, 70, .5)],
    [(0, 65, .75), (.75, 70, .5), (1.5, 74, 1.25), (3, 72, .5), (3.5, 74, .5)],
    [(0, 74, .5), (.75, 75, .5), (1.5, 77, .75), (2.5, 75, .5), (3, 74, .5), (3.5, 72, .5)],
    [(0, 75, 2.0), (2.5, 79, .5), (3, 75, 1.0)],
]


def hz(m):
    return 440.0 * 2 ** ((m - 69) / 12)


def sect(bar):
    name, start = SECTIONS[0][1], 0
    for b, s in SECTIONS:
        if bar >= b:
            name, start = s, b
    return name, start


def chord(bar):
    name, start = sect(bar)
    return CH[PROG[name][(bar - start) % 4]]


def place(buf, x, t, gain=1.0, pan=0.0):
    i = int(round(t * SR))
    if i >= len(buf) or i + len(x) <= 0:
        return
    j0 = max(0, -i)
    i = max(0, i)
    x = x[j0:j0 + len(buf) - i]
    if x.ndim == 1:
        l, r = np.cos((pan + 1) * np.pi / 4), np.sin((pan + 1) * np.pi / 4)
        buf[i:i + len(x), 0] += x * gain * l * 1.414
        buf[i:i + len(x), 1] += x * gain * r * 1.414
    else:
        buf[i:i + len(x)] += x * gain


_SAW = {}


def saw(f, n):
    """帶限鋸齒波（加法合成，快取）。"""
    key = (round(f, 3), n)
    if key not in _SAW:
        t = np.arange(n) / SR
        out = np.zeros(n)
        k = 1
        while k * f < SR / 2.3 and k <= 48:
            out += np.sin(2 * np.pi * k * f * t) / k
            k += 1
        _SAW[key] = out * 0.6
    return _SAW[key]


def square(f, n):
    t = np.arange(n) / SR
    out = np.zeros(n)
    k = 1
    while k * f < SR / 2.3 and k <= 31:
        out += np.sin(2 * np.pi * k * f * t) / k
        k += 2
    return out * 0.7


def lp(x, fc, order=2):
    b, a = signal.butter(order, min(max(fc, 30), SR / 2.2) / (SR / 2))
    return signal.lfilter(b, a, x, axis=0)


def hp(x, fc, order=2):
    b, a = signal.butter(order, fc / (SR / 2), btype='high')
    return signal.lfilter(b, a, x, axis=0)


def sweep_lp(x, f0, f1, seg=1024):
    out = np.zeros_like(x)
    n = len(x)
    zi = None
    for s in range(0, n, seg):
        fc = f0 * (f1 / f0) ** (s / max(1, n - 1))
        b, a = signal.butter(2, min(fc, SR / 2.2) / (SR / 2))
        if zi is None:
            zi = np.zeros((max(len(a), len(b)) - 1,) + x.shape[1:])
        out[s:s + seg], zi = signal.lfilter(b, a, x[s:s + seg], axis=0, zi=zi)
    return out


def reverb_ir(sec=1.8, decay=4.0, seed=3):
    r = np.random.default_rng(seed)
    n = int(sec * SR)
    t = np.arange(n) / SR
    ir = np.stack([r.normal(0, 1, n), r.normal(0, 1, n)], 1) * np.exp(-t * decay)[:, None]
    ir[:int(0.01 * SR)] *= np.linspace(0, 1, int(0.01 * SR))[:, None]
    ir = hp(lp(ir, 7000), 250)
    return ir / np.sqrt((ir ** 2).sum(0))


def conv(x, ir):
    return np.stack([signal.fftconvolve(x[:, c], ir[:, c])[:len(x)] for c in range(2)], 1)


# ───────── 樂器 ─────────
def kick():
    n = int(0.32 * SR)
    t = np.arange(n) / SR
    f = 47 + 135 * np.exp(-t * 38)
    x = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 9.5)
    click = hp(rng.normal(0, 1, n), 2500) * np.exp(-t * 500) * 0.22
    return np.tanh((x + click) * 1.7) * 0.82


def clap():
    n = int(0.42 * SR)
    t = np.arange(n) / SR
    b, a = signal.butter(2, [1000 / (SR / 2), 6000 / (SR / 2)], btype='band')
    nz = signal.lfilter(b, a, rng.normal(0, 1, n))
    e = np.zeros(n)
    for k, d in enumerate((0.0, 0.010, 0.021, 0.031)):
        i = int(d * SR)
        e[i:] += np.exp(-t[:n - i] * (120 if k < 3 else 24)) * (0.6 if k < 3 else 1.0)
    return nz * e * 0.5


def snare():
    n = int(0.2 * SR)
    t = np.arange(n) / SR
    nz = hp(rng.normal(0, 1, n), 1800) * np.exp(-t * 26)
    tone = np.sin(2 * np.pi * (190 + 60 * np.exp(-t * 40)) * t) * np.exp(-t * 30)
    return (nz * 0.5 + tone * 0.4) * 0.5


def hat(open_=False, vel=1.0):
    n = int((0.26 if open_ else 0.045) * SR)
    t = np.arange(n) / SR
    nz = hp(rng.normal(0, 1, n), 7500)
    return nz * np.exp(-t * (13 if open_ else 85)) * 0.15 * vel


def bass(m, dur):
    n = int(dur * SR)
    t = np.arange(n) / SR
    f = hz(m)
    x = saw(f, n) * 0.8 + square(f, n) * 0.35
    y = np.zeros(n)
    seg = 512
    zi = np.zeros(2)
    for s in range(0, n, seg):
        fc = 180 + 1500 * np.exp(-s / SR * 16)
        b, a = signal.butter(2, fc / (SR / 2))
        y[s:s + seg], zi = signal.lfilter(b, a, x[s:s + seg], zi=zi)
    y += np.sin(2 * np.pi * f * t) * 0.55
    e = np.minimum(1, t / 0.004) * np.clip((dur - t) / 0.02, 0, 1) * (0.75 + 0.25 * np.exp(-t * 8))
    return np.tanh(y * 1.4) * e * 0.34


def stab(ms, dur, bright=1.0):
    n = int((dur + 0.25) * SR)
    t = np.arange(n) / SR
    out = np.zeros((n, 2))
    for j, m in enumerate(ms):
        for det, pan in ((-0.07, -0.6), (0.07, 0.6)):
            v = saw(hz(m + det), n)
            out[:, 0] += v * np.cos((pan + 1) * np.pi / 4)
            out[:, 1] += v * np.sin((pan + 1) * np.pi / 4)
    out /= len(ms)
    out = lp(out, 1400 + 2600 * bright)
    e = np.minimum(1, t / 0.003) * np.where(t < dur, 0.55 + 0.45 * np.exp(-t * 14), (0.55 + 0.45 * np.exp(-dur * 14)) * np.exp(-(t - dur) * 28))
    return out * e[:, None] * 0.42


def pad(ms, dur):
    n = int((dur + 0.6) * SR)
    t = np.arange(n) / SR
    out = np.zeros((n, 2))
    for m in ms:
        for det, pan in ((-0.1, -0.8), (0.1, 0.8)):
            v = saw(hz(m + det), n)
            out[:, 0] += v * np.cos((pan + 1) * np.pi / 4)
            out[:, 1] += v * np.sin((pan + 1) * np.pi / 4)
    out = lp(out / len(ms), 1800)
    e = np.minimum(1, t / 0.25) * np.clip((dur + 0.6 - t) / 0.6, 0, 1)
    return out * e[:, None] * 0.16


def lead(m, dur):
    n = int((dur + 0.3) * SR)
    t = np.arange(n) / SR
    f = hz(m) * (1 + 0.004 * np.sin(2 * np.pi * 5.5 * t) * np.clip((t - 0.12) / 0.2, 0, 1))
    ph = 2 * np.pi * np.cumsum(f) / SR
    x = np.sin(ph) + 0.42 * np.sin(2 * ph) + 0.30 * np.sin(3 * ph) + 0.12 * np.sin(5 * ph) + 0.25 * np.sin(ph + 2.2 * np.sin(2 * ph) * np.exp(-t * 18))
    e = np.minimum(1, t / 0.004) * np.where(t < dur, 0.6 + 0.4 * np.exp(-t * 9), (0.6 + 0.4 * np.exp(-dur * 9)) * np.exp(-(t - dur) * 16))
    return x * e * 0.2


def pluck(m):
    n = int(0.3 * SR)
    t = np.arange(n) / SR
    x = lp(saw(hz(m), n) + square(hz(m), n) * 0.4, 3800)
    return x * np.exp(-t * 20) * 0.22


def vox(m, dur=0.16):
    """像人聲切片的「啊」：鋸齒波過兩個共振峰（800、1150 Hz）。很小聲的點綴。"""
    n = int((dur + 0.1) * SR)
    t = np.arange(n) / SR
    x = saw(hz(m), n)
    y = np.zeros(n)
    for fc, g in ((800, 1.0), (1150, 0.6), (2900, 0.2)):
        b, a = signal.butter(2, [fc * 0.86 / (SR / 2), fc * 1.16 / (SR / 2)], btype='band')
        y += signal.lfilter(b, a, x) * g
    e = np.minimum(1, t / 0.008) * np.where(t < dur, 1.0, np.exp(-(t - dur) * 40))
    return y * e * 0.5


def riser(dur):
    n = int(dur * SR)
    y = sweep_lp(rng.normal(0, 1, n), 400, 11000)
    return y * (np.linspace(0, 1, n) ** 2.4) * 0.2


def swish(dur=0.42):
    n = int(dur * SR)
    t = np.arange(n) / SR
    y = sweep_lp(rng.normal(0, 1, n), 900, 8000)
    return y * (np.sin(np.pi * np.clip(t / dur, 0, 1)) ** 2) * 0.12


def crash():
    n = int(1.8 * SR)
    t = np.arange(n) / SR
    return hp(rng.normal(0, 1, n), 4500) * np.exp(-t * 2.6) * 0.16


def boom():
    n = int(1.6 * SR)
    t = np.arange(n) / SR
    f = 40 + 70 * np.exp(-t * 7)
    return np.tanh(np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 2.4) * 1.5) * 0.5


def build():
    bus = {k: np.zeros((N, 2)) for k in ('kick', 'drums', 'bass', 'chords', 'lead', 'fx')}
    K, C, S = kick(), clap(), snare()
    kick_t = []
    for bar in range(BARS):
        name, start = sect(bar)
        k = bar - start
        ms, root = chord(bar)
        t0 = bar * BAR
        last = bar == BARS - 1
        nxt = sect(bar + 1)[0] if bar + 1 < BARS else None
        build_bar = name == 'verse' and nxt == 'chorus'
        breakdown = name == 'verse' and start > 4 and k < 4
        chorus = name == 'chorus'
        second = chorus and (k >= 8 or start > 12)
        # ── 鼓
        if last:
            place(bus['kick'], K, t0, 1.0)
            kick_t.append(t0)
            place(bus['fx'], boom(), t0, 1.0)
            place(bus['fx'], crash(), t0, 0.9)
        else:
            for b in range(4):
                if breakdown:
                    continue
                if build_bar and b == 3:
                    continue                                   # 進副歌前最後一拍留白
                g = 0.78 if name == 'intro' else 1.0
                place(bus['kick'], K, t0 + b * BEAT, g)
                kick_t.append(t0 + b * BEAT)
            if not (name == 'intro' and k < 2):
                for b in (1, 3):
                    if not (build_bar and b == 3):
                        place(bus['drums'], C, t0 + b * BEAT, 0.85 if chorus else 0.6, 0.05)
            for s in range(16):
                if build_bar and s >= 12:
                    break
                acc = 1.0 if s % 4 == 2 else 0.55 if s % 2 == 0 else 0.32
                if name == 'intro' and k < 1:
                    continue
                if chorus or s % 2 == 0:
                    place(bus['drums'], hat(False, acc * (1.0 if chorus else 0.7)), t0 + s * BEAT / 4 + (0.012 if s % 2 else 0), 1.0, 0.3)
            if chorus or (name == 'verse' and not breakdown and k >= 4):
                for b in range(4):
                    place(bus['drums'], hat(True, 0.9 if chorus else 0.6), t0 + (b + 0.5) * BEAT, 1.0, -0.25)
            if build_bar:                                      # 小鼓滾奏：八分 → 十六分 → 三十二分
                pos = [0, .5, 1, 1.5, 2, 2.25, 2.5, 2.75] + [3 + i / 8 for i in range(6)]
                for i, b in enumerate(pos):
                    place(bus['drums'], S, t0 + b * BEAT, 0.35 + 0.5 * i / len(pos))
                place(bus['fx'], riser(BAR), t0, 1.0)
        # ── 貝斯
        if not last and name != 'intro' or (name == 'intro' and k >= 2):
            if chorus:
                for e in range(8):
                    if e == 7 and k % 4 == 3:
                        m = root + 12 + 7
                    else:
                        m = root + 12 if e % 2 == 0 else root + 24
                    place(bus['bass'], bass(m, BEAT * 0.42), t0 + e * BEAT / 2, 1.0 if e % 2 == 0 else 0.8)
            elif breakdown:
                place(bus['bass'], bass(root + 12, BAR * 0.9), t0, 0.7)
            elif not last:
                for b_, d in ((0, 0.9), (1.5, 0.45), (2.5, 0.45), (3.5, 0.4)):
                    if build_bar and b_ >= 3:
                        continue
                    place(bus['bass'], bass(root + 12, BEAT * d), t0 + b_ * BEAT, 0.9)
        # ── 和弦
        if last:
            place(bus['chords'], pad(CH['I'][0] + [74, 79], BAR * 1.0), t0, 1.6)
            place(bus['chords'], stab(CH['I'][0] + [75], 0.5, 1.0), t0, 1.3)
        else:
            place(bus['chords'], pad(ms, BAR), t0, 0.9 if chorus else 0.7)
            if chorus:
                for s in (0, 3, 6, 8, 11, 14):
                    place(bus['chords'], stab(ms, 0.13 if s != 14 else 0.2, 1.0), t0 + s * BEAT / 4, 1.0)
            elif name in ('verse', 'intro', 'outro'):
                for s in (2, 6, 10, 14):
                    if build_bar and s >= 12:
                        continue
                    place(bus['chords'], stab(ms, 0.11, 0.45 if name != 'outro' else 0.6), t0 + s * BEAT / 4, 0.75)
        # ── 主旋律與點綴
        if chorus:
            for b_, m, d in HOOK[k % 8]:
                place(bus['lead'], lead(m, d * BEAT), t0 + b_ * BEAT, 1.0, -0.1)
                if second:
                    place(bus['lead'], lead(m + 12, d * BEAT), t0 + b_ * BEAT, 0.42, 0.25)
            if second:
                for s in range(16):
                    place(bus['lead'], pluck(ms[s % 4] + 12 + (12 if s % 8 >= 4 else 0)), t0 + s * BEAT / 4, 0.55, 0.5 if s % 2 else -0.5)
            for b_ in ((1.5, 3.5) if k % 2 == 0 else (2.5,)):
                place(bus['lead'], vox(ms[2] + 12), t0 + b_ * BEAT, 0.32, 0.4)
        elif name == 'verse':
            for s in range(0, 16, 2):
                if build_bar and s >= 12:
                    continue
                place(bus['lead'], pluck(ms[(s // 2) % 4] + 12), t0 + s * BEAT / 4, 0.5 if not breakdown else 0.7, 0.45 if s % 4 else -0.45)
            if breakdown and k % 2 == 0:
                for b_, m, d in HOOK[k % 8][:3]:
                    place(bus['lead'], lead(m, d * BEAT), t0 + b_ * BEAT, 0.5)
        elif name == 'outro' and not last:
            for b_, m, d in HOOK[k % 8][:4]:
                place(bus['lead'], lead(m, d * BEAT), t0 + b_ * BEAT, 0.6)
        # ── 段落頭的重擊
        if k == 0 and chorus:
            place(bus['fx'], crash(), t0, 1.0)
            place(bus['fx'], boom(), t0, 0.7)
        elif k == 8 and chorus:
            place(bus['fx'], crash(), t0, 0.7)
    for b in SWISH_BARS:
        place(bus['fx'], swish(), b * BAR - 0.36, 1.0, rng.uniform(-0.5, 0.5))
    # ── 旁鏈：底鼓一下，貝斯與和弦讓開
    duck = np.ones(N)
    t = np.arange(int(0.42 * SR)) / SR
    shape = 1 - 0.72 * np.exp(-t / 0.085)
    for kt in kick_t:
        i = int(round(kt * SR))
        seg = shape[:max(0, min(len(shape), N - i))]
        duck[i:i + len(seg)] = np.minimum(duck[i:i + len(seg)], seg)
    bus['bass'] *= duck[:, None]
    bus['chords'] *= (0.35 + 0.65 * duck)[:, None]
    # ── 前奏：低通慢慢打開；結尾前兩小節慢慢關
    i1 = int(4 * BAR * SR)
    for k_ in ('chords', 'bass', 'drums'):
        bus[k_][:i1] = sweep_lp(bus[k_][:i1], 500 if k_ != 'drums' else 2500, 14000)
    o0, o1 = int(44 * BAR * SR), int(47 * BAR * SR)
    for k_ in ('chords', 'lead'):
        bus[k_][o0:o1] = sweep_lp(bus[k_][o0:o1], 12000, 900)
    # ── 延遲與殘響
    d = int(0.75 * BEAT * SR)
    dl = np.zeros_like(bus['lead'])
    dl[d:, 0] += bus['lead'][:-d, 1] * 0.30
    dl[2 * d:, 1] += bus['lead'][:-2 * d, 0] * 0.18
    bus['lead'] += lp(dl, 4500)
    ir = reverb_ir()
    wet = conv(bus['lead'] * 0.5 + bus['chords'] * 0.22 + bus['drums'] * 0.10 + bus['fx'] * 0.3, ir)
    # 第一版量到底鼓 −12 dB、鼓組（拍手、鈸）−28 dB、和弦 −26 dB：只聽得到底鼓。底鼓降 3 dB、鼓組與和弦各加 6–8 dB
    gains = dict(kick=0.7, drums=2.3, bass=0.9, chords=1.7, lead=1.05, fx=1.4)
    mix = sum(bus[k_] * g for k_, g in gains.items()) + wet * 0.5
    mix = hp(mix, 28)
    mix = np.tanh(mix * 1.25) / 1.25
    tail = int(0.6 * SR)
    mix[-tail:] *= np.linspace(1, 0, tail)[:, None] ** 2
    mix *= 0.89 / np.abs(mix).max()
    # ── 量一下
    rms = lambda x: 20 * np.log10(np.sqrt(np.mean(x ** 2)) + 1e-9)       # noqa: E731
    print('各軌 RMS dB：' + '、'.join(f'{k_} {rms(v * gains[k_]):.1f}' for k_, v in bus.items()) + f'、殘響 {rms(wet * 0.5):.1f}')
    m = mix.mean(1)
    lo, mid, hi = rms(lp(m, 150, 4)), rms(hp(lp(m, 4000, 4), 150, 4)), rms(hp(m, 4000, 4))
    print(f'混音：RMS {rms(m):.1f} dB、峰值 {20 * np.log10(np.abs(mix).max()):.1f} dB；低 {lo:.1f}／中 {mid:.1f}／高 {hi:.1f} dB')
    return mix


def grid_json(path):
    beats = [round(i * BEAT, 4) for i in range(BARS * 4)]
    downs = [round(i * BAR, 4) for i in range(BARS)]
    secs, cnt = [], {}
    for i, (b, name) in enumerate(SECTIONS):
        e = SECTIONS[i + 1][0] if i + 1 < len(SECTIONS) else BARS
        cnt[name] = cnt.get(name, 0) + 1
        secs.append(dict(name=f'{name}{cnt[name]}', role=name, start=round(b * BAR, 4), end=round(e * BAR, 4), bar=b))
    json.dump(dict(duration=DUR, sr=SR, tempo=BPM, meter=4, beats=beats, downbeats=downs, sections=secs,
                   cut=dict(source='原創（music_dance.py）', joins=[], pieces=[])), open(path, 'w'), ensure_ascii=False)


if __name__ == '__main__':
    out = sys.argv[1] if len(sys.argv) > 1 else 'dance.wav'
    import re
    import subprocess
    import soundfile as sf
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    mix = build().astype(np.float32)
    for _ in range(2):                                         # 響度拉到 −14 LUFS（ffmpeg ebur128 量）
        sf.write(out, mix, SR, subtype='PCM_16')
        r = subprocess.run(['ffmpeg', '-nostdin', '-hide_banner', '-i', out, '-af', 'ebur128', '-f', 'null', '-'], capture_output=True, text=True).stderr
        m = re.findall(r'I:\s+(-?[\d.]+) LUFS', r)
        if not m:
            break
        lufs = float(m[-1])
        if abs(lufs + 14.0) < 0.3:
            break
        mix = mix * 10 ** ((-14.0 - lufs) / 20)
        pk = np.abs(mix).max()
        if pk > 0.89:
            mix = np.tanh(mix / pk * 1.2) / np.tanh(1.2) * 0.89
    print(f'響度 {lufs:.1f} LUFS、峰值 {20 * np.log10(np.abs(mix).max()):.1f} dBFS')
    grid_json(os.path.splitext(out)[0] + '.json')
    print(f'寫入 {out}（{DUR:g} 秒、{BPM} BPM、{BARS} 小節）與拍格 json')
