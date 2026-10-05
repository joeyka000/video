"""Veo 生成工具（Gemini API，純 REST、不需額外套件）。

金鑰：讀環境變數 GEMINI_API_KEY（在雲端環境設定裡加，不要貼在對話裡）。
  python veo.py models                         列出這把金鑰能用的 Veo / 圖片模型（免費）
  python veo.py keyframe shots.json [id ...]   先用圖片模型把參考照片改成每個鏡頭的首格（付費，量小）
  python veo.py gen shots.json [id ...] --yes  生成影片（付費；沒加 --yes 只印出預估總秒數）
輸出：out/<id>.png（首格）、out/<id>.mp4（影片）。
"""
import base64
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


def pick(kind):
    names = [m['name'] for m in models()]
    if kind == 'veo':
        c = sorted([n for n in names if 'veo' in n], reverse=True)
    else:
        c = sorted([n for n in names if 'image' in n and 'gemini' in n], reverse=True)
    if not c:
        sys.exit(f'這把金鑰看不到 {kind} 模型：{names}')
    return c[0]


def load(path, ids):
    spec = json.load(open(path))
    shots = spec['shots']
    if ids:
        shots = [s for s in shots if s['id'] in ids]
    return spec, shots


def keyframe(path, ids):
    spec, shots = load(path, ids)
    model = pick('image')
    print('圖片模型：', model)
    for s in shots:
        if not s.get('ref'):
            continue
        img = base64.b64encode(open(os.path.join(HERE, s['ref']), 'rb').read()).decode()
        body = {'contents': [{'parts': [{'inline_data': {'mime_type': 'image/jpeg', 'data': img}},
                                        {'text': spec['character'] + ' ' + s['keyframe'] + ' Vertical 9:16 composition, photorealistic film still.'}]}]}
        r = call('POST', f'{API}/{model}:generateContent', body, 300)
        parts = r['candidates'][0]['content']['parts']
        data = next((p['inlineData']['data'] for p in parts if 'inlineData' in p), None)
        if not data:
            print(s['id'], '沒有回傳圖片：', [p.get('text', '')[:200] for p in parts])
            continue
        open(os.path.join(OUT, f"{s['id']}.png"), 'wb').write(base64.b64decode(data))
        print('ok', s['id'])


def gen(path, ids, yes):
    spec, shots = load(path, ids)
    total = sum(s.get('seconds', 8) for s in shots)
    print(f'{len(shots)} 個鏡頭，共 {total} 秒（Veo 依生成秒數計費，價格請看 Google AI Studio 定價頁）')
    if not yes:
        print('加上 --yes 才會真的送出。')
        return
    model = pick('veo')
    print('影片模型：', model)
    ops = {}
    for s in shots:
        inst = {'prompt': spec['character'] + ' ' + s['prompt'] + ' ' + spec['style']}
        kf = os.path.join(OUT, f"{s['id']}.png")
        if os.path.exists(kf):
            inst['image'] = {'bytesBase64Encoded': base64.b64encode(open(kf, 'rb').read()).decode(), 'mimeType': 'image/png'}
        params = {'aspectRatio': spec.get('aspect', '9:16'), 'durationSeconds': s.get('seconds', 8),
                  'negativePrompt': spec.get('negative', '')}
        r = call('POST', f'{API}/{model}:predictLongRunning', {'instances': [inst], 'parameters': params}, 300)
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
            if not samples:
                print(sid, '沒有影片（可能被安全過濾）：', json.dumps(r['response'])[:400])
                continue
            uri = samples[0]['video']['uri']
            req = urllib.request.Request(uri, headers={'x-goog-api-key': key()})
            open(os.path.join(OUT, f'{sid}.mp4'), 'wb').write(urllib.request.urlopen(req, timeout=600).read())
            print('完成', sid)


if __name__ == '__main__':
    cmd, args = sys.argv[1], [a for a in sys.argv[2:] if not a.startswith('--')]
    if cmd == 'models':
        for m in models():
            if 'veo' in m['name'] or 'image' in m['name']:
                print(m['name'], m.get('displayName', ''), m.get('supportedGenerationMethods', []))
    elif cmd == 'keyframe':
        keyframe(args[0], args[1:])
    elif cmd == 'gen':
        gen(args[0], args[1:], '--yes' in sys.argv)
