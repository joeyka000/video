#!/usr/bin/env python3
"""依剪點表（小節／拍）把素材剪成踩拍 montage，精準到格（重編碼）。

  python cutlist.py cuts.csv --audio-json data/audio.json -o out/montage.mp4
  python cutlist.py cuts.csv --audio-json data/audio.json -o out/montage.mp4 --music song.mp3 --sheet

cuts.csv 欄位：bar,beat,src,in,speed,label
  bar    小節序（0 起；bar 0 = audio.json 的第一個 downbeat）
  beat   拍（1–meter，可用 2.5 這種半拍）
  src    素材影片路徑（相對路徑先以目前目錄、再以 cuts.csv 所在目錄找）
  in     從素材的第幾秒開始播（預設 0）
  speed  播放速度（預設 1；2 = 兩倍速，0.5 = 慢動作）
  label  備註（會印在表與拼圖上，可留空；拼圖上 % 與 '";:,\[] 會被換成空白，表格照原文印）
每列從該拍的時間開始播 src 的 in 秒處，播到下一列為止；最後一列播到下一個 downbeat。

做法：
  1. bar/beat → 絕對秒：downbeats[bar] + (beat-1)×拍長；先印剪點表（列、秒、長度、格數、來源、in、速度、標籤）
  2. 輸出 fps／解析度取第一支素材（ffprobe），其他素材縮放加黑邊到同尺寸
  3. 每段 ffmpeg 精準重編碼：-accurate_seek -ss in -i src，setpts=(PTS-STARTPTS)/speed，fps=FPS，
     素材不夠長時 tpad 停格補足，-frames:v 固定格數；libx264 crf 16。
     in 超過素材最後一格（in > 長度 − 1/fps）會直接報錯（-ss 會解不出任何格，整段無聲無息消失）；
     每段轉完用 ffprobe 核對格數，不等於預期就中止並指出第幾列
  4. concat demuxer 串接（-c copy）；有 --music 時從第一列的時間起合音軌：apad 補靜音、-t 切齊影片長度；
     音樂比剪點表短時表格上方會印「音樂於 X 秒結束，之後無聲」
  5. 影片的 0 秒 = 第一列的時間；另寫 OUT.cuts.json（offset、fps、各列絕對秒）給 qa.py --cuts 用
  6. --sheet：另出 OUT.cuts.png，每段第一格的拼圖，每格下方 52 px 黑條兩行：第一行列序、小節／拍、秒數，
     第二行標籤（全形字算 2 單位、超過 42 單位截斷加「…」，不會被下一格蓋掉）
"""
import argparse
import csv
import json
import os
import shutil
import subprocess
import sys
import unicodedata
from fractions import Fraction


def run(cmd, what):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode:
        sys.exit(f"{what} 失敗：\n{' '.join(cmd)}\n{r.stderr.strip()}")
    return r.stdout


def probe(path):
    out = run(["ffprobe", "-v", "error", "-select_streams", "v:0",
               "-show_entries", "stream=width,height,r_frame_rate,avg_frame_rate,nb_frames,duration:format=duration",
               "-of", "json", path], f"ffprobe {path}")
    d = json.loads(out)
    if not d.get("streams"):
        sys.exit(f"{path} 沒有視訊軌")
    st = d["streams"][0]
    fr = st.get("avg_frame_rate")
    if not fr or fr == "0/0":
        fr = st["r_frame_rate"]
    # 視訊軌長度優先（容器長度可能被較長的音軌撐大）
    vdur = float(st.get("duration") or 0) or float(d["format"].get("duration", 0) or 0)
    return {"w": int(st["width"]), "h": int(st["height"]), "fps": float(Fraction(fr)),
            "dur": vdur, "nb": int(st.get("nb_frames") or 0)}


def count_frames(path):
    """輸出檔的格數：先讀容器的 nb_frames，沒有就逐格解碼數（-count_frames）。"""
    out = run(["ffprobe", "-v", "error", "-select_streams", "v:0",
               "-show_entries", "stream=nb_frames", "-of", "csv=p=0", path], f"ffprobe {path}")
    try:
        return int(out.strip())
    except ValueError:
        pass
    out = run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-count_frames",
               "-show_entries", "stream=nb_read_frames", "-of", "csv=p=0", path], f"ffprobe {path}")
    try:
        return int(out.strip())
    except ValueError:
        return 0


