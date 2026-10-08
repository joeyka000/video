"""原創合成配樂範本（不需取樣、沒有版權問題）：pad、撥弦琶音、鼓組、旁鏈 sub bass、主旋律、上升噪音、重擊、撕裂聲。

改 BPM、DUR、SECTIONS（每段從第幾小節開始、什麼型態）、DROP（落拍小節）、LOGO（片尾重擊小節）、TICKS（字卡提示音秒數），
讓音樂的段落對齊畫面：小節長 = 240 / BPM 秒，畫面的段落邊界最好落在小節上（100 BPM → 2.4 秒一小節）。

段落型態：intro（濾暗 pad）、arp（加撥弦）、light（輕鼓）、groove（穩定律動，教學／介紹段）、build（漸強，最後半拍留白）、
         main（主段：完整鼓組＋八分音符低音＋高八度琶音＋主旋律）、break（抽離）、end（長和弦收尾）
  python music.py out.wav
"""
import sys

import numpy as np
from scipy import signal

SR = 48000
BPM = 100
BEAT = 60 / BPM
BAR = BEAT * 4
DUR = 30.0
N = int(DUR * SR)
rng = np.random.default_rng(7)

CHORDS = [  # 每小節一個和弦（循環）：Fmaj9 → C/E(add9) → Am9 → G6
    [53, 57, 60, 64, 67],
    [52, 55, 60, 62, 67],
    [57, 60, 64, 67, 71],
    [55, 59, 62, 64, 69],
]
ROOTS = [29, 28, 33, 31]


def hz(m):
    return 440.0 * 2 ** ((m - 69) / 12)


def chord_at(bar):
    return CHORDS[bar % 4], ROOTS[bar % 4]


def t_of(bar, beat=0.0):
    return bar * BAR + beat * BEAT


def place(buf, x, t, gain=1.0, pan=0.0):
    i = int(t * SR)
    if i >= len(buf) or i + len(x) <= 0:
        return
    j0 = max(0, -i)
    i = max(0, i)
    x = x[j0:j0 + len(buf) - i]
    l, r = np.cos((pan + 1) * np.pi / 4), np.sin((pan + 1) * np.pi / 4)
    if x.ndim == 1:
        buf[i:i + len(x), 0] += x * gain * l * 1.414
        buf[i:i + len(x), 1] += x * gain * r * 1.414
    else:
        buf[i:i + len(x)] += x * gain


def env_adsr(n, a, d, s, r, sustain_len):
    a, d, r = int(a * SR), int(d * SR), int(r * SR)
    hold = max(0, int(sustain_len * SR) - a - d)
    e = np.concatenate([np.linspace(0, 1, max(a, 1)), np.linspace(1, s, max(d, 1)), np.full(hold, s), np.linspace(s, 0, max(r, 1))])
    return e[:n] if len(e) >= n else np.pad(e, (0, n - len(e)))


def saw(f, n, phase=0.0):
    t = np.arange(n) / SR
    # 加法合成的帶限鋸齒波（避免混疊）
    out = np.zeros(n)
    k = 1
    while k * f < SR / 2.2 and k < 60:
        out += np.sin(2 * np.pi * k * f * t + phase * k) / k
        k += 1
    return out * 0.6


def lowpass(x, fc, q=0.707):
    fc = np.clip(fc, 20, SR / 2.1)
    b, a = signal.iirfilter(2, fc / (SR / 2), btype='low', ftype='butter')
    return signal.lfilter(b, a, x, axis=0)


def sweep_lp(x, f0, f1, seg=2048):
    """隨時間變化的低通（分段濾波，簡單但夠用）。"""
    out = np.zeros_like(x)
    n = len(x)
    zi = None
    for s in range(0, n, seg):
        u = s / max(1, n - 1)
        fc = f0 * (f1 / f0) ** u
        b, a = signal.butter(2, min(fc, SR / 2.2) / (SR / 2))
        if zi is None or zi.shape[0] != max(len(a), len(b)) - 1:
            zi = signal.lfilter_zi(b, a) * 0
        out[s:s + seg], zi = signal.lfilter(b, a, x[s:s + seg], zi=zi)
    return out


def reverb_ir(sec=2.4, decay=3.2, seed=1):
    r = np.random.default_rng(seed)
    n = int(sec * SR)
    t = np.arange(n) / SR
    ir = np.stack([r.normal(0, 1, n), r.normal(0, 1, n)], 1) * np.exp(-t * decay)[:, None]
    ir[:int(0.012 * SR)] *= np.linspace(0, 1, int(0.012 * SR))[:, None]
    ir = lowpass(ir, 6500)
    return ir / np.sqrt((ir ** 2).sum(0))


