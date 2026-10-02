#!/usr/bin/env python3
"""footage.py — 實拍照片與影片精修 CLI（配方詳見 references/footage.md）

子命令：stabilize、denoise、sharpen、deflicker、skin、relight、match、photo、kenburns、upscale、slowmo
共通選項：-o 輸出、-y 覆寫、--dry-run 只印指令、--preview N 只處理前 N 秒
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
OUTPUTS = []   # (實際寫入的路徑, 最終路徑)：失敗時只刪本次新建的檔；輸出已存在時先寫到 .partial、成功後改名（見 check_out）


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


def safe_path(path):
    """路徑含冒號（例如 macOS 匯出的「12:30 clip.mp4」）時，ffmpeg／ffprobe 把冒號前的字串當協定名（Protocol not found）、
    ImageMagick 當格式名；轉成絕對路徑（以 / 開頭）三者都當一般檔名（本機實測）。只在含冒號的相對路徑上動。"""
    if path and ":" in path and not os.path.isabs(path):
        return os.path.abspath(path)
    return path


def check_in(path):
    if not os.path.isfile(path):
        die(f"找不到輸入檔：{path}")


def check_out(path, inputs=()):
    """登記一個輸出檔，回傳「實際要寫的路徑」（呼叫端之後都用回傳值）。
    - 與任一輸入（inputs：輸入檔、--ref 等）同一個檔案就停：ffmpeg 會拒絕（Output same as Input），convert 則原地覆寫原檔
    - 已存在且沒加 -y 就停
    - 已存在且加了 -y：回傳同目錄的 NAME.partial.EXT，成功後由 finalize_outputs() 改名蓋回去；失敗只刪 .partial、原檔不動
      （ffmpeg -y 在濾鏡初始化失敗時會先把既有輸出截成 0 byte，本機實測，所以不能直接寫在原檔上）
    - 順便建立輸出資料夾"""
    for src in inputs:
        if src and os.path.abspath(src) == os.path.abspath(path):
            die(f"輸出不能與輸入同一個檔案：{path}，請改輸出檔名")
    for _, final in OUTPUTS:
        if os.path.abspath(final) == os.path.abspath(path):
            die(f"兩個輸出不能是同一個檔案：{path}")
    if os.path.exists(path) and not OVERWRITE:
        die(f"輸出檔已存在：{path}（加 -y 覆寫）")
    d = os.path.dirname(os.path.abspath(path))
    os.makedirs(d, exist_ok=True)
    write = path
    if os.path.exists(path):
        base, ext = os.path.splitext(path)
        write = base + ".partial" + ext
        print(f"輸出 {path} 已存在：先寫到 {write}，成功後改名蓋回（失敗不動原檔）")
    OUTPUTS.append((write, path))
    return write


def cleanup_outputs():
    """指令失敗後刪掉本次寫的檔（ffmpeg 失敗常留下 0 byte 或半截檔）。
    只刪 check_out() 回傳的寫入路徑：本來就存在的輸出檔走 .partial，所以原檔不會被刪。"""
    for write, _ in OUTPUTS:
        if os.path.isfile(write):
            try:
                os.remove(write)
                print(f"已刪除未完成的輸出：{write}", file=sys.stderr)
            except OSError:
                pass


def finalize_outputs():
    """全部成功後，把 .partial 改名成最終檔名。"""
    for write, final in OUTPUTS:
        if write != final and os.path.isfile(write):
            os.replace(write, final)


def ff_escape(path):
    """濾鏡選項裡的檔案路徑要做兩層跳脫（ffmpeg 官方說明〈Notes on filtergraph escaping〉）：
    選項層跳脫 \\ ' :，濾鏡圖層再跳脫 \\ ' [ ] , ;。路徑含冒號或逗號時沒跳脫會 Invalid argument。"""
    s = path.replace("\\", "\\\\").replace("'", "\\'").replace(":", "\\:")
    s = s.replace("\\", "\\\\").replace("'", "\\'")
    for ch in "[],;":
        s = s.replace(ch, "\\" + ch)
    return s


def run(cmd, capture=False, quiet=False, check=True):
    """印出並執行指令；--dry-run 只印。失敗時給繁中訊息；check=False 時不結束，直接回傳 CompletedProcess 讓呼叫端自己判斷。"""
    if not quiet:
        print("$ " + shlex.join(cmd), flush=True)
    if DRY:
        return None if not check else ""
    try:
        r = subprocess.run(cmd, text=True, capture_output=capture)
    except FileNotFoundError:
        die(f"無法執行 {cmd[0]}，請確認已安裝")
    if not check:
        return r
    if r.returncode != 0:
        tail = ""
        if capture and r.stderr:
            tail = "\n" + "\n".join(r.stderr.strip().splitlines()[-8:])
        cleanup_outputs()
        die(f"{cmd[0]} 執行失敗（exit {r.returncode}），請看上方訊息{tail}")
    return (r.stdout or "") + (r.stderr or "") if capture else ""


def bit_depth(pix_fmt):
    """從 pix_fmt 名稱推每個分量的位深：yuv420p10le → 10、gray16le → 16、yuv420p／rgb24 → 8；
    包裝式 RGB 的數字是整個畫素的位元數（rgb48be、rgba64be 都是每分量 16）。"""
    m = re.search(r"(\d+)(le|be)$", pix_fmt or "")
    if not m:
        return 8
    n = int(m.group(1))
    if n <= 16:
        return n
    return 16 if n in (48, 64) else 8


def probe(path):
    """ffprobe 取得第一條影像串流（含 pix_fmt、位深）與是否有音軌。"""
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
    pf = v.get("pix_fmt", "")
    return {"w": int(v["width"]), "h": int(v["height"]), "fps": fps, "audio": a, "dur": dur,
            "pix_fmt": pf, "bits": bit_depth(pf)}


def ffmpeg_base():
    return ["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostats", "-y" if OVERWRITE else "-n"]


def in_args(path, preview):
    """影片可加 --preview 只讀前 N 秒；照片直接 -i 單張。"""
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


def simple_vf(inp, out, vf, preview, has_audio=None, audio_filter=None, overwrite=False, check=True):
    """單輸入單濾鏡鏈的標準呼叫；overwrite=True 時不管 -y 都覆寫（給程式自己的暫存檔用）；check=False 時失敗不結束，回傳 CompletedProcess。"""
    if has_audio is None:
        has_audio = (not is_image(inp)) and probe(inp)["audio"]
    cmd = ffmpeg_base() + in_args(inp, preview) + ["-vf", vf]
    if overwrite and "-n" in cmd:
        cmd[cmd.index("-n")] = "-y"
    if has_audio:
        cmd += ["-map", "0:v:0", "-map", "0:a:0"]
    cmd += enc_args(out, has_audio, audio_filter) + [out]
    return run(cmd, capture=not check, check=check)


def fnum(x):
    return f"{x:.4f}".rstrip("0").rstrip(".")


# ---------- stabilize ----------
def parse_trf(path):
    """解析 vidstabdetect 的 transforms 檔：每格取所有區域運動（LM x y）的中位數當整體位移。"""
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
    """用 vidstabdetect 量一支片的逐格位移，回傳平均與最大畫素。transforms 檔寫在 mkdtemp 的私有目錄（不用 mktemp：只給檔名不建檔，兩個工作流同時跑會撞名）。"""
    tmpd = tempfile.mkdtemp(prefix="footage_report_")
    trf = os.path.join(tmpd, "report.trf")
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostats"] + in_args(path, preview) + \
          ["-vf", f"vidstabdetect=shakiness=5:accuracy=15:result={ff_escape(trf)}", "-f", "null", "-"]
    try:
        run(cmd)
        m = None if DRY else parse_trf(trf)
    finally:
        shutil.rmtree(tmpd, ignore_errors=True)
    if not m:
        return None
    avg, mx = sum(m) / len(m), max(m)
    print(f"[{label}] 逐格位移 平均 {avg:.2f} px、最大 {mx:.1f} px（{len(m)} 格）")
    return avg, mx


def cmd_stabilize(a):
    """vidstab 兩段式穩定：先 detect 寫 transforms，再 transform 套用；--zoom 放大 % 避免黑邊。
    strength 1/2/3 = smoothing 10/20/40（越大越像滑軌，但需要更多放大）；--lock = smoothing 0（固定機位）。
    transforms 檔預設寫在暫存目錄、完成後刪除；--keep-trf 改存在輸出旁（OUT.trf）供重跑第二段。"""
    check_in(a.input)
    if not 0 <= a.zoom <= 10:
        die("--zoom 必須在 0–10（放大百分比；超過 10% 先考慮換素材）")
    out = check_out(a.output, [a.input])
    info = probe(a.input)
    shakiness = {1: 4, 2: 6, 3: 8}[a.strength]
    smoothing = 0 if a.lock else {1: 10, 2: 20, 3: 40}[a.strength]
    tmpd = None
    if a.keep_trf:
        trf = os.path.splitext(a.output)[0] + ".trf"
    else:
        tmpd = tempfile.mkdtemp(prefix="footage_stab_")
        trf = os.path.join(tmpd, "stab.trf")
    print(f"[1/2] 偵測位移 shakiness={shakiness}（strength {a.strength}）→ {trf}" +
          ("（--keep-trf：保留，重跑第二段時可直接用）" if a.keep_trf else "（暫存，完成後刪除；要保留加 --keep-trf）"))
    try:
        run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostats"] + in_args(a.input, a.preview) +
            ["-vf", f"vidstabdetect=shakiness={shakiness}:accuracy=15:stepsize=6:result={ff_escape(trf)}", "-f", "null", "-"])
        before = None
        if not DRY:
            m = parse_trf(trf)
            if m:
                before = (sum(m) / len(m), max(m))
                need_zoom = before[1] / info["w"] * 100 * 2
                print(f"[原片] 逐格位移 平均 {before[0]:.2f} px、最大 {before[1]:.1f} px")
                if need_zoom > a.zoom:
                    print(f"提示：最大位移約佔寬度 {need_zoom:.1f}%，--zoom {a.zoom} 可能仍露邊；露邊時改 --zoom {math.ceil(need_zoom)}")
        vf = (f"vidstabtransform=input={ff_escape(trf)}:smoothing={smoothing}:zoom={a.zoom}:optzoom=0:"
              f"crop=keep:interpol=bicubic")
        print(f"[2/2] 套用平滑 smoothing={smoothing}{'（固定機位模式）' if a.lock else ''}、zoom={a.zoom}%")
        simple_vf(a.input, out, vf, a.preview, info["audio"])
        if a.report and not DRY:
            after = shake_report(out, a.preview, "穩定後")
            if before and after:
                print(f"位移平均 {before[0]:.2f} → {after[0]:.2f} px（降 {100 * (1 - after[0] / max(before[0], 1e-6)):.0f}%）")
    finally:
        if tmpd:
            shutil.rmtree(tmpd, ignore_errors=True)


# ---------- denoise ----------
DENOISE = {
    # 各組設定的實測 PSNR 與耗時見 footage.md 第三節 1 的表（同一次量測，這裡不另抄數字）
    # hqdn3d：空間＋時間，快、保守
    "hqdn3d": {"light": "hqdn3d=4:3:6:4.5", "medium": "hqdn3d=8:6:12:9", "heavy": "hqdn3d=12:9:20:15"},
    # nlmeans 的 s 約取雜訊 σ 的一半才有效；慢（720p 約 10–25 倍即時時間）
    "nlmeans": {"light": "nlmeans=s=3:p=5:r=9", "medium": "nlmeans=s=6:p=7:r=11", "heavy": "nlmeans=s=10:p=7:r=15"},
    # atadenoise 門檻以 σ/255 為單位（a≈2σ、b≈4σ）；純時間域，只適合靜態場景
    "atadenoise": {"light": "atadenoise=0a=0.04:0b=0.08:1a=0.04:1b=0.08:2a=0.04:2b=0.08:s=9",
                   "medium": "atadenoise=0a=0.08:0b=0.16:1a=0.08:1b=0.16:2a=0.08:2b=0.16:s=15",
                   "heavy": "atadenoise=0a=0.15:0b=0.3:1a=0.15:1b=0.3:2a=0.15:2b=0.3:s=33"},
}


def cmd_denoise(a):
    """降噪：hqdn3d 快（720p 約 1–1.5 倍即時時間）、nlmeans 慢而乾淨（約 10–25 倍）、atadenoise 時間域（靜態場景）。"""
    check_in(a.input)
    out = check_out(a.output, [a.input])
    vf = DENOISE[a.method][a.level]
    if a.method == "nlmeans" and not is_image(a.input) and not a.preview:
        print("提示：nlmeans 很慢，長片先加 --preview 10 試跑")
    if a.method == "atadenoise" and is_image(a.input):
        die("atadenoise 是時間域濾鏡，單張照片請改 --method hqdn3d 或 nlmeans")
    print(f"降噪 {a.method} / {a.level}：{vf}")
    simple_vf(a.input, out, vf, a.preview)


# ---------- sharpen ----------
def cmd_sharpen(a):
    """銳化：cas（對比自適應銳化），邊緣過衝比 unsharp 小；影片與照片皆可；放在流程最後。
    cas 對 16-bit PNG 直接有效（實測 16-bit 與先轉 rgb24 的 PSNR 36.3 對 36.3）；unsharp 對 16-bit 幾乎不動作，要先 format=rgb24（見 footage.md 三 6）。"""
    check_in(a.input)
    out = check_out(a.output, [a.input])
    if not 0 <= a.amount <= 1:
        die("--amount 必須在 0–1")
    simple_vf(a.input, out, f"cas=strength={fnum(a.amount)}", a.preview)


# ---------- deflicker ----------
def cmd_deflicker(a):
    """去閃爍：deflicker 用前後 size 格的亮度平均拉平，適合日光燈頻閃、縮時曝光跳動。"""
    check_in(a.input)
    out = check_out(a.output, [a.input])
    if is_image(a.input):
        die("deflicker 需要影片輸入")
    simple_vf(a.input, out, f"deflicker=size={a.size}:mode=am", a.preview)


# ---------- skin ----------
def skin_mask_expr(cr=155, crw=30, cb=106, cbw=20, lo=40, hi=245, gain=1.0):
    """膚色遮罩的 geq 表示式（YCbCr 三角窗：Cr 中心 155±30、Cb 中心 106±20、亮度 40–245）。
    回傳 0–255 的軟遮罩；gain 乘上強度。棕髮、木頭、磚牆也可能被抓到，用 --mask-out 檢查。"""
    return (f"255*{fnum(gain)}*clip(1-abs(cr(X,Y)-{cr})/{crw},0,1)"
            f"*clip(1-abs(cb(X,Y)-{cb})/{cbw},0,1)*between(lum(X,Y),{lo},{hi})")


def skin_sigmas(strength):
    """bilateral 的設定值：σS 15→40、σR 0.06→0.10。ffmpeg 的 bilateral 色差權重是指數型 exp(-|Δ|/(σR·255))，
    σR 才是髮際線、眉毛的暗部會不會被拉進平坦皮膚的關鍵（實測 σR 0.22 明顯滲邊、≤ 0.10 幾乎沒有）；
    σS 只決定抹得平多大的斑塊。平坦額頭低頻 std 實測見 footage.md 第三節 7。"""
    return 15 + 25 * strength, 0.06 + 0.04 * strength


MASK_BIN = 32   # 遮罩二值化門檻（0–255）：低於這個值當非皮膚，只在這種硬邊界收邊


def skin_graph(src_label, out_label, strength, mask_out_label=None, feather=4, split_sigma=3, shrink=3, mask_blur=3):
    """頻率分離柔膚的 filter_complex 片段：
    遮罩：輸入先 gblur σ=mask_blur 再用 geq 算 YCbCr 窗（畫素雜訊不會把遮罩打成破洞），另外把遮罩二值化、
    erosion 收 shrink px 後乘回軟遮罩（只在皮膚／非皮膚的硬邊界收邊，斑塊造成的遮罩凹陷不受影響），再羽化；
    低頻 = gblur(σ=split_sigma)；高頻 = 原圖 − 低頻（grainextract）；
    低頻再用 bilateral 抹平斑塊（保邊，σS／σR 見 skin_sigmas）；合回 = 低頻' + 高頻（grainmerge）；
    最後 maskedmerge 只在遮罩內替換。遮罩只用 geq 算一個平面，再 mergeplanes 複製到三個平面（快一倍）。"""
    gain = math.sqrt(strength)       # 遮罩不透明度：0.5 → 0.71
    m = skin_mask_expr(gain=gain)
    sig_s, sig_r = skin_sigmas(strength)
    g = (f"[{src_label}]format=yuv444p,split=3[s0][s1][s2];"
         f"[s1]{f'gblur=sigma={mask_blur},' if mask_blur else ''}geq=lum='{m}':cb=128:cr=128,format=gray")
    if shrink:
        g += (f",split=2[ms][mb];[mb]lut=c0='if(gt(val,{MASK_BIN}),255,0)',{','.join(['erosion'] * shrink)}[mbe];"
              f"[ms][mbe]blend=all_mode=multiply")
    g += (f",gblur=sigma={feather},split=3[m0][m1][m2];"
          f"[m0][m1][m2]mergeplanes=0x001020:yuv444p,split=2[mask][maskv];"
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
    out = check_out(a.output, [a.input])
    if not 0 <= a.strength <= 1:
        die("--strength 必須在 0–1")
    img = is_image(a.input)
    info = None if img else probe(a.input)
    has_audio = bool(info and info["audio"])
    mask_label = "maskout" if a.mask_out else None
    graph = skin_graph("0:v", "out", a.strength, mask_label)
    graph += ";[out]format=" + ("rgb24" if img and out.lower().endswith(".png") else "yuv420p") + "[fin]"
    cmd = ffmpeg_base() + in_args(a.input, a.preview) + ["-filter_complex", graph, "-map", "[fin]"]
    if has_audio:
        cmd += ["-map", "0:a:0"]
    cmd += enc_args(out, has_audio) + [out]
    if a.mask_out:
        mask_out = check_out(a.mask_out, [a.input])
        cmd += ["-map", "[maskout]"] + enc_args(mask_out, False) + [mask_out]
    sig_s, sig_r = skin_sigmas(a.strength)
    if not img and not a.preview:
        print("提示：skin 約 4–6 倍即時時間（720p，含遮罩輸出），長片先加 --preview 10 試跑")
    if a.strength > 0.7:
        print("提示：strength > 0.7 會在髮際線、眉毛旁邊滲出陰影，正常範圍 0.3–0.5；請看 100% 放大的額頭")
    print(f"柔膚 strength={a.strength}（遮罩：輸入 gblur σ3 → Cr 155±30、Cb 106±20、Y 40–245 → 硬邊界收 3 px → 羽化 σ4；"
          f"bilateral σS={fnum(sig_s)} σR={fnum(sig_r)}）")
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
    """用 geq 產生 0–255 的光圖（PNG）：高斯徑向 key 光 + 均勻 fill + 單邊線性 rim。
    key 的第三個數是高斯 σ（佔畫寬比），不是半徑：光斑看得見的範圍約 2σ（半徑）、強度在 σ 處剩 61%。"""
    terms = []
    if key:
        x, y, sg, i = key
        cx, cy, sp = x * w, y * h, max(sg * w, 1)
        terms.append(f"{fnum(i)}*exp(-((X-{fnum(cx)})^2+(Y-{fnum(cy)})^2)/(2*{fnum(sp)}^2))")
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
    """後製虛擬打光：光圖（key／fill／rim）疊到畫面上，再加暈影與色溫；至少 key 與 vignette 可單獨用。
    預設 --mode masked：光圖先乘上原圖亮度（multiply）再 screen，黑位不動、亮的地方才被打亮（光 ∝ 反射率）；
    --mode screen 直接 screen，會把黑背景抬成灰，只在背景本來就不是黑的時候用；
    --mode gain：輸出 ＝ 原圖 × (1 + 光圖)，三個色版等比放大，膚色 R/G 不變（screen 疊中性白光會把膚色沖淡：
    實測臉頰 R/G 1.40 → 1.25），代價是亮部先爆 R，只給臉本來偏暗（臉頰 Y < 140）的素材，跑完量 YMAX < 250。"""
    check_in(a.input)
    out = check_out(a.output, [a.input])
    light_out = check_out(a.light_out, [a.input]) if a.light_out else None
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
        post.append(f"vignette=angle={fnum(a.vignette * math.pi / 4)}")  # 0.5（PI/8）角落剩約 70–75%、1（PI/4）約 23–28%
    if a.temp:
        post.append(f"colortemperature=temperature={int(6500 + a.temp)}:pl=1")  # 負=變暖、正=變冷
    has_audio = info["audio"]
    out_fmt = "rgb24" if img and out.lower().endswith(".png") else "yuv420p"
    cmd = ffmpeg_base() + in_args(a.input, a.preview)
    tmpd = None
    if key or a.fill or rim:
        if light_out:
            lm = light_out
        else:
            tmpd = tempfile.mkdtemp(prefix="relight_")
            lm = os.path.join(tmpd, "light.png")
        print(f"[1/2] 產生光圖 {w}x{h} → {lm}" + ("" if light_out else "（暫存，完成後刪除；要留下檢查加 --light-out）"))
        build_light_map(w, h, key, a.fill, rim, lm)
        if a.mode == "masked":
            graph = (f"[0:v]format=gbrp,split=2[base][b2];[b2]format=gray,format=gbrp[lum];[1:v]format=gbrp[lm];"
                     f"[lum][lm]blend=all_mode=multiply:shortest=1[lm2];"
                     f"[base][lm2]blend=all_mode=screen:all_opacity={fnum(a.opacity)}[lit];")
            desc = "光圖 × 原圖亮度 → screen（黑位不動）"
        elif a.mode == "gain":
            # 原圖 × 光圖（每個色版各自乘）再加回原圖：out = 原圖 × (1 + 光圖)，比例不變所以膚色不會變淡
            graph = (f"[0:v]format=gbrp,split=2[base][b2];[1:v]format=gbrp[lm];"
                     f"[b2][lm]blend=all_mode=multiply:shortest=1[prod];"
                     f"[base][prod]blend=all_mode=addition:all_opacity={fnum(a.opacity)}[lit];")
            desc = "原圖 × (1 + 光圖)（等比增益，膚色比例不變，亮部會先爆）"
        else:
            graph = (f"[0:v]format=gbrp[base];[1:v]format=gbrp[lm];"
                     f"[base][lm]blend=all_mode=screen:all_opacity={fnum(a.opacity)}:shortest=1[lit];")
            desc = "直接 screen（會抬黑位）"
        graph += f"[lit]{','.join(post + ['format=' + out_fmt])}[fin]"
        cmd += ["-loop", "1", "-i", lm, "-filter_complex", graph, "-map", "[fin]"]
        print(f"[2/2] 疊加 {desc}，opacity {a.opacity}" + (f" + {' + '.join(post)}" if post else ""))
    else:
        cmd += ["-vf", ",".join(post + ["format=" + out_fmt])]
    if has_audio:
        cmd += ["-map", "0:a:0"]
    cmd += enc_args(out, has_audio) + [out]
    run(cmd)
    if tmpd:
        shutil.rmtree(tmpd, ignore_errors=True)


# ---------- match ----------
KEYS = ["YAVG", "UAVG", "VAVG", "YMIN", "YMAX", "YLOW", "YHIGH", "SATAVG"]


def measure(path, preview, label, pre=""):
    """用 signalstats 每秒取樣（影片 fps=1）量 YAVG／UAVG／VAVG／YMIN／YMAX／YLOW／YHIGH／SATAVG，各格平均。
    signalstats 以輸入的原生位深回報（10-bit 影片 0–1023、16-bit PNG 0–65535），所以先 format 成 8-bit
    （影片 yuv420p、照片 yuv444p），後面以 0–255 單位、128 為軸的計算才成立。
    pre：先套在量測鏈前面的濾鏡（cmd_match 用它量「去偏色後」的 SATAVG）。統計檔寫在 mkdtemp 的私有目錄。"""
    tmpd = tempfile.mkdtemp(prefix="footage_stats_")
    statf = os.path.join(tmpd, "stats.txt")
    info = probe(path)
    if info["bits"] > 8:
        print(f"提示：{path} 是 {info['pix_fmt']}（{info['bits']}-bit），量測與套用前先轉成 8-bit")
    vf = ("format=yuv444p," if is_image(path) else "format=yuv420p,fps=1,") + (pre + "," if pre else "") + \
         f"signalstats,metadata=print:file={ff_escape(statf)}"
    try:
        run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostats"] + in_args(path, preview) +
            ["-vf", vf, "-f", "null", "-"])
        if DRY:
            return {k: 0.0 for k in KEYS}
        vals = {k: [] for k in KEYS}
        for line in open(statf, encoding="utf-8", errors="ignore"):
            m = re.match(r"lavfi\.signalstats\.(\w+)=([-\d.]+)", line.strip())
            if m and m.group(1) in vals:
                vals[m.group(1)].append(float(m.group(2)))
    finally:
        shutil.rmtree(tmpd, ignore_errors=True)
    if not vals["YAVG"]:
        die(f"量不到 {path} 的 signalstats 數值")
    r = {k: (sum(v) / len(v) if v else 0.0) for k, v in vals.items()}
    print(f"[{label}] " + " ".join(f"{k}={r[k]:.1f}" for k in KEYS) + f"（取樣 {len(vals['YAVG'])} 格）")
    return r


MATCH_TOL = 3.0     # Y／U／V 平均值殘差都 ≤ 3（0–255 單位）
SAT_TOL = 1.5       # SATAVG 殘差 ≤ 1.5
MATCH_PASSES = 3    # 每次都從 SRC 重跑（不重複壓縮），最多三次


def clamp(x, lo, hi):
    return min(max(x, lo), hi)


def cmd_match(a):
    """顏色匹配（規格寫 eq／colorbalance：對比與飽和用 eq，平均值位移改用 lutyuv 而不是 colorbalance，原因見 footage.md 三 10）：
    量 SRC 與 REF 的 signalstats → eq 補對比／飽和（乘法），lutyuv 補 Y／U／V 平均值位移（加法）
    → 量 OUT 的殘差（Y／U／V 平均值與 SATAVG）；超出門檻就把殘差加回位移、飽和倍率乘上 REF/OUT 的 SATAVG 比，
    從 SRC 再跑一次（最多三次，不重複壓縮）。
    飽和倍率的分母不能直接用 SRC 的 SATAVG：SATAVG 是色度向量長度 hypot(U−128, V−128) 的平均，SRC 整體偏色時
    向量被偏色撐長（實測純偏色片 18.3，去偏色後 10.4，REF 10.5），直接相除會把輸出壓得比 REF 淡一半，而 Y／U／V 平均值
    殘差看不出來；所以先把 SRC 的 U／V 平均移到 REF 的位置再量一次 SATAVG 當分母。
    不用 eq 的 brightness（量化成 1% 一格、每格 2.5 級，實測短少 15–30%）也不用 colorbalance（權重隨亮度變，
    中低調素材幾乎不動）。濾鏡鏈最前面先 format 成 8-bit（影片 yuv420p、照片 yuv444p），與 measure() 的刻度一致。"""
    check_in(a.input)
    check_in(a.ref)
    out = check_out(a.output, [a.input, a.ref])
    s = measure(a.input, a.preview, "SRC")
    r = measure(a.ref, a.preview, "REF")
    if DRY:
        print("（--dry-run 無量測值，略過計算）")
        return
    # 對比用 YLOW／YHIGH（10%／90% 分位）比 YMIN／YMAX 穩，極值常被單一畫素帶偏
    span_s = max(s["YHIGH"] - s["YLOW"], 1.0)
    span_r = max(r["YHIGH"] - r["YLOW"], 1.0)
    contrast = clamp(span_r / span_s, 0.6, 1.6)
    # 飽和：先只移 U／V 平均值（去偏色）量一次 SATAVG，再算倍率
    dU0, dV0 = r["UAVG"] - s["UAVG"], r["VAVG"] - s["VAVG"]
    sat_src = s["SATAVG"]
    if abs(dU0) + abs(dV0) > 1.0:
        sat_src = measure(a.input, a.preview, "SRC 去偏色", pre=f"lutyuv=y=val:u=val{dU0:+.1f}:v=val{dV0:+.1f}")["SATAVG"]
    sat = 1.0
    if sat_src > 1 and r["SATAVG"] > 1:
        sat = clamp(r["SATAVG"] / sat_src, 0.5, 2.0)
    print(f"目標：ΔY {r['YAVG'] - s['YAVG']:+.1f}、對比 x{contrast:.3f}、飽和 x{sat:.3f}"
          f"（SATAVG：SRC {s['SATAVG']:.1f} → 去偏色後 {sat_src:.1f}，REF {r['SATAVG']:.1f}）")
    has_audio = (not is_image(a.input)) and probe(a.input)["audio"]
    base, ext = os.path.splitext(out)
    tmp = base + ".pass" + ext          # 每次都從 SRC 重跑寫到這裡，最後改名成輸出
    OUTPUTS.append((tmp, tmp))
    fmt = "yuv444p" if is_image(a.input) else "yuv420p"
    corr = [0.0, 0.0, 0.0]              # 用殘差累積的位移修正（模型算不到的部分：clip、取樣差）
    for n in range(1, MATCH_PASSES + 1):
        # eq 的 contrast／saturation 以 128 為軸：Y' = (Y-128)*c + 128、U' = (U-128)*s + 128；縮放後再算要補的位移
        dY = r["YAVG"] - ((s["YAVG"] - 128) * contrast + 128) + corr[0]
        dU = r["UAVG"] - ((s["UAVG"] - 128) * sat + 128) + corr[1]
        dV = r["VAVG"] - ((s["VAVG"] - 128) * sat + 128) + corr[2]
        vf = (f"format={fmt},eq=contrast={fnum(contrast)}:saturation={fnum(sat)},"
              f"lutyuv=y=val{dY:+.1f}:u=val{dU:+.1f}:v=val{dV:+.1f}")
        print(f"[第 {n} 次] 套用：{vf}")
        simple_vf(a.input, tmp, vf, a.preview, has_audio, overwrite=True)
        o = measure(tmp, a.preview, f"OUT{n}")
        eY, eU, eV, eS = (o["YAVG"] - r["YAVG"], o["UAVG"] - r["UAVG"], o["VAVG"] - r["VAVG"],
                          o["SATAVG"] - r["SATAVG"])
        ok = max(abs(eY), abs(eU), abs(eV)) <= MATCH_TOL and abs(eS) <= SAT_TOL
        print(f"殘差（OUT−REF）：ΔY {eY:+.1f}、ΔU {eU:+.1f}、ΔV {eV:+.1f}、ΔSAT {eS:+.1f}" +
              ("（Y／U／V |Δ| ≤ 3、SATAVG |Δ| ≤ 1.5，肉眼幾乎分不出）" if ok else "（超出門檻）"))
        if ok:
            break
        if n < MATCH_PASSES:
            corr = [corr[0] - eY, corr[1] - eU, corr[2] - eV]
            if abs(eS) > SAT_TOL and o["SATAVG"] > 1:
                sat = clamp(sat * r["SATAVG"] / o["SATAVG"], 0.5, 2.0)
                print(f"飽和倍率改成 x{sat:.3f}（REF/OUT 的 SATAVG 比），位移重算，從 SRC 再跑一次")
            else:
                print("用殘差修正位移，從 SRC 再跑一次")
        else:
            print(f"提示：{MATCH_PASSES} 次後仍超出門檻，通常是兩支的範圍被 clip（極亮或極暗）或色度分佈差太多；"
                  "拿 OUT 當 SRC 再跑或改手動 lutyuv")
    os.replace(tmp, out)


# ---------- photo ----------
def read_exif_segment(jpg):
    """讀出 JPEG 的 APP1 EXIF 區段（含 FFE1 與長度），沒有就回 None。"""
    with open(jpg, "rb") as f:
        data = f.read()
    if data[:2] != b"\xff\xd8":
        return None
    i = 2
    while i + 4 <= len(data) and data[i] == 0xFF:
        marker, ln = data[i + 1], int.from_bytes(data[i + 2:i + 4], "big")
        if marker == 0xE1 and data[i + 4:i + 10] == b"Exif\x00\x00":
            return data[i:i + 2 + ln]
        if marker in (0xDA, 0xD9):
            break
        i += 2 + ln
    return None


def write_exif_segment(jpg, seg):
    """把 EXIF 區段插到輸出 JPEG 的 SOI 之後。"""
    with open(jpg, "rb") as f:
        data = f.read()
    if data[:2] != b"\xff\xd8":
        return False
    with open(jpg, "wb") as f:
        f.write(data[:2] + seg + data[2:])
    return True


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
    out = check_out(a.output, [a.input])
    p = PRESETS[a.preset]
    skin = p["skin"] if a.skin is None else a.skin
    sharpen = p["sharpen"] if a.sharpen is None else a.sharpen
    if a.strip_exif and not DRY:
        # identify 的 %[profiles] 列出嵌入的描述檔名稱（exif、icc、xmp…）；-strip 會把 ICC 一起丟掉但不做色彩轉換
        prof = subprocess.run(["identify", "-format", "%[profiles]", a.input], text=True, capture_output=True).stdout
        if "icc" in prof.lower() or "icm" in prof.lower():
            print("提示：輸入嵌有 ICC 色彩描述檔（手機照片常是 Display P3），-strip 只丟掉它、不轉換色彩，輸出會略偏色；"
                  "要正確轉成 sRGB 先 convert in.jpg -profile sRGB.icc tmp.jpg 再丟進來（需要 sRGB.icc 檔，本機沒有、未測）")
    tmpd = tempfile.mkdtemp(prefix="photo_")
    t1 = os.path.join(tmpd, "step1.png")
    t2 = os.path.join(tmpd, "step2.png")
    # 第一步：ImageMagick
    c1 = ["convert", a.input]
    if a.strip_exif:
        c1 += ["-auto-orient", "-strip"]   # 畫素轉正後再去掉含 Orientation 的 EXIF，避免看圖軟體二次旋轉
    else:
        print("提示：--keep-exif 會保留 GPS，且不做 -auto-orient（EXIF 的方向標籤照舊）")
    if a.exposure:
        # 線性光域乘 2^EV，接近相機曝光；sRGB→RGB(線性)→sRGB
        c1 += ["-colorspace", "RGB", "-evaluate", "Multiply", fnum(2 ** a.exposure), "-colorspace", "sRGB"]
    if p["contrast"]:
        c1 += ["-sigmoidal-contrast", p["contrast"]]
    if p["sat"] != 100:
        c1 += ["-modulate", f"100,{p['sat']}"]
    if a.max_size:
        c1 += ["-filter", "Lanczos", "-resize", f"{a.max_size}x{a.max_size}>"]   # -filter 是設定，要在 -resize 之前才生效
    c1 += ["-depth", "8", t1]
    print("[1/3] ImageMagick：" + ("轉正、去 EXIF／GPS" if a.strip_exif else "保留 EXIF") +
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
    ext = os.path.splitext(out)[1].lower()
    if ext in (".jpg", ".jpeg", ".webp"):
        c3 += ["-quality", str(a.quality)]
    c3 += [out]
    print(f"[3/3] 輸出 {a.output}（quality {a.quality}）")
    run(c3)
    shutil.rmtree(tmpd, ignore_errors=True)
    if not a.strip_exif and not DRY:
        in_jpg = os.path.splitext(a.input)[1].lower() in (".jpg", ".jpeg")
        out_jpg = ext in (".jpg", ".jpeg")
        seg = read_exif_segment(a.input) if in_jpg else None
        if seg and out_jpg and write_exif_segment(out, seg):
            print(f"已把來源 EXIF（{len(seg)} bytes）寫回輸出")
        else:
            print("提示：只支援 JPEG→JPEG 保留 EXIF，這次沒有寫回")


# ---------- kenburns ----------
EASE = {
    "linear": "P",
    "out": "(1-(1-P)*(1-P))",
    "inOut": "if(lt(P,0.5),2*P*P,1-pow(-2*P+2,2)/2)",
}


def cmd_kenburns(a):
    """Ken Burns：zoompan 做緩動推軌；--from／--to 是 x,y,zoom（x、y 為視窗中心的 0–1 相對座標，zoom ≥ 1）。"""
    check_in(a.input)
    out = check_out(a.output, [a.input])
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
    run(ffmpeg_base() + ["-i", a.input, "-vf", vf, "-frames:v", str(D)] + enc_args(out, False) + [out])


# ---------- upscale ----------
def cmd_upscale(a):
    """放大：lanczos（銳）／spline（柔）／placebo（libplacebo，需要 Vulkan，本機未測）；之後視需要再 sharpen。"""
    check_in(a.input)
    out = check_out(a.output, [a.input])
    m = re.match(r"^(-?\d+)x(-?\d+)$", a.size)
    if not m:
        die("--size 格式：WxH（可用 -2 自動算另一邊，例如 3840x-2）")
    W, H = m.group(1), m.group(2)
    if a.method == "placebo":
        h = subprocess.run(["ffmpeg", "-hide_banner", "-h", "filter=libplacebo"], text=True, capture_output=True)
        if h.returncode != 0 or "Unknown filter" in h.stdout + h.stderr:
            die("本機 ffmpeg 沒有 libplacebo 濾鏡，改用 --method lanczos 或 spline")
        vf = f"libplacebo=w={W}:h={H}:upscaler=ewa_lanczos,format=yuv420p"
        print("提示：libplacebo 需要 Vulkan 裝置（本機沒有，未測）；失敗請改 --method lanczos")
        r = simple_vf(a.input, out, vf, a.preview, check=False)
        if r is not None and r.returncode != 0:
            tail = (r.stderr.strip().splitlines() or ["無訊息"])[-1]
            cleanup_outputs()
            die(f"libplacebo 放大失敗（exit {r.returncode}：{tail}）；通常是沒有 Vulkan 裝置，改用 --method lanczos 或 spline")
        return
    vf = f"scale={W}:{H}:flags={a.method}"
    simple_vf(a.input, out, vf, a.preview)


# ---------- slowmo ----------
def cmd_slowmo(a):
    """慢動作：--factor 2|4。
    不加 --interp：只拉長時間（setpts）。來源 ≥ 48fps（拍 60／120 的片）時輸出 fps ÷ factor（下限 24），每格都是實拍格，
    是真慢動作（60fps ÷ 2 → 30fps）；來源 < 48fps 時保留來源 fps，每格重複 factor 次。
    加 --interp：minterpolate 先補成 fps × factor 再放慢，輸出維持來源 fps（720p 約 25 倍即時時間）。"""
    check_in(a.input)
    out = check_out(a.output, [a.input])
    if is_image(a.input):
        die("slowmo 需要影片輸入")
    info = probe(a.input)
    fps = info["fps"]
    out_fps = fps
    if a.interp:
        vf = (f"minterpolate=fps={fnum(fps * a.factor)}:mi_mode=mci:mc_mode=aobmc:me_mode=bidir:vsbmc=1,"
              f"setpts={a.factor}*PTS")
        how = "補格"
        if not a.preview:
            print("提示：minterpolate 很慢，長片先加 --preview 5 試跑")
    else:
        vf = f"setpts={a.factor}*PTS"
        if fps >= 48:
            out_fps = max(fps / a.factor, 24.0)
            if fps / a.factor >= 24:
                how = f"真慢動作：來源 {fnum(fps)} fps ÷ {a.factor}，每格都是實拍格、不重複"
            else:
                how = f"來源 {fnum(fps)} fps ÷ {a.factor} = {fnum(fps / a.factor)} 低於 24，輸出 24 fps、部分格重複"
        else:
            how = f"重複格：來源 {fnum(fps)} fps 低於 48，每格重複 {a.factor} 次；要平順改 --interp 或用 60／120fps 拍"
    af = ",".join(["atempo=0.5"] * int(math.log2(a.factor))) if info["audio"] else None
    print(f"慢動作 x{a.factor}（{how}；輸出 {fnum(out_fps)} fps）")
    cmd = ffmpeg_base() + in_args(a.input, a.preview) + ["-vf", vf, "-r", fnum(out_fps)]
    if info["audio"]:
        cmd += ["-map", "0:v:0", "-map", "0:a:0"]
    cmd += enc_args(out, info["audio"], af) + [out]
    run(cmd)


# ---------- 選項 ----------
def translate_argparse(msg):
    """把 argparse 的英文錯誤翻成繁中；對不上的原樣回傳。"""
    m = re.match(r"argument (\S+): invalid choice: (.+?) \(choose from (.+)\)$", msg)
    if m:
        name = "子命令" if m.group(1) in ("cmd", "子命令") or m.group(1).startswith("{") else f"引數 {m.group(1)} "
        choices = "、".join(c.strip().strip("'\"") for c in m.group(3).split(","))
        return f"{name}只能是 {choices}，不能是 {m.group(2).strip(chr(39))}"
    m = re.match(r"argument (\S+): invalid (\w+) value: (.+)$", msg)
    if m:
        kind = {"int": "整數", "float": "數字"}.get(m.group(2), m.group(2))
        return f"引數 {m.group(1)} 要是{kind}，不能是 {m.group(3)}"
    m = re.match(r"argument (\S+): expected one argument$", msg)
    if m:
        return f"引數 {m.group(1)} 後面要接一個值"
    m = re.match(r"the following arguments are required: (.+)$", msg)
    if m:
        missing = ", ".join("子命令" if x.strip() in ("cmd",) or x.strip().startswith("{") else x.strip()
                            for x in m.group(1).split(","))
        return f"缺少必要引數：{missing}"
    m = re.match(r"unrecognized arguments: (.+)$", msg)
    if m:
        return f"不認識的引數：{m.group(1)}（用 -h 看可用選項）"
    return msg


class Parser(argparse.ArgumentParser):
    """argparse 的錯誤改印繁中（子命令用同一個類別：add_subparsers 預設 parser_class 就是自己的類別）。"""

    def error(self, message):
        self.print_usage(sys.stderr)
        die(translate_argparse(message), 2)


def build_parser():
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("-o", "--output", required=True, help="輸出檔")
    common.add_argument("-y", dest="overwrite", action="store_true", help="覆寫輸出")
    common.add_argument("--dry-run", action="store_true", help="只印指令不執行")
    common.add_argument("--preview", type=float, metavar="秒", help="只處理前 N 秒（影片）")

    p = Parser(description="實拍照片與影片精修 CLI（配方見 references/footage.md）")
    sub = p.add_subparsers(dest="cmd", required=True, metavar="子命令")

    s = sub.add_parser("stabilize", parents=[common], help="vidstab 兩段式穩定")
    s.add_argument("input")
    s.add_argument("--strength", type=int, choices=[1, 2, 3], default=2, help="1 輕 / 2 中 / 3 強（預設 2）")
    s.add_argument("--zoom", type=float, default=5, help="放大 %% 避免黑邊（0–10，預設 5）")
    s.add_argument("--lock", action="store_true", help="固定機位模式（smoothing=0，把所有位移都抵銷；有運鏡的片不要用）")
    s.add_argument("--report", action="store_true", help="穩定後再量一次位移，印前後比較")
    s.add_argument("--keep-trf", dest="keep_trf", action="store_true",
                   help="把 vidstabdetect 的 transforms 檔留在輸出旁（OUT.trf）；預設寫暫存目錄、完成後刪除")
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
    s.add_argument("--strength", type=float, default=0.5, help="0–1，預設 0.5；正常範圍 0.3–0.5，>0.7 髮際線旁會滲出陰影")
    s.add_argument("--mask-out", metavar="mask.mp4", help="另存遮罩影片／圖片供檢查")
    s.set_defaults(fn=cmd_skin)

    s = sub.add_parser("relight", parents=[common], help="後製虛擬打光")
    s.add_argument("input")
    s.add_argument("--key", metavar="X,Y,R,強度", help="徑向主光：中心 0–1 相對座標、R 以高斯 σ 解釋（佔畫寬比，光斑看得見的範圍約 2σ；特寫 0.1–0.15、半身 0.15–0.25）、強度 0–1，例 0.42,0.4,0.14,0.6")
    s.add_argument("--fill", type=float, default=0.0, help="均勻加光 0–1（內部乘 0.35 寫進光圖；預設 masked 模式下亮處被提得多、黑位不動，要抬暗部改 --mode screen 或 eq=brightness）")
    s.add_argument("--rim", metavar="方向,強度", help="單邊線性光：left|right|top|bottom,強度，例 right,0.4")
    s.add_argument("--temp", type=float, default=0.0, help="色溫偏移 K：負=變暖、正=變冷，例 -800")
    s.add_argument("--vignette", type=float, default=0.0, help="暈影 0–1（0.5＝angle PI/8，角落剩約七成亮；1＝PI/4，剩約兩成多）")
    s.add_argument("--mode", choices=["masked", "screen", "gain"], default="masked",
                   help="masked（預設）：光圖先乘原圖亮度再 screen，黑位不動；screen：直接 screen，會把黑背景抬成灰；"
                        "gain：原圖 × (1 + 光圖)，膚色 R/G 不變但亮部先爆，只給偏暗的臉")
    s.add_argument("--opacity", type=float, default=1.0, help="光圖不透明度 0–1")
    s.add_argument("--light-out", metavar="light.png", help="把光圖另存下來檢查（預設寫在暫存目錄、完成後刪除）")
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
    s.add_argument("--max-size", type=int, metavar="畫素", help="長邊超過就縮到這個畫素")
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
    for k in ("input", "output", "ref", "mask_out", "light_out"):   # 含冒號的相對路徑轉絕對路徑（見 safe_path）
        if getattr(a, k, None):
            setattr(a, k, safe_path(getattr(a, k)))
    if DRY:
        print("（--dry-run：只印指令，不執行）")
    a.fn(a)
    if not DRY:
        finalize_outputs()
        print(f"完成：{a.output}")


if __name__ == "__main__":
    main()
