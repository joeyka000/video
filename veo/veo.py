"""Veo 生成工具（Gemini API，純 REST、不需額外套件）——預設走省錢流程。

省錢規則（使用者要求，2026-10-05）：先用便宜的方式試，確認後才花大錢。
  1. 首格：預設 Nano Banana 2（gemini-3.1-flash-image，1K），只有加 --pro 才用 Nano Banana Pro。已存在的首格不重生。
  2. 試片：預設 Veo 3.1 lite、720p、每段 4 秒。先給使用者看試片。
  3. 定稿：只重生使用者點頭的鏡頭；--tier fast 或 --tier standard，standard 另外要加 --final。
  4. 每個指令都先印出預估花費；超過 --budget（預設 2 美元）就拒絕；沒加 --yes 不會送出。
     任何付費步驟都要先通知使用者並取得這一筆的明確同意，才可以加 --yes（不論金額多小）。
  5. 每次實際花費記在 out/spend.jsonl，`python veo.py spend` 看累計。

金鑰：讀環境變數 GEMINI_API_KEY（在雲端環境設定裡加，不要貼在對話裡）。
  python veo.py models                                   列出可用模型（免費）
  python veo.py keyframe shots.json [id ...] [--pro] [--redo] --yes
  python veo.py gen shots.json [id ...] [--tier lite|fast|standard] [--res 720p|1080p] [--seconds 4|6|8] [--final] --yes
  python veo.py spend                                    累計花費
輸出：out/<id>.png（首格）、out/<id>_<tier>.mp4（影片，試片與定稿分開存）。
"""
import argparse
import base64
import datetime
import json
import os
import sys
import time
import urllib.error
import urllib.request

API = 'https://generativelanguage.googleapis.com/v1beta'
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, 'out')
os.makedirs(OUT, exist_ok=True)

# 單價（美元，Gemini API 付費層，2026-10-05 查 https://ai.google.dev/gemini-api/docs/pricing；價格會變，大筆花費前再查一次）
VEO = {  # tier: (模型, {解析度: 每秒})
    'lite': ('veo-3.1-lite-generate-preview', {'720p': 0.05, '1080p': 0.08}),
    'fast': ('veo-3.1-fast-generate-preview', {'720p': 0.10, '1080p': 0.12, '4k': 0.30}),
    'standard': ('veo-3.1-generate-preview', {'720p': 0.40, '1080p': 0.40, '4k': 0.60}),
}
IMAGE = {'flash': ('gemini-3.1-flash-image', 0.067), 'pro': ('gemini-3-pro-image', 0.134)}


def key():
    k = os.environ.get('GEMINI_API_KEY')
    if not k:
        sys.exit('沒有 GEMINI_API_KEY：請在雲端環境設定加入這個環境變數，開新 session 後再執行。')
    return k


def call(method, url, body=None, timeout=120):
    req = urllib.request.Request(url, data=json.dumps(body).encode() if body is not None else None, method=method,
                                 headers={'x-goog-api-key': key(), 'Content-Type': 'application/json'})
    try:
        return json.load(urllib.request.urlopen(req, timeout=timeout))
    except urllib.error.HTTPError as e:
        sys.exit(f'{e.code} {e.read().decode()[:800]}')


def models():
    out, tok = [], ''
    while True:
        r = call('GET', f'{API}/models?pageSize=200' + (f'&pageToken={tok}' if tok else ''))
        out += r.get('models', [])
        tok = r.get('nextPageToken')
        if not tok:
            return out


def log_spend(kind, model, item, usd):
    with open(os.path.join(OUT, 'spend.jsonl'), 'a') as f:
        f.write(json.dumps({'time': datetime.datetime.now().isoformat(timespec='seconds'), 'kind': kind, 'model': model,
                            'item': item, 'usd': round(usd, 4)}) + '\n')


def spend():
    p = os.path.join(OUT, 'spend.jsonl')
    rows = [json.loads(x) for x in open(p)] if os.path.exists(p) else []
    for r in rows:
        print(f"{r['time']}  {r['kind']:8s} {r['model']:34s} {r['item']:10s} ${r['usd']:.3f}")
    print(f'累計 ${sum(r["usd"] for r in rows):.2f}')


def guard(est, a):
    print(f'預估花費：${est:.2f}（上限 --budget ${a.budget:.2f}）')
    if est > a.budget:
        sys.exit('超過預算上限：縮小範圍（指定鏡頭 id、--seconds 4、--tier lite）或明確提高 --budget。')
    if not a.yes:
        sys.exit('只是預估。確認後加 --yes 才會送出。')


def load(path, ids):
    spec = json.load(open(path))
    shots = spec['shots']
    if ids:
        shots = [s for s in shots if s['id'] in ids]
    return spec, shots


