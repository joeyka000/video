#!/usr/bin/env python3
"""footage.py — 實拍照片與影片精修 CLI（配方詳見 references/footage.md）

子命令：stabilize、denoise、sharpen、deflicker、skin、relight、match、photo、kenburns、upscale、slowmo
共通參數：-o 輸出、-y 覆寫、--dry-run 只印指令、--preview N 只處理前 N 秒
每次執行都會先印出實際跑的 ffmpeg／convert 指令（以 $ 開頭），方便複製重跑。
只用標準函式庫，系統 python3 即可執行；需要 ffmpeg、ffprobe，photo 子命令另需 ImageMagick 的 convert。
"""
import argparse
import json
import math
import os
import re
import shlex
import shutil
import statistics
import subprocess
import sys
import tempfile

IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff", ".bmp", ".heic", ".heif"}
DRY = False
OVERWRITE = False


# ---------- 共用工具 ----------
def die(msg, code=1):
    """印出繁中錯誤並結束。"""
    print(f"錯誤：{msg}", file=sys.stderr)
    sys.exit(code)


def need(tool, hint=""):
    """確認外部工具存在。"""
    if shutil.which(tool) is None:
        die(f"找不到 {tool}。{hint}".strip())


def is_image(path):
    return os.path.splitext(path)[1].lower() in IMAGE_EXT


def check_in(path):
    if not os.path.isfile(path):
        die(f"找不到輸入檔：{path}")


def check_out(path):
    """輸出檔存在且沒加 -y 就停；順便建立資料夾。"""
    if os.path.exists(path) and not OVERWRITE:
        die(f"輸出檔已存在：{path}（加 -y 覆寫）")
    d = os.path.dirname(os.path.abspath(path))
    os.makedirs(d, exist_ok=True)


def run(cmd, capture=False, quiet=False):
    """印出並執行指令；--dry-run 只印。失敗時給繁中訊息。"""
    if not quiet:
        print("$ " + shlex.join(cmd), flush=True)
    if DRY:
        return ""
    try:
        r = subprocess.run(cmd, text=True, capture_output=capture)
    except FileNotFoundError:
        die(f"無法執行 {cmd[0]}，請確認已安裝")
    if r.returncode != 0:
        tail = ""
        if capture and r.stderr:
            tail = "\n" + "\n".join(r.stderr.strip().splitlines()[-8:])
        die(f"指令失敗（exit {r.returncode}）：{cmd[0]} {cmd[1] if len(cmd) > 1 else ''}{tail}")
    return (r.stdout or "") + (r.stderr or "") if capture else ""


def probe(path):
    """ffprobe 取得第一條影像串流與是否有音軌。"""
    need("ffprobe", "請安裝 ffmpeg")
    cmd = ["ffprobe", "-v", "error", "-print_format", "json", "-show_streams", "-show_format", path]
    try:
        out = subprocess.run(cmd, text=True, capture_output=True, check=True).stdout
    except subprocess.CalledProcessError as e:
        die(f"ffprobe 讀不了 {path}：{e.stderr.strip()[-200:]}")
    info = json.loads(out)
    v = next((s for s in info.get("streams", []) if s.get("codec_type") == "video"), None)
    if v is None:
        die(f"{path} 沒有影像串流")
    a = any(s.get("codec_type") == "audio" for s in info.get("streams", []))
    fr = v.get("r_frame_rate", "30/1")
    num, den = fr.split("/") if "/" in fr else (fr, "1")
    fps = float(num) / float(den) if float(den) else 30.0
    dur = float(info.get("format", {}).get("duration", 0) or 0)
    return {"w": int(v["width"]), "h": int(v["height"]), "fps": fps, "audio": a, "dur": dur}


def ffmpeg_base():
    return ["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostats", "-y" if OVERWRITE else "-n"]


def in_args(path, preview):
    """影片可加 --preview 只讀前 N 秒；照片用 -loop 0 單張。"""
    a = []
    if preview and not is_image(path):
        a += ["-t", str(preview)]
    a += ["-i", path]
    return a


def enc_args(out, has_audio, audio_filter=None):
    """輸出編碼：影片 H.264 yuv420p faststart；照片沿用副檔名。"""
    ext = os.path.splitext(out)[1].lower()
    if ext in IMAGE_EXT:
        a = ["-frames:v", "1", "-update", "1"]
        if ext in (".jpg", ".jpeg"):
            a += ["-q:v", "2"]
        return a
    a = ["-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p", "-movflags", "+faststart"]
    if has_audio:
        a += ["-c:a", "aac", "-b:a", "192k"]
        if audio_filter:
            a += ["-af", audio_filter]
    return a


