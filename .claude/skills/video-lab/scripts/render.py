#!/usr/bin/env python3
"""把定義了 window.render(t) 的 HTML 逐格截圖，合成影片。

  python render.py page.html -o out/title.mp4 --dur 5
  python render.py page.html -o out/title.mov --dur 5 --alpha      # ProRes 4444 透明
  python render.py page.html -o out/title.webm --dur 5 --alpha     # VP9 透明
  python render.py page.html -o out/sheet.png --sheet 0.5,1.5,3    # 輸出指定時間點的預覽拼圖（每格標秒數）
  python render.py page.html -o out/mv.mp4 --dur 10 --from 30 --audio song.mp3   # 從第 30 秒起算，音軌同步偏移
  python render.py page.html -o out/mv.mp4 --dur 10 --data audio=data/audio.json --data lyrics=data/lyrics.json
  python render.py page.html -o out/mv.mp4 --dur 10 --samples 6 --shutter 0.5     # 子格平均動態模糊（Canvas 2D）
  python render.py page.html -o out/mv4k.mp4 --dur 10 --scale 2                   # 3840×2160（deviceScaleFactor 2）
  python render.py page.html -o out/cuts.png --cuts                                # 讀 window.CUTS 出剪點拼圖
  python render.py page.html -o out/mv.mp4 --dur 10 --dump-cuts out/mv.cuts.json   # 另把 window.CUTS 寫成 JSON 給 qa.py --cuts
  python render.py page.html -o out/mv.mp4 --dur 10 --profile                      # 印每格 render／截圖毫秒數

頁面約定：
  - window.render(t) 把第 t 秒的畫面畫出來（可以是 async）。畫面必須是 t 的純函式：同一個 t 永遠畫出同一張圖。
  - 可選 window.DURATION（秒），沒給 --dur 時使用；可選 window.CUTS = [秒, ...] 給 --cuts 用。
  - --data key=path 會在頁面載入前注入 window.DATA = {key: JSON, ...}（例如 window.DATA.audio、window.DATA.lyrics）。
  - 另注入 window.RENDER_SCALE（--scale）與 window.RENDER_FPS（--fps），頁面要做真 4K 時可依 RENDER_SCALE 放大 canvas 畫素。
  - --samples N：在 shutter×(1/fps) 內以該格時間為中心取 N 個子格，各呼叫 render(t_k) 後把主 canvas
    （window.CANVAS 或 document.querySelector('canvas')）的畫素平均再截圖；只支援 Canvas 2D。N=1 走原路徑。
  - --scale 2：deviceScaleFactor=2，頁面仍以 --w×--h 的 CSS 版面排版，截圖與影片為實體尺寸（1920×1080 → 3840×2160）。
    頁面 canvas 若仍是 1920×1080 畫素，輸出只是放大；要真 4K 請頁面依 window.RENDER_SCALE 放大 canvas.width/height。
  - 截圖走 CDP（Chrome DevTools Protocol）Page.captureScreenshot 的 optimizeForSpeed（PNG 不壓縮），畫素與 page.screenshot
    完全相同、--alpha 與 --scale 也相同；1080p 每格截圖約 60–180 ms（內容越雜越慢），page.screenshot 要 100–490 ms。
  - --cuts：每個剪點出前 2 格、該格、後 2 格（一列 5 格，該格標籤加 <），看剪點有沒有差一格。
  - --dump-cuts PATH：把 window.CUTS 寫成 {"offset": --from, "fps": --fps, "cuts": [秒, ...]}（歌曲絕對秒），
    可與影片輸出同一次跑；qa.py --cuts 直接吃這個檔。
  - 音軌編碼依副檔名：.webm 用 libopus 128k（WebM 不收 AAC），其他用 aac 192k；--alpha 只接受 .mov／.webm，
    .mp4 不支援透明會直接報錯。render(t) 丟例外、pageerror 或 ffmpeg 失敗時刪掉寫到一半的輸出檔再以非 0 結束。
  - 頁面的 console.error 與未捕捉的例外（pageerror）會印到 stderr；有 pageerror 或 render(t) 丟例外時以非 0 結束。
  - --audio：先用 ffprobe 查音訊長度；--from 之後剩下的音訊比影片短時印警告，並用 apad 補靜音到影片長度（不截短影片）。
  - --profile：每格印 render(t) 與截圖各花幾毫秒到 stderr，最後印平均與最大值；用來找頁面的效能瓶頸。
  - 拼圖（--sheet／--cuts）每格下方加 28 px 黑條放標籤，不壓到畫面；標籤超過黑條寬度（中文算 2 個單位、共 42 單位）
    會截斷加「…」，不會被下一格蓋掉。
"""
import argparse
import base64
import json
import os
import subprocess
import sys
import time
import unicodedata

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import sync_playwright

