#!/usr/bin/env python3
"""合成測試歌（numpy，不用外部素材），給 analyze.py／cutlist.py／qa.py 驗證用。

  python testsong.py -o song.wav                      # 120 BPM、32 小節、44100 Hz
  python testsong.py -o song.wav --bpm 89 --bars 24   # 換速度與長度

編制（4/4 拍，前面留 0.5 秒空白、尾端留 1 秒餘韻）：
  kick  低頻正弦掃頻＋指數衰減，每拍一下（verse、chorus）
  snare 帶通雜訊爆發＋短音，第 2、4 拍（chorus）
  hat   短高頻雜訊，八分音符（chorus）
  bass  鋸齒波（additive）跟和絃根音，verse 四分音符、chorus 八分音符
  pad   每小節換和絃 I–V–vi–IV（C 大調），所有段落都有
段落：intro（只有 pad，4 小節）→ verse（加 kick＋bass，8 小節）→ chorus（全編制、更大聲，8 小節）
      → verse → chorus …交替到小節用完。

同時輸出 song.truth.json（與 -o 同名、副檔名 .truth.json）：
  { "duration", "sr", "tempo", "meter": 4, "beats": [秒,...], "downbeats": [秒,...],
    "sections": [{"name","start","end","bar"}, ...],
    "onsets": {"kick": [秒,...], "snare": [...], "hat": [...]}, "notes": "..." }
欄位格式與 analyze.py 的 audio.json 相同，可直接比對（含 onsets 真值：合成時放下去的時間）。
注意：chorus 每個正拍都有 hat，第 2、4 拍與 snare 同時；analyze.py 會排除 snare ±40 ms 內的 hat，
所以 analyze 的 hat 數比真值少（每小節少 2 個）是設計使然，不是漏抓。
"""
import argparse
import json
import math
import os

import numpy as np
import soundfile as sf

LEAD = 0.5   # 開頭空白（秒）：讓拍格相位不是 0，才測得到相位擬合
TAIL = 1.0   # 尾端餘韻（秒）
METER = 4

# I–V–vi–IV（C 大調）：和絃名、根音 MIDI、pad 三和音 MIDI（用轉位讓聲部平順）
CHORDS = [
    ("C", 36, [60, 64, 67]),
    ("G", 43, [59, 62, 67]),
    ("Am", 45, [57, 60, 64]),
    ("F", 41, [57, 60, 65]),
]


def hz(midi):
    return 440.0 * 2 ** ((midi - 69) / 12)


def kick(sr, level):
    """低頻正弦掃頻（150→50 Hz）＋指數衰減。"""
    n = int(0.30 * sr)
    t = np.arange(n) / sr
    tau = 0.03
    # 瞬時頻率 f(t) = 50 + 100·e^(-t/τ)，相位取積分
    phase = 2 * math.pi * (50 * t + 100 * tau * (1 - np.exp(-t / tau)))
    return level * np.sin(phase) * np.exp(-t / 0.12)


def snare(sr, level, rng):
    """帶通雜訊爆發（200–8000 Hz）＋ 180 Hz 短音。"""
    from scipy.signal import butter, sosfilt
    n = int(0.22 * sr)
    t = np.arange(n) / sr
    noise = rng.standard_normal(n)
    noise = sosfilt(butter(2, [200, 8000], btype="band", fs=sr, output="sos"), noise)
    body = np.sin(2 * math.pi * 180 * t) * np.exp(-t / 0.05)
    return level * (0.5 * noise * np.exp(-t / 0.08) + 0.6 * body)


def hat(sr, level, rng):
    """短高頻雜訊：白噪音做兩次差分（高通）再乘衰減。"""
    n = int(0.08 * sr)
    t = np.arange(n) / sr
    noise = rng.standard_normal(n + 2)
    noise = np.diff(np.diff(noise)) / 4
    return level * noise * np.exp(-t / 0.03)


def saw(freq, n, sr):
    """加法合成鋸齒波（限制諧波數避免混疊）。"""
    t = np.arange(n) / sr
    H = max(1, min(40, int(3000 / freq)))   # 諧波到 3 kHz 為止（真實 bass 的亮度）
    y = np.zeros(n)
    for h in range(1, H + 1):
        y += np.sin(2 * math.pi * h * freq * t) / h
    return y * (2 / math.pi)


def bass_note(freq, dur, sr, level):
    n = int(dur * sr)
    t = np.arange(n) / sr
    env = np.minimum(1, t / 0.005) * (0.35 + 0.65 * np.exp(-t / 0.25))
    # 收尾 10 ms 淡出，避免爆音
    fade = np.minimum(1, (dur - t) / 0.01)
    return level * saw(freq, n, sr) * env * np.clip(fade, 0, 1)


def pad_chord(midis, dur, sr, level):
    n = int(dur * sr)
    t = np.arange(n) / sr
    y = np.zeros(n)
    for m in midis:
        f = hz(m)
        # 兩個微失諧振盪器，聽起來像 pad
        y += np.sin(2 * math.pi * f * t) + 0.5 * np.sin(2 * math.pi * f * 1.003 * t + 0.7)
    env = np.minimum(1, t / 0.03) * np.minimum(1, (dur - t) / 0.08)
    return level * y / len(midis) * np.clip(env, 0, 1)


