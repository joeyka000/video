#!/usr/bin/env python3
"""檢查成片：剪點是否踩拍、黑場與閃白、每秒亮度、每段落在 downbeat 抽格的拼圖。

  python qa.py out/montage.mp4 --audio-json data/audio.json
  python qa.py out/montage.mp4 --audio-json data/audio.json -o out/qa --cuts out/montage.cuts.json
  python qa.py out/montage.mp4 --audio-json data/audio.json --threshold 0.2    # 場景分數門檻（預設 0.3）

產出（-o 預設 out/qa）：
  sheet_<段落>.png   每個段落在其 downbeats 抽格的拼圖（每格標歌曲秒數；超過 32 格時均勻取樣）
  report.md          繁體中文報告：剪點與最近拍點的誤差、落在 ±1 格內的比例、每秒亮度、黑場、閃白；
                     給 --cuts 時另列預期剪點 vs 偵測到的剪點

做法：
  - 剪點：ffmpeg select='gt(scene,門檻)' + metadata=print（印出用的方法）；fps 用 ffprobe 取。
    偵測限制：同一鏡頭的子剪（punch-in）、兩個相似畫面之間的剪點，場景分數常低於門檻而偵測不到；
    報告把它們標成「未偵測到（門檻 X）」，不代表成片有問題。畫面變化大的鏡頭內動作也可能被當成剪點。
    門檻用 --threshold 調（越低越敏感）
  - 亮度：signalstats 的 YAVG（0–255，限制範圍黑位 16、白位 235）
      黑場 = YAVG ≤ 16 連續 ≥ 0.5 秒；閃白 = YAVG ≥ 235 的格（連續的算一次）
  - --cuts 接受兩種格式：[秒, ...]（歌曲絕對秒）或 cutlist.py 的 OUT.cuts.json
    （{"offset": 影片 0 秒對應的歌曲秒, "cuts": [...]}）；offset 會用在拍點比對與抽格
  - 沒有 --cuts 時假設影片 0 秒 = 歌曲 0 秒
"""
import argparse
import json
import os
import re
import subprocess
import sys
from fractions import Fraction


def run(cmd, what):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode:
        sys.exit(f"{what} 失敗：\n{' '.join(cmd)}\n{r.stderr.strip()}")
    return r.stdout


def probe(path):
    out = run(["ffprobe", "-v", "error", "-select_streams", "v:0",
               "-show_entries", "stream=width,height,r_frame_rate,avg_frame_rate,nb_frames:format=duration",
               "-of", "json", path], f"ffprobe {path}")
    d = json.loads(out)
    if not d.get("streams"):
        sys.exit(f"{path} 沒有視訊軌")
    st = d["streams"][0]
    fr = st.get("avg_frame_rate")
    if not fr or fr == "0/0":
        fr = st["r_frame_rate"]
    return {"w": int(st["width"]), "h": int(st["height"]), "fps": float(Fraction(fr)),
            "dur": float(d["format"].get("duration", 0) or 0), "nb": int(st.get("nb_frames") or 0)}


FRAME_RE = re.compile(r"^frame:\s*(\d+)\s+pts:\s*(-?\d+)\s+pts_time:\s*(-?[\d.]+)")


def parse_metadata(text, key):
    """解析 metadata=print 的輸出：回傳 [(pts_time, value)]。"""
    out, t = [], None
    for line in text.splitlines():
        m = FRAME_RE.match(line)
        if m:
            t = float(m.group(3))
        elif t is not None and line.startswith(key + "="):
            out.append((t, float(line.split("=", 1)[1])))
    return out


def safe_label(s):
    """sendcmd／drawtext 的文字：會被當成語法的字元換成空白（% 是 drawtext 的展開起始符，含 % 整行標籤不畫）。"""
    return "".join(ch if ch not in "'\";:,\\[]%" else " " for ch in s)


def safe_name(s):
    return re.sub(r"[^\w\-]+", "_", s).strip("_") or "section"


