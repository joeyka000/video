"""可愛風原創配樂範本（合成、沒有版權問題）：旅行手帳、情侶日常、寵物、開箱。128 BPM、96 小節＝剛好 180 秒（3 分鐘）。

  python music_kawaii.py out.wav        → out.wav ＋ out.json（精確拍格與段落，psyfx.Grid／beatqa.py 直接吃）

風格：kawaii pop（音樂盒＋鐵琴主旋律、彈跳貝斯、拍手、晶片琶音、反拍開鈸），降 E 大調，最後一次副歌升到 F 大調。
段落（SECTIONS：起小節、名稱、角色）對齊畫面的頁——改 SECTIONS 就換結構；小節長 = 240 / BPM 秒：
  intro 8（前 4 小節只有音樂盒，後 4 小節加鼓）→ verse 8 → verse 8（最後一小節滾奏）→ chorus 16
  → verse 16（前 8 小節抽掉底鼓，音樂盒＋貝斯）→ chorus 16 → bridge 8（半速、柔）→ chorus 8（升 key）→ outro 8
PAGE_BARS：畫面換頁的小節，小節線前放一聲咻；PIN_BEATS：(小節, 拍) 放一聲「啵」（圖釘落下、貼紙彈出）。
樂器都從 music_dance.py 借；這裡多了音樂盒 box()、晶片音 chip()、啵 pop()。寫歌不能用耳朵聽，靠量（各軌 RMS、頻段、響度 −14 LUFS）。
"""
import json
import os
import re
import subprocess
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import music_dance as M  # noqa: E402

SR = M.SR
BPM = 128
BEAT = 60 / BPM
BAR = BEAT * 4
BARS = 96
DUR = BARS * BAR
N = int(round(DUR * SR))
SECTIONS = [(0, 'intro', 'intro'), (8, 'verse', 'verse'), (16, 'verse', 'verse'), (24, 'chorus', 'chorus'), (40, 'verse', 'verse'),
            (56, 'chorus', 'chorus'), (72, 'bridge', 'bridge'), (80, 'chorus', 'chorus'), (88, 'outro', 'outro')]
KEY_UP = {80: 2, 88: 2}                      # 從這個小節起整體升幾個半音
PAGE_BARS = [8, 16, 24, 32, 40, 48, 56, 64, 72, 80, 88]
PIN_BEATS = [(b, 2) for b in (8, 16, 24, 32, 40, 56, 64, 72, 80)]
rng = M.rng

CH = {'IV': ([56, 60, 63, 67], 32), 'V': ([58, 62, 65, 70], 34), 'iii': ([55, 58, 62, 65], 31), 'vi': ([60, 63, 67, 70], 36),
      'I': ([58, 63, 67, 70], 27), 'ii': ([53, 56, 60, 65], 29)}
PROG = {'chorus': ['IV', 'V', 'iii', 'vi', 'IV', 'V', 'I', 'I'], 'verse': ['I', 'vi', 'IV', 'V'], 'intro': ['I', 'vi', 'IV', 'V'],
        'bridge': ['ii', 'V', 'iii', 'vi', 'ii', 'V', 'I', 'V'], 'outro': ['IV', 'V', 'iii', 'vi', 'IV', 'V', 'I', 'I']}
