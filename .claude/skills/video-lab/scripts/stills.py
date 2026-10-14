"""平面圖（活動圖、貼文、限動、橫幅、印刷桌卡）：HTML/CSS 排版 → Chromium 截圖，附出框／壓字檢查與總覽。
排版用網頁做：中文字距、字重、漸層字、陰影、遮罩都比 PIL 精準；畫面只由 HTML 決定，重出一張只要一秒。

  python stills.py render posters.py [名稱前綴 ...] -o deliver/ [--html qa/html] [--png 05_] [--pdf 05_ --dpi 300]
  python stills.py sheet deliver/ -o qa/sheet.jpg            # 總覽（檔名當標題），再用 review.py 評分
  python stills.py qr deliver/05_桌卡.png                     # 印刷前確認 QR 掃得到、內容對

posters.py 要提供 POSTERS = {名稱: (寬, 高, fn)}，fn() 回傳完整 HTML。HTML 慣例：
  - 最外層 <div class="page" data-safe="40">：data-safe 是安全邊（px），字都要在裡面
  - 每個字塊加 class="t"：檢查出框、檢查兩個字塊互相壓到（大字的行高框會誤報，以看圖為準）
  - 要自動縮字的加 class="fit"（data-max＝最大寬，預設父層寬）：跟 seekkit.fit_text 同規則，量了再放
  - 本機圖片、字型用 file:// 絕對路徑
"""
import argparse
import glob
import importlib.util
import json
import os
import sys

CHECK_JS = """
() => {
  for (const el of document.querySelectorAll('.fit')) {
    let fs = parseFloat(getComputedStyle(el).fontSize), max = parseFloat(el.dataset.max || el.parentElement.clientWidth);
    while (el.scrollWidth > max + 0.5 && fs > 10) { fs -= 1; el.style.fontSize = fs + 'px'; }
  }
  const pg = document.querySelector('.page') || document.body, W = pg.clientWidth, H = pg.clientHeight;
  const m = parseFloat(pg.dataset.safe || 40), bad = [];
  for (const el of document.querySelectorAll('.t')) {
    const r = el.getBoundingClientRect();
    if (r.width && (r.left < m - 1 || r.top < m - 1 || r.right > W - m + 1 || r.bottom > H - m + 1))
      bad.push(['出框', el.textContent.trim().slice(0, 24), Math.round(r.left), Math.round(r.top), Math.round(r.right), Math.round(r.bottom)]);
  }
  const ts = [...document.querySelectorAll('.t')].map(e => [e, e.getBoundingClientRect()]);
  for (let i = 0; i < ts.length; i++) for (let j = i + 1; j < ts.length; j++) {
    const [a, ra] = ts[i], [b, rb] = ts[j];
    if (a.contains(b) || b.contains(a)) continue;
    const ox = Math.min(ra.right, rb.right) - Math.max(ra.left, rb.left), oy = Math.min(ra.bottom, rb.bottom) - Math.max(ra.top, rb.top);
    if (ox > 2 && oy > 2) bad.push(['重疊', a.textContent.trim().slice(0, 12), b.textContent.trim().slice(0, 12)]);
  }
  return bad;
}
"""


def load(path):
    spec = importlib.util.spec_from_file_location('posters', path)
    m = importlib.util.module_from_spec(spec)
    sys.path.insert(0, os.path.dirname(os.path.abspath(path)))
    spec.loader.exec_module(m)
    return m.POSTERS