# 子格平均：N 個子格的 RGBA 累加到 Float32Array，平均後寫回主 canvas
SAMPLE_JS = r"""
window.__mvSample = async function (t, n, shutter, fps) {
  const cv = window.CANVAS || document.querySelector('canvas');
  if (!cv) throw new Error('--samples 需要頁面有 <canvas>（或指定 window.CANVAS）');
  const ctx = cv.getContext('2d');
  if (!ctx) throw new Error('--samples 只支援 Canvas 2D 頁面（getContext("2d") 失敗）');
  const W = cv.width, H = cv.height, N = W * H * 4;
  const acc = new Float32Array(N);
  for (let k = 0; k < n; k++) {
    const tk = t + (shutter / fps) * ((k + 0.5) / n - 0.5);   // 以 t 為中心、分佈在 shutter 內
    await window.render(tk);
    const d = ctx.getImageData(0, 0, W, H).data;
    for (let i = 0; i < N; i++) acc[i] += d[i];
  }
  const out = ctx.createImageData(W, H), o = out.data;
  for (let i = 0; i < N; i++) o[i] = acc[i] / n;
  ctx.putImageData(out, 0, 0);
};
"""


def encoder_args(out, alpha):
    ext = os.path.splitext(out)[1].lower()
    if ext == ".mov" and alpha:
        return ["-c:v", "prores_ks", "-profile:v", "4444", "-pix_fmt", "yuva444p10le"]
    if ext == ".webm":
        return ["-c:v", "libvpx-vp9", "-pix_fmt", "yuva420p" if alpha else "yuv420p", "-b:v", "8M"]
    return ["-c:v", "libx264", "-crf", "16", "-preset", "medium", "-pix_fmt", "yuv420p", "-movflags", "+faststart"]


def audio_args(out):
    """音軌編碼依容器：WebM 只收 Opus／Vorbis（給 aac 會 Could not write header），其他用 AAC。"""
    if os.path.splitext(out)[1].lower() == ".webm":
        return ["-c:a", "libopus", "-b:a", "128k"]
    return ["-c:a", "aac", "-b:a", "192k"]


def remove_partial(path):
    """失敗時刪掉寫到一半的輸出檔，免得下游（qa.py、concat）誤用；回傳是否有刪。"""
    if path and os.path.exists(path):
        try:
            os.remove(path)
            return True
        except OSError:
            pass
    return False


def probe_duration(path):
    """用 ffprobe 取音訊檔長度（秒）；取不到回傳 None。"""
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path],
                       capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except ValueError:
        return None


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