# 副歌鉤子（8 小節）：(拍, MIDI, 幾拍)。五聲音階為主，好記、像童謠
HOOK = [
    [(0, 75, .5), (.5, 75, .5), (1, 79, .5), (1.5, 82, 1.0), (2.5, 79, .5), (3, 75, 1.0)],
    [(0, 77, .5), (.5, 77, .5), (1, 82, .5), (1.5, 84, 1.0), (2.5, 82, .5), (3, 77, 1.0)],
    [(0, 79, .5), (.5, 77, .5), (1, 74, .5), (1.5, 77, 1.0), (2.5, 74, .5), (3, 70, 1.0)],
    [(0, 72, .5), (.5, 75, .5), (1, 79, 1.5), (2.5, 77, .5), (3, 75, 1.0)],
    [(0, 75, .5), (.5, 75, .5), (1, 79, .5), (1.5, 82, 1.0), (2.5, 79, .5), (3, 84, 1.0)],
    [(0, 86, .5), (.5, 84, .5), (1, 82, .5), (1.5, 77, 1.0), (2.5, 79, .5), (3, 82, 1.0)],
    [(0, 79, .75), (.75, 77, .75), (1.5, 75, .5), (2, 74, .5), (2.5, 75, .5), (3, 70, 1.0)],
    [(0, 75, 2.0), (2.5, 70, .5), (3, 75, 1.0)],
]
VERSE = [  # 主歌的音樂盒短句（4 小節循環）
    [(0, 70, .5), (1, 75, .5), (1.5, 79, .5), (2.5, 77, .5), (3, 75, .5)],
    [(0, 72, .5), (1, 75, .5), (1.5, 79, .5), (2.5, 75, .5), (3.5, 72, .5)],
    [(0, 68, .5), (1, 72, .5), (1.5, 75, .5), (2.5, 79, .5), (3, 80, .5)],
    [(0, 77, .5), (1, 74, .5), (1.5, 70, .5), (2.5, 74, .5), (3, 77, 1.0)],
]


def sect(bar):
    cur = SECTIONS[0]
    for s in SECTIONS:
        if bar >= s[0]:
            cur = s
    return cur[1], cur[0]


def shift(bar):
    v = 0
    for b, s in KEY_UP.items():
        if bar >= b:
            v = s
    return v


def box(m, dur=0.5):
    """音樂盒／鐵琴：正弦＋非整數倍泛音，敲一下就衰減。"""
    n = int(1.1 * SR)
    t = np.arange(n) / SR
    f = M.hz(m)
    x = np.sin(2 * np.pi * f * t) * np.exp(-t * 5.5) + 0.38 * np.sin(2 * np.pi * f * 2.76 * t) * np.exp(-t * 11) \
        + 0.18 * np.sin(2 * np.pi * f * 5.4 * t) * np.exp(-t * 22) + 0.25 * np.sin(2 * np.pi * f * 2 * t) * np.exp(-t * 7)
    return x * np.minimum(1, t / 0.002) * 0.22


def chip(m, dur=0.09):
    n = int((dur + 0.03) * SR)
    t = np.arange(n) / SR
    x = M.square(M.hz(m), n)
    return x * np.minimum(1, t / 0.002) * np.where(t < dur, 1.0, np.exp(-(t - dur) * 120)) * 0.09


def pop():
    """啵：音高往上滑的短正弦（圖釘、貼紙彈出）。"""
    n = int(0.12 * SR)
    t = np.arange(n) / SR
    f = 420 + 900 * (t / 0.12) ** 0.6
    return np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 26) * np.minimum(1, t / 0.003) * 0.3