def simple_vf(inp, out, vf, preview, has_audio=None, audio_filter=None):
    """單輸入單濾鏡鏈的標準呼叫。"""
    if has_audio is None:
        has_audio = (not is_image(inp)) and probe(inp)["audio"]
    cmd = ffmpeg_base() + in_args(inp, preview) + ["-vf", vf]
    if has_audio:
        cmd += ["-map", "0:v:0", "-map", "0:a:0"]
    cmd += enc_args(out, has_audio, audio_filter) + [out]
    run(cmd)


def fnum(x):
    return f"{x:.4f}".rstrip("0").rstrip(".")


# ---------- stabilize ----------
def parse_trf(path):
    """解析 vidstabdetect 的 transforms 檔：每格取所有局部運動（LM x y）的中位數當整體位移。"""
    mags = []
    if not os.path.isfile(path):
        return mags
    for line in open(path, encoding="utf-8", errors="ignore"):
        if not line.startswith("Frame"):
            continue
        xs, ys = [], []
        for m in re.finditer(r"\(LM\s+(-?\d+)\s+(-?\d+)", line):
            xs.append(int(m.group(1)))
            ys.append(int(m.group(2)))
        if xs:
            mags.append(math.hypot(statistics.median(xs), statistics.median(ys)))
        else:
            mags.append(0.0)
    return mags


def shake_report(path, preview, label):
    """用 vidstabdetect 量一支片的逐格位移，回傳平均與最大像素。"""
    trf = tempfile.mktemp(suffix=".trf", prefix="report_")
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostats"] + in_args(path, preview) + \
          ["-vf", f"vidstabdetect=shakiness=5:accuracy=15:result={trf}", "-f", "null", "-"]
    run(cmd)
    if DRY:
        return None
    m = parse_trf(trf)
    os.remove(trf)
    if not m:
        return None
    avg, mx = sum(m) / len(m), max(m)
    print(f"[{label}] 逐格位移 平均 {avg:.2f} px、最大 {mx:.1f} px（{len(m)} 格）")
    return avg, mx


def cmd_stabilize(a):
    """vidstab 兩段式穩定：先 detect 寫 transforms，再 transform 套用；--zoom 放大 % 避免黑邊。"""
    check_in(a.input)
    check_out(a.output)
    info = probe(a.input)
    shakiness = {1: 4, 2: 6, 3: 8}[a.strength]
    smoothing = {1: 10, 2: 20, 3: 30}[a.strength]
    trf = os.path.splitext(a.output)[0] + ".trf"
    print(f"[1/2] 偵測位移 shakiness={shakiness}（strength {a.strength}）→ {trf}")
    run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostats"] + in_args(a.input, a.preview) +
        ["-vf", f"vidstabdetect=shakiness={shakiness}:accuracy=15:stepsize=6:result={trf}", "-f", "null", "-"])
    before = None
    if not DRY:
        m = parse_trf(trf)
        if m:
            before = (sum(m) / len(m), max(m))
            need_zoom = before[1] / info["w"] * 100 * 2
            print(f"[原片] 逐格位移 平均 {before[0]:.2f} px、最大 {before[1]:.1f} px")
            if need_zoom > a.zoom:
                print(f"提示：最大位移約佔寬度 {need_zoom:.1f}%，--zoom {a.zoom} 可能仍露邊；露邊時改 --zoom {math.ceil(need_zoom)}")
    vf = (f"vidstabtransform=input={trf}:smoothing={smoothing}:zoom={a.zoom}:optzoom=0:"
          f"crop=keep:interpol=bicubic")
    print(f"[2/2] 套用平滑 smoothing={smoothing}、zoom={a.zoom}%")
    simple_vf(a.input, a.output, vf, a.preview, info["audio"])
    if a.report and not DRY:
        after = shake_report(a.output, a.preview, "穩定後")
        if before and after:
            print(f"位移平均 {before[0]:.2f} → {after[0]:.2f} px（降 {100 * (1 - after[0] / max(before[0], 1e-6)):.0f}%）")


# ---------- denoise ----------
DENOISE = {
    "hqdn3d": {"light": "hqdn3d=2:1.5:3:3", "medium": "hqdn3d=4:3:6:4.5", "heavy": "hqdn3d=8:6:12:9"},
    "nlmeans": {"light": "nlmeans=s=1.5:p=5:r=9", "medium": "nlmeans=s=3:p=7:r=11", "heavy": "nlmeans=s=6:p=7:r=15"},
    "atadenoise": {"light": "atadenoise=0a=0.01:0b=0.02:1a=0.01:1b=0.02:2a=0.01:2b=0.02:s=9",
                   "medium": "atadenoise=0a=0.02:0b=0.04:1a=0.02:1b=0.04:2a=0.02:2b=0.04:s=9",
                   "heavy": "atadenoise=0a=0.04:0b=0.08:1a=0.04:1b=0.08:2a=0.04:2b=0.08:s=15"},
}