def sheet_filter(labels, cols, cmd_path):
    """把逐格標籤寫成 sendcmd 指令檔；回傳拼圖用的 -vf 字串（輸入 -framerate 1，第 i 張在第 i 秒）。"""
    with open(cmd_path, "w", encoding="utf-8") as f:
        for i, lab in enumerate(labels):
            f.write(f"{i}.0 drawtext reinit 'text={safe_label(fit_label(lab))}';\n")
    rows = (len(labels) + cols - 1) // cols
    # 先縮到 480 寬、下方補 28 px 黑條，標籤畫在黑條上（不壓到畫面）
    return (f"sendcmd=f={cmd_path},scale=480:-2,pad=iw:ih+28:0:0:black,"
            f"drawtext=text='':x=8:y=h-24:fontsize=20:fontcolor=white,"
            f"tile={cols}x{rows}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("html")
    ap.add_argument("-o", "--out", required=True)
    ap.add_argument("--w", type=int, default=1920)
    ap.add_argument("--h", type=int, default=1080)
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--dur", type=float)
    ap.add_argument("--from", dest="t0", type=float, default=0.0)
    ap.add_argument("--alpha", action="store_true", help="透明背景（.mov 或 .webm）")
    ap.add_argument("--audio", help="要合進去的音訊檔（從 --from 秒起）")
    ap.add_argument("--sheet", help="逗號分隔的時間點，輸出預覽拼圖而非影片")
    ap.add_argument("--scale", type=int, default=1, help="deviceScaleFactor；2 = 3840×2160，版面仍 1920×1080")
    ap.add_argument("--samples", type=int, default=1, help="每格的子格數（動態模糊），1 = 不做")
    ap.add_argument("--shutter", type=float, default=0.5, help="快門開角：子格分佈在 shutter×(1/fps) 內")
    ap.add_argument("--data", action="append", default=[], metavar="KEY=PATH", help="注入 window.DATA[KEY] = JSON")
    ap.add_argument("--cuts", action="store_true", help="讀頁面 window.CUTS 輸出剪點拼圖（每個剪點前後各 2 格，一列 5 格）")
    ap.add_argument("--profile", action="store_true", help="每格印 render／截圖毫秒數到 stderr")
    ap.add_argument("--dump-cuts", dest="dump_cuts", metavar="PATH",
                    help="把頁面 window.CUTS 寫成 JSON（{offset,fps,cuts}）給 qa.py --cuts 用；可與影片輸出同時")
    a = ap.parse_args()
    if a.scale < 1 or a.samples < 1 or a.fps < 1:
        ap.error("--scale、--samples、--fps 都要 ≥ 1")
    out_ext = os.path.splitext(a.out)[1].lower()
    if a.alpha and not (a.sheet or a.cuts) and out_ext not in (".mov", ".webm"):
        ap.error(f"--alpha 需要 .mov（ProRes 4444）或 .webm（VP9）；{out_ext or '（無副檔名）'} 不支援透明，會變成不透明的 yuv420p")
    if not os.path.exists(a.html):
        sys.exit(f"找不到頁面：{a.html}")

    data = {}
    for item in a.data:
        k, _, path = item.partition("=")
        if not k or not path:
            sys.exit(f"--data 要寫成 key=path：{item!r}")
        if not os.path.exists(path):
            sys.exit(f"--data {k}：找不到 {path}")
        with open(path, encoding="utf-8") as f:
            data[k] = json.load(f)

    audio_dur = None
    if a.audio:
        if not os.path.exists(a.audio):
            sys.exit(f"--audio：找不到 {a.audio}")
        audio_dur = probe_duration(a.audio)

    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    page_errors = []
    pr = None
    prof = []   # (render 毫秒, 截圖毫秒)
    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"])
        context = browser.new_context(viewport={"width": a.w, "height": a.h}, device_scale_factor=a.scale)
        page = context.new_page()
        # 截圖走 CDP Page.captureScreenshot（optimizeForSpeed）：畫素與 page.screenshot 相同，1080p 快 2–3 倍
        cdp = context.new_cdp_session(page)
        if a.alpha:
            # 等同 page.screenshot(omit_background=True)：預設背景改成全透明（CDP 的 emulation 狀態是每個 session 各自的）
            cdp.send("Emulation.setDefaultBackgroundColorOverride", {"color": {"r": 0, "g": 0, "b": 0, "a": 0}})
        # clip.scale 用 deviceScaleFactor：這個 session 沒有 Playwright 的 device metrics override，
        # 不帶 clip 或 scale=1 只會拿到 CSS 畫素尺寸（--scale 2 時少掉 4K）
        shot_args = {"format": "png", "optimizeForSpeed": True, "captureBeyondViewport": False,
                     "clip": {"x": 0, "y": 0, "width": a.w, "height": a.h, "scale": a.scale}}
        page.on("console", lambda m: m.type == "error" and print(f"[console.error] {m.text}", file=sys.stderr))
        page.on("pageerror", lambda e: (page_errors.append(str(e)), print(f"[pageerror] {e}", file=sys.stderr)))
        init = f"window.RENDER_SCALE = {a.scale}; window.RENDER_FPS = {a.fps};"
        if data:
            init += "window.DATA = " + json.dumps(data, ensure_ascii=False) + ";"
        page.add_init_script(init)
        page.goto("file://" + os.path.abspath(a.html))
        deadline = time.time() + 30
        while not page.evaluate("typeof window.render === 'function'"):
            if page_errors:
                browser.close()
                sys.exit(f"頁面載入時發生錯誤，中止（{len(page_errors)} 個 pageerror）")
            if time.time() > deadline:
                browser.close()
                sys.exit("頁面 30 秒內沒有定義 window.render(t)")
            page.wait_for_timeout(100)
        page.evaluate("document.fonts.ready")
        if a.samples > 1:
            # 包成箭頭函式：evaluate 收到「回傳函式的運算式」會立刻呼叫它，這裡只要定義 window.__mvSample
            page.evaluate("() => {" + SAMPLE_JS + "}")
        dur = a.dur or page.evaluate("window.DURATION || 0")
        if not a.sheet and not a.cuts and not dur:
            browser.close()
            sys.exit("需要 --dur 或頁面上的 window.DURATION")
        if a.dump_cuts:
            cuts = page.evaluate("Array.isArray(window.CUTS) ? window.CUTS : null")
            if not cuts:
                browser.close()
                sys.exit("--dump-cuts 需要頁面定義 window.CUTS = [秒, ...]")
            os.makedirs(os.path.dirname(os.path.abspath(a.dump_cuts)), exist_ok=True)
            with open(a.dump_cuts, "w", encoding="utf-8") as f:
                json.dump({"offset": a.t0, "fps": a.fps, "cuts": [round(float(c), 4) for c in cuts]}, f,
                          ensure_ascii=False, indent=1)
            print(f"寫入 {a.dump_cuts}（{len(cuts)} 個剪點）", file=sys.stderr)

        def shot(t):
            t_a = time.perf_counter()
            try:
                if a.samples > 1:
                    page.evaluate("([t, n, s, fps]) => window.__mvSample(t, n, s, fps)", [t, a.samples, a.shutter, a.fps])
                else:
                    page.evaluate("async (t) => { await window.render(t); }", t)
            except PlaywrightError as e:
                msg = str(e).splitlines()[0]
                page_errors.append(msg)
                print(f"\n[render error] t={t:.3f}: {msg}", file=sys.stderr)
                raise
            t_b = time.perf_counter()
            png = base64.b64decode(cdp.send("Page.captureScreenshot", shot_args)["data"])
            t_c = time.perf_counter()
            prof.append(((t_b - t_a) * 1000, (t_c - t_b) * 1000))
            if a.profile:
                print(f"[profile] t={t:.3f} render {prof[-1][0]:.0f} ms  截圖 {prof[-1][1]:.0f} ms", file=sys.stderr)
            return png

        try:
            if a.sheet or a.cuts:
                if a.cuts:
                    cuts = page.evaluate("Array.isArray(window.CUTS) ? window.CUTS : null")
                    if not cuts:
                        sys.exit("--cuts 需要頁面定義 window.CUTS = [秒, ...]")
                    times, labels, cols = [], [], 5
                    for i, c in enumerate(cuts):
                        for k in (-2, -1, 0, 1, 2):
                            t = max(0.0, c + k / a.fps)
                            times.append(t)
                            labels.append(f"cut{i + 1} {k:+d}f {t:.3f}s" + (" <" if k == 0 else ""))
                else:
                    times = [float(x) for x in a.sheet.split(",")]
                    labels = [f"{t:.3f}s" for t in times]
                    cols = min(len(times), 4)
                cmd_path = os.path.abspath(a.out) + ".cmds.txt"
                ff = ["ffmpeg", "-v", "error", "-y", "-f", "image2pipe", "-framerate", "1", "-i", "-",
                      "-vf", sheet_filter(labels, cols, cmd_path), "-frames:v", "1", a.out]
                pr = subprocess.Popen(ff, stdin=subprocess.PIPE)
                for t in times:
                    pr.stdin.write(shot(t))
                pr.stdin.close()
                pr.wait()
                if os.path.exists(cmd_path):
                    os.remove(cmd_path)
            else:
                n = round(dur * a.fps)
                ff = ["ffmpeg", "-v", "error", "-y", "-f", "image2pipe", "-framerate", str(a.fps), "-i", "-"]
                if a.audio:
                    total = n / a.fps
                    if audio_dur is not None and audio_dur - a.t0 < total - 0.5 / a.fps:
                        print(f"警告：{a.audio} 從 {a.t0:g} 秒起只剩 {max(0.0, audio_dur - a.t0):.3f} 秒，影片 {total:.3f} 秒，"
                              f"不足的補靜音", file=sys.stderr)
                    # apad 補靜音、-t 切齊影片長度（不用 -shortest：音訊短時它會把影片截短）
                    ff += ["-ss", str(a.t0), "-i", a.audio, "-af", "apad", "-t", f"{total:.6f}"] + audio_args(a.out)
                ff += encoder_args(a.out, a.alpha) + [a.out]
                pr = subprocess.Popen(ff, stdin=subprocess.PIPE)
                for i in range(n):
                    pr.stdin.write(shot(a.t0 + i / a.fps))
                    if i % a.fps == 0:
                        print(f"\r{i}/{n}", end="", file=sys.stderr, flush=True)
                print(f"\r{n}/{n}", file=sys.stderr)
                pr.stdin.close()
                pr.wait()
        except PlaywrightError:
            pass
        except BrokenPipeError:
            print("ffmpeg 提前結束（見上方 ffmpeg 錯誤訊息）", file=sys.stderr)
        finally:
            if pr and pr.stdin and not pr.stdin.closed:
                pr.stdin.close()
                pr.wait()
            browser.close()
    if prof and (a.profile or len(prof) >= 10):
        r = [x[0] for x in prof]
        q = [x[1] for x in prof]
        print(f"每格 render 平均 {sum(r) / len(r):.0f} ms（最大 {max(r):.0f}）  截圖平均 {sum(q) / len(q):.0f} ms"
              f"（最大 {max(q):.0f}）  共 {len(prof)} 格", file=sys.stderr)
    if page_errors:
        removed = remove_partial(a.out)
        sys.exit(f"頁面有 {len(page_errors)} 個錯誤（見 stderr），輸出不可信" + ("，已刪除 " + a.out if removed else ""))
    if pr is None or pr.returncode:
        removed = remove_partial(a.out)
        print(f"ffmpeg 失敗（exit {pr.returncode if pr else 1}）" + ("，已刪除寫到一半的 " + a.out if removed else ""),
              file=sys.stderr)
        sys.exit(pr.returncode if pr else 1)
    print(a.out)


if __name__ == "__main__":
    main()
