#!/usr/bin/env python3
"""把 prompts/*.md 裡的 {{include:路徑}} 展開成完整指令，寫到 dist/（每一步一個 .txt，直接整段貼進 Lovable）。

  python3 build_prompts.py            # 產生 dist/*.txt
  python3 build_prompts.py --json X   # 另外輸出 JSON（給說明頁用）
"""
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def expand(text: str) -> str:
    return re.sub(r'\{\{include:([^}]+)\}\}', lambda m: (HERE / m.group(1).strip()).read_text(encoding='utf-8').rstrip(), text)


def main() -> None:
    out = HERE / 'dist'
    out.mkdir(exist_ok=True)
    steps = []
    for p in sorted((HERE / 'prompts').glob('*.md')):
        full = expand(p.read_text(encoding='utf-8'))
        (out / (p.stem + '.txt')).write_text(full, encoding='utf-8')
        steps.append({'id': p.stem, 'text': full, 'chars': len(full)})
        print(f'{p.stem}: {len(full):,} 字元')
    if '--json' in sys.argv:
        Path(sys.argv[sys.argv.index('--json') + 1]).write_text(json.dumps(steps, ensure_ascii=False), encoding='utf-8')


if __name__ == '__main__':
    main()
