#!/usr/bin/env python3
"""把定義了 window.render(t) 的 HTML 逐格截圖，合成影片。

  python render.py page.html -o out/title.mp4 --dur 5
  python render.py page.html -o out/title.mov --dur 5 --alpha      # ProRes 4444 透明
  python render.py page.html -o out/title.webm --dur 5 --alpha     # VP9 透明
  python render.py page.html -o out/sheet.png --sheet 0.5,1.5,3    # 輸出指定時間點的預覽拼圖

頁面可選擇定義 window.DURATION（秒），沒給 --dur 時使用。
畫面必須是 t 的純函數：同一個 t 永遠畫出同一張圖。
"""
import argparse
import os
import subprocess
import sys

from playwright.sync_api import sync_playwright


def encoder_args(out, alpha):
    ext = os.path.splitext(out)[1].lower()
    if ext == ".mov" and alpha:
        return ["-c:v", "prores_ks", "-profile:v", "4444", "-pix_fmt", "yuva444p10le"]
    if ext == ".webm":
        return ["-c:v", "libvpx-vp9", "-pix_fmt", "yuva420p" if alpha else "yuv420p", "-b:v", "8M"]
    return ["-c:v", "libx264", "-crf", "16", "-preset", "medium", "-pix_fmt", "yuv420p", "-movflags", "+faststart"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("html")
    ap.add_argument("-o", "--out", required=True)
    ap.add_argument("--w", type=int, default=1920)
    ap.add_argument("--h", type=int, default=1080)
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--dur", type=float)
    ap.add_argument("--from", dest="t0", type=float, default=0.0)
    ap.add_argument("--alpha", action="store_true", help="透明背景（.mov 或 .webm）")
    ap.add_argument("--audio", help="要合進去的音訊檔")
    ap.add_argument("--sheet", help="逗號分隔的時間點，輸出預覽拼圖而非影片")
    a = ap.parse_args()

    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"])
        page = browser.new_page(viewport={"width": a.w, "height": a.h})
        page.goto("file://" + os.path.abspath(a.html))
        page.wait_for_function("typeof window.render === 'function'")
        page.evaluate("document.fonts.ready")
        dur = a.dur or page.evaluate("window.DURATION || 0")
        if not a.sheet and not dur:
            sys.exit("需要 --dur 或頁面上的 window.DURATION")

        def shot(t):
            page.evaluate(f"(async () => {{ await window.render({t}); }})()")
            return page.screenshot(omit_background=a.alpha)

        if a.sheet:
            times = [float(x) for x in a.sheet.split(",")]
            cols = min(len(times), 4)
            ff = ["ffmpeg", "-v", "error", "-y", "-f", "image2pipe", "-i", "-",
                  "-vf", f"scale=480:-2,drawtext=text='%{{n}}':x=8:y=8:fontsize=20:fontcolor=white:box=1:boxcolor=black@0.5,"
                         f"tile={cols}x{(len(times) + cols - 1) // cols}", "-frames:v", "1", a.out]
            pr = subprocess.Popen(ff, stdin=subprocess.PIPE)
            for t in times:
                pr.stdin.write(shot(t))
        else:
            n = round(dur * a.fps)
            ff = ["ffmpeg", "-v", "error", "-y", "-f", "image2pipe", "-framerate", str(a.fps), "-i", "-"]
            if a.audio:
                ff += ["-ss", str(a.t0), "-i", a.audio, "-c:a", "aac", "-b:a", "192k", "-shortest"]
            ff += encoder_args(a.out, a.alpha) + [a.out]
            pr = subprocess.Popen(ff, stdin=subprocess.PIPE)
            for i in range(n):
                pr.stdin.write(shot(a.t0 + i / a.fps))
                if i % a.fps == 0:
                    print(f"\r{i}/{n}", end="", file=sys.stderr, flush=True)
            print(f"\r{n}/{n}", file=sys.stderr)
        pr.stdin.close()
        pr.wait()
        browser.close()
    if pr.returncode:
        sys.exit(pr.returncode)
    print(a.out)


if __name__ == "__main__":
    main()