def cmd_denoise(a):
    """降噪：hqdn3d 快（約即時 6 倍）、nlmeans 慢而乾淨（720p 約 10–25 倍即時時間）、atadenoise 時間域（靜態場景）。"""
    check_in(a.input)
    check_out(a.output)
    vf = DENOISE[a.method][a.level]
    if a.method == "nlmeans" and not is_image(a.input) and not a.preview:
        print("提示：nlmeans 很慢，長片先加 --preview 10 試跑")
    if a.method == "atadenoise" and is_image(a.input):
        die("atadenoise 是時間域濾鏡，單張照片請改 --method hqdn3d 或 nlmeans")
    print(f"降噪 {a.method} / {a.level}：{vf}")
    simple_vf(a.input, a.output, vf, a.preview)


# ---------- sharpen ----------
def cmd_sharpen(a):
    """銳化：cas（對比自適應銳化），不易出現白邊；影片與照片皆可；放在流程最後。"""
    check_in(a.input)
    check_out(a.output)
    if not 0 <= a.amount <= 1:
        die("--amount 必須在 0–1")
    simple_vf(a.input, a.output, f"cas=strength={fnum(a.amount)}", a.preview)


# ---------- deflicker ----------
def cmd_deflicker(a):
    """去閃爍：deflicker 用前後 size 格的亮度平均拉平，適合日光燈頻閃、縮時曝光跳動。"""
    check_in(a.input)
    check_out(a.output)
    if is_image(a.input):
        die("deflicker 需要影片輸入")
    simple_vf(a.input, a.output, f"deflicker=size={a.size}:mode=am", a.preview)


# ---------- skin ----------
def skin_mask_expr(cr=152, crw=22, cb=106, cbw=24, lo=40, hi=245, gain=1.0):
    """膚色遮罩的 geq 表達式（YCbCr 窗：Cr 中心 152±22、Cb 中心 106±24、亮度 40–245）。
    回傳 0–255 的軟遮罩；gain 乘上強度。"""
    return (f"255*{fnum(gain)}*clip(1-abs(cr(X,Y)-{cr})/{crw},0,1)"
            f"*clip(1-abs(cb(X,Y)-{cb})/{cbw},0,1)*between(lum(X,Y),{lo},{hi})")


def skin_graph(src_label, out_label, strength, mask_out_label=None, feather=4, split_sigma=3):
    """頻率分離柔膚的 filter_complex 片段：
    低頻 = gblur(σ=split_sigma)；高頻 = 原圖 − 低頻（grainextract）；
    低頻再用 bilateral 抹平斑塊（保邊）；合回 = 低頻' + 高頻（grainmerge）；最後 maskedmerge 只在膚色遮罩內替換。"""
    m = skin_mask_expr(gain=strength)
    sig_s = 6 + 10 * strength      # 空間半徑：強度 1 → 16
    sig_r = 0.05 + 0.10 * strength  # 色差容忍：強度 1 → 0.15
    g = (f"[{src_label}]format=yuv444p,split=3[s0][s1][s2];"
         f"[s1]geq=lum='{m}':cb='{m}':cr='{m}',gblur=sigma={feather},split=2[mask][maskv];"
         f"[s2]gblur=sigma={split_sigma},split=2[low][lowb];"
         f"[s0]split=2[orig][origb];"
         f"[origb][lowb]blend=all_mode=grainextract[high];"
         f"[low]bilateral=sigmaS={fnum(sig_s)}:sigmaR={fnum(sig_r)}[low2];"
         f"[low2][high]blend=all_mode=grainmerge[smooth];"
         f"[orig][smooth][mask]maskedmerge[{out_label}]")
    if mask_out_label:
        g += f";[maskv]format=gray[{mask_out_label}]"
    else:
        g += ";[maskv]nullsink"
    return g


def cmd_skin(a):
    """柔膚：膚色遮罩（geq 的 YCbCr 窗）→ 只在遮罩內做頻率分離（低頻保邊柔化、高頻毛孔保留）→ maskedmerge。"""
    check_in(a.input)
    check_out(a.output)
    if not 0 <= a.strength <= 1:
        die("--strength 必須在 0–1")
    img = is_image(a.input)
    info = None if img else probe(a.input)
    has_audio = bool(info and info["audio"])
    mask_label = "maskout" if a.mask_out else None
    graph = skin_graph("0:v", "out", a.strength, mask_label)
    graph += ";[out]format=" + ("rgb24" if img and a.output.lower().endswith(".png") else "yuv420p") + "[fin]"
    cmd = ffmpeg_base() + in_args(a.input, a.preview) + ["-filter_complex", graph, "-map", "[fin]"]
    if has_audio:
        cmd += ["-map", "0:a:0"]
    cmd += enc_args(a.output, has_audio) + [a.output]
    if a.mask_out:
        check_out(a.mask_out)
        cmd += ["-map", "[maskout]"] + enc_args(a.mask_out, False) + [a.mask_out]
    print(f"柔膚 strength={a.strength}（遮罩：Cr 152±22、Cb 106±24、Y 40–245；bilateral σS={fnum(6 + 10 * a.strength)}）")
    run(cmd)


