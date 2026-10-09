"""真實地圖運鏡（seek(t) 純函式）：衛星底圖拼接、連續縮放、俯仰傾斜、航線、地標。

旅行片「從 A 飛到 B」「今天去了哪裡」用真的地球，不用假地圖或向量示意圖。
底圖來源（畫面角落或片尾一定要標註 credit）：
  s2     Sentinel-2 cloudless 2021（EOX，CC BY-NC-SA 4.0：只能非商用）  z ≤ 14，約 10 m/px
  bm     NASA Blue Marble 地形＋海底地形（公有領域）                   z ≤ 8
  night  NASA VIIRS 夜間燈光 2012（公有領域）                          z ≤ 8
  osm    OpenStreetMap 標準圖（© OpenStreetMap contributors，量少才可）z ≤ 19
  （CARTO 現在要 API key；Esri 衛星圖授權要帳號，不用）
快取：~/video-lab/cache/tiles/<來源>/<z>/<x>/<y>；渲染前先 prefetch()，平行渲染時才不會每個行程都去抓。

  import mapfx as M
  cam = M.fly(M.TPE, M.DPS, u, z0=5.2, z1=9.5)           # 先拉高再降落的平滑飛行（van Wijk–Nuij）
  img, P = M.view('s2', cam, W, H, tilt=38)               # P(lat, lon) → (x, y, 透視縮放) 或 None（在地平線後面）
  M.arc(img, P, M.TPE, M.DPS, u)                          # 航線：發光的大圓弧，畫到 u
  M.pin(img, P, *M.DPS, e, '峇里島', 'BALI')               # 地標：落點脈衝＋引線＋字
  python mapfx.py demo -o /tmp/map.jpg                    # 自我測試：飛行的 6 個時間點
"""
import functools
import math
import os
import sys
import threading
import time
import urllib.request

import cv2
import numpy as np

CACHE = os.path.expanduser('~/video-lab/cache/tiles')
UA = 'video-lab/1.0 (personal travel video renderer)'
SOURCES = {
    's2': dict(url='https://tiles.maps.eox.at/wmts/1.0.0/s2cloudless-2021_3857/default/g/{z}/{y}/{x}.jpg', maxz=14,
               credit='Sentinel-2 cloudless 2021 by EOX (Copernicus Sentinel data 2021)'),
    'bm': dict(url='https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/BlueMarble_ShadedRelief_Bathymetry/default/'
                   'GoogleMapsCompatible_Level8/{z}/{y}/{x}.jpeg', maxz=8, credit='NASA Blue Marble'),
    'night': dict(url='https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/VIIRS_CityLights_2012/default/'
                      'GoogleMapsCompatible_Level8/{z}/{y}/{x}.jpeg', maxz=8, credit='NASA Earth Observatory / VIIRS'),
    'osm': dict(url='https://tile.openstreetmap.org/{z}/{x}/{y}.png', maxz=19, credit='© OpenStreetMap contributors'),
}
TPE = (25.0777, 121.2328)   # 桃園機場
DPS = (-8.7482, 115.1675)   # 峇里島 伍拉·賴機場
GOLD = (1.00, 0.84, 0.45)
WHITE = (1.0, 1.0, 1.0)


# ───────── 投影 ─────────
def merc(lat, lon):
    """經緯度 → 正規化 Web Mercator（0–1）。"""
    x = (lon + 180.0) / 360.0
    s = math.sin(math.radians(max(-85.0, min(85.0, lat))))
    y = 0.5 - math.log((1 + s) / (1 - s)) / (4 * math.pi)
    return x, y


def unmerc(x, y):
    lon = x * 360.0 - 180.0
    lat = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * y))))
    return lat, lon


def slerp(a, b, u):
    """大圓上的插值（航線）。"""
    def vec(p):
        la, lo = map(math.radians, p)
        return np.array([math.cos(la) * math.cos(lo), math.cos(la) * math.sin(lo), math.sin(la)])
    va, vb = vec(a), vec(b)
    om = math.acos(max(-1.0, min(1.0, float(va @ vb))))
    if om < 1e-9:
        return a
    v = (math.sin((1 - u) * om) * va + math.sin(u * om) * vb) / math.sin(om)
    return math.degrees(math.asin(v[2])), math.degrees(math.atan2(v[1], v[0]))