def font_arg():
    try:
        f = subprocess.run(["fc-match", "-f", "%{file}", "Noto Sans CJK TC"], capture_output=True, text=True).stdout.strip()
        return f":fontfile={f}" if f and os.path.exists(f) else ""
    except OSError:
        return ""


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("video")
    ap.add_argument("--audio-json", dest="audio_json", required=True)
    ap.add_argument("-o", "--out", default="out/qa", help="輸出資料夾（預設 out/qa）")
    ap.add_argument("--cuts", help="預期剪點：[秒,...] 或 cutlist.py 的 OUT.cuts.json")
    ap.add_argument("--threshold", type=float, default=0.3, help="場景分數門檻（預設 0.3；越低越敏感）")
    a = ap.parse_args()
    if not (0 < a.threshold <= 1):
        ap.error("--threshold 要在 0 到 1 之間")
    for p in (a.video, a.audio_json) + ((a.cuts,) if a.cuts else ()):
        if not os.path.exists(p):
            sys.exit(f"找不到檔案：{p}")
    with open(a.audio_json, encoding="utf-8") as f:
        audio = json.load(f)
    beats = sorted(audio["beats"])
    downbeats = sorted(audio["downbeats"])
    sections = audio.get("sections") or [{"name": "all", "start": 0, "end": audio["duration"]}]
    offset = 0.0
    expected = None
    if a.cuts:
        with open(a.cuts, encoding="utf-8") as f:
            c = json.load(f)
        if isinstance(c, dict):
            offset = float(c.get("offset", 0))
            expected = [float(x) for x in c.get("cuts", [])]
        else:
            expected = [float(x) for x in c]
    os.makedirs(a.out, exist_ok=True)
    info = probe(a.video)
    fps, dur = info["fps"], info["dur"]
    fr = 1.0 / fps
    total_frames = info["nb"] or int(round(dur * fps))

    # 1. 剪點偵測
    thr = f"{a.threshold:g}"
    method = f"select='gt(scene,{thr})'"
    txt = run(["ffmpeg", "-v", "error", "-i", a.video, "-vf", f"select='gt(scene\\,{thr})',metadata=print:file=-",
               "-f", "null", "-"], "剪點偵測")
    detected = parse_metadata(txt, "lavfi.scene_score")   # (影片秒, 分數)

    def nearest(ts, t):
        if not ts:
            return None, None
        i = min(range(len(ts)), key=lambda k: abs(ts[k] - t))
        return ts[i], t - ts[i]

    cut_rows = []
    for tv, score in detected:
        ts = tv + offset
        nb, eb = nearest(beats, ts)
        nd, ed = nearest(downbeats, ts)
        cut_rows.append({"tv": tv, "ts": ts, "score": score, "beat": nb, "err": eb, "db": nd, "err_db": ed,
                         "on_beat": abs(eb) <= fr + 1e-6, "on_db": abs(ed) <= fr + 1e-6})
    n_cut = len(cut_rows)
    n_on = sum(r["on_beat"] for r in cut_rows)
    n_on_db = sum(r["on_db"] for r in cut_rows)
    mae = sum(abs(r["err"]) for r in cut_rows) / n_cut * 1000 if n_cut else 0.0

    # 2. 亮度
    txt = run(["ffmpeg", "-v", "error", "-i", a.video, "-vf", "signalstats,metadata=print:key=lavfi.signalstats.YAVG:file=-",
               "-f", "null", "-"], "亮度統計")
    yavg = parse_metadata(txt, "lavfi.signalstats.YAVG")
    per_sec = {}
    for t, v in yavg:
        per_sec.setdefault(int(t), []).append(v)
    black_runs, flash_runs = [], []
    cur = None
    for t, v in yavg:
        if v <= 16:
            cur = [t, t] if cur is None else [cur[0], t]
        else:
            if cur is not None:
                black_runs.append(cur)
            cur = None
    if cur is not None:
        black_runs.append(cur)
    black_runs = [(s, e + fr) for s, e in black_runs if e + fr - s >= 0.5 - 1e-6]
    cur = None
    for t, v in yavg:
        if v >= 235:
            cur = [t, 1] if cur is None else [cur[0], cur[1] + 1]
        else:
            if cur is not None:
                flash_runs.append(tuple(cur))
            cur = None
    if cur is not None:
        flash_runs.append(tuple(cur))

    # 3. 每段落在 downbeat 抽格的拼圖（一次解碼、多個輸出）
    sheets = []
    branches = []
    cmd_files = []
    for s in sections:
        dbs = [d for d in downbeats if s["start"] - 1e-3 <= d < s["end"] - 1e-3]
        frames = [(round((d - offset) * fps), d) for d in dbs if 0 <= (d - offset) < dur]
        frames = [(fi, d) for fi, d in frames if fi < total_frames]
        if not frames:
            continue
        note = ""
        if len(frames) > 32:
            step = len(frames) / 32
            frames = [frames[int(i * step)] for i in range(32)]
            note = "（超過 32 格，均勻取樣）"
        name = safe_name(str(s["name"]))
        path = os.path.join(a.out, f"sheet_{name}.png")
        cmd_path = os.path.join(a.out, f"_cmds_{name}.txt")
        k = len(branches)
        # 一張 filter_complex 裡有多個 drawtext：sendcmd 的目標寫 drawtext 會命中圖內每一個 drawtext，
        # 所以每條分支的 drawtext 取名 drawtext@s{k}，指令檔也只對它下指令
        with open(cmd_path, "w", encoding="utf-8") as f:
            for fi, d in frames:
                lab = safe_label(f"{s['name']} {d:.3f}s")
                f.write(f"{max(0.0, (fi - 0.5) / fps):.4f} drawtext@s{k} reinit 'text={lab}';\n")
        cmd_files.append(cmd_path)
        sel = "+".join(f"eq(n\\,{fi})" for fi, _ in frames)
        cols = min(4, len(frames))
        branches.append((f"[v{k}]select='{sel}',sendcmd=f={cmd_path},scale=480:-2,pad=iw:ih+28:0:0:black,"
                         f"drawtext@s{k}=text='':x=8:y=h-24:fontsize=20:fontcolor=white{font_arg()},"
                         f"tile={cols}x{(len(frames) + cols - 1) // cols}[s{k}]", path))
        sheets.append((s["name"], path, len(frames), note))
    if branches:
        fc = f"[0:v]split={len(branches)}" + "".join(f"[v{k}]" for k in range(len(branches))) + ";" + \
             ";".join(b for b, _ in branches)
        cmd = ["ffmpeg", "-v", "error", "-y", "-i", a.video, "-filter_complex", fc]
        for k, (_, path) in enumerate(branches):
            cmd += ["-map", f"[s{k}]", "-frames:v", "1", path]
        run(cmd, "段落拼圖")
    for c in cmd_files:
        if os.path.exists(c):
            os.remove(c)

    # 4. 預期剪點比對
    exp_rows = []
    extra = 0
    if expected is not None:
        det_ts = [r["ts"] for r in cut_rows]
        for te in expected:
            if te - offset < fr * 0.5:
                exp_rows.append((te, None, None, "影片開頭（不算剪點）"))
                continue
            nd, e = nearest(det_ts, te)
            miss = f"未偵測到（門檻 {thr}）"
            if nd is None:
                exp_rows.append((te, None, None, miss))
            else:
                exp_rows.append((te, nd, e, "命中" if abs(e) <= fr + 1e-6 else miss))
        hit_ts = {r[1] for r in exp_rows if r[3] == "命中"}
        extra = sum(1 for t in det_ts if t not in hit_ts)

    # 5. 報告
    L = []
    L.append(f"# QA 報告：{os.path.basename(a.video)}\n")
    L.append(f"- 解析度 {info['w']}×{info['h']}，{fps:g} fps，長度 {dur:.3f} 秒，{info['nb'] or len(yavg)} 格")
    L.append(f"- 節拍資料 {os.path.basename(a.audio_json)}：{audio['tempo']} BPM，{len(beats)} 拍，{len(downbeats)} 小節")
    L.append(f"- 影片 0 秒 = 歌曲 {offset:.3f} 秒" + ("（來自 --cuts 的 offset）" if a.cuts else "（未給 --cuts，假設 0）"))
    L.append(f"- 剪點偵測方法：ffmpeg `{method}`（--threshold {thr}）")
    L.append("- 偵測限制：同鏡頭子剪（punch-in）與相似畫面間的剪點場景分數低，常偵測不到；"
             "「未偵測到」不代表成片有問題，請對照段落拼圖或調低 --threshold 再跑\n")
    L.append("## 剪點與拍點\n")
    L.append(f"- 偵測到 {n_cut} 個剪點；落在最近拍點 ±1 格（±{fr * 1000:.1f} ms）內 {n_on} 個"
             f"（{n_on / n_cut * 100 if n_cut else 0:.0f}%）；落在 downbeat ±1 格內 {n_on_db} 個；平均絕對誤差 {mae:.1f} ms\n")
    L.append("| # | 影片秒 | 歌曲秒 | 場景分數 | 最近拍 | 誤差 ms | ±1 格 | 最近 downbeat | 誤差 ms |")
    L.append("|--:|--:|--:|--:|--:|--:|:-:|--:|--:|")
    for i, r in enumerate(cut_rows, 1):
        L.append(f"| {i} | {r['tv']:.3f} | {r['ts']:.3f} | {r['score']:.2f} | {r['beat']:.3f} | {r['err'] * 1000:+.1f} | "
                 f"{'是' if r['on_beat'] else '否'} | {r['db']:.3f} | {r['err_db'] * 1000:+.1f} |")
    if expected is not None:
        L.append("\n## 預期剪點 vs 偵測\n")
        n_hit = sum(1 for r in exp_rows if r[3] == "命中")
        n_chk = sum(1 for r in exp_rows if r[3] != "影片開頭（不算剪點）")
        L.append(f"- 預期 {len(expected)} 個（可檢查 {n_chk} 個），命中 {n_hit} 個，未偵測到 {n_chk - n_hit} 個，"
                 f"多出的偵測剪點 {extra} 個\n")
        L.append("| 預期（歌曲秒） | 偵測到（歌曲秒） | 誤差 ms | 狀態 |")
        L.append("|--:|--:|--:|:--|")
        for te, nd, e, status in exp_rows:
            L.append(f"| {te:.3f} | {nd:.3f} | {e * 1000:+.1f} | {status} |" if nd is not None else f"| {te:.3f} | – | – | {status} |")
    L.append("\n## 亮度\n")
    L.append(f"- 黑場（YAVG ≤ 16 連續 ≥ 0.5 秒）：{len(black_runs)} 段" +
             ("：" + "、".join(f"{s:.2f}–{e:.2f}s" for s, e in black_runs) if black_runs else ""))
    L.append(f"- 閃白（YAVG ≥ 235）：{len(flash_runs)} 次" +
             ("：" + "、".join(f"{t:.2f}s（{n} 格）" for t, n in flash_runs) if flash_runs else "") + "\n")
    L.append("| 秒 | YAVG 平均 | 最低 | 最高 |")
    L.append("|--:|--:|--:|--:|")
    for sec in sorted(per_sec):
        v = per_sec[sec]
        L.append(f"| {sec} | {sum(v) / len(v):.1f} | {min(v):.1f} | {max(v):.1f} |")
    L.append("\n## 段落拼圖\n")
    for name, path, n, note in sheets:
        L.append(f"- {name}：`{os.path.basename(path)}`（{n} 格{note}）")
    report = os.path.join(a.out, "report.md")
    with open(report, "w", encoding="utf-8") as f:
        f.write("\n".join(L) + "\n")

    print(f"剪點偵測：{method}  偵測到 {n_cut} 個，±1 格內 {n_on}（{n_on / n_cut * 100 if n_cut else 0:.0f}%），"
          f"平均絕對誤差 {mae:.1f} ms")
    if expected is not None:
        n_hit = sum(1 for r in exp_rows if r[3] == "命中")
        n_chk = sum(1 for r in exp_rows if r[3] != "影片開頭（不算剪點）")
        print(f"預期剪點 {len(expected)} 個：命中 {n_hit}，未偵測到 {n_chk - n_hit}（門檻 {thr}；同鏡頭子剪可能偵測不到），多出 {extra}")
    print(f"黑場 {len(black_runs)} 段  閃白 {len(flash_runs)} 次  拼圖 {len(sheets)} 張")
    print(report)


if __name__ == "__main__":
    main()