# ---------- relight ----------
def parse_floats(s, n, name):
    try:
        v = [float(x) for x in s.split(",")]
    except ValueError:
        die(f"--{name} 格式錯誤：{s}")
    if len(v) != n:
        die(f"--{name} 需要 {n} 個數值（逗號分隔）：{s}")
    return v


def build_light_map(w, h, key, fill, rim, path):
    """用 geq 產生 0–255 的光圖（PNG）：高斯徑向 key 光 + 均勻 fill + 單邊線性 rim；之後用 screen 疊上去。"""
    terms = []
    if key:
        x, y, r, i = key
        cx, cy, rp = x * w, y * h, max(r * w, 1)
        terms.append(f"{fnum(i)}*exp(-((X-{fnum(cx)})^2+(Y-{fnum(cy)})^2)/(2*{fnum(rp)}^2))")
    if fill:
        terms.append(f"{fnum(fill * 0.35)}")
    if rim:
        d, s = rim
        ramp = {"left": "(0.45-X/W)/0.45", "right": "(X/W-0.55)/0.45",
                "top": "(0.45-Y/H)/0.45", "bottom": "(Y/H-0.55)/0.45"}[d]
        terms.append(f"{fnum(s)}*pow(clip({ramp},0,1),1.5)")
    expr = "+".join(terms) if terms else "0"
    run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i", f"color=black:s={w}x{h},format=gray",
         "-vf", f"geq=lum='255*clip({expr},0,1)'", "-frames:v", "1", "-update", "1", path])


def cmd_relight(a):
    """後製虛擬打光：光圖（key／fill／rim）用 screen 或 softlight 疊加，再加暈影與色溫；至少 key 與 vignette 可單獨用。"""
    check_in(a.input)
    check_out(a.output)
    img = is_image(a.input)
    info = probe(a.input)
    w, h = info["w"], info["h"]
    key = parse_floats(a.key, 4, "key") if a.key else None
    rim = None
    if a.rim:
        parts = a.rim.split(",")
        if len(parts) != 2 or parts[0] not in ("left", "right", "top", "bottom"):
            die("--rim 格式：方向,強度，方向為 left|right|top|bottom，例如 --rim right,0.4")
        rim = (parts[0], float(parts[1]))
    if not any([key, a.fill, rim, a.vignette, a.temp]):
        die("至少給一項：--key、--fill、--rim、--vignette、--temp")
    if a.vignette and not 0 <= a.vignette <= 1:
        die("--vignette 必須在 0–1")
    post = []
    if a.vignette:
        post.append(f"vignette=angle={fnum(a.vignette * math.pi / 4)}")  # 0.5≈角落 70%、1≈角落 27% 亮度
    if a.temp:
        post.append(f"colortemperature=temperature={int(6500 + a.temp)}:pl=1")  # 負=變暖、正=變冷
    has_audio = info["audio"]
    out_fmt = "rgb24" if img and a.output.lower().endswith(".png") else "yuv420p"
    cmd = ffmpeg_base() + in_args(a.input, a.preview)
    if key or a.fill or rim:
        lm = os.path.splitext(a.output)[0] + "_light.png"
        print(f"[1/2] 產生光圖 {w}x{h} → {lm}")
        build_light_map(w, h, key, a.fill, rim, lm)
        mode = a.mode
        graph = (f"[0:v]format=gbrp[base];[1:v]format=gbrp[lm];"
                 f"[base][lm]blend=all_mode={mode}:all_opacity={fnum(a.opacity)}:shortest=1[lit];"
                 f"[lit]{','.join(post + ['format=' + out_fmt])}[fin]")
        cmd += ["-loop", "1", "-i", lm, "-filter_complex", graph, "-map", "[fin]"]
        print(f"[2/2] 疊加 {mode}（opacity {a.opacity}）" + (f" + {' + '.join(post)}" if post else ""))
    else:
        cmd += ["-vf", ",".join(post + ["format=" + out_fmt])]
    if has_audio:
        cmd += ["-map", "0:a:0"]
    cmd += enc_args(a.output, has_audio) + [a.output]
    run(cmd)


# ---------- match ----------
KEYS = ["YAVG", "UAVG", "VAVG", "YMIN", "YMAX", "YLOW", "YHIGH", "SATAVG"]


