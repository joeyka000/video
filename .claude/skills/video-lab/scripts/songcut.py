#!/usr/bin/env python3
"""把一首歌剪成指定長度（例 90 秒）：前奏 → 主歌 → 副歌 → 原曲的自然結尾，剪點都在小節線上。

  python analyze.py song.mp3 -o data/audio.json                       # 先分析（拍格、小節、段落）
  python songcut.py song.mp3 data/audio.json --dur 90 -o data/song90.wav
  python songcut.py song.mp3 data/audio.json --dur 90 -o data/song90.wav --plan          # 只印段落與計畫，不輸出
  python songcut.py song.mp3 data/audio.json --dur 90 -o x.wav --roles "S1:intro,S3:verse,S4:chorus"
  python songcut.py song.mp3 data/audio.json --dur 90 -o x.wav --keep "0-4,16-56,140-144"  # 手動指定小節區間

輸出：
  x.wav          剪好的歌（44.1 kHz 立體聲，長度剛好 --dur 秒，最後 --fade 秒淡出）
  x.json         新時間軸的 audio.json（beats、downbeats、sections 帶 role、env、onsets 全部換算到剪後的秒數），
                 引擎直接吃；另有 "cut": {"pieces": [{src0, src1, out0, bars}], "joins": [剪後秒數], "source"}
  終端機印：段落表（能量、角色）、選中的區間、每個剪接點在第幾秒（原曲幾秒接到幾秒）

做法：
  1. 段落角色：audio.json 的 sections 若已用 intro／verse／chorus／bridge／outro 命名就照用；
     自動分段（S1、S2…）時依每段平均能量分：第一段且偏小聲＝intro、最後一段＝outro、能量前 35% 的段＝chorus、其他＝verse。
     --roles 可逐段覆寫（判錯時一定要改：剪的品質取決於角色對不對，先跑 --plan 聽一下段落表）
  2. 組合搜尋：總小節數 B（最後一小節後留 --tail-min～--tail-max 秒殘響）、前奏 2–8 小節（第一段的長度、4 或 8）、
     結尾＝原曲最後有聲的 2–8 小節（原曲真正的收尾，不是硬淡出）、中段＝B − 前奏 − 結尾，起點是「樂句頭（段落頭＋4 小節倍數）」：
       ＋ 中段結束在副歌（接原曲結尾最自然）、＋ 有主歌→副歌的轉換、＋ 副歌佔比、＋ 能量、＋ 前奏剛好是整段
       − 接點的音色／和聲跳動（原本該接的那一小節 vs 現在接上的：chroma cos 距離＋MFCC 距離，除以相鄰小節的典型跳動）
       − 中段不是 4 的倍數、結尾不是樂句頭、只跳掉 1–3 小節（像卡帶）、尾音離 2 秒太遠
  3. 接法：兩邊的 downbeat 對齊到同一個樣本，前後各 15 ms 的等功率交叉（樂句頭的鼓點完整保留、沒有爆音）
  4. 尾音：原曲最後一小節之後的殘響照留（自然收），剩下的時間不夠或太長就補靜音／在 --fade 秒內淡出
  0. 逐段相位校正（一定做）：每段用大鼓殘差中位數（不夠就用起音）把該段拍格平移，剪接點才會在真的小節線上
  5. 拍格鎖定（預設開，--no-lock 關）：每 16 拍一個視窗，對大鼓＋小鼓的攻擊點量殘差（沒鼓的視窗用 onset 強度、扣掉它比鼓晚的
     30–40 ms），±110 ms 內平滑後套到 beats／downbeats。畫面閃白、換人都照這份 json 走，才會落在聽得到的那一下（beatqa.py 驗）
限制：拍格是常數（analyze.py 的假設）；中途變速的歌（慢板前奏接樂團）先用 analyze.py --bpm／--first-beat 對主體部分，
或用 --keep 手動給小節區間。剪完一定要聽每個接點（終端機印的秒數），並用剪後的 json 做畫面。
"""
import argparse
import json
import math
import os
import subprocess
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
SR = 44100
ROLES = ('intro', 'verse', 'pre', 'chorus', 'bridge', 'outro', 'inst')


