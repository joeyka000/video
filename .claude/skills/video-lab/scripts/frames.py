#!/usr/bin/env python3
"""seek(t) 引擎的執行器：抽格、縮圖總覽、分段平行渲染、社群交付壓檔。

engine.py 約定（Python）：
  W, H, FPS, TOTAL          畫面尺寸、每秒格數、總長（秒）
  frame(t) -> np.uint8 (H, W, 3) RGB    只由 t 決定；不靠「上一格」的狀態
  可選 AUDIO = '路徑'        video 指令自動混入
  可選 MARKS = [(秒, '標籤'), ...]   sheet 指令的預設抽格點（每個段落、每個大招各一格）

  python frames.py still  engine.py 1.0,2.5,7          → <engine 目錄>/stills/<秒>.jpg
  python frames.py sheet  engine.py -o sheet.jpg        → 縮圖總覽（每格編號＋秒數）＋ sheet.review.json 評分表
         [--at 0.5,3,7 | --every 1.5 | --n 24] [--cols 6] [--width 270]
  python frames.py video  engine.py -o master.mp4 [--jobs 4] [--from 0 --to 10] [--audio a.wav] [--crf 14]
  python frames.py deliver master.mp4 -o post.mp4 [--max-mb 29]   → HEVC 兩段式，壓在上傳上限內（雲端傳檔上限 30 MiB）

正式渲染前一定先 sheet → 評分 → 修 → review.py gate 通過，再 video（見 references/review.md）。
"""
import argparse
import importlib.util
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)