def measure(path, preview, label):
    """用 signalstats 每秒取樣（影片 fps=1）量 YAVG／UAVG／VAVG／YMIN／YMAX／YLOW／YHIGH／SATAVG，各格平均。"""
    statf = tempfile.mktemp(suffix=".txt", prefix="stats_")
    vf = ("" if is_image(path) else "fps=1,") + f"signalstats,metadata=print:file={statf}"
    run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostats"] + in_args(path, preview) +
        ["-vf", vf, "-f", "null", "-"])
    if DRY:
        return {k: 0.0 for k in KEYS}
    vals = {k: [] for k in KEYS}
    for line in open(statf, encoding="utf-8", errors="ignore"):
        m = re.match(r"lavfi\.signalstats\.(\w+)=([-\d.]+)", line.strip())
        if m and m.group(1) in vals:
            vals[m.group(1)].append(float(m.group(2)))
    os.remove(statf)
    if not vals["YAVG"]:
        die(f"量不到 {path} 的 signalstats 數值")
    r = {k: (sum(v) / len(v) if v else 0.0) for k, v in vals.items()}
    print(f"[{label}] " + " ".join(f"{k}={r[k]:.1f}" for k in KEYS) + f"（取樣 {len(vals['YAVG'])} 格）")
    return r


def solve_rgb(dU, dV):
    """已知要補的 ΔU、ΔV（0–255 單位）且 ΔY=0，解 BT.601 的 RGB 位移（0–1 單位）。"""
    # 方程：219*(0.299R+0.587G+0.114B)=0；224*(-0.1687R-0.3313G+0.5B)=dU；224*(0.5R-0.4187G-0.0813B)=dV
    A = [[219 * 0.299, 219 * 0.587, 219 * 0.114],
         [224 * -0.1687, 224 * -0.3313, 224 * 0.5],
         [224 * 0.5, 224 * -0.4187, 224 * -0.0813]]
    b = [0.0, dU, dV]

    def det3(m):
        return (m[0][0] * (m[1][1] * m[2][2] - m[1][2] * m[2][1])
                - m[0][1] * (m[1][0] * m[2][2] - m[1][2] * m[2][0])
                + m[0][2] * (m[1][0] * m[2][1] - m[1][1] * m[2][0]))

    d = det3(A)
    out = []
    for i in range(3):
        M = [row[:] for row in A]
        for r in range(3):
            M[r][i] = b[r]
        out.append(det3(M) / d)
    return out


def cmd_match(a):
    """顏色匹配：量 SRC 與 REF 的 signalstats → eq 補亮度／對比／飽和，colorbalance 補色偏 → 套用後再量一次印殘差。"""
    check_in(a.input)
    check_in(a.ref)
    check_out(a.output)
    s = measure(a.input, a.preview, "SRC")
    r = measure(a.ref, a.preview, "REF")
    if DRY:
        print("（--dry-run 無量測值，略過計算）")
        return
    # 對比用 YLOW／YHIGH（10%／90% 分位）比 YMIN／YMAX 穩，極值常被單一像素帶偏
    span_s = max(s["YHIGH"] - s["YLOW"], 1.0)
    span_r = max(r["YHIGH"] - r["YLOW"], 1.0)
    contrast = min(max(span_r / span_s, 0.6), 1.6)
    # eq 的 contrast 以 128 為軸：Y' = (Y-128)*c + 128 + brightness*255
    brightness = (r["YAVG"] - ((s["YAVG"] - 128) * contrast + 128)) / 255
    brightness = min(max(brightness, -0.5), 0.5)
    sat = 1.0
    if s["SATAVG"] > 1 and r["SATAVG"] > 1:
        sat = min(max(r["SATAVG"] / s["SATAVG"], 0.5), 2.0)
    # 飽和度縮放後的色度再算殘差
    dU = r["UAVG"] - (128 + (s["UAVG"] - 128) * sat)
    dV = r["VAVG"] - (128 + (s["VAVG"] - 128) * sat)
    R, G, B = solve_rgb(dU, dV)
    # ffmpeg 6.1 的 colorbalance：rh/gh/bh 才會動到中間調以上（實測），每 1.0 等於 RGB +0.7
    rh, gh, bh = (min(max(x / 0.7, -1), 1) for x in (R, G, B))
    eq = f"eq=brightness={fnum(brightness)}:contrast={fnum(contrast)}:saturation={fnum(sat)}"
    cb = f"colorbalance=rh={fnum(rh)}:gh={fnum(gh)}:bh={fnum(bh)}"
    print(f"目標：ΔY {r['YAVG'] - s['YAVG']:+.1f}、對比 x{contrast:.3f}、飽和 x{sat:.3f}、ΔU {dU:+.1f}、ΔV {dV:+.1f}")
    print(f"套用：{eq},{cb}")
    simple_vf(a.input, a.output, f"{eq},{cb}", a.preview)
    o = measure(a.output, a.preview, "OUT")
    print(f"殘差（OUT−REF）：ΔY {o['YAVG'] - r['YAVG']:+.1f}、ΔU {o['UAVG'] - r['UAVG']:+.1f}、ΔV {o['VAVG'] - r['VAVG']:+.1f}"
          f"（|Δ|≤3 肉眼幾乎分不出；不夠再以 OUT 當 SRC 跑一次）")