def audio_duration(path):
    out = run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path], f"ffprobe {path}")
    try:
        return float(out.strip())
    except ValueError:
        return 0.0


def safe_label(s):
    """sendcmd／drawtext 的文字：會被當成語法的字元換成空白（% 是 drawtext 的展開起始符，含 % 整行標籤不畫）。"""
    return "".join(ch if ch not in "'\";:,\\[]%" else " " for ch in s)


def fit_label(s, max_units=42):
    """把標籤截到黑條放得下的寬度：全形（中日韓）字算 2 單位、其他 1 單位；fontsize 20 時 1 單位約 11 px，
    480 px 寬的格子扣掉左邊 8 px 約放 42 單位。超過就截斷加「…」。"""
    w = 0
    out = []
    for ch in s:
        u = 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1
        if w + u > max_units - 2:
            return "".join(out) + "…"
        out.append(ch)
        w += u
    return s


def font_arg():
    """找 Noto Sans CJK TC 的字型檔給 drawtext（標籤可能有中文）；找不到就用預設字型。"""
    try:
        f = subprocess.run(["fc-match", "-f", "%{file}", "Noto Sans CJK TC"], capture_output=True, text=True).stdout.strip()
        return f":fontfile={f}" if f and os.path.exists(f) else ""
    except OSError:
        return ""