def load_audio(path):
    raw = subprocess.run(['ffmpeg', '-v', 'error', '-nostdin', '-i', path, '-f', 'f32le', '-ac', '2', '-ar', str(SR), '-'],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.float32).reshape(-1, 2).copy()


def role_of(name):
    n = name.lower().rstrip('0123456789_- ')
    for r in ROLES:
        if n.startswith(r):
            return r
    return None


def section_roles(A, bar_e, roles_override):
    """回傳每段 [(name, bar0, bar1, role, energy)]。"""
    db = A['downbeats']
    nb = len(db)
    secs = []
    S = A['sections']
    for i, s in enumerate(S):
        b0 = int(s['bar'])
        b1 = int(S[i + 1]['bar']) if i + 1 < len(S) else nb
        b0, b1 = max(0, b0), min(nb, b1)
        if b1 <= b0:
            continue
        e = float(np.mean(bar_e[b0:b1]))
        secs.append([s['name'], b0, b1, role_of(s['name']), e])
    if not secs:
        sys.exit('audio.json 沒有段落（sections）')
    if any(r is None for _, _, _, r, _ in secs):
        es = np.array([x[4] for x in secs])
        hi = np.percentile(es, 65)
        for i, x in enumerate(secs):
            if x[3] is not None:
                continue
            if i == 0 and x[4] < np.median(es):
                x[3] = 'intro'
            elif i == len(secs) - 1:
                x[3] = 'outro'
            elif x[4] >= hi:
                x[3] = 'chorus'
            else:
                x[3] = 'verse'
    for kv in (roles_override or '').split(','):
        if ':' in kv:
            k, v = kv.split(':', 1)
            for x in secs:
                if x[0] == k.strip():
                    x[3] = v.strip()
    return [tuple(x) for x in secs]


def bar_feats(y_mono, downbeats, dur):
    """每小節：chroma（和聲）與 MFCC（音色），用來量接點跳不跳。"""
    import librosa
    y22 = librosa.resample(y_mono, orig_sr=SR, target_sr=22050)
    hop = 512
    ch = librosa.feature.chroma_stft(y=y22, sr=22050, hop_length=hop)
    mf = librosa.feature.mfcc(y=y22, sr=22050, hop_length=hop, n_mfcc=13)[1:]
    fps = 22050 / hop
    edges = list(downbeats) + [dur]
    C, M = [], []
    for i in range(len(downbeats)):
        a, b = int(edges[i] * fps), max(int(edges[i] * fps) + 1, int(edges[i + 1] * fps))
        C.append(ch[:, a:b].mean(1))
        M.append(mf[:, a:b].mean(1))
    C = np.array(C)
    C /= np.linalg.norm(C, axis=1, keepdims=True) + 1e-9
    M = np.array(M)
    M = (M - M.mean(0)) / (M.std(0) + 1e-9)
    return C, M


def jump(C, M, a, b):
    """原本 a 之後該接 a，現在接 b：兩小節的差異（0 = 一樣）。"""
    if a == b:
        return 0.0
    if not (0 <= a < len(C) and 0 <= b < len(C)):
        return 2.0
    return float((1 - C[a] @ C[b]) * 2 + np.linalg.norm(M[a] - M[b]) / math.sqrt(M.shape[1]))