# ---------- photo ----------
PRESETS = {
    "none": {"contrast": None, "sat": 100, "skin": 0.0, "sharpen": 0.0},
    "portrait": {"contrast": "2.5x50%", "sat": 100, "skin": 0.45, "sharpen": 0.25},
    "product": {"contrast": "3x50%", "sat": 100, "skin": 0.0, "sharpen": 0.6},
    "landscape": {"contrast": "3.5x50%", "sat": 112, "skin": 0.0, "sharpen": 0.5},
}


def cmd_photo(a):
    """照片修圖管線：convert（轉正、去 EXIF／GPS、曝光、對比、飽和）→ ffmpeg（色溫、柔膚、銳化）→ convert 輸出品質。"""
    need("convert", "請安裝 ImageMagick（apt install imagemagick）")
    check_in(a.input)
    check_out(a.output)
    p = PRESETS[a.preset]
    skin = p["skin"] if a.skin is None else a.skin
    sharpen = p["sharpen"] if a.sharpen is None else a.sharpen
    tmpd = tempfile.mkdtemp(prefix="photo_")
    t1 = os.path.join(tmpd, "step1.png")
    t2 = os.path.join(tmpd, "step2.png")
    # 第一步：ImageMagick
    c1 = ["convert", a.input, "-auto-orient"]
    if a.strip_exif:
        c1 += ["-strip"]
    if a.exposure:
        # 線性光域乘 2^EV，接近相機曝光；sRGB→RGB(線性)→sRGB
        c1 += ["-colorspace", "RGB", "-evaluate", "Multiply", fnum(2 ** a.exposure), "-colorspace", "sRGB"]
    if p["contrast"]:
        c1 += ["-sigmoidal-contrast", p["contrast"]]
    if p["sat"] != 100:
        c1 += ["-modulate", f"100,{p['sat']}"]
    if a.max_size:
        c1 += ["-resize", f"{a.max_size}x{a.max_size}>", "-filter", "Lanczos"]
    c1 += ["-depth", "8", t1]
    print("[1/3] ImageMagick：轉正" + ("、去 EXIF／GPS" if a.strip_exif else "") +
          (f"、曝光 {a.exposure:+} EV" if a.exposure else "") + (f"、S 曲線 {p['contrast']}" if p["contrast"] else ""))
    run(c1)
    # 第二步：ffmpeg（色溫、柔膚、銳化）
    chain = []
    if a.wb:
        chain.append(f"colortemperature=temperature={int(6500 + a.wb)}:pl=1")
    graph = "[0:v]" + (",".join(chain) if chain else "null") + "[a]"
    if skin > 0:
        graph += ";" + skin_graph("a", "b", skin)
        cur = "b"
    else:
        cur = "a"
    tail = f"cas=strength={fnum(sharpen)}," if sharpen > 0 else ""
    graph += f";[{cur}]{tail}format=rgb24[fin]"
    print(f"[2/3] ffmpeg：" + (f"色溫 {a.wb:+}K、" if a.wb else "") + f"柔膚 {skin}、銳化 {sharpen}")
    run(ffmpeg_base() + ["-i", t1, "-filter_complex", graph, "-map", "[fin]", "-frames:v", "1", "-update", "1", t2])
    # 第三步：輸出
    c3 = ["convert", t2]
    if a.strip_exif:
        c3 += ["-strip"]
    ext = os.path.splitext(a.output)[1].lower()
    if ext in (".jpg", ".jpeg", ".webp"):
        c3 += ["-quality", str(a.quality)]
    c3 += [a.output]
    print(f"[3/3] 輸出 {a.output}（quality {a.quality}）")
    run(c3)
    shutil.rmtree(tmpd, ignore_errors=True)


# ---------- kenburns ----------
EASE = {
    "linear": "P",
    "out": "(1-(1-P)*(1-P))",
    "inOut": "if(lt(P,0.5),2*P*P,1-pow(-2*P+2,2)/2)",
}


def cmd_kenburns(a):
    """Ken Burns：zoompan 做緩動推軌；--from／--to 是 x,y,zoom（x、y 為視窗中心的 0–1 相對座標，zoom ≥ 1）。"""
    check_in(a.input)
    check_out(a.output)
    m = re.match(r"^(\d+)x(\d+)$", a.size)
    if not m:
        die("--size 格式：WxH，例如 1920x1080")
    W, H = int(m.group(1)), int(m.group(2))
    x0, y0, z0 = parse_floats(a.from_, 3, "from")
    x1, y1, z1 = parse_floats(a.to, 3, "to")
    if min(z0, z1) < 1:
        die("zoom 必須 ≥ 1")
    D = max(int(round(a.dur * a.fps)), 2)
    P = f"(on/{D - 1})"
    e = EASE[a.ease].replace("P", P)
    z = f"({fnum(z0)}+({fnum(z1 - z0)})*{e})"
    cx = f"(({fnum(x0)}+({fnum(x1 - x0)})*{e})*iw)"
    cy = f"(({fnum(y0)}+({fnum(y1 - y0)})*{e})*ih)"
    xe = f"clip({cx}-iw/{z}/2,0,iw-iw/{z})"
    ye = f"clip({cy}-ih/{z}/2,0,ih-ih/{z})"
    # 先把照片縮放成輸出比例的 2 倍（抑制 zoompan 的整數抖動），再做推軌
    vf = (f"scale={W * 2}:{H * 2}:force_original_aspect_ratio=increase:flags=lanczos,crop={W * 2}:{H * 2},"
          f"zoompan=z='{z}':x='{xe}':y='{ye}':d={D}:s={W}x{H}:fps={a.fps},format=yuv420p")
    print(f"Ken Burns {a.dur}s @ {a.fps}fps，{a.from_} → {a.to}，緩動 {a.ease}")
    run(ffmpeg_base() + ["-i", a.input, "-vf", vf, "-frames:v", str(D)] + enc_args(a.output, False) + [a.output])


