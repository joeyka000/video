"""iCloud 照片分享連結（share.icloud.com/photos/<代碼>）→ 原檔下載；對方還在上傳時自動等。
走 CloudKit 公開 API（跟 icloud.com 網頁一樣）：records/resolve 拿匿名 token 與 zone → records/query 列資產 → 原檔下載網址。

  python icloud.py https://share.icloud.com/photos/095b8AfRpARzH2_3MbJ0jrsEA -o projects/<案名>/media
  python icloud.py <網址> -o media --wait 120      # 相簿顯示「正在上傳」時每分鐘再查一次，最多等 120 分鐘

輸出：<out>/<原始檔名>（已存在且大小相同就跳過）、<out>/icloud.json（檔名、大小、拍攝時間、長度、寬高）。
相簿頁面寫「Please check back soon… is uploading」＝資產還沒進 zone：查得到的張數會一張張增加，原檔一出現就先下載。
"""
import argparse
import base64
import datetime
import json
import os
import re
import subprocess
import sys
import time
from urllib.parse import quote

RESOLVE = 'https://ckdatabasews.icloud.com/database/1/com.apple.photos.cloud/production/public/records/resolve?remapEnums=true&getCurrentSyncToken=true'


def post(url, body):
    r = subprocess.run(['curl', '-sS', '--max-time', '60', '-X', 'POST', url, '-H', 'Content-Type: text/plain',
                        '-H', 'Origin: https://www.icloud.com', '--data', json.dumps(body)], capture_output=True, text=True)
    return json.loads(r.stdout)


def token_of(s):
    m = re.search(r'photos/(?:#)?([A-Za-z0-9_-]{10,})', s)
    return m.group(1) if m else s


def listing(guid):
    r = post(RESOLVE, {'shortGUIDs': [{'value': guid, 'shouldFetchRootRecord': True}]})['results'][0]
    root = r.get('rootRecord', {}).get('fields', {})
    want = int(root.get('assetCount', {}).get('value', 0))
    ap, zone = r['anonymousPublicAccess'], r['zoneID']
    url = ap['databasePartition'].rstrip('/') + '/database/1/com.apple.photos.cloud/production/shared/records/query' \
        '?remapEnums=true&publicAccessAuthToken=' + quote(ap['token'], safe='')
    recs, rank = [], 0
    while True:
        d = post(url, {'query': {'recordType': 'CPLAssetAndMasterByAssetDateWithoutHiddenOrDeleted', 'filterBy': [
            {'fieldName': 'startRank', 'comparator': 'EQUALS', 'fieldValue': {'value': rank, 'type': 'INT64'}},
            {'fieldName': 'direction', 'comparator': 'EQUALS', 'fieldValue': {'value': 'ASCENDING', 'type': 'STRING'}}]},
            'zoneID': zone, 'resultsLimit': 200})
        got = d.get('records', [])
        recs += got
        n_assets = sum(1 for x in got if x.get('recordType') == 'CPLAsset')
        if n_assets < 100 or not got:
            break
        rank += n_assets
    masters = {x['recordName']: x for x in recs if x.get('recordType') == 'CPLMaster'}
    assets = [x for x in recs if x.get('recordType') == 'CPLAsset']
    items = []
    for a in assets:
        m = masters.get(a['fields'].get('masterRef', {}).get('value', {}).get('recordName'))
        if not m:
            continue
        f = m['fields']
        orig = f.get('resOriginalRes', {}).get('value')
        if not orig:
            continue
        name = base64.b64decode(f['filenameEnc']['value']).decode() if 'filenameEnc' in f else m['recordName'][:12]
        ts = a['fields'].get('assetDate', {}).get('value') or f.get('originalCreationDate', {}).get('value')
        items.append(dict(name=name, size=orig['size'], url=orig['downloadURL'].replace('${f}', name),
                          taken_utc=datetime.datetime.utcfromtimestamp(ts / 1000).isoformat() + 'Z' if ts else None,
                          duration=(a['fields'].get('duration', {}).get('value') or 0) / 1000 or None,
                          w=f.get('resOriginalWidth', {}).get('value'), h=f.get('resOriginalHeight', {}).get('value')))
    return want, items


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('link')
    ap.add_argument('-o', '--out', required=True)
    ap.add_argument('--wait', type=float, default=0, help='相簿還在上傳時最多等幾分鐘（每分鐘查一次）')
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    guid, t0 = token_of(a.link), time.time()
    while True:
        want, items = listing(guid)
        for it in items:
            dst = os.path.join(a.out, it['name'])
            if os.path.exists(dst) and os.path.getsize(dst) == it['size']:
                continue
            print(f"下載 {it['name']}  {it['size'] / 1e9:.2f} GB", flush=True)
            subprocess.run(['curl', '-sS', '-L', '--retry', '5', '-C', '-', '--max-time', '7200', '-o', dst, it['url']], check=True)
        json.dump([{k: v for k, v in it.items() if k != 'url'} for it in items], open(os.path.join(a.out, 'icloud.json'), 'w'),
                  ensure_ascii=False, indent=1)
        print(f'{time.strftime("%H:%M:%S")} 相簿 {want} 個，已下載 {len(items)} 個', flush=True)
        if len(items) >= want or time.time() - t0 > a.wait * 60:
            break
        time.sleep(60)
    if len(items) < want:
        sys.exit(f'還有 {want - len(items)} 個在上傳：稍後再跑一次（已下載的會跳過）')


if __name__ == '__main__':
    main()