# ───────── 相機 ─────────
def cam(lat, lon, z, bearing=0.0):
    x, y = merc(lat, lon)
    return dict(x=x, y=y, z=float(z), bearing=float(bearing))


def fly(a, b, u, z0, z1, rho=1.35, W=1080, pad=0.0):
    """從 a（lat, lon, 縮放 z0）飛到 b（z1）：van Wijk–Nuij 平滑縮放路徑（先拉高看全貌再降落，跟 d3.interpolateZoom 同一條公式）。
    u 0–1（自己套緩動）。w＝畫面寬對應的世界寬。"""
    ax, ay = merc(*a[:2])
    bx, by = merc(*b[:2])
    w0, w1 = W / (256 * 2 ** z0), W / (256 * 2 ** z1)
    dx, dy = bx - ax, by - ay
    d2 = dx * dx + dy * dy
    d1 = math.sqrt(d2)
    if d1 < 1e-12:
        S = math.log(w1 / w0) / rho
        w = w0 * math.exp(rho * u * S)
        return dict(x=ax, y=ay, z=math.log2(W / (256 * w)), bearing=0.0)
    b0 = (w1 * w1 - w0 * w0 + rho ** 4 * d2) / (2 * w0 * rho * rho * d1)
    b1 = (w1 * w1 - w0 * w0 - rho ** 4 * d2) / (2 * w1 * rho * rho * d1)
    r0 = math.log(math.sqrt(b0 * b0 + 1) - b0)
    r1 = math.log(math.sqrt(b1 * b1 + 1) - b1)
    S = (r1 - r0) / rho
    s = u * S
    coshr0 = math.cosh(r0)
    k = w0 / (rho * rho * d1) * (coshr0 * math.tanh(rho * s + r0) - math.sinh(r0))
    w = w0 * coshr0 / math.cosh(rho * s + r0)
    return dict(x=ax + k * dx, y=ay + k * dy, z=math.log2(W / (256 * w)), bearing=0.0)


def lerp_cam(c0, c1, u):
    return dict(x=c0['x'] + (c1['x'] - c0['x']) * u, y=c0['y'] + (c1['y'] - c0['y']) * u, z=c0['z'] + (c1['z'] - c0['z']) * u,
                bearing=c0.get('bearing', 0) + (c1.get('bearing', 0) - c0.get('bearing', 0)) * u)


# ───────── 圖磚 ─────────
_lock = threading.Lock()


def _path(src, z, x, y):
    return os.path.join(CACHE, src, str(z), str(x), f'{y}.img')


def fetch(src, z, x, y, retries=3):
    p = _path(src, z, x, y)
    if os.path.exists(p):
        return p
    os.makedirs(os.path.dirname(p), exist_ok=True)
    url = SOURCES[src]['url'].format(z=z, x=x, y=y)
    for k in range(retries):
        try:
            data = urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': UA}), timeout=30).read()
            tmp = f'{p}.{os.getpid()}.tmp'
            with open(tmp, 'wb') as f:
                f.write(data)
            os.replace(tmp, p)
            return p
        except Exception as e:  # noqa: BLE001
            if k == retries - 1:
                print(f'mapfx: 抓不到 {url}: {e}', file=sys.stderr)
            time.sleep(1.5 * (k + 1))
    return None


@functools.lru_cache(maxsize=1500)
def tile(src, z, x, y):
    n = 2 ** z
    x %= n
    if not (0 <= y < n):
        return None
    p = fetch(src, z, x, y)
    if p is None:
        return None
    im = cv2.imread(p, cv2.IMREAD_COLOR)
    if im is None:
        return None
    if im.shape[:2] != (256, 256):
        im = cv2.resize(im, (256, 256), interpolation=cv2.INTER_AREA)
    return im[..., ::-1].copy()   # RGB uint8