def build_sections(bars):
    """intro 4 小節 → verse 8 → chorus 8 → verse 8 → chorus … 回傳 [(name, start_bar, end_bar)]。"""
    out = []
    b = 0
    intro = min(4, bars)
    out.append(("intro", 0, intro))
    b = intro
    i = 1
    while b < bars:
        for name in ("verse", "chorus"):
            if b >= bars:
                break
            e = min(bars, b + 8)
            out.append((f"{name}{i}", b, e))
            b = e
        i += 1
    return out


def add(y, start_sample, sig):
    a = start_sample
    e = min(len(y), a + len(sig))
    if e > a:
        y[a:e] += sig[: e - a]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-o", "--out", required=True, help="輸出 wav 路徑（真值 JSON 同名 .truth.json）")
    ap.add_argument("--bpm", type=float, default=120.0)
    ap.add_argument("--bars", type=int, default=32)
    ap.add_argument("--sr", type=int, default=44100)
    a = ap.parse_args()
    if a.bars < 1 or a.bpm <= 0:
        ap.error("--bars 至少 1，--bpm 必須大於 0")

    sr = a.sr
    P = 60.0 / a.bpm
    bar_dur = METER * P
    dur = LEAD + a.bars * bar_dur + TAIL
    y = np.zeros(int(dur * sr))
    rng = np.random.default_rng(12345)
    sections = build_sections(a.bars)

    def section_of(bar):
        for name, s, e in sections:
            if s <= bar < e:
                return name
        return sections[-1][0]

    k_sig = {lv: kick(sr, lv) for lv in (0.8, 1.0)}
    sn_sig = snare(sr, 0.7, rng)
    hat_on = hat(sr, 0.28, rng)
    hat_off = hat(sr, 0.18, rng)
    onsets = {"kick": [], "snare": [], "hat": []}   # 真值：實際放下去的時間（秒）

    for bar in range(a.bars):
        kind = section_of(bar).rstrip("0123456789")
        chord_name, root, triad = CHORDS[bar % len(CHORDS)]
        t_bar = LEAD + bar * bar_dur
        pad_level = 0.30 if kind == "chorus" else 0.22
        add(y, int(t_bar * sr), pad_chord(triad, bar_dur, sr, pad_level))
        for beat in range(METER):
            t_beat = t_bar + beat * P
            s0 = int(round(t_beat * sr))
            if kind == "intro":
                continue
            add(y, s0, k_sig[1.0 if kind == "chorus" else 0.8])
            onsets["kick"].append(round(s0 / sr, 4))
            accent = 1.15 if beat == 0 else 1.0
            if kind == "verse":
                add(y, s0, bass_note(hz(root), P * 0.95, sr, 0.35 * accent))
            else:
                add(y, s0, bass_note(hz(root), P / 2 * 0.95, sr, 0.45 * accent))
                add(y, int(round((t_beat + P / 2) * sr)), bass_note(hz(root), P / 2 * 0.95, sr, 0.40))
                if beat in (1, 3):
                    add(y, s0, sn_sig)
                    onsets["snare"].append(round(s0 / sr, 4))
                add(y, s0, hat_on)
                onsets["hat"].append(round(s0 / sr, 4))
                s_off = int(round((t_beat + P / 2) * sr))
                add(y, s_off, hat_off)
                onsets["hat"].append(round(s_off / sr, 4))
        if kind == "chorus":
            # chorus 整段再大聲一些
            seg = slice(int(t_bar * sr), int((t_bar + bar_dur) * sr))
            y[seg] *= 1.25

    y *= 0.9 / (np.max(np.abs(y)) + 1e-9)
    os.makedirs(os.path.dirname(os.path.abspath(a.out)) or ".", exist_ok=True)
    sf.write(a.out, y.astype(np.float32), sr, subtype="PCM_16")

    beats = [round(LEAD + i * P, 4) for i in range(a.bars * METER)]
    downbeats = beats[::METER]
    sec_json = []
    for i, (name, s, e) in enumerate(sections):
        start = LEAD + s * bar_dur
        end = dur if i == len(sections) - 1 else LEAD + e * bar_dur
        sec_json.append({"name": name, "start": round(start, 4), "end": round(end, 4), "bar": s})
    truth = {
        "duration": round(len(y) / sr, 4), "sr": sr, "tempo": a.bpm, "meter": METER,
        "beats": beats, "downbeats": downbeats, "sections": sec_json,
        "onsets": onsets,
        "notes": "onsets 是合成時放下去的時間。chorus 第 2、4 拍的 hat 與 snare 同時，analyze.py 會排除 snare ±40 ms 內的 hat，"
                 "所以 analyze 的 hat 數每小節比這裡少 2 個是設計使然。",
    }
    truth_path = os.path.splitext(a.out)[0] + ".truth.json"
    with open(truth_path, "w", encoding="utf-8") as f:
        json.dump(truth, f, ensure_ascii=False, indent=1)

    print(f"寫入 {a.out}  {dur:.2f} 秒  {a.bpm:g} BPM  {a.bars} 小節  第一拍 {LEAD} 秒")
    print(f"真值 {truth_path}  onsets kick {len(onsets['kick'])} snare {len(onsets['snare'])} hat {len(onsets['hat'])}")
    print(f"{'段落':<10}{'起(秒)':>9}{'迄(秒)':>9}{'小節':>6}")
    for s in sec_json:
        print(f"{s['name']:<10}{s['start']:>9.3f}{s['end']:>9.3f}{s['bar']:>6}")


if __name__ == "__main__":
    main()