def convolve_st(x, ir):
    if x.ndim == 1:
        x = np.stack([x, x], 1)
    return np.stack([signal.fftconvolve(x[:, c], ir[:, c])[:len(x)] for c in range(2)], 1)


# ───────── 樂器 ─────────
def pad_note(m, dur, bright=1.0):
    n = int((dur + 1.6) * SR)
    voices = []
    for det, pan in ((-0.09, -0.7), (0.0, 0.0), (0.08, 0.7)):
        f = hz(m + det)
        v = saw(f, n, rng.random() * 6.28)
        voices.append((v, pan))
    out = np.zeros((n, 2))
    for v, pan in voices:
        out[:, 0] += v * np.cos((pan + 1) * np.pi / 4)
        out[:, 1] += v * np.sin((pan + 1) * np.pi / 4)
    e = env_adsr(n, 0.5, 0.6, 0.8, 1.5, dur)
    return out * e[:, None] * 0.12


def pluck(m, bright=1.0):
    n = int(0.6 * SR)
    t = np.arange(n) / SR
    f = hz(m)
    x = saw(f, n) * 0.7 + np.sin(2 * np.pi * f * 2 * t) * 0.15
    e = np.exp(-t * 9)
    # 濾波包絡：起音亮，迅速變暗
    y = np.zeros(n)
    seg = 1024
    for s in range(0, n, seg):
        fc = 300 + 5200 * bright * np.exp(-s / SR * 14)
        b, a = signal.butter(2, min(fc, SR / 2.2) / (SR / 2))
        y[s:s + seg] = signal.lfilter(b, a, x[s:s + seg])
    return y * e * 0.32


def kick(gain=1.0):
    n = int(0.45 * SR)
    t = np.arange(n) / SR
    f = 46 + 110 * np.exp(-t * 32)
    ph = 2 * np.pi * np.cumsum(f) / SR
    x = np.sin(ph) * np.exp(-t * 7.5)
    click = rng.normal(0, 1, n) * np.exp(-t * 400) * 0.25
    return np.tanh((x + click) * 1.6) * 0.75 * gain


def clap():
    n = int(0.5 * SR)
    t = np.arange(n) / SR
    nz = rng.normal(0, 1, n)
    b, a = signal.butter(2, [900 / (SR / 2), 5200 / (SR / 2)], btype='band')
    nz = signal.lfilter(b, a, nz)
    e = np.zeros(n)
    for k, d in enumerate((0.0, 0.011, 0.022, 0.034)):
        i = int(d * SR)
        e[i:] += np.exp(-(t[:n - i]) * (110 if k < 3 else 22)) * (0.6 if k < 3 else 1.0)
    return nz * e * 0.5


def hat(open_=False, vel=1.0):
    n = int((0.32 if open_ else 0.06) * SR)
    t = np.arange(n) / SR
    nz = rng.normal(0, 1, n)
    b, a = signal.butter(2, 7000 / (SR / 2), btype='high')
    nz = signal.lfilter(b, a, nz)
    return nz * np.exp(-t * (11 if open_ else 70)) * 0.16 * vel


def sub(m, dur):
    n = int(dur * SR)
    t = np.arange(n) / SR
    f = hz(m)
    x = np.sin(2 * np.pi * f * t) + 0.25 * np.sin(2 * np.pi * f * 2 * t)
    e = np.minimum(1, t / 0.008) * np.minimum(1, (dur - t) / 0.03).clip(0, 1)
    return np.tanh(x * 1.3) * e * 0.42


def noise_riser(dur, f0=300, f1=9000):
    n = int(dur * SR)
    nz = rng.normal(0, 1, n)
    y = sweep_lp(nz, f0, f1)
    e = np.linspace(0, 1, n) ** 2.2
    return y * e * 0.22


def swish(dur=0.6, up=True):
    n = int(dur * SR)
    t = np.arange(n) / SR
    nz = rng.normal(0, 1, n)
    y = sweep_lp(nz, 600 if up else 9000, 9000 if up else 500)
    e = np.sin(np.pi * np.clip(t / dur, 0, 1)) ** 1.5
    return y * e * 0.3


def tear(dur=0.55):
    """撕開包裝：帶顆粒的高頻噪音，加隨機小爆點。"""
    n = int(dur * SR)
    t = np.arange(n) / SR
    nz = rng.normal(0, 1, n)
    b, a = signal.butter(2, [1800 / (SR / 2), 9500 / (SR / 2)], btype='band')
    y = signal.lfilter(b, a, nz)
    grain = (rng.random(n) < 0.02).astype(float) * rng.normal(0, 3, n)
    e = np.minimum(1, t / 0.03) * np.exp(-t * 4.0)
    am = 0.6 + 0.4 * np.sin(2 * np.pi * 38 * t + 3 * np.sin(2 * np.pi * 5 * t))
    return (y * am + grain * 0.4) * e * 0.35