# ───────── 畫面 ─────────
def _tilt_h(W, H, tilt, D):
    """地面（以畫面中心為原點、單位＝畫面像素）→ 螢幕的單應矩陣。tilt＝俯仰角（0＝正上方往下看）。"""
    s, c = math.sin(math.radians(tilt)), math.cos(math.radians(tilt))
    return np.array([[D, -(W / 2) * s, (W / 2) * D], [0, D * c - (H / 2) * s, (H / 2) * D], [0, -s, D]], np.float64)


def _ground_m(cm, z_px, W, H, tilt, D, cy_off):
    """世界像素（縮放 z_px 的像素格）→ 螢幕。cy_off：目標點在畫面上的垂直位置（0.5＝正中）。"""
    s = 2 ** (cm['z'] - z_px)
    b = math.radians(cm.get('bearing', 0.0))
    n = 256 * 2 ** z_px
    T = np.array([[1, 0, -cm['x'] * n], [0, 1, -cm['y'] * n], [0, 0, 1]], np.float64)
    R = np.array([[math.cos(b) * s, math.sin(b) * s, 0], [-math.sin(b) * s, math.cos(b) * s, 0], [0, 0, 1]], np.float64)
    Ht = _tilt_h(W, H, tilt, D)
    Sh = np.array([[1, 0, 0], [0, 1, (cy_off - 0.5) * H], [0, 0, 1]], np.float64)
    return Sh @ Ht @ R @ T


def _bounds(cm, L, W, H, tilt, D, cy_off, far=3.0, nx=5, ny=9):
    """這一層要用到的圖磚範圍 (x0, y0, x1, y1)：螢幕格點反推到地面；地平線以上的點換成 far 倍距離的遠點。"""
    M = _ground_m(cm, L, W, H, tilt, D, cy_off)
    Mi = np.linalg.inv(M)
    pts, sky = [], False
    for sx in np.linspace(0, W, nx):
        for sy in np.linspace(0, H, ny):
            g = Mi @ np.array([sx, sy, 1.0])
            if g[2] > 1e-9:
                pts.append(g[:2] / g[2])
            else:
                sky = True
    if sky and tilt > 0:
        n = 256 * 2 ** L
        sc = 2 ** (cm['z'] - L)
        b = math.radians(cm.get('bearing', 0.0))
        s = math.sin(math.radians(tilt))
        gy = D * (1 - far) / s
        for side in (-1, 0, 1):
            gx = side * W * 0.5 * far
            pts.append(np.array([(math.cos(b) * gx - math.sin(b) * gy) / sc + cm['x'] * n,
                                 (math.sin(b) * gx + math.cos(b) * gy) / sc + cm['y'] * n]))
    pts = np.array(pts)
    n_t = 2 ** L
    x0, y0 = np.floor(pts.min(0) / 256).astype(int) - 1
    x1, y1 = np.floor(pts.max(0) / 256).astype(int) + 1
    cxl, cyl = int(cm['x'] * n_t), int(cm['y'] * n_t)
    x0, x1 = max(x0, cxl - 12), min(x1, cxl + 12)        # 安全上限：一層最多 25×25 磚
    y0, y1 = max(y0, cyl - 12, 0), min(y1, cyl + 12, n_t - 1)
    return M, x0, y0, x1, y1