def build():
    place = M.place
    bus = {k: np.zeros((N, 2)) for k in ('kick', 'drums', 'bass', 'chords', 'lead', 'bells', 'fx')}
    K, C, S = M.kick(), M.clap(), M.snare()
    kick_t = []
    for bar in range(BARS):
        name, start = sect(bar)
        k = bar - start
        tr = shift(bar)
        prog = PROG[name]
        ms, root = CH[prog[k % len(prog)]]
        ms, root = [m + tr for m in ms], root + tr
        t0 = bar * BAR
        last = bar == BARS - 1
        nxt = sect(bar + 1)[0] if bar + 1 < BARS else None
        nxt_start = sect(bar + 1)[1] if bar + 1 < BARS else None
        build_bar = (nxt == 'chorus' and nxt_start == bar + 1 and name != 'chorus')
        chorus, verse, bridge, intro, outro = (name == x for x in ('chorus', 'verse', 'bridge', 'intro', 'outro'))
        light = (verse and start == 40 and k < 8) or (intro and k < 4)          # 抽掉底鼓的小節
        second = chorus and (k >= 8 or start >= 56)
        # ── 鼓
        if last:
            place(bus['kick'], K, t0, 0.9)
            kick_t.append(t0)
            place(bus['fx'], M.crash(), t0, 0.8)
        elif bridge:                                         # 半速：1、3 拍底鼓，3 拍拍手
            for b in (0, 2.5):
                place(bus['kick'], K, t0 + b * BEAT, 0.8)
                kick_t.append(t0 + b * BEAT)
            if not (build_bar):
                place(bus['drums'], C, t0 + 2 * BEAT, 0.55, 0.05)
            for s in range(0, 16, 2):
                place(bus['drums'], M.hat(False, 0.5), t0 + s * BEAT / 4, 1.0, 0.3)
        elif not light:
            for b in range(4):
                if build_bar and b == 3:
                    continue
                place(bus['kick'], K, t0 + b * BEAT, 0.85 if (verse or intro or outro) else 1.0)
                kick_t.append(t0 + b * BEAT)
            for b in (1, 3):
                if not (build_bar and b == 3):
                    place(bus['drums'], C, t0 + b * BEAT, 0.9 if chorus else 0.6, 0.05)
            for s in range(16):
                if build_bar and s >= 12:
                    break
                acc = 1.0 if s % 4 == 2 else 0.55 if s % 2 == 0 else 0.3
                if chorus or s % 2 == 0:
                    place(bus['drums'], M.hat(False, acc * (1.0 if chorus else 0.65)), t0 + s * BEAT / 4 + (0.012 if s % 2 else 0), 1.0, 0.3)
            if chorus:
                for b in range(4):
                    place(bus['drums'], M.hat(True, 0.85), t0 + (b + 0.5) * BEAT, 1.0, -0.25)
        else:                                                # light：只有很輕的八分鈸與 2、4 拍彈指
            for s in range(0, 16, 2):
                place(bus['drums'], M.hat(False, 0.35), t0 + s * BEAT / 4, 1.0, 0.3)
            if not intro:
                for b in (1, 3):
                    place(bus['drums'], C, t0 + b * BEAT, 0.3, 0.05)
        if build_bar:
            pos = [0, .5, 1, 1.5, 2, 2.25, 2.5, 2.75] + [3 + i / 8 for i in range(6)]
            for i, b in enumerate(pos):
                place(bus['drums'], S, t0 + b * BEAT, 0.3 + 0.5 * i / len(pos))
            place(bus['fx'], M.riser(BAR), t0, 1.0)
        # ── 貝斯（彈跳：根音與八度交替；主歌四分音符跳）
        if last:
            place(bus['bass'], M.bass(root + 12, BAR * 0.9), t0, 0.9)
        elif chorus:
            for e in range(8):
                m = root + 12 if e % 2 == 0 else root + 24
                if e == 7 and k % 4 == 3:
                    m = root + 19
                place(bus['bass'], M.bass(m, BEAT * 0.4), t0 + e * BEAT / 2, 1.0 if e % 2 == 0 else 0.75)
        elif bridge:
            place(bus['bass'], M.bass(root + 12, BEAT * 1.8), t0, 0.85)
            place(bus['bass'], M.bass(root + 12, BEAT * 1.2), t0 + 2.5 * BEAT, 0.7)
        elif not (intro and k < 4):
            for b_, d, m in ((0, .45, 12), (1, .3, 24), (1.5, .3, 12), (2, .45, 12), (3, .3, 24), (3.5, .3, 19)):
                if build_bar and b_ >= 3:
                    continue
                place(bus['bass'], M.bass(root + m, BEAT * d), t0 + b_ * BEAT, 0.85 if not light else 0.7)
        # ── 和弦：柔的墊底＋反拍的短和弦（像拍手打拍子）
        if last:
            place(bus['chords'], M.pad([m + tr for m in CH['I'][0]] + [75 + tr, 79 + tr], BAR), t0, 1.6)
        else:
            place(bus['chords'], M.pad(ms, BAR), t0, 0.85 if chorus else 0.65)
            if chorus:
                for s in (2, 6, 10, 14):
                    place(bus['chords'], M.stab(ms, 0.10, 0.9), t0 + s * BEAT / 4, 0.9)
                for s in (0, 8):
                    place(bus['chords'], M.stab(ms, 0.16, 0.7), t0 + s * BEAT / 4, 0.7)
            elif not bridge and not (intro and k < 4):
                for s in (2, 6, 10, 14):
                    if build_bar and s >= 12:
                        continue
                    place(bus['chords'], M.stab(ms, 0.09, 0.5), t0 + s * BEAT / 4, 0.7)
        # ── 主旋律
        if chorus:
            for b_, m, d in HOOK[k % 8]:
                place(bus['bells'], box(m + tr), t0 + b_ * BEAT, 1.0, -0.15)
                place(bus['lead'], M.lead(m + tr - 12, d * BEAT), t0 + b_ * BEAT, 0.55, 0.15)
                if second:
                    place(bus['bells'], box(m + tr + 12), t0 + b_ * BEAT, 0.45, 0.3)
            for s in range(16):                              # 晶片琶音
                place(bus['lead'], chip(ms[s % 4] + 24 + (12 if s % 8 >= 4 else 0)), t0 + s * BEAT / 4, 0.8 if second else 0.5, 0.55 if s % 2 else -0.55)
        elif verse or intro:
            for b_, m, d in VERSE[k % 4]:
                place(bus['bells'], box(m + tr), t0 + b_ * BEAT, 0.9, 0.2 if (b_ * 2) % 2 else -0.2)
            if verse and not light and k % 4 >= 2:
                for s in range(0, 16, 2):
                    place(bus['lead'], chip(ms[(s // 2) % 4] + 24), t0 + s * BEAT / 4, 0.45, 0.5 if s % 4 else -0.5)
        elif bridge:
            for b_, m, d in HOOK[k % 8][::2]:               # 鉤子的骨幹音，慢一點
                place(bus['bells'], box(m + tr - 12), t0 + b_ * BEAT, 1.0)
            for s in range(0, 16, 4):
                place(bus['bells'], box(ms[(s // 4) % 4] + 24), t0 + (s + 2) * BEAT / 4, 0.4, 0.5)
        elif outro and not last:
            for b_, m, d in HOOK[k % 8]:
                place(bus['bells'], box(m + tr), t0 + b_ * BEAT, 0.9 * (1 - 0.08 * k))
        if k == 0 and chorus:
            place(bus['fx'], M.crash(), t0, 1.0)
            place(bus['fx'], M.boom(), t0, 0.5)
        elif k == 8 and chorus:
            place(bus['fx'], M.crash(), t0, 0.6)
    for b in PAGE_BARS:
        place(bus['fx'], M.swish(), b * BAR - 0.36, 1.0, rng.uniform(-0.5, 0.5))
    for b, beat in PIN_BEATS:
        place(bus['fx'], pop(), b * BAR + beat * BEAT, 1.0)
    # ── 旁鏈
    duck = np.ones(N)
    t = np.arange(int(0.4 * SR)) / SR
    shape = 1 - 0.6 * np.exp(-t / 0.08)
    for kt in kick_t:
        i = int(round(kt * SR))
        seg = shape[:max(0, min(len(shape), N - i))]
        duck[i:i + len(seg)] = np.minimum(duck[i:i + len(seg)], seg)
    bus['bass'] *= duck[:, None]
    bus['chords'] *= (0.4 + 0.6 * duck)[:, None]
    # ── 延遲與殘響（音樂盒要有空間感）
    d = int(0.75 * BEAT * SR)
    dl = np.zeros_like(bus['bells'])
    dl[d:, 0] += bus['bells'][:-d, 1] * 0.28
    dl[2 * d:, 1] += bus['bells'][:-2 * d, 0] * 0.16
    bus['bells'] += M.lp(dl, 5000)
    ir = M.reverb_ir(sec=2.0, decay=3.6)
    wet = M.conv(bus['bells'] * 0.55 + bus['lead'] * 0.3 + bus['chords'] * 0.2 + bus['drums'] * 0.08 + bus['fx'] * 0.3, ir)
    gains = dict(kick=0.62, drums=2.0, bass=0.85, chords=1.5, lead=1.0, bells=1.5, fx=1.3)
    mix = sum(bus[k_] * g for k_, g in gains.items()) + wet * 0.55
    mix = M.hp(mix, 28)
    mix = np.tanh(mix * 1.2) / 1.2
    tail = int(0.8 * SR)
    mix[-tail:] *= np.linspace(1, 0, tail)[:, None] ** 2
    mix *= 0.89 / np.abs(mix).max()
    rms = lambda x: 20 * np.log10(np.sqrt(np.mean(x ** 2)) + 1e-9)       # noqa: E731
    print('各軌 RMS dB：' + '、'.join(f'{k_} {rms(v * gains[k_]):.1f}' for k_, v in bus.items()) + f'、殘響 {rms(wet * 0.55):.1f}')
    m = mix.mean(1)
    print(f'混音：低 {rms(M.lp(m, 150, 4)):.1f}／中 {rms(M.hp(M.lp(m, 4000, 4), 150, 4)):.1f}／高 {rms(M.hp(m, 4000, 4)):.1f} dB')
    for s0, nm, _ in SECTIONS:
        e = next((x[0] for x in SECTIONS if x[0] > s0), BARS)
        print(f'  {nm:7} 小節 {s0:2d}–{e:2d}  RMS {rms(m[int(s0 * BAR * SR):int(e * BAR * SR)]):.1f} dB')
    return mix


def grid_json(path):
    beats = [round(i * BEAT, 4) for i in range(BARS * 4)]
    downs = [round(i * BAR, 4) for i in range(BARS)]
    secs, cnt = [], {}
    for i, (b, name, role) in enumerate(SECTIONS):
        e = SECTIONS[i + 1][0] if i + 1 < len(SECTIONS) else BARS
        cnt[name] = cnt.get(name, 0) + 1
        secs.append(dict(name=f'{name}{cnt[name]}', role=role, start=round(b * BAR, 4), end=round(e * BAR, 4), bar=b))
    json.dump(dict(duration=DUR, sr=SR, tempo=BPM, meter=4, beats=beats, downbeats=downs, sections=secs,
                   cut=dict(source='原創（music_kawaii.py）', joins=[], pieces=[])), open(path, 'w'), ensure_ascii=False)


if __name__ == '__main__':
    import soundfile as sf
    out = sys.argv[1] if len(sys.argv) > 1 else 'kawaii.wav'
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    mix = build().astype(np.float32)
    lufs = 0.0
    for _ in range(2):
        sf.write(out, mix, SR, subtype='PCM_16')
        r = subprocess.run(['ffmpeg', '-nostdin', '-hide_banner', '-i', out, '-af', 'ebur128', '-f', 'null', '-'], capture_output=True, text=True).stderr
        mm = re.findall(r'I:\s+(-?[\d.]+) LUFS', r)
        if not mm:
            break
        lufs = float(mm[-1])
        if abs(lufs + 14.0) < 0.3:
            break
        mix = mix * 10 ** ((-14.0 - lufs) / 20)
        pk = np.abs(mix).max()
        if pk > 0.89:
            mix = np.tanh(mix / pk * 1.2) / np.tanh(1.2) * 0.89
    grid_json(os.path.splitext(out)[0] + '.json')
    print(f'響度 {lufs:.1f} LUFS；寫入 {out}（{DUR:g} 秒、{BPM} BPM、{BARS} 小節）與拍格 json')
