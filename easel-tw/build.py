#!/usr/bin/env python3
"""Easel 台灣版建置：取得上游 ZJU-REAL/Easel（固定版本）→ 繁體中文（臺灣用語）→ 台灣平台與資料來源 → 覆蓋新增檔案。

  python3 build.py --out ~/easel-tw                 # 從 GitHub clone 上游（UPSTREAM 檔裡的固定 commit）
  python3 build.py --src /path/to/easel --out DIR   # 用本機已有的上游 checkout（必須是同一個 commit）
  python3 build.py --out DIR --check                # 只檢查所有修補點都對得上，不寫檔

步驟：
  1. 複製上游（不含 .git 以外的建置產物；--no-showcase 可略過 web/static/showcase 與 README 用的 assets/readme，約 430 MB 的示範影片與圖）
  2. 刪掉中國平臺專用技能（小紅書、抖音、快手、視頻號、知乎、B 站、公眾號）與 AGPL 授權的 gzh-design
  3. 所有文字檔做 OpenCC s2twp（簡→繁、臺灣用語），再套一份社群用語修正表（帳號、發布、貼文、按讚…）
  4. 套用台灣版修補（patches.py：語言規則、台灣平台、熱門來源、台灣配音、字型、官方套件來源、預設模型）
  5. 複製 overlay/ 裡的新增檔案（台灣熱門話題、Threads 日報、台灣節慶、平台規格…）
  6. 寫入 TAIWAN-BUILD.json（上游 commit、修補清單、轉換檔案數）

需要 Python 套件 opencc（pip install opencc）。上游授權 Apache-2.0；本工具只改動並標註，不改上游 LICENSE。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

UPSTREAM = dict(line.split('=', 1) for line in (HERE / 'UPSTREAM').read_text().split() if '=' in line)

# 只在中國平臺有用、或授權不適合的技能
REMOVE_SKILLS = [
    'gzh-design',                     # AGPL-3.0，微信公眾號排版
    'skill-bilibili-upload', 'skill-channels-upload', 'skill-douyin-upload', 'skill-kuaishou-upload',
    'skill-wechat-publisher', 'skill-xhs-analyzer', 'skill-xhs-comment-reply', 'skill-xhs-publisher',
    'skill-zhihu-answer', 'skill-zhihu-publisher', 'xhs-note-creator', 'skill-my-account', 'skill-cross-platform-publish',
]

TEXT_EXT = {'.py', '.ts', '.tsx', '.js', '.mjs', '.css', '.html', '.md', '.json', '.json5', '.yaml', '.yml', '.toml',
            '.txt', '.sh', '.ps1', '.ini', '.cfg', '.example', '.svg'}
SKIP_NAMES = {'LICENSE', 'package-lock.json', 'marked.umd.js'}
SKIP_DIRS = {'.git', 'node_modules', 'dist', '__pycache__', '.venv'}

# s2twp 之後再修的社群／產品用語（左邊是 s2twp 的結果）
FIXES = [
    ('臺', '台'),                                  # 台灣日常寫法
    ('賬號', '帳號'), ('賬戶', '帳戶'), ('賬單', '帳單'), ('對賬', '對帳'),
    ('釋出', '發布'), ('質量', '品質'), ('二維碼', 'QR Code'), ('掃碼', '掃描 QR Code'),
    ('帖子', '貼文'), ('發帖', '發文'), ('博主', '創作者'), ('點贊', '按讚'), ('點讚', '按讚'), ('評論區', '留言區'),
    ('運營', '經營'), ('網際網路', '網路'), ('最佳化', '優化'), ('資訊流', '動態牆'),
    ('會話', '對話'), ('排期', '排程'), ('社媒', '社群'), ('流式', '串流'), ('產物', '成品'), ('拉取', '抓取'),
    ('校驗', '驗證'), ('行業', '產業'), ('短影片', '短影音'), ('用戶', '使用者'),
    ('二建立議', '二創建議'),                        # s2twp 把「创建」當成一個詞
    ('受眾畫像', '受眾輪廓'), ('使用者畫像', '人設'), ('畫像', '人設'),  # Easel 的「畫像」= 帳號人設檔
    ('指令碼', '腳本'),                              # s2twp 把「脚本」當程式語境
]


def run(cmd, **kw):
    print('$', ' '.join(map(str, cmd)))
    subprocess.run(cmd, check=True, **kw)


def fetch(out: Path, src: str | None, showcase: bool) -> None:
    if out.exists() and any(out.iterdir()):
        sys.exit(f'{out} 已存在且不是空的：換一個 --out，或先移走舊的（裡面的 .env 與 outputs/ 記得備份）')
    out.mkdir(parents=True, exist_ok=True)
    if src:
        head = subprocess.run(['git', '-C', src, 'rev-parse', 'HEAD'], capture_output=True, text=True).stdout.strip()
        if head and head != UPSTREAM['sha']:
            print(f'⚠ {src} 的 commit 是 {head[:10]}，UPSTREAM 固定的是 {UPSTREAM["sha"][:10]}；修補點可能對不上（會在第 4 步報錯）')

        def ignore(d, names):
            skip = {n for n in names if n in SKIP_DIRS and n != '.git'} | {'.git'}
            if not showcase and Path(d).name == 'static':
                skip |= {'showcase'}
            if not showcase and Path(d).name == 'assets' and Path(d).parent == Path(src):
                skip |= {'readme'}
            return skip
        shutil.copytree(src, out, dirs_exist_ok=True, ignore=ignore)
    else:
        env = {**os.environ, 'GIT_LFS_SKIP_SMUDGE': '1'}
        run(['git', 'init', '-q', str(out)])
        run(['git', '-C', str(out), 'remote', 'add', 'origin', UPSTREAM['url']])
        run(['git', '-C', str(out), 'fetch', '-q', '--depth', '1', '--filter=blob:none', 'origin', UPSTREAM['sha']], env=env)
        if not showcase:
            run(['git', '-C', str(out), 'sparse-checkout', 'set', '--no-cone', '/*', '!/web/static/showcase/', '!/assets/readme/'])
        run(['git', '-C', str(out), 'checkout', '-q', 'FETCH_HEAD'], env=env)
        run(['git', '-C', str(out), 'switch', '-q', '-c', 'taiwan'])


def remove_skills(out: Path) -> list[str]:
    gone = []
    for name in REMOVE_SKILLS:
        p = out / 'skills' / 'openclaw' / name
        if p.exists():
            shutil.rmtree(p)
            gone.append(name)
    return gone


def convert(out: Path) -> int:
    import opencc
    cc = opencc.OpenCC('s2twp')
    han = re.compile(r'[一-鿿]')
    n = 0
    for root, dirs, files in os.walk(out):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS and d != 'showcase']
        for f in files:
            p = Path(root) / f
            if f in SKIP_NAMES or (p.suffix.lower() not in TEXT_EXT and f not in ('.env.example', 'Dockerfile')):
                continue
            try:
                text = p.read_text(encoding='utf-8')
            except (UnicodeDecodeError, OSError):
                continue
            if not han.search(text):
                continue
            new = cc.convert(text)
            for a, b in FIXES:
                new = new.replace(a, b)
            if new != text:
                p.write_text(new, encoding='utf-8')
                n += 1
    return n


def copy_overlay(out: Path) -> list[str]:
    done = []
    base = HERE / 'overlay'
    for p in sorted(base.rglob('*')):
        if p.is_file() and '__pycache__' not in p.parts:
            rel = p.relative_to(base)
            dst = out / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(p, dst)
            done.append(str(rel))
    return done


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--out', required=True)
    ap.add_argument('--src', help='本機上游 checkout（省下載）')
    ap.add_argument('--no-showcase', action='store_true', help='不放首頁示範影片與 README 圖（省約 430 MB）')
    ap.add_argument('--check', action='store_true', help='在暫存目錄跑一遍，只回報修補點是否都對得上')
    a = ap.parse_args()
    import patches
    out = Path(a.out).expanduser().resolve()
    if a.check:
        import tempfile
        out = Path(tempfile.mkdtemp(prefix='easel-tw-check-')) / 'easel'
    fetch(out, a.src, showcase=not a.no_showcase)
    gone = remove_skills(out)
    print(f'移除技能 {len(gone)} 個')
    n = convert(out)
    print(f'簡→繁（s2twp）轉換 {n} 個檔案')
    applied = patches.apply(out, gone)
    print(f'台灣版修補 {len(applied)} 處')
    added = copy_overlay(out)
    print(f'新增／覆蓋檔案 {len(added)} 個')
    if (out / '.git').exists():  # clone 模式：把轉換結果記成一個 commit，之後可以 git diff FETCH_HEAD 看改了什麼
        subprocess.run(['git', '-C', str(out), 'add', '-A'], check=True)
        subprocess.run(['git', '-C', str(out), '-c', 'user.name=easel-tw', '-c', 'user.email=easel-tw@localhost',
                        'commit', '-qm', 'Easel 台灣版轉換（easel-tw/build.py）'], check=True)
    (out / 'TAIWAN-BUILD.json').write_text(json.dumps({
        'upstream': UPSTREAM, 'removed_skills': gone, 'converted_files': n, 'patches': applied, 'overlay': added,
    }, ensure_ascii=False, indent=1), encoding='utf-8')
    if a.check:
        shutil.rmtree(out.parent)
        print('檢查通過')
    else:
        print(f'完成：{out}\n下一步：cd {out} && bash setup.sh')


if __name__ == '__main__':
    main()