def _render_level(src, cm, L, W, H, tilt, D, cy_off, far):
    M, x0, y0, x1, y1 = _bounds(cm, L, W, H, tilt, D, cy_off, far)
    patch = np.zeros(((y1 - y0 + 1) * 256, (x1 - x0 + 1) * 256, 3), np.uint8)
    for ty in range(y0, y1 + 1):
        for tx in range(x0, x1 + 1):
            im = tile(src, L, tx, ty)
            if im is not None:
                patch[(ty - y0) * 256:(ty - y0 + 1) * 256, (tx - x0) * 256:(tx - x0 + 1) * 256] = im
    Tm = np.array([[1, 0, x0 * 256], [0, 1, y0 * 256], [0, 0, 1]], np.float64)
    out = cv2.warpPerspective(patch, M @ Tm, (W, H), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
    return out.astype(np.float32) / 255


def needed(src, cm, W, H, tilt=0.0, D=None, cy_off=0.5, far=3.0):
    """這個相機會用到的圖磚 (z, x, y)（prefetch 用）。"""
    D = D or 1.25 * H
    maxz = SOURCES[src]['maxz']
    Lf = max(0, min(maxz, int(math.floor(cm['z']))))
    out = set()
    for L in {Lf, min(maxz, Lf + 1)}:
        _, x0, y0, x1, y1 = _bounds(cm, L, W, H, tilt, D, cy_off, far)
        out |= {(L, x % 2 ** L, y) for x in range(x0, x1 + 1) for y in range(y0, y1 + 1)}
    return out


def prefetch(src, cams, W, H, tilt=0.0, workers=4, **kw):
    """把一串相機要用的圖磚先抓進快取（OSM 規定最多 2 條連線，會自動降）。"""
    from concurrent.futures import ThreadPoolExecutor
    need = set()
    for cm in cams:
        need |= needed(src, cm, W, H, tilt, **kw)
    todo = [k for k in need if not os.path.exists(_path(src, *k))]
    if src == 'osm':
        workers = min(workers, 2)
    with ThreadPoolExecutor(workers) as ex:
        list(ex.map(lambda k: fetch(src, *k), todo))
    return len(need), len(todo)


def view(src, cm, W, H, tilt=0.0, D=None, cy_off=0.5, haze=0.55, sky=(0.62, 0.74, 0.90), far=3.0, dof=0.0):
    """渲染一格地圖。回傳 (float32 RGB, P)；P(lat, lon) → (x, y, 縮放) 或 None。
    縮放在兩層圖磚之間做三線性混合（放大縮小都連續、不閃）；有俯仰時地平線加大氣霧，遠處加景深模糊（擋遠處縮小的閃爍）。"""
    D = D or 1.25 * H
    maxz = SOURCES[src]['maxz']
    z = cm['z']
    L = int(math.floor(z))
    f = z - L
    if L >= maxz:
        img = _render_level(src, cm, maxz, W, H, tilt, D, cy_off, far)
    elif L < 0:
        img = _render_level(src, cm, 0, W, H, tilt, D, cy_off, far)
    else:
        img = _render_level(src, cm, L, W, H, tilt, D, cy_off, far)
        if f > 0.02:
            b = _render_level(src, cm, L + 1, W, H, tilt, D, cy_off, far)
            img = img * (1 - f) + b * f
    if tilt > 0:
        s, c_ = math.sin(math.radians(tilt)), math.cos(math.radians(tilt))
        a = np.arange(H, dtype=np.float64) - cy_off * H            # 相對目標點那一列
        den = D * c_ + a * s
        ok = den > 1e-6                                             # 地平線以下
        r = np.where(ok, D * c_ / np.maximum(den, 1e-6), 1e6)      # 距離比：目標點＝1，越遠越大
        fog = np.where(ok, 1 - np.exp(-haze * np.maximum(r - 1, 0)), 1.0).astype(np.float32)[:, None, None]
        if dof > 0:
            bl = cv2.GaussianBlur(img, (0, 0), dof)
            k = np.clip(np.abs(np.log(np.maximum(r, 1e-6))) / 0.5, 0, 1).astype(np.float32)[:, None, None]  # 遠處與最近處都糊（移軸感）
            img = img * (1 - k) + bl * k
        img = img * (1 - fog) + np.float32(sky) * fog
    Mz = _ground_m(cm, cm['z'], W, H, tilt, D, cy_off)
    n = 256 * 2 ** cm['z']

    def P(lat, lon):
        x, y = merc(lat, lon)
        g = Mz @ np.array([x * n, y * n, 1.0])
        if g[2] <= 1e-6:
            return None
        sc = _scale_at(Mz, x * n, y * n, D, tilt, cm)
        return g[0] / g[2], g[1] / g[2], sc
    return np.clip(img, 0, 1), P


def _scale_at(Mz, wx, wy, D, tilt, cm):
    a = Mz @ np.array([wx, wy, 1.0])
    b = Mz @ np.array([wx + 1.0, wy, 1.0])
    return float(math.hypot(b[0] / b[2] - a[0] / a[2], b[1] / b[2] - a[1] / a[2]))


# ───────── 調色：讓衛星圖跟片子同一個世界 ─────────
def grade(img, mood='dusk', k=1.0):
    """衛星圖原色偏灰綠、海很黑：加對比、海面帶一點青藍、陸地暖一點；dusk＝傍晚的暖光斜照、night＝藍調。"""
    x = img.astype(np.float32)
    L = x @ np.float32([0.2126, 0.7152, 0.0722])
    water = np.clip((0.16 - L) / 0.10, 0, 1)[..., None] * np.clip((x[..., 2] - x[..., 0] + 0.02) / 0.06, 0, 1)[..., None]
    y = np.clip((x - 0.03) * 1.18, 0, 1) ** 0.92
    y = y * (1 - water) + (y * np.float32([0.55, 0.95, 1.25]) + np.float32([0.0, 0.03, 0.07])) * water
    if mood == 'dusk':
        y = y * np.float32([1.06, 0.98, 0.88]) + np.float32([0.02, 0.008, 0.0])
    elif mood == 'night':
        y = y * np.float32([0.55, 0.65, 0.95])
    return np.clip(x * (1 - k) + y * k, 0, 1)


# ───────── 疊加：航線、地標、字 ─────────
def _poly(c, pts, col, width, glow, k, u_alpha=None):
    if len(pts) < 2 or k <= 0:
        return
    h, w = c.shape[:2]
    S = 4
    lay = np.zeros((h, w), np.float32)
    p = np.round(np.array(pts) * S).astype(np.int32).reshape(-1, 1, 2)
    cv2.polylines(lay, [p], False, 1.0, max(1, int(width * S)), cv2.LINE_AA, shift=2)
    if glow > 0:
        g = cv2.GaussianBlur(lay, (0, 0), glow)
        c += (g * 0.9 * k)[..., None] * np.float32(col)
    c[:] = c * (1 - (lay * k)[..., None]) + (lay * k)[..., None] * np.float32([min(1, x * 0.35 + 0.75) for x in col])


def arc(c, P, a, b, u, lift=0.18, col=GOLD, width=4.0, glow=9.0, k=1.0, n=160, head=True, dash=False):
    """大圓航線畫到 u（0–1）；lift＝弧線往畫面上方拱起的比例（像飛機飛在空中）。頭端有一顆發光的點。"""
    if u <= 0:
        return None
    pts = []
    ma, mb = merc(*a), merc(*b)
    dx, dy = mb[0] - ma[0], mb[1] - ma[1]
    chord = math.hypot(dx, dy)
    nx, ny = dy / max(chord, 1e-12), -dx / max(chord, 1e-12)
    if ny > 0:
        nx, ny = -nx, -ny   # 往北（畫面上方）拱：弧高在地圖座標裡算，縮放時形狀不變
    for i in range(n + 1):
        v = i / n * u
        mx, my = merc(*slerp(a, b, v))
        h = lift * chord * math.sin(math.pi * v)
        q = P(*unmerc(mx + nx * h, my + ny * h))
        if q is None:
            continue
        pts.append((q[0], q[1]))
    if dash:
        for i in range(0, len(pts) - 1, 6):
            _poly(c, pts[i:i + 4], col, width, glow, k)
    else:
        _poly(c, pts, col, width, glow, k)
    if head and pts:
        x, y = pts[-1]
        dot(c, x, y, 10, col, k)
        if len(pts) > 2:
            return x, y, math.atan2(pts[-1][1] - pts[-3][1], pts[-1][0] - pts[-3][0])
        return x, y, 0.0
    return None


def route(c, P, pts_ll, u, col=GOLD, width=4.0, glow=8.0, k=1.0):
    """依序連起地點（地面上的路線），畫到 u。"""
    sp = [P(*p) for p in pts_ll]
    sp = [(q[0], q[1]) for q in sp if q is not None]
    if len(sp) < 2 or u <= 0:
        return
    seg = [math.hypot(sp[i + 1][0] - sp[i][0], sp[i + 1][1] - sp[i][1]) for i in range(len(sp) - 1)]
    total = sum(seg) * min(1.0, u)
    out = [sp[0]]
    for i, s in enumerate(seg):
        if total <= 0:
            break
        f = min(1.0, total / max(s, 1e-6))
        out.append((sp[i][0] + (sp[i + 1][0] - sp[i][0]) * f, sp[i][1] + (sp[i + 1][1] - sp[i][1]) * f))
        total -= s
    _poly(c, out, col, width, glow, k)
    dot(c, out[-1][0], out[-1][1], 8, col, k)


@functools.lru_cache(maxsize=32)
def _dot_spr(r, col):
    d = int(r * 8)
    yy, xx = np.mgrid[0:d, 0:d].astype(np.float32) - d / 2
    rr = np.sqrt(xx * xx + yy * yy)
    core = np.clip(r * 0.55 - rr + 0.5, 0, 1)
    glow = np.exp(-(rr / (r * 1.3)) ** 2) * 0.85 + np.exp(-(rr / (r * 3.2)) ** 2) * 0.35
    glow *= np.clip(1 - rr / (d / 2), 0, 1) ** 2      # 精靈邊緣歸零：加光合成才不會看到方框
    rgb = np.float32(col) * glow[..., None] + core[..., None]
    return np.clip(rgb, 0, 3).astype(np.float32)


def dot(c, x, y, r, col=GOLD, k=1.0):
    from animepro import add_c
    add_c(c, _dot_spr(int(r), tuple(col)), x, y, k)


def pulse(c, x, y, e, col=GOLD, rmax=90, period=1.2, k=1.0, width=3):
    """落點的脈衝圈：每 period 秒一圈往外擴、變淡。"""
    h, w = c.shape[:2]
    lay = np.zeros((h, w), np.float32)
    for j in range(2):
        v = ((e / period) + j * 0.5) % 1.0
        if e < j * period * 0.5:
            continue
        r = 6 + rmax * (1 - (1 - v) ** 2)
        cv2.circle(lay, (int(x * 4), int(y * 4)), int(r * 4), float(1 - v), width * 4, cv2.LINE_AA, shift=2)
    c += (cv2.GaussianBlur(lay, (0, 0), 1.2) * k)[..., None] * np.float32(col)


def pin(c, P, lat, lon, e, title=None, sub=None, side=1, col=GOLD, k=1.0, lead=120, size=40, pulse_r=70, dot_r=9):
    """地標：落下的光點（第 0–0.3 秒）＋脈衝＋斜引線＋兩行字（中文名、英文小字）。e＝出現後經過秒數。"""
    q = P(lat, lon)
    if q is None or e < 0 or k <= 0:
        return
    from seekkit import ease_out
    x, y, _ = q
    a = ease_out(min(1.0, e / 0.3))
    dot(c, x, y, dot_r, col, k * a)
    if pulse_r > 0:
        pulse(c, x, y, e, col, pulse_r, 1.4, 0.8 * k * a)
    if title is None:
        return
    u = ease_out(min(1.0, max(0.0, (e - 0.12) / 0.4)))
    if u <= 0:
        return
    ex, ey = x + side * lead * 0.6 * u, y - lead * u
    _poly(c, [(x, y), (ex, ey), (ex + side * 46 * u, ey)], col, 2.0, 3.0, 0.9 * k)
    from animepro import put_text
    from seekkit import CJK_B, CJK_TC
    v = ease_out(min(1.0, max(0.0, (e - 0.3) / 0.4)))
    tx = ex + side * 58
    put_text(c, title, size, tx, ey - 4 - (1 - v) * 10, k * v, CJK_B, CJK_TC, 0.06, shadow=0.75, glow=0.12,
             align='left' if side > 0 else 'right')
    if sub:
        put_text(c, sub, int(size * 0.5), tx, ey + size * 0.78 - (1 - v) * 10, k * v * 0.9, CJK_B, CJK_TC, 0.28, col=col,
                 shadow=0.75, glow=0.0, align='left' if side > 0 else 'right')


@functools.lru_cache(maxsize=8)
def plane_sprite(size=64, col=(1.0, 1.0, 1.0)):
    """俯視的飛機剪影（朝右），4 倍超取樣。"""
    S = 4
    d = size * S
    m = np.zeros((d, d), np.uint8)
    cx, cy = d / 2, d / 2
    L = d * 0.46
    body = [(cx + L, cy), (cx + L * 0.78, cy - L * 0.07), (cx - L * 0.80, cy - L * 0.06), (cx - L * 0.95, cy),
            (cx - L * 0.80, cy + L * 0.06), (cx + L * 0.78, cy + L * 0.07)]
    wing = [(cx + L * 0.18, cy - L * 0.05), (cx - L * 0.22, cy - L * 0.92), (cx - L * 0.40, cy - L * 0.92), (cx - L * 0.12, cy - L * 0.05),
            (cx - L * 0.12, cy + L * 0.05), (cx - L * 0.40, cy + L * 0.92), (cx - L * 0.22, cy + L * 0.92), (cx + L * 0.18, cy + L * 0.05)]
    tail = [(cx - L * 0.62, cy - L * 0.04), (cx - L * 0.86, cy - L * 0.36), (cx - L * 0.96, cy - L * 0.36), (cx - L * 0.84, cy),
            (cx - L * 0.96, cy + L * 0.36), (cx - L * 0.86, cy + L * 0.36), (cx - L * 0.62, cy + L * 0.04)]
    for poly in (body, wing, tail):
        cv2.fillPoly(m, [np.int32(poly)], 255, cv2.LINE_AA)
    a = cv2.resize(m, (size, size), interpolation=cv2.INTER_AREA).astype(np.float32) / 255
    out = np.zeros((size, size, 4), np.float32)
    out[..., :3] = col
    out[..., 3] = a
    return out


def plane(c, x, y, ang, size=64, k=1.0, shadow=(14, 22)):
    """飛機（朝 ang 弧度）＋地面陰影（往右下偏移、模糊）。"""
    from seekkit import blit
    spr = plane_sprite(size)
    M = cv2.getRotationMatrix2D((size / 2, size / 2), -math.degrees(ang), 1.0)
    rs = cv2.warpAffine(spr, M, (size, size), flags=cv2.INTER_LINEAR)
    if shadow:
        sh = rs.copy()
        sh[..., :3] = 0
        sh[..., 3] = cv2.GaussianBlur(sh[..., 3], (0, 0), 3) * 0.45
        blit(c, sh, x - size / 2 + shadow[0], y - size / 2 + shadow[1], k)
    blit(c, rs, x - size / 2, y - size / 2, k)


def credit(c, text, op=0.7, size=17):
    """右下角很小的資料來源標註（地圖出現期間都要在）。"""
    from animepro import put_text
    from seekkit import CJK_R, CJK_TC
    h, w = c.shape[:2]
    put_text(c, text, size, w - 36, h - 44, op, CJK_R, CJK_TC, 0.04, shadow=0.6, glow=0.0, align='right')


# ───────── 自我測試 ─────────
def _demo(out):
    from seekkit import CJK_B  # noqa: F401
    W, H = 540, 960
    frames = []
    cams = [fly((*TPE, 0), (*DPS, 0), u, 5.0, 9.0, W=W) for u in np.linspace(0, 1, 6)]
    print('prefetch', prefetch('s2', cams, W, H, tilt=35))
    for i, u in enumerate(np.linspace(0, 1, 6)):
        cm = cams[i]
        img, P = view('s2', cm, W, H, tilt=35, dof=2.0)
        img = grade(img)
        hd = arc(img, P, TPE, DPS, max(0.02, u))
        if hd:
            plane(img, hd[0], hd[1], hd[2], 40)
        pin(img, P, *TPE, 1.0, '桃園', 'TAOYUAN', size=24)
        if u > 0.6:
            pin(img, P, *DPS, (u - 0.6) * 4, '峇里島', 'BALI', size=24)
        frames.append((np.clip(img, 0, 1) * 255).astype(np.uint8))
    sheet = np.concatenate([np.concatenate(frames[:3], 1), np.concatenate(frames[3:], 1)], 0)
    cv2.imwrite(out, sheet[..., ::-1])
    print(out)


if __name__ == '__main__':
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    if len(sys.argv) > 1 and sys.argv[1] == 'demo':
        _demo(sys.argv[sys.argv.index('-o') + 1] if '-o' in sys.argv else '/tmp/map_demo.jpg')