def boom(dur=2.8):
    n = int(dur * SR)
    t = np.arange(n) / SR
    f = 38 + 60 * np.exp(-t * 6)
    x = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 1.6)
    nz = lowpass(rng.normal(0, 1, n), 900) * np.exp(-t * 3) * 0.3
    return np.tanh((x + nz) * 1.5) * 0.7


def shimmer(ms, dur=3.0):
    n = int(dur * SR)
    t = np.arange(n) / SR
    out = np.zeros(n)
    for m in ms:
        f = hz(m + 24)
        out += np.sin(2 * np.pi * f * t + 2 * np.sin(2 * np.pi * 5.5 * t) * 0.01) * np.exp(-t * 1.2)
    return out / len(ms) * 0.18


def tick():
    n = int(0.03 * SR)
    t = np.arange(n) / SR
    return np.sin(2 * np.pi * 2800 * t) * np.exp(-t * 260) * 0.12


# ───────── 這支片要改的地方 ─────────
SECTIONS = [(0, 'intro'), (1, 'arp'), (3, 'light'), (5, 'build'), (6, 'main'), (10, 'break'), (11, 'end')]
LOGO = 11                    # 片尾重擊的小節（通常 = 第一個 end）
TICKS = [2.4, 7.2, 12.0]     # 字卡出現的秒數：各放一聲小提示音
MELODY_FROM = 8              # main 段從第幾小節開始加主旋律


def sect(bar):
    name = SECTIONS[0][1]
    for b, s in SECTIONS:
        if bar >= b:
            name = s
    return name


def blip(f, dur=0.12):
    n = int(dur * SR)
    t = np.arange(n) / SR
    return (np.sin(2 * np.pi * f * t) + 0.3 * np.sin(2 * np.pi * f * 2 * t)) * np.exp(-t * 30) * 0.16