def read_rows(path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        rd = csv.DictReader(f)
        if not rd.fieldnames:
            sys.exit(f"{path} 是空的")
        cols = [c.strip().lower() for c in rd.fieldnames]
        for need in ("bar", "beat", "src"):
            if need not in cols:
                sys.exit(f"{path} 缺少欄位 {need}（需要 bar,beat,src,in,speed,label）")
        rows = []
        for i, raw in enumerate(rd, start=2):
            r = {k.strip().lower(): (v or "").strip() for k, v in raw.items() if k}
            if not r.get("src") and not r.get("bar"):
                continue   # 空列
            try:
                bar = int(r["bar"])
                beat = float(r["beat"])
                t_in = float(r.get("in") or 0)
                speed = float(r.get("speed") or 1)
            except ValueError:
                sys.exit(f"{path} 第 {i} 行數字格式錯誤：{raw}")
            if beat < 1 or speed <= 0 or t_in < 0:
                sys.exit(f"{path} 第 {i} 行：beat 要 ≥ 1、speed 要 > 0、in 要 ≥ 0")
            rows.append({"line": i, "bar": bar, "beat": beat, "src": r["src"], "in": t_in,
                         "speed": speed, "label": r.get("label", "")})
    if not rows:
        sys.exit(f"{path} 沒有任何剪點")
    return rows


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cuts", help="cuts.csv")
    ap.add_argument("--audio-json", dest="audio_json", required=True, help="analyze.py 的 audio.json")
    ap.add_argument("-o", "--out", required=True, help="輸出 mp4")
    ap.add_argument("--music", help="要合進去的歌曲（從第一列的時間起）")
    ap.add_argument("--sheet", action="store_true", help="另輸出剪點拼圖 OUT.cuts.png")
    a = ap.parse_args()
    for p in (a.cuts, a.audio_json) + ((a.music,) if a.music else ()):
        if not os.path.exists(p):
            sys.exit(f"找不到檔案：{p}")
    with open(a.audio_json, encoding="utf-8") as f:
        audio = json.load(f)
    downbeats = audio["downbeats"]
    meter = int(audio.get("meter", 4))
    P = 60.0 / float(audio["tempo"])
    if not downbeats:
        sys.exit("audio.json 沒有 downbeats")

    rows = read_rows(a.cuts)
    csv_dir = os.path.dirname(os.path.abspath(a.cuts))
    for r in rows:
        if not os.path.exists(r["src"]):
            alt = os.path.join(csv_dir, r["src"])
            if os.path.exists(alt):
                r["src"] = alt
            else:
                sys.exit(f"第 {r['line']} 行：找不到素材 {r['src']}")
        if r["bar"] < 0:
            sys.exit(f"第 {r['line']} 行：bar 不能是負數")
        if r["bar"] < len(downbeats):
            t = downbeats[r["bar"]]
        else:
            t = downbeats[-1] + (r["bar"] - (len(downbeats) - 1)) * meter * P
            print(f"警告：第 {r['line']} 行 bar {r['bar']} 超過歌曲小節數 {len(downbeats)}，用拍長外推", file=sys.stderr)
        r["t"] = t + (r["beat"] - 1) * P
    for p, q in zip(rows, rows[1:]):
        if q["t"] <= p["t"]:
            sys.exit(f"第 {q['line']} 行的時間 {q['t']:.3f} 沒有晚於上一列 {p['t']:.3f}（剪點表要依時間排序）")
    last = rows[-1]
    t_end = next((d for d in downbeats if d > last["t"] + 1e-6), None)
    if t_end is None:
        t_end = last["t"] + (meter - (last["beat"] - 1)) * P

    # 輸出規格取第一支素材
    info = {}
    for r in rows:
        if r["src"] not in info:
            info[r["src"]] = probe(r["src"])
    first = info[rows[0]["src"]]
    fps, W, H = first["fps"], first["w"], first["h"]
    if fps <= 0:
        fps = 30.0
    t0 = rows[0]["t"]
    frames = [round((r["t"] - t0) * fps) for r in rows] + [round((t_end - t0) * fps)]
    for i, r in enumerate(rows):
        r["f"] = frames[i]
        r["n"] = frames[i + 1] - frames[i]
        r["dur"] = r["n"] / fps
        if r["n"] < 1:
            sys.exit(f"第 {r['line']} 行與下一列之間不到一格（{fps:g} fps），請拉開剪點")

    total = frames[-1]
    print(f"輸出 {W}×{H} {fps:g} fps  tempo {audio['tempo']} BPM  拍長 {P:.4f} 秒  "
          f"影片 0 秒 = 歌曲 {t0:.3f} 秒  結束於歌曲 {t_end:.3f} 秒  共 {total} 格 {total / fps:.3f} 秒")
    music_dur = audio_duration(a.music) if a.music else None
    if music_dur is not None and music_dur < t_end - 0.5 / fps:
        print(f"音樂 {os.path.basename(a.music)} 只有 {music_dur:.3f} 秒：音樂於歌曲 {music_dur:.3f} 秒"
              f"（影片 {max(0.0, music_dur - t0):.3f} 秒）結束，之後無聲")
    print(f"{'列':>3} {'小節:拍':>8} {'歌曲秒':>8} {'影片秒':>8} {'長(秒)':>7} {'格數':>5}  {'來源':<28} {'in':>7} {'速度':>5}  標籤")
    bad = []
    for i, r in enumerate(rows, 1):
        print(f"{i:>3} {r['bar']:>4}:{r['beat']:<3g} {r['t']:>8.3f} {r['f'] / fps:>8.3f} {r['dur']:>7.3f} {r['n']:>5}  "
              f"{os.path.basename(r['src'])[:28]:<28} {r['in']:>7.2f} {r['speed']:>5g}  {r['label']}")
        src = info[r["src"]]
        if src["dur"]:
            last = src["dur"] - 1.0 / (src["fps"] or fps)   # 素材最後一格的時間
            if r["in"] > last + 1e-6:
                bad.append(f"第 {r['line']} 行（列 {i}）：in {r['in']:.3f} 超過 {os.path.basename(r['src'])} 的最後一格 "
                           f"{last:.3f} 秒（素材長 {src['dur']:.3f} 秒），-ss 會解不出任何格")
                continue
            need = r["in"] + r["dur"] * r["speed"]
            if need > src["dur"] + 0.01:
                print(f"    警告：{os.path.basename(r['src'])} 只有 {src['dur']:.2f} 秒，需要到 {need:.2f} 秒，"
                      f"不足的 {(need - src['dur']) / r['speed'] * fps:.0f} 格用最後一格停格補足", file=sys.stderr)
    if bad:
        sys.exit("剪點表有錯，未轉檔：\n" + "\n".join(bad))

    out_abs = os.path.abspath(a.out)
    os.makedirs(os.path.dirname(out_abs), exist_ok=True)
    seg_dir = os.path.splitext(out_abs)[0] + "_segs"
    os.makedirs(seg_dir, exist_ok=True)
    seg_files = []
    for i, r in enumerate(rows):
        seg = os.path.join(seg_dir, f"seg_{i:03d}.mp4")
        vf = (f"setpts=(PTS-STARTPTS)/{r['speed']},fps={fps},"
              f"scale={W}:{H}:force_original_aspect_ratio=decrease,pad={W}:{H}:(ow-iw)/2:(oh-ih)/2,setsar=1,"
              f"tpad=stop_mode=clone:stop={r['n']}")
        run(["ffmpeg", "-v", "error", "-y", "-accurate_seek", "-ss", f"{r['in']:.4f}", "-i", r["src"], "-an",
             "-vf", vf, "-frames:v", str(r["n"]), "-c:v", "libx264", "-preset", "veryfast", "-crf", "16",
             "-pix_fmt", "yuv420p", seg], f"第 {i + 1} 段轉檔")
        got = count_frames(seg)
        if got != r["n"]:
            sys.exit(f"\n第 {r['line']} 行（列 {i + 1}，{os.path.basename(r['src'])} in {r['in']:.3f}）轉出 {got} 格，"
                     f"預期 {r['n']} 格；中止（請檢查 in 是否超過素材長度、素材是否可解碼）")
        seg_files.append(seg)
        print(f"\r轉檔 {i + 1}/{len(rows)}", end="", file=sys.stderr, flush=True)
    print(file=sys.stderr)
    list_path = os.path.join(seg_dir, "list.txt")
    with open(list_path, "w", encoding="utf-8") as f:
        for s in seg_files:
            f.write(f"file '{s}'\n")
    cmd = ["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", list_path]
    if a.music:
        # apad 補靜音、-t 切齊影片長度；不用 -shortest（音樂短時它會把影片截掉、而且切點不準）
        cmd += ["-ss", f"{t0:.4f}", "-i", a.music, "-map", "0:v", "-map", "1:a", "-af", "apad",
                "-t", f"{total / fps:.6f}", "-c:a", "aac", "-b:a", "192k"]
    cmd += ["-c:v", "copy", "-movflags", "+faststart", out_abs]
    run(cmd, "串接")
    got = count_frames(out_abs)
    if got != total:
        sys.exit(f"串接後 {got} 格，預期 {total} 格；輸出不可信")
    shutil.rmtree(seg_dir, ignore_errors=True)

    meta = {"offset": round(t0, 4), "fps": fps, "end": round(t_end, 4),
            "cuts": [round(r["t"], 4) for r in rows],
            "rows": [{k: r[k] for k in ("bar", "beat", "src", "in", "speed", "label", "t", "f", "n")} for r in rows]}
    meta_path = os.path.splitext(out_abs)[0] + ".cuts.json"
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=1)
    print(f"{a.out}\n{meta_path}")

    if a.sheet:
        sheet = os.path.splitext(out_abs)[0] + ".cuts.png"
        cmd_path = sheet + ".cmds.txt"
        # 黑條兩行：drawtext@l1 放列序／小節／拍／秒，drawtext@l2 放標籤（截到格寬）；sendcmd 分別對這兩個 drawtext 下指令
        with open(cmd_path, "w", encoding="utf-8") as f:
            for i, r in enumerate(rows, 1):
                at = f"{max(0.0, (r['f'] - 0.5) / fps):.4f}"
                l1 = safe_label(fit_label(f"{i} bar{r['bar']} beat{r['beat']:g} {r['t']:.3f}s"))
                l2 = safe_label(fit_label(r["label"]))
                f.write(f"{at} drawtext@l1 reinit 'text={l1}';\n")
                f.write(f"{at} drawtext@l2 reinit 'text={l2}';\n")
        sel = "+".join(f"eq(n\\,{r['f']})" for r in rows)
        cols = min(4, len(rows))
        font = font_arg()
        vf = (f"select='{sel}',sendcmd=f={cmd_path},scale=480:-2,pad=iw:ih+52:0:0:black,"
              f"drawtext@l1=text='':x=8:y=h-48:fontsize=20:fontcolor=white{font},"
              f"drawtext@l2=text='':x=8:y=h-24:fontsize=20:fontcolor=0xdddddd{font},"
              f"tile={cols}x{(len(rows) + cols - 1) // cols}")
        run(["ffmpeg", "-v", "error", "-y", "-i", out_abs, "-vf", vf, "-frames:v", "1", sheet], "剪點拼圖")
        os.remove(cmd_path)
        print(sheet)


if __name__ == "__main__":
    main()