def keyframe(a):
    spec, shots = load(a.shots, a.ids)
    model, price = IMAGE['pro' if a.pro else 'flash']
    model = os.environ.get('IMAGE_MODEL', model)
    todo = [s for s in shots if s.get('ref') and (a.redo or not os.path.exists(os.path.join(OUT, f"{s['id']}.png")))]
    print(f'圖片模型：{model}，要產生 {len(todo)} 張（已存在的不重做，要重做加 --redo）')
    if not todo:
        return
    guard(len(todo) * price, a)
    for s in todo:
        img = base64.b64encode(open(os.path.join(os.path.dirname(os.path.abspath(a.shots)), s['ref']), 'rb').read()).decode()
        body = {'contents': [{'parts': [{'inline_data': {'mime_type': 'image/jpeg', 'data': img}},
                                        {'text': 'Use the person in this photo as the character and keep their face recognizable. '
                                         + spec['character'] + ' ' + s['keyframe'] + ' ' + spec['style'] + ' Vertical 9:16 photorealistic film still.'}]}],
                'generationConfig': {'responseModalities': ['IMAGE'], 'imageConfig': {'aspectRatio': '9:16'}}}
        r = call('POST', f'{API}/models/{model}:generateContent', body, 300)
        parts = r['candidates'][0]['content']['parts']
        data = next((p['inlineData']['data'] for p in parts if 'inlineData' in p), None)
        log_spend('keyframe', model, s['id'], price)
        if not data:
            print(s['id'], '沒有回傳圖片：', [p.get('text', '')[:200] for p in parts])
            continue
        open(os.path.join(OUT, f"{s['id']}.png"), 'wb').write(base64.b64decode(data))
        print('ok', s['id'])


def gen(a):
    spec, shots = load(a.shots, a.ids)
    if a.tier == 'standard' and not a.final:
        sys.exit('standard 是定稿等級（每秒 $0.40）：確定只重生使用者點頭的鏡頭後，再加 --final。')
    model, prices = VEO[a.tier]
    model = os.environ.get('VEO_MODEL', model)
    if a.res not in prices:
        sys.exit(f'{a.tier} 不支援 {a.res}')
    secs = {s['id']: (a.seconds or s.get('seconds', 8)) for s in shots}
    total = sum(secs.values())
    print(f'{len(shots)} 個鏡頭，共 {total} 秒，{model} {a.res}（每秒 ${prices[a.res]}）')
    guard(total * prices[a.res], a)
    ops = {}
    for s in shots:
        inst = {'prompt': spec['character'] + ' ' + s['prompt'] + ' ' + spec['style']}
        kf = os.path.join(OUT, f"{s['id']}.png")
        params = {}
        if os.path.exists(kf):
            inst['image'] = {'bytesBase64Encoded': base64.b64encode(open(kf, 'rb').read()).decode(), 'mimeType': 'image/png'}
            params['personGeneration'] = 'allow_adult'
        params |= {'aspectRatio': spec.get('aspect', '9:16'), 'durationSeconds': secs[s['id']], 'resolution': a.res,
                   'negativePrompt': spec.get('negative', '')}
        r = call('POST', f'{API}/models/{model}:predictLongRunning', {'instances': [inst], 'parameters': params}, 300)
        ops[s['id']] = r['name']
        print('送出', s['id'], r['name'])
    while ops:
        time.sleep(15)
        for sid, name in list(ops.items()):
            r = call('GET', f'{API}/{name}')
            if not r.get('done'):
                continue
            del ops[sid]
            if 'error' in r:
                print(sid, '失敗：', r['error'])
                continue
            samples = r['response'].get('generateVideoResponse', {}).get('generatedSamples', [])
            log_spend('video', model, f'{sid}/{a.res}', secs[sid] * prices[a.res])
            if not samples:
                print(sid, '沒有影片（可能被安全過濾）：', json.dumps(r['response'])[:400])
                continue
            req = urllib.request.Request(samples[0]['video']['uri'], headers={'x-goog-api-key': key()})
            open(os.path.join(OUT, f'{sid}_{a.tier}.mp4'), 'wb').write(urllib.request.urlopen(req, timeout=600).read())
            print('完成', sid)


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('cmd', choices=['models', 'keyframe', 'gen', 'spend'])
    p.add_argument('shots', nargs='?')
    p.add_argument('ids', nargs='*')
    p.add_argument('--tier', choices=list(VEO), default='lite')
    p.add_argument('--res', default='720p')
    p.add_argument('--seconds', type=int, choices=[4, 6, 8], default=4, help='試片預設 4 秒；定稿用 --seconds 8')
    p.add_argument('--pro', action='store_true', help='首格改用 Nano Banana Pro（較貴）')
    p.add_argument('--redo', action='store_true', help='已存在的首格也重做')
    p.add_argument('--final', action='store_true', help='允許 standard 等級')
    p.add_argument('--budget', type=float, default=2.0, help='這一次指令的花費上限（美元）')
    p.add_argument('--yes', action='store_true', help='確認送出（付費）')
    a = p.parse_args()
    if a.cmd == 'models':
        for m in models():
            if 'veo' in m['name'] or 'image' in m['name']:
                print(m['name'], m.get('displayName', ''))
    elif a.cmd == 'spend':
        spend()
    elif a.cmd == 'keyframe':
        keyframe(a)
    elif a.cmd == 'gen':
        gen(a)