# ---------- upscale ----------
def cmd_upscale(a):
    """放大：lanczos（銳）／spline（柔）／placebo（libplacebo，需要 Vulkan，這台未測）；之後視需要再 sharpen。"""
    check_in(a.input)
    check_out(a.output)
    m = re.match(r"^(-?\d+)x(-?\d+)$", a.size)
    if not m:
        die("--size 格式：WxH（可用 -2 自動算另一邊，例如 3840x-2）")
    W, H = m.group(1), m.group(2)
    if a.method == "placebo":
        vf = f"libplacebo=w={W}:h={H}:upscaler=ewa_lanczos,format=yuv420p"
        print("提示：libplacebo 需要 Vulkan 裝置，容器內通常會失敗；失敗請改 --method lanczos")
    else:
        vf = f"scale={W}:{H}:flags={a.method}"
    simple_vf(a.input, a.output, vf, a.preview)


# ---------- slowmo ----------
def cmd_slowmo(a):
    """慢動作：--factor 2|4；預設只拉長時間（重複格），--interp 用 minterpolate 補中間格（720p 約 25 倍即時時間）。"""
    check_in(a.input)
    check_out(a.output)
    if is_image(a.input):
        die("slowmo 需要影片輸入")
    info = probe(a.input)
    fps = info["fps"]
    if a.interp:
        vf = (f"minterpolate=fps={fnum(fps * a.factor)}:mi_mode=mci:mc_mode=aobmc:me_mode=bidir:vsbmc=1,"
              f"setpts={a.factor}*PTS")
        if not a.preview:
            print("提示：minterpolate 很慢，長片先加 --preview 5 試跑")
    else:
        vf = f"setpts={a.factor}*PTS"
    af = ",".join(["atempo=0.5"] * int(math.log2(a.factor))) if info["audio"] else None
    print(f"慢動作 x{a.factor}（{'補格' if a.interp else '重複格'}，輸出 {fnum(fps)} fps）")
    cmd = ffmpeg_base() + in_args(a.input, a.preview) + ["-vf", vf, "-r", fnum(fps)]
    if info["audio"]:
        cmd += ["-map", "0:v:0", "-map", "0:a:0"]
    cmd += enc_args(a.output, info["audio"], af) + [a.output]
    run(cmd)