def render(posters, names, out, html_dir=None, png=(), pdf=(), dpi=300, quality=94):
    """每張：寫 HTML → file:// 開 → 等字型 → 檢查 → 截 .page → JPG（png／pdf 前綴另存無損與印刷檔）。"""
    from PIL import Image
    from playwright.sync_api import sync_playwright
    os.makedirs(out, exist_ok=True)
    html_dir = html_dir or os.path.join(out, '_html')
    os.makedirs(html_dir, exist_ok=True)
    report = {}
    with sync_playwright() as p:
        br = p.chromium.launch(args=['--allow-file-access-from-files'])
        for name in names:
            w, h, fn = posters[name]
            hp = os.path.abspath(os.path.join(html_dir, name + '.html'))
            open(hp, 'w', encoding='utf-8').write(fn())
            pg = br.new_page(viewport={'width': w, 'height': h}, device_scale_factor=1)
            pg.goto('file://' + hp)
            pg.wait_for_load_state('networkidle')
            pg.evaluate('document.fonts.ready')
            pg.wait_for_timeout(300)
            bad = pg.evaluate(CHECK_JS)
            tmp = os.path.join(out, name + '.png')
            (pg.locator('.page') if pg.locator('.page').count() else pg).screenshot(path=tmp)
            pg.close()
            im = Image.open(tmp).convert('RGB')
            im.save(os.path.join(out, name + '.jpg'), quality=quality, subsampling=0, optimize=True)
            if any(name.startswith(s) for s in pdf):
                im.save(os.path.join(out, name + '_印刷.pdf'), resolution=float(dpi))
            if any(name.startswith(s) for s in png):
                im.save(tmp, dpi=(dpi, dpi))
            else:
                os.remove(tmp)
            report[name] = bad
            print(name, 'OK' if not bad else bad)
        br.close()
    json.dump(report, open(os.path.join(out, '_check.json'), 'w'), ensure_ascii=False, indent=1)
    return report


def sheet(src, out, cols=5, cell=(360, 505), font=None):
    from PIL import Image, ImageDraw, ImageFont
    fs = sorted(glob.glob(os.path.join(src, '*.jpg')))
    fs = [f for f in fs if os.path.abspath(f) != os.path.abspath(out)]
    cw, ch = cell[0] + 20, cell[1] + 56
    S = Image.new('RGB', (cols * cw + 20, max(1, (len(fs) + cols - 1) // cols) * ch + 10), (18, 18, 18))
    d = ImageDraw.Draw(S)
    try:
        f = ImageFont.truetype(font or '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc', 20)
    except OSError:
        f = ImageFont.load_default()
    for i, p in enumerate(fs):
        im = Image.open(p)
        im.thumbnail(cell)
        x, y = 20 + (i % cols) * cw, 10 + (i // cols) * ch
        S.paste(im, (x, y + 34))
        d.text((x, y + 4), os.path.splitext(os.path.basename(p))[0], font=f, fill=(235, 225, 200))
    S.save(out, quality=88)
    return out


def qr(path):
    import cv2
    val, pts, _ = cv2.QRCodeDetector().detectAndDecode(cv2.imread(path))
    return val


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest='cmd', required=True)
    r = sp.add_parser('render')
    r.add_argument('module')
    r.add_argument('names', nargs='*', help='名稱前綴；不給＝全部')
    r.add_argument('-o', '--out', required=True)
    r.add_argument('--html')
    r.add_argument('--png', nargs='*', default=[], help='這些前綴另存無損 PNG（帶 dpi）')
    r.add_argument('--pdf', nargs='*', default=[], help='這些前綴另存印刷 PDF')
    r.add_argument('--dpi', type=int, default=300)
    s = sp.add_parser('sheet')
    s.add_argument('src')
    s.add_argument('-o', '--out', required=True)
    s.add_argument('--cols', type=int, default=5)
    q = sp.add_parser('qr')
    q.add_argument('image')
    a = ap.parse_args()
    if a.cmd == 'render':
        P = load(a.module)
        names = [n for n in P if not a.names or any(n.startswith(x) for x in a.names)]
        render(P, names, a.out, a.html, a.png, a.pdf, a.dpi)
    elif a.cmd == 'sheet':
        print(sheet(a.src, a.out, a.cols))
    else:
        v = qr(a.image)
        print(repr(v) if v else '解不出 QR：放大、加白邊（quiet zone ≥ 4 格）或提高對比')
        sys.exit(0 if v else 1)


if __name__ == '__main__':
    main()