def build():
    mus, drm, bas, fx, send = (np.zeros((N, 2)) for _ in range(5))
    kicks = []
    nbars = int(np.ceil(DUR / BAR))
    for bar in range(nbars):
        s = sect(bar)
        ch, root = chord_at(bar)
        t0 = t_of(bar)
        if s == 'end' and bar > LOGO:
            continue  # end 段只在 LOGO 那一小節下一個長和弦
        pd = BAR * (2.8 if s == 'end' else 1.0)
        pg = {'intro': .55, 'arp': .75, 'light': .8, 'groove': .7, 'build': .75, 'main': .75, 'break': .85, 'end': .85}[s]
        fc = {'intro': 900, 'arp': 1500, 'light': 2200, 'groove': 2600, 'build': 3200, 'main': 4200, 'break': 1200, 'end': 3000}[s]
        for m in ch:
            p = lowpass(pad_note(m, pd), fc)
            place(mus, p, t0, pg)
            place(send, p, t0, pg * 0.35)
        if s not in ('intro', 'end'):
            pat = [0, 2, 4, 1, 3, 2, 4, 3, 0, 2, 4, 1, 4, 3, 2, 1]
            bright = {'arp': .35, 'light': .5, 'groove': .6, 'build': .75, 'main': 1.0, 'break': .35}[s]
            vel0 = {'arp': .55, 'light': .75, 'groove': .8, 'build': .9, 'main': 1.0, 'break': .6}[s]
            for k in range(16):
                if s == 'build' and k >= 14:
                    break
                note = ch[pat[k]] + (12 if (k >= 8 and s == 'main') else 0)
                vel = (0.75 + 0.25 * (k % 4 == 0)) * vel0
                p = pluck(note, bright)
                pan = -0.35 if k % 2 else 0.35
                place(mus, p, t0 + k * BEAT / 4, vel, pan)
                place(send, p, t0 + k * BEAT / 4, vel * 0.5, pan)
                place(mus, p * 0.35, t0 + k * BEAT / 4 + BEAT * 0.75, vel, -pan)
        if s == 'main' and bar >= MELODY_FROM:
            motif = [(0, 76, 0.5), (0.5, 79, 0.5), (1.0, 81, 1.0), (2.0, 79, 0.5), (2.5, 76, 0.5), (3.0, 74 if bar % 2 else 72, 1.0)]
            for b, m, l in motif:
                n = int((l * BEAT + 0.4) * SR)
                tt = np.arange(n) / SR
                f = hz(m)
                x = np.sin(2 * np.pi * f * tt + 0.8 * np.sin(2 * np.pi * f * 2 * tt) * np.exp(-tt * 6)) * env_adsr(n, 0.01, 0.15, 0.6, 0.35, l * BEAT)
                place(mus, x * 0.12, t0 + b * BEAT, 1.0, 0.1)
                place(send, x * 0.12, t0 + b * BEAT, 0.6, 0.1)
        if s in ('light', 'groove', 'main'):
            kg = {'light': .6, 'groove': .8, 'main': 1.0}[s]
            for b in range(4):
                place(drm, kick(kg), t0 + b * BEAT)
                kicks.append(t0 + b * BEAT)
            if s != 'light':
                for b in (1, 3):
                    cg = .9 if s == 'main' else .6
                    place(drm, clap(), t0 + b * BEAT, cg, 0.05)
                    place(send, clap(), t0 + b * BEAT, 0.3 * cg)
            steps = 16 if s == 'main' else 8
            for k in range(steps):
                place(drm, hat(False, 1.0 if k % 2 == 0 else 0.55), t0 + k * BEAT / (steps / 4), 1.0 if s == 'main' else 0.85, 0.25)
            if s == 'main':
                for b in range(4):
                    place(drm, hat(True, 0.6), t0 + b * BEAT + BEAT / 2, 1.0, -0.25)
        if s in ('light', 'groove'):
            for b in range(4):
                place(bas, sub(root, BEAT * 0.9), t0 + b * BEAT, 0.7 if s == 'light' else 0.85)
        if s == 'main':
            for k in range(8):
                place(bas, sub(root + (12 if k in (3, 7) else 0), BEAT / 2 * 0.92), t0 + k * BEAT / 2, 1.0)
        if s == 'break':
            place(bas, sub(root, BAR * 0.95), t0, 0.7)
        if s == 'build':  # 小鼓漸密＋上升噪音，最後半拍留白，下一小節落拍
            hits = [0, 1, 2, 3, 4, 4.5, 5, 5.5, 6, 6.5, 7, 7.25, 7.5, 7.75]
            for k, h in enumerate(hits):
                tt = t0 + h * BEAT / 2
                if tt >= t0 + BAR - BEAT * 0.5:
                    break
                place(drm, clap() * (0.35 + 0.65 * k / len(hits)), tt, 0.8)
            place(fx, noise_riser(BAR - BEAT * 0.5), t0, 1.0)
        if s == 'main' and sect(bar - 1) == 'build':  # 落拍
            place(fx, boom(2.2), t0, 0.6)
            place(fx, tear(0.7), t0 - 0.08, 0.9)
            place(fx, swish(0.5, False), t0 + 0.02, 0.5)
        if s == 'break' and sect(bar + 1) == 'end':
            place(fx, noise_riser(BAR * 0.95, 400, 7000) * 0.8, t0 + BAR * 0.05, 1.0)
    place(fx, tear(0.6), 1.15, 0.8)
    place(fx, swish(0.9, True), 0.35, 0.35)
    tl = t_of(LOGO)
    place(fx, boom(3.0), tl, 0.8)
    place(fx, shimmer(chord_at(LOGO)[0], 4.0), tl, 1.0)
    place(send, shimmer(chord_at(LOGO)[0], 4.0), tl, 0.8)
    for tt in TICKS:
        place(fx, tick(), tt + 0.12, 1.0, 0.3)

    sc = np.ones(N)
    for tk in kicks:
        i = int(tk * SR)
        L = int(0.32 * SR)
        e = 1 - 0.6 * np.exp(-np.arange(L) / SR / 0.075)
        j = min(N, i + L)
        sc[i:j] = np.minimum(sc[i:j], e[:j - i])
    rev = convolve_st(send, reverb_ir())
    mix = (mus + bas) * sc[:, None] + drm + fx + rev * 0.55 * sc[:, None] ** 0.5
    b, a = signal.butter(2, 28 / (SR / 2), btype='high')
    mix = signal.lfilter(b, a, mix, axis=0)
    mix = np.tanh(mix * 1.15) / np.tanh(1.15)
    t = np.arange(N) / SR
    mix *= np.clip((DUR - t) / 1.4, 0, 1)[:, None]
    mix *= 0.9 / (np.abs(mix).max() + 1e-9)
    return mix.astype(np.float32)


if __name__ == '__main__':
    import soundfile as sf
    out = sys.argv[1] if len(sys.argv) > 1 else 'music.wav'
    sf.write(out, build(), SR)
    print(out)