# ---------- 參數 ----------
def build_parser():
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("-o", "--output", required=True, help="輸出檔")
    common.add_argument("-y", dest="overwrite", action="store_true", help="覆寫輸出")
    common.add_argument("--dry-run", action="store_true", help="只印指令不執行")
    common.add_argument("--preview", type=float, metavar="秒", help="只處理前 N 秒（影片）")

    p = argparse.ArgumentParser(description="實拍照片與影片精修 CLI（配方見 references/footage.md）")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("stabilize", parents=[common], help="vidstab 兩段式穩定")
    s.add_argument("input")
    s.add_argument("--strength", type=int, choices=[1, 2, 3], default=2, help="1 輕 / 2 中 / 3 強（預設 2）")
    s.add_argument("--zoom", type=float, default=5, help="放大 %% 避免黑邊（0–10，預設 5）")
    s.add_argument("--report", action="store_true", help="穩定後再量一次位移，印前後比較")
    s.set_defaults(fn=cmd_stabilize)

    s = sub.add_parser("denoise", parents=[common], help="降噪")
    s.add_argument("input")
    s.add_argument("--level", choices=["light", "medium", "heavy"], default="medium")
    s.add_argument("--method", choices=["hqdn3d", "nlmeans", "atadenoise"], default="hqdn3d")
    s.set_defaults(fn=cmd_denoise)

    s = sub.add_parser("sharpen", parents=[common], help="cas 銳化（影片與照片）")
    s.add_argument("input")
    s.add_argument("--amount", type=float, default=0.5, help="0–1，預設 0.5")
    s.set_defaults(fn=cmd_sharpen)

    s = sub.add_parser("deflicker", parents=[common], help="去閃爍")
    s.add_argument("input")
    s.add_argument("--size", type=int, default=10, help="參考格數（預設 10）")
    s.set_defaults(fn=cmd_deflicker)

    s = sub.add_parser("skin", parents=[common], help="膚色遮罩內頻率分離柔膚")
    s.add_argument("input")
    s.add_argument("--strength", type=float, default=0.5, help="0–1，預設 0.5")
    s.add_argument("--mask-out", metavar="mask.mp4", help="另存遮罩影片／圖片供檢查")
    s.set_defaults(fn=cmd_skin)

    s = sub.add_parser("relight", parents=[common], help="後製虛擬打光")
    s.add_argument("input")
    s.add_argument("--key", metavar="X,Y,R,強度", help="徑向主光：中心 0–1 相對座標、半徑（佔寬比）、強度 0–1，例 0.4,0.35,0.3,0.5")
    s.add_argument("--fill", type=float, default=0.0, help="均勻補光 0–1（提亮暗部）")
    s.add_argument("--rim", metavar="方向,強度", help="單邊線性光：left|right|top|bottom,強度，例 right,0.4")
    s.add_argument("--temp", type=float, default=0.0, help="色溫偏移 K：負=變暖、正=變冷，例 -800")
    s.add_argument("--vignette", type=float, default=0.0, help="暈影 0–1（0.5≈角落剩 70%% 亮）")
    s.add_argument("--mode", choices=["screen", "softlight", "overlay"], default="screen", help="光圖疊加模式（預設 screen）")
    s.add_argument("--opacity", type=float, default=1.0, help="光圖不透明度 0–1")
    s.set_defaults(fn=cmd_relight)

    s = sub.add_parser("match", parents=[common], help="顏色匹配（SRC 靠近 REF）")
    s.add_argument("input", metavar="SRC")
    s.add_argument("--ref", required=True, help="參考片／照片")
    s.set_defaults(fn=cmd_match)

    s = sub.add_parser("photo", parents=[common], help="照片修圖管線（ImageMagick＋ffmpeg）")
    s.add_argument("input")
    s.add_argument("--preset", choices=list(PRESETS), default="none")
    s.add_argument("--exposure", type=float, default=0.0, metavar="EV", help="曝光補償，例 +0.3 / -0.5")
    s.add_argument("--wb", type=float, default=0.0, metavar="K", help="色溫偏移：負=變暖、正=變冷")
    s.add_argument("--skin", type=float, help="柔膚 0–1（覆蓋 preset）")
    s.add_argument("--sharpen", type=float, help="銳化 0–1（覆蓋 preset）")
    s.add_argument("--strip-exif", dest="strip_exif", action="store_true", default=True, help="去 EXIF 與 GPS（預設開）")
    s.add_argument("--keep-exif", dest="strip_exif", action="store_false", help="保留 EXIF")
    s.add_argument("--quality", type=int, default=92, help="JPEG／WebP 品質（預設 92）")
    s.add_argument("--max-size", type=int, metavar="像素", help="長邊超過就縮到這個像素")
    s.set_defaults(fn=cmd_photo)

    s = sub.add_parser("kenburns", parents=[common], help="照片推軌（zoompan 緩動）")
    s.add_argument("input")
    s.add_argument("--dur", type=float, required=True, help="秒")
    s.add_argument("--from", dest="from_", default="0.5,0.5,1.0", metavar="x,y,zoom", help="起點（預設 0.5,0.5,1.0）")
    s.add_argument("--to", default="0.5,0.5,1.15", metavar="x,y,zoom", help="終點（預設 0.5,0.5,1.15）")
    s.add_argument("--fps", type=int, default=30)
    s.add_argument("--size", default="1920x1080")
    s.add_argument("--ease", choices=["inOut", "out", "linear"], default="inOut")
    s.set_defaults(fn=cmd_kenburns)

    s = sub.add_parser("upscale", parents=[common], help="放大")
    s.add_argument("input")
    s.add_argument("--size", required=True, help="WxH，例 3840x2160 或 3840x-2")
    s.add_argument("--method", choices=["lanczos", "spline", "placebo"], default="lanczos")
    s.set_defaults(fn=cmd_upscale)

    s = sub.add_parser("slowmo", parents=[common], help="慢動作")
    s.add_argument("input")
    s.add_argument("--factor", type=int, choices=[2, 4], required=True)
    s.add_argument("--interp", action="store_true", help="用 minterpolate 補格")
    s.set_defaults(fn=cmd_slowmo)
    return p


def main():
    global DRY, OVERWRITE
    need("ffmpeg", "請先安裝 ffmpeg")
    a = build_parser().parse_args()
    DRY = a.dry_run
    OVERWRITE = a.overwrite
    if DRY:
        print("（--dry-run：只印指令，不執行）")
    a.fn(a)
    if not DRY:
        print(f"完成：{a.output}")


if __name__ == "__main__":
    main()