def plan(A, secs, bar_e, C, M, dur, barlen, tail_rng):
    """在（前奏小節數, 中段起點, 中段長度, 結尾小節數, 總小節數）的組合裡挑分數最高的。
    中段長度是 4 的倍數（樂句完整）、起點是樂句頭；結尾的起點也盡量是樂句頭；總小節數由尾音秒數的彈性決定。"""
    nb = len(A['downbeats'])
    role = ['verse'] * nb
    sec_of = [0] * nb
    for k, (_, b0, b1, r, _) in enumerate(secs):
        for b in range(b0, b1):
            role[b] = r
            sec_of[b] = k
    # 有聲的最後一小節（之後是殘響或靜音）
    loud = np.where(bar_e > 0.12 * np.median(bar_e[bar_e > 0]))[0]
    last = int(loud[-1]) + 1 if len(loud) else nb
    heads = sorted({b0 + 4 * k for _, b0, b1, _, _ in secs for k in range((b1 - b0 + 3) // 4) if b0 + 4 * k < b1})
    hset = set(heads)
    # 相鄰小節的典型跳動，用來把接點跳動標準化（1 = 跟平常換小節差不多）
    base = float(np.median([jump(C, M, b, b + 1) for b in range(nb - 1)])) or 1.0
    s0 = secs[0]
    il = s0[2] - s0[1]
    ib_opts = sorted({x for x in (il, 4, 8) if 2 <= x <= 8 and x <= max(il, 4)})
    ob_opts = [ob for ob in range(2, 9) if last - ob >= 0]
    Bs = range(int(math.ceil((dur - tail_rng[1]) / barlen)), int(math.floor((dur - tail_rng[0]) / barlen)) + 1)
    best = None
    for B in Bs:
        tail = dur - B * barlen
        for ib in ib_opts:
            for ob in ob_opts:
                body = B - ib - ob
                if body < 8:
                    continue
                out0 = last - ob
                for s in heads:
                    e = s + body
                    if s < ib or e > out0:
                        continue
                    rs = role[s:e]
                    cov = sum(r == 'chorus' for r in rs) / body
                    end_ch = 1.0 if role[e - 1] == 'chorus' else 0.0
                    vc = 1.0 if any(rs[i] in ('verse', 'pre') and rs[i + 1] == 'chorus' for i in range(len(rs) - 1)) else 0.0
                    en = float(np.mean(bar_e[s:e]) / (bar_e.max() + 1e-9))
                    j = (jump(C, M, ib, s) + jump(C, M, e, out0)) / base
                    skip = out0 - e
                    score = (2.0 * end_ch + 1.0 * vc + 1.0 * cov + 0.5 * en - 0.25 * j
                             - (0.6 if body % 4 else 0) - (0.4 if out0 not in hset and skip else 0)
                             - (1.0 if 0 < skip < 4 else 0)                     # 跳掉 1–3 小節像卡帶
                             + (0.3 if ib == il else 0) - 0.15 * abs(tail - 2.0))
                    if best is None or score > best[0]:
                        best = (score, ib, s, e, out0, cov, end_ch, vc, j, tail)
    if best is None:
        sys.exit('找不到合適的組合（歌太短或目標太長）；用 --keep 手動指定小節區間')
    score, ib, s, e, out0, cov, end_ch, vc, j, tail = best
    pieces = [(0, ib), (s, e), (out0, last)]
    return pieces, dict(score=round(score, 3), chorus_cover=round(cov, 2), end_on_chorus=bool(end_ch), verse_to_chorus=bool(vc),
                        join_jump=round(j, 2), tail=round(tail, 2)), role


def phase_fix(A, y_mono):
    """逐段校正拍格相位（就地改 A 的 beats／downbeats）。analyze.py 假設整首歌速度固定；現場錄音的長歌在過門放慢後，
    後面整段會錯開（Sparkle 實測：420 秒之後大鼓全部晚 +160～+200 ms，約 1/3 拍）。每一段：段內大鼓對最近拍點的殘差
    （±半拍內）≥ 4 個且集中 → 用中位數；不夠就用 onset 強度在 ±0.45 拍內找最佳位移（對比 ≥ 1.3 才採用）。回傳每段位移表。"""
    import librosa
    b = np.array(A['beats'], np.float64)
    d = np.array(A['downbeats'], np.float64)
    P = float(np.median(np.diff(b)))
    kicks = np.array(A.get('onsets', {}).get('kick', []), np.float64)
    sr, hop = 22050, 256
    o = librosa.onset.onset_strength(y=librosa.resample(y_mono, orig_sr=SR, target_sr=sr), sr=sr, hop_length=hop)
    o = o / (o.max() + 1e-9)
    fps = sr / hop
    S = A['sections']
    rows = []
    nb, nd = b.copy(), d.copy()
    for i, s_ in enumerate(S):
        t0 = s_['start']
        t1 = S[i + 1]['start'] if i + 1 < len(S) else A['duration'] + 1
        kk = kicks[(kicks >= t0) & (kicks < t1)]
        off, how = 0.0, '—'
        if len(kk) >= 4:
            r = np.array([x - b[np.argmin(np.abs(b - x))] for x in kk])
            r = r[np.abs(r) < 0.5 * P]
            if len(r) >= 4 and np.median(np.abs(r - np.median(r))) < 0.12 * P:
                off, how = float(np.median(r)), f'大鼓 {len(r)} 個'
        if how == '—':
            bb = b[(b >= t0) & (b < t1)]
            if len(bb) >= 8:
                lags = np.arange(-0.45 * P, 0.45 * P + 1e-9, 1 / fps)
                sc = np.array([o[np.clip(np.round((bb + L) * fps).astype(int), 0, len(o) - 1)].mean() for L in lags])
                j = int(np.argmax(sc))
                if sc[j] / (np.median(sc) + 1e-9) >= 1.3:
                    off, how = float(lags[j]), f'起音（對比 {sc[j] / np.median(sc):.2f}）'
        if how == '—' and rows:                             # 量不到（安靜的段、尾音）：沿用前一段，不要跳回 0
            off, how = rows[-1][2], '沿用前一段'
        if abs(off) < 0.015:                                # 15 ms 內不動（留給最後的拍格鎖定）
            off = 0.0
        m = (b >= t0 - 0.5 * P) & (b < t1 - 0.5 * P)
        nb[m] = b[m] + off
        md = (d >= t0 - 0.5 * P) & (d < t1 - 0.5 * P)
        nd[md] = d[md] + off
        rows.append((s_['name'], t0, off, how))
    A['beats'], A['downbeats'] = nb.tolist(), nd.tolist()
    for s_ in S:                                            # 段落起點跟著該段的第一個小節線
        k = int(np.argmin(np.abs(d - s_['start'])))
        if abs(d[k] - s_['start']) < 0.05:
            s_['start'] = float(nd[k])
    for i, s_ in enumerate(S):
        s_['end'] = S[i + 1]['start'] if i + 1 < len(S) else s_.get('end', A['duration'])
    return rows


def lock_grid(beats, wav_y, drums=(), win=16, max_lag=0.11, min_con=1.25):
    """拍格鎖到實際起音：每 win 拍一個視窗（滑動半個視窗）。有鼓（大鼓＋小鼓的攻擊點，±0.3 拍內）≥ 3 個就用殘差中位數；
    沒有鼓的視窗用 onset 強度在 ±max_lag 內的最佳位移，再扣掉「onset 強度峰值比鼓的攻擊點晚多少」（同時有兩者的視窗量中位數，
    量不到用 35 ms；Sparkle 實測 30–40 ms）。對比 < min_con 的視窗不採用，前後內插、中位數平滑。回傳 (新拍點, 每拍位移秒)。"""
    import librosa
    from scipy.ndimage import median_filter
    sr, hop = 22050, 128
    y = librosa.resample(wav_y, orig_sr=SR, target_sr=sr)
    o = librosa.onset.onset_strength(y=y, sr=sr, hop_length=hop)
    o = o / (o.max() + 1e-9)
    fps = sr / hop
    b = np.asarray(beats)
    P = float(np.median(np.diff(b)))
    dr = np.sort(np.asarray(drums, np.float64))
    lags = np.arange(-max_lag, max_lag + 1e-9, 1 / fps)
    rows = []                                              # (中心, 鼓位移或 None, 起音位移或 None)
    for k in range(0, len(b), win // 2):
        seg = b[k:k + win]
        if len(seg) < 4:
            continue
        dlag = None
        dd = dr[(dr >= seg[0] - 0.3 * P) & (dr <= seg[-1] + 0.3 * P)]
        if len(dd) >= 3:
            r = np.array([x - seg[np.argmin(np.abs(seg - x))] for x in dd])
            r = r[np.abs(r) < 0.3 * P]
            if len(r) >= 3:
                dlag = float(np.clip(np.median(r), -max_lag, max_lag))
        sc = np.array([o[np.clip(np.round((seg + L) * fps).astype(int), 0, len(o) - 1)].mean() for L in lags])
        i = int(np.argmax(sc))
        flag = float(lags[i]) if sc[i] / (np.median(sc) + 1e-9) >= min_con else None
        rows.append((float(seg.mean()), dlag, flag))
    both = [f - d for _, d, f in rows if d is not None and f is not None]
    bias = float(np.median(both)) if len(both) >= 2 else 0.035
    centers, vals = [], []
    for c, d, f in rows:
        # 只有起音強度（沒鼓）的視窗最多動 ±50 ms：鋼琴、人聲的起音會把拍格拉歪（Sparkle 27–32 秒被拉到 −126 ms）
        v = d if d is not None else (float(np.clip(f - bias, -0.05, 0.05)) if f is not None else None)
        if v is not None:
            centers.append(c)
            vals.append(v)
    if len(vals) < 2:
        return b, np.zeros(len(b)), bias
    vals = median_filter(np.array(vals), size=5, mode='nearest')
    shift = np.interp(b, centers, vals)
    return b + shift, shift, bias


def merge(pieces):
    out = []
    for p in pieces:
        if out and out[-1][1] == p[0]:
            out[-1] = (out[-1][0], p[1])
        else:
            out.append(p)
    return out


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('song')
    p.add_argument('audio_json')
    p.add_argument('--dur', type=float, default=90.0)
    p.add_argument('-o', '--out')
    p.add_argument('--roles', help='逐段覆寫角色，例 "S1:intro,S4:chorus"')
    p.add_argument('--keep', help='手動小節區間，例 "0-4,16-56,140-144"（含頭不含尾）')
    p.add_argument('--tail-min', type=float, default=0.8, help='最後一小節之後留給殘響的最短秒數')
    p.add_argument('--tail-max', type=float, default=4.5, help='最長秒數（總小節數在這個範圍內挑）')
    p.add_argument('--fade', type=float, default=1.2)
    p.add_argument('--xf', type=float, default=0.015, help='接點兩側交叉秒數')
    p.add_argument('--plan', action='store_true')
    p.add_argument('--no-lock', action='store_true', help='不要把拍格鎖到實際起音')
    a = p.parse_args()

    A = json.load(open(a.audio_json))
    db = np.array(A['downbeats'])
    nb = len(db)
    barlen = float(np.median(np.diff(db)))
    y = load_audio(a.song)
    dur_src = len(y) / SR
    rows = phase_fix(A, y.mean(1))
    if any(r[2] for r in rows):
        print('逐段相位校正（固定速度的拍格在現場錄音的長歌會漂）：')
        for name, t0, off, how in rows:
            if off:
                print(f'  {name:6} {t0:7.1f} 秒起  {off * 1000:+5.0f} ms（{how}）')
    db = np.array(A['downbeats'])
    # 每小節能量（env.rms 100 fps）
    rms = np.array(A['env']['rms'])
    efps = A['env']['fps']
    edges = list(db) + [dur_src]
    bar_e = np.array([rms[int(edges[i] * efps):max(int(edges[i] * efps) + 1, int(edges[i + 1] * efps))].mean() for i in range(nb)])
    secs = section_roles(A, bar_e, a.roles)

    print(f'原曲 {dur_src:.1f} 秒、{A["tempo"]:.2f} BPM、一小節 {barlen:.3f} 秒、{nb} 小節')
    print(f'{"段落":8}{"小節":>10}{"秒":>16}{"能量":>8}  角色')
    for name, b0, b1, r, e in secs:
        t1 = db[b1] if b1 < nb else dur_src
        print(f'{name:8}{b0:>5}–{b1:<4}{db[b0]:>8.1f}–{t1:<7.1f}{e:>8.3f}  {r}')

    C, M = bar_feats(y.mean(1), db, dur_src)
    if a.keep:
        pieces = [tuple(int(v) for v in r.split('-')) for r in a.keep.split(',')]
        info = {'manual': True, 'joins_jump': [round(jump(C, M, pieces[i][1], pieces[i + 1][0]), 3) for i in range(len(pieces) - 1)]}
        role = ['verse'] * nb
        for _, b0, b1, r, _ in secs:
            role[b0:b1] = [r] * (b1 - b0)
    else:
        pieces, info, role = plan(A, secs, bar_e, C, M, a.dur, barlen, (a.tail_min, a.tail_max))
    pieces = merge(pieces)
    tot = sum(b1 - b0 for b0, b1 in pieces)
    print(f'\n目標 {a.dur:g} 秒 → {tot} 小節（{tot * barlen:.1f} 秒）＋尾音 {a.dur - tot * barlen:.1f} 秒；計畫 {info}')
    out_t = 0.0
    joins = []
    plist = []
    for i, (b0, b1) in enumerate(pieces):
        s0 = 0.0 if b0 == 0 and db[0] < barlen else float(db[b0])      # 第一段含 pickup（第一個 downbeat 前的弱起）
        s1 = float(db[b1]) if b1 < nb else dur_src
        if i == 0 and s0 == 0.0:
            pre = float(db[0])
        else:
            pre = 0.0
        if i > 0:
            joins.append(out_t)
        rl = sorted(set(role[b0:b1]), key=role[b0:b1].index)
        plist.append(dict(src0=round(s0, 4), src1=round(s1, 4), out0=round(out_t, 4), bars=[b0, b1], roles=rl))
        print(f'  片段 {i + 1}：原曲 {s0:6.2f}–{s1:6.2f} 秒（小節 {b0}–{b1}，{"／".join(rl)}）→ 剪後 {out_t:6.2f} 秒起')
        out_t += s1 - s0
    for k, jt in enumerate(joins):
        print(f'  剪接點 {k + 1}：剪後第 {jt:.2f} 秒（原曲 {plist[k]["src1"]:.2f} → {plist[k + 1]["src0"]:.2f}）')
    if a.plan or not a.out:
        return

    # 拼接：每段 [s0, s1)，接點兩側等功率交叉
    n_out = int(round(a.dur * SR))
    out = np.zeros((n_out + SR, 2), np.float32)
    xf = int(a.xf * SR)
    for i, pc in enumerate(plist):
        i0, i1 = int(round(pc['src0'] * SR)), int(round(pc['src1'] * SR))
        o0 = int(round(pc['out0'] * SR))
        last = i == len(plist) - 1
        if last:
            i1 = min(len(y), i0 + (n_out - o0))           # 最後一段一路播到片長（含殘響）
        a0, a1 = max(0, i0 - (xf if i > 0 else 0)), min(len(y), i1 + (0 if last else xf))
        seg = y[a0:a1].copy()
        L = len(seg)
        g = np.ones(L, np.float32)
        if i > 0:
            r = np.linspace(0, 1, 2 * xf, dtype=np.float32)
            g[:2 * xf] = np.sin(r * np.pi / 2)
        if not last:
            r = np.linspace(0, 1, 2 * xf, dtype=np.float32)
            g[L - 2 * xf:] *= np.cos(r * np.pi / 2)
        d0 = o0 - (i0 - a0)
        e = min(len(out), d0 + L)
        out[d0:e] += seg[:e - d0] * g[:e - d0, None]
    out = out[:n_out]
    nf = int(a.fade * SR)
    out[-nf:] *= np.linspace(1, 0, nf, dtype=np.float32)[:, None] ** 2
    peak = float(np.abs(out).max())
    if peak > 0.999:
        out *= 0.999 / peak
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    subprocess.run(['ffmpeg', '-v', 'error', '-nostdin', '-y', '-f', 'f32le', '-ac', '2', '-ar', str(SR), '-i', '-',
                    '-c:a', 'pcm_s16le', a.out], input=out.tobytes(), check=True)

    # 新時間軸的 audio.json
    def remap(ts):
        res = []
        for pc in plist:
            last = pc is plist[-1]
            hi = pc['src0'] + (a.dur - pc['out0']) if last else pc['src1']
            for t in ts:
                if pc['src0'] - 1e-6 <= t < hi - 1e-6:
                    res.append(round(pc['out0'] + t - pc['src0'], 4))
        return sorted(t for t in res if t < a.dur)
    beats = remap(A['beats'])
    downs = remap(A['downbeats'])
    lock = None
    if not a.no_lock:
        drums = sorted(remap(A.get('onsets', {}).get('kick', [])) + remap(A.get('onsets', {}).get('snare', [])))
        nb_, sh, bias = lock_grid(beats, out.mean(1), drums)
        idx = {round(x, 4): i for i, x in enumerate(beats)}
        dsh = [sh[idx[d]] if d in idx else float(np.interp(d, beats, sh)) for d in downs]
        beats = [round(float(x), 4) for x in nb_]
        downs = [round(float(d + s), 4) for d, s in zip(downs, dsh)]
        lock = dict(mean_ms=round(float(np.mean(sh)) * 1000, 1), min_ms=round(float(sh.min()) * 1000, 1), max_ms=round(float(sh.max()) * 1000, 1),
                    flux_bias_ms=round(bias * 1000, 1))
        print(f'拍格鎖到鼓的攻擊點：平均位移 {lock["mean_ms"]:+.0f} ms（{lock["min_ms"]:+.0f}～{lock["max_ms"]:+.0f}）；'
              f'onset 強度峰值比鼓晚 {bias * 1000:.0f} ms（沒鼓的地方扣掉）')
    env = {'fps': efps}
    for k, v in A['env'].items():
        if k == 'fps':
            continue
        v = np.array(v)
        nv = np.zeros(int(a.dur * efps))
        for pc in plist:
            last = pc is plist[-1]
            s1 = pc['src0'] + (a.dur - pc['out0']) if last else pc['src1']
            o0, i0, i1 = int(round(pc['out0'] * efps)), int(round(pc['src0'] * efps)), int(round(s1 * efps))
            seg = v[i0:i1]
            nv[o0:o0 + len(seg)] = seg[:max(0, len(nv) - o0)]
        nf_ = int(a.fade * efps)
        nv[-nf_:] *= np.linspace(1, 0, nf_) ** 2
        env[k] = [round(float(x), 4) for x in nv]
    sections = []
    for pc in plist:
        b0, b1 = pc['bars']
        for name, s_b0, s_b1, r, _ in secs:
            lo_, hi_ = max(b0, s_b0), min(b1, s_b1)
            if hi_ <= lo_:
                continue
            st = pc['out0'] + (db[lo_] - pc['src0']) if lo_ > b0 or pc['src0'] > 0 else pc['out0']
            sections.append({'name': f'{r}', 'role': r, 'src': name, 'start': round(float(st), 4)})
    sections.sort(key=lambda s: s['start'])
    # 同角色相鄰合併、補 end 與 bar
    merged = []
    for s in sections:
        if merged and merged[-1]['role'] == s['role']:
            continue
        merged.append(s)
    cnt = {}
    for i, s in enumerate(merged):
        s['end'] = merged[i + 1]['start'] if i + 1 < len(merged) else a.dur
        cnt[s['role']] = cnt.get(s['role'], 0) + 1
        s['name'] = f"{s['role']}{cnt[s['role']]}"
        s['bar'] = int(np.searchsorted(np.array(downs), s['start'] - 0.05))
    if lock:                                               # 段落起訖跟著鎖定後的小節線走（引擎用「段內第幾小節」排萬花筒等）
        old_downs = remap(A['downbeats'])
        for s_ in merged:
            for key in ('start', 'end'):
                v = s_[key]
                k = int(np.argmin(np.abs(np.array(old_downs) - v))) if old_downs else -1
                if k >= 0 and abs(old_downs[k] - v) < 0.05 and v > 0 and v < a.dur:
                    s_[key] = downs[k]
    onsets = {k: remap(v) for k, v in A.get('onsets', {}).items()}
    J = dict(duration=a.dur, sr=SR, tempo=A['tempo'], meter=A.get('meter', 4), beats=beats, downbeats=downs,
             sections=merged, env=env, onsets=onsets,
             cut=dict(source=os.path.basename(a.song), pieces=plist, joins=[round(j, 4) for j in joins], plan=info, grid_lock=lock))
    jp = os.path.splitext(a.out)[0] + '.json'
    json.dump(J, open(jp, 'w'), ensure_ascii=False)
    print(f'\n寫入 {a.out}（{a.dur:g} 秒）、{jp}（{len(downs)} 個小節線、段落：{"、".join(s["name"] for s in merged)}）')


if __name__ == '__main__':
    main()