def load(path):
    path = os.path.abspath(path)
    sys.path.insert(0, os.path.dirname(path))
    spec = importlib.util.spec_from_file_location('engine', path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    for k in ('W', 'H', 'FPS', 'TOTAL', 'frame'):
        if not hasattr(m, k):
            sys.exit(f'{path} 缺少 {k}（engine 約定見 frames.py 檔頭）')
    return m


def times_for(m, a):
    if a.at:
        return [float(x) for x in a.at.split(',')]
    if a.every:
        n = int(m.TOTAL / a.every)
        return [round(a.every * (i + 0.5), 3) for i in range(n)]
    if a.n:
        return [round(m.TOTAL * (i + 0.5) / a.n, 3) for i in range(a.n)]
    if getattr(m, 'MARKS', None):
        return [float(t) for t, _ in m.MARKS]
    return [round(m.TOTAL * (i + 0.5) / 24, 3) for i in range(24)]


def cmd_still(a):
    import cv2
    m = load(a.engine)
    d = a.out or os.path.join(os.path.dirname(os.path.abspath(a.engine)), 'stills')
    os.makedirs(d, exist_ok=True)
    for t in (float(x) for x in a.times.split(',')):
        p = os.path.join(d, f'{t:07.2f}.jpg')
        cv2.imwrite(p, m.frame(t)[..., ::-1], [cv2.IMWRITE_JPEG_QUALITY, 92])
        print(p)


def cmd_sheet(a):
    import review
    m = load(a.engine)
    ts = times_for(m, a)
    labels = dict(getattr(m, 'MARKS', []) or [])
    frames = [m.frame(t) for t in ts]
    review.make_sheet(frames, ts, a.out, cols=a.cols, width=a.width, labels=[labels.get(t, '') for t in ts],
                      source=os.path.abspath(a.engine))


def cmd_chunk(a):
    """內部用：渲一段寫成 mp4（無聲）。"""
    m = load(a.engine)
    n0, n1 = int(round(a.t0 * m.FPS)), int(round(a.t1 * m.FPS))
    enc = ['ffmpeg', '-v', 'error', '-y', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', f'{m.W}x{m.H}', '-r', str(m.FPS), '-i', '-',
           '-c:v', 'libx264', '-preset', 'slow', '-crf', str(a.crf), '-pix_fmt', 'yuv420p', a.out]
    pr = subprocess.Popen(enc, stdin=subprocess.PIPE)
    for k in range(n0, n1):
        pr.stdin.write(m.frame(k / m.FPS).tobytes())
        if (k - n0) % (m.FPS * 3) == 0:
            print(f'[{a.t0:.1f}–{a.t1:.1f}] {k / m.FPS:6.1f}s', flush=True)
    pr.stdin.close()
    if pr.wait():
        sys.exit('ffmpeg 失敗')


def cmd_video(a):
    m = load(a.engine)
    t0 = a.t_from
    t1 = a.to if a.to is not None else m.TOTAL
    fps = m.FPS
    # 依格數切段，邊界落在整格上，接起來不重複不缺格
    f0, f1 = int(round(t0 * fps)), int(round(t1 * fps))
    jobs = max(1, min(a.jobs, (f1 - f0) // fps or 1))
    cuts = [f0 + (f1 - f0) * i // jobs for i in range(jobs + 1)]
    tmp = tempfile.mkdtemp(prefix='frames_', dir=os.path.dirname(os.path.abspath(a.out)))
    procs, parts = [], []
    for i in range(jobs):
        p = os.path.join(tmp, f'p{i:02d}.mp4')
        parts.append(p)
        procs.append(subprocess.Popen([sys.executable, __file__, '_chunk', a.engine, '-o', p, '--t0', str(cuts[i] / fps),
                                       '--t1', str(cuts[i + 1] / fps), '--crf', str(a.crf)]))
    bad = [i for i, pr in enumerate(procs) if pr.wait()]
    if bad:
        sys.exit(f'第 {bad} 段失敗；分段檔留在 {tmp}')
    lst = os.path.join(tmp, 'list.txt')
    with open(lst, 'w') as f:
        f.writelines(f"file '{p}'\n" for p in parts)
    audio = a.audio or getattr(m, 'AUDIO', None)
    cmd = ['ffmpeg', '-v', 'error', '-y', '-f', 'concat', '-safe', '0', '-i', lst]
    if audio:
        cmd += ['-ss', str(t0), '-i', audio, '-map', '0:v', '-map', '1:a', '-c:a', 'aac', '-b:a', '256k', '-shortest']
    cmd += ['-c:v', 'copy', '-movflags', '+faststart', a.out]
    subprocess.run(cmd, check=True)
    for p in parts + [lst]:
        os.remove(p)
    os.rmdir(tmp)
    print(a.out)


def probe_dur(path):
    r = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', path],
                       capture_output=True, text=True, check=True)
    return float(r.stdout)


def cmd_deliver(a):
    dur = probe_dur(a.master)
    budget_kbit = a.max_mb * 1024 * 1024 * 8 / 1000 * 0.97
    vk = int(budget_kbit / dur - 192)
    if vk < 600:
        sys.exit(f'{dur:.0f} 秒要壓進 {a.max_mb} MB，影像只剩 {vk} kbps，畫質會崩：改短或改用雲端連結交付')
    vk = min(vk, a.cap_kbps)
    log = os.path.join(tempfile.mkdtemp(), 'x265')
    base = ['ffmpeg', '-v', 'error', '-y', '-i', a.master, '-c:v', 'libx265', '-preset', 'slow', '-b:v', f'{vk}k', '-tag:v', 'hvc1',
            '-pix_fmt', 'yuv420p', '-color_primaries', 'bt709', '-color_trc', 'bt709', '-colorspace', 'bt709']
    subprocess.run(base + ['-x265-params', f'pass=1:stats={log}:log-level=error', '-an', '-f', 'null', '/dev/null'], check=True)
    subprocess.run(base + ['-x265-params', f'pass=2:stats={log}:log-level=error', '-c:a', 'aac', '-b:a', '192k',
                           '-movflags', '+faststart', a.out], check=True)
    mb = os.path.getsize(a.out) / 1024 / 1024
    print(f'{a.out}  {mb:.1f} MiB  影像 {vk} kbps  {dur:.1f} 秒')
    if mb > a.max_mb:
        sys.exit('超過上限：把 --max-mb 調小再跑一次')


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = p.add_subparsers(dest='cmd', required=True)
    s = sp.add_parser('still')
    s.add_argument('engine')
    s.add_argument('times')
    s.add_argument('-o', '--out')
    s = sp.add_parser('sheet')
    s.add_argument('engine')
    s.add_argument('-o', '--out', required=True)
    s.add_argument('--at')
    s.add_argument('--every', type=float)
    s.add_argument('--n', type=int)
    s.add_argument('--cols', type=int, default=6)
    s.add_argument('--width', type=int, default=270)
    s = sp.add_parser('video')
    s.add_argument('engine')
    s.add_argument('-o', '--out', required=True)
    s.add_argument('--jobs', type=int, default=os.cpu_count() or 4)
    s.add_argument('--from', dest='t_from', type=float, default=0.0)
    s.add_argument('--to', type=float)
    s.add_argument('--audio')
    s.add_argument('--crf', type=int, default=14)
    s = sp.add_parser('_chunk')
    s.add_argument('engine')
    s.add_argument('-o', '--out', required=True)
    s.add_argument('--t0', type=float, required=True)
    s.add_argument('--t1', type=float, required=True)
    s.add_argument('--crf', type=int, default=14)
    s = sp.add_parser('deliver')
    s.add_argument('master')
    s.add_argument('-o', '--out', required=True)
    s.add_argument('--max-mb', type=float, default=29)
    s.add_argument('--cap-kbps', type=int, default=12000, help='短片不必塞滿上限')
    a = p.parse_args()
    {'still': cmd_still, 'sheet': cmd_sheet, 'video': cmd_video, '_chunk': cmd_chunk, 'deliver': cmd_deliver}[a.cmd](a)


if __name__ == '__main__':
    main()
