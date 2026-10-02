// anime-fx.js — 日系動畫演出效果（Canvas 2D）
// 每個函式的畫面只由引數 t（秒）決定，不累加狀態，可直接用在 render(t)。
// 用法：<script src="anime-fx.js"></script> 之後用 AFX.xxx(ctx, t, {...})。
// 對照說明見 ../references/anime.md
(() => {
  const TAU = Math.PI * 2;
  const clamp = (x, a = 0, b = 1) => Math.min(b, Math.max(a, x));
  const lerp = (a, b, u) => a + (b - a) * u;
  const ease = {
    outCubic: u => 1 - Math.pow(1 - clamp(u), 3),
    outBack: u => { u = clamp(u); const s = 1.70158; return 1 + (s + 1) * Math.pow(u - 1, 3) + s * Math.pow(u - 1, 2); },
    inCubic: u => Math.pow(clamp(u), 3),
  };
  // 可重現的亂數：同一個 seed 永遠同一串數字
  function rng(seed) {
    let s = (Math.floor(seed) * 2654435761) >>> 0 || 1;
    return () => { s ^= s << 13; s >>>= 0; s ^= s >>> 17; s ^= s << 5; s >>>= 0; return s / 4294967296; };
  }
  const size = c => [c.canvas.width, c.canvas.height];

  // 2コマ打ち／3コマ打ち：把時間量化成 24fps 下每 n 格一張，做出手繪動畫的頓挫感
  const onTwos = (t, n = 2, base = 24) => Math.floor(t * base / n) * n / base;

  // 集中線：從畫面外往中心收的放射線，重點處留白。每秒換 fps 次線條（預設 12，像手繪）
  function speedLines(c, t, o = {}) {
    const [W, H] = size(c), cx = o.x ?? W / 2, cy = o.y ?? H / 2, R = Math.hypot(W, H);
    const n = o.n ?? 110, r0 = o.r0 ?? Math.min(W, H) * 0.28, r = rng(Math.floor(t * (o.fps ?? 12)) + (o.seed ?? 1));
    c.save(); c.fillStyle = o.color ?? '#111'; c.globalAlpha = o.alpha ?? 1;
    for (let i = 0; i < n; i++) {
      const a = r() * TAU, w = (0.002 + r() * 0.011) * (o.width ?? 1), rr = r0 * (0.75 + r() * 0.7);
      c.beginPath();
      c.moveTo(cx + Math.cos(a) * rr, cy + Math.sin(a) * rr);
      c.lineTo(cx + Math.cos(a - w) * R, cy + Math.sin(a - w) * R);
      c.lineTo(cx + Math.cos(a + w) * R, cy + Math.sin(a + w) * R);
      c.fill();
    }
    c.restore();
  }

  // 流線：水平（或指定角度）的速度線，表現高速移動；背景往反方向流
  function streaks(c, t, o = {}) {
    const [W, H] = size(c), r = rng(Math.floor(t * (o.fps ?? 12)) + (o.seed ?? 5));
    c.save(); c.translate(W / 2, H / 2); c.rotate(o.angle ?? 0); c.fillStyle = o.color ?? '#fff'; c.globalAlpha = o.alpha ?? 0.8;
    const D = Math.hypot(W, H);
    for (let i = 0; i < (o.n ?? 45); i++) {
      const y = (r() - 0.5) * D, h = 1 + r() * (o.thick ?? 6), x = (r() - 0.5) * D, w = 200 + r() * 900;
      c.fillRect(x - w / 2, y, w, h);
    }
    c.restore();
  }

  // 放射背景（サンバースト）：角色登場、必殺技的背景
  function sunburst(c, t, o = {}) {
    const [W, H] = size(c), cx = o.x ?? W / 2, cy = o.y ?? H / 2, n = o.n ?? 24, R = Math.hypot(W, H);
    const rot = t * (o.speed ?? 0.25);
    c.save(); c.fillStyle = o.bg ?? '#FFD23F'; c.fillRect(0, 0, W, H); c.fillStyle = o.color ?? '#FF8C1A';
    for (let i = 0; i < n; i += 2) {
      const a0 = rot + i * TAU / n, a1 = rot + (i + 1) * TAU / n;
      c.beginPath(); c.moveTo(cx, cy); c.lineTo(cx + Math.cos(a0) * R, cy + Math.sin(a0) * R); c.lineTo(cx + Math.cos(a1) * R, cy + Math.sin(a1) * R); c.fill();
    }
    c.restore();
  }

  // 畫面震動（日文術語見 references/anime.md 的 AFX.shake 列）：整個畫面抖動。回傳 [dx, dy]，在畫主體前 ctx.translate(dx, dy)
  // amp 為畫素幅度，decay 為從 t0 起衰減的秒數（0 = 不衰減）
  function shake(t, o = {}) {
    const t0 = o.t0 ?? 0, amp = o.amp ?? 24, fps = o.fps ?? 24;
    if (t < t0) return [0, 0];
    const k = o.decay ? Math.max(0, 1 - (t - t0) / o.decay) : 1, r = rng(Math.floor(t * fps) + 7);
    return [(r() * 2 - 1) * amp * k, (r() * 2 - 1) * amp * k];
  }

  // 白閃（フラッシュ）：t0 瞬間全白後快速消退。beat 用時可每拍呼叫
  function flash(c, t, t0, o = {}) {
    const d = t - t0; if (d < 0 || d > (o.dur ?? 0.25)) return;
    const [W, H] = size(c); c.save(); c.globalAlpha = (o.max ?? 0.9) * (1 - d / (o.dur ?? 0.25)); c.fillStyle = o.color ?? '#fff'; c.fillRect(0, 0, W, H); c.restore();
  }

  // 衝擊格（インパクトフレーム）：把目前畫面轉成高反差黑白反轉，只維持 2–4 格
  // 先畫好整張畫面，再呼叫；active 為 true 時才套用
  function impactFrame(c, active, o = {}) {
    if (!active) return;
    const [W, H] = size(c), tmp = document.createElement('canvas'); tmp.width = W; tmp.height = H;
    tmp.getContext('2d').drawImage(c.canvas, 0, 0);
    c.save(); c.filter = `grayscale(1) contrast(${o.contrast ?? 12})${o.invert === false ? '' : ' invert(1)'}`;
    c.drawImage(tmp, 0, 0); c.restore();
    if (o.tint) { c.save(); c.globalCompositeOperation = 'multiply'; c.fillStyle = o.tint; c.fillRect(0, 0, W, H); c.restore(); }
  }

  // 透過光：光點＋十字星芒，mix 為 screen 疊加。用於刀光、眼神光、水面反光
  function tokaLight(c, x, y, t, o = {}) {
    const r = o.r ?? 60, pulse = 1 + 0.15 * Math.sin(t * (o.pulse ?? 10)), col = o.color ?? '255,240,200';
    c.save(); c.globalCompositeOperation = 'screen';
    const g = c.createRadialGradient(x, y, 0, x, y, r * 3 * pulse);
    g.addColorStop(0, `rgba(${col},1)`); g.addColorStop(0.15, `rgba(${col},0.6)`); g.addColorStop(1, `rgba(${col},0)`);
    c.fillStyle = g; c.fillRect(x - r * 4, y - r * 4, r * 8, r * 8);
    c.translate(x, y); c.rotate(o.rot ?? 0);
    const lines = Math.max(1, Math.round((o.rays ?? 4) / 2)), L = r * (o.len ?? 7) * pulse;
    for (let k = 0; k < lines; k++) {
      const sg = c.createLinearGradient(-L, 0, L, 0);
      sg.addColorStop(0, `rgba(${col},0)`); sg.addColorStop(0.5, `rgba(${col},0.95)`); sg.addColorStop(1, `rgba(${col},0)`);
      c.fillStyle = sg; c.beginPath(); c.moveTo(-L, 0); c.lineTo(0, -r * 0.08); c.lineTo(L, 0); c.lineTo(0, r * 0.08); c.fill();
      c.rotate(Math.PI / lines);
    }
    c.restore();
  }

  // 閃爍星點（キラキラ）：四角星，數量與位置固定，亮度依 t 閃動
  function sparkles(c, t, o = {}) {
    const [W, H] = size(c), r = rng(o.seed ?? 11), n = o.n ?? 30;
    c.save(); c.fillStyle = o.color ?? '#fff';
    for (let i = 0; i < n; i++) {
      const x = (o.box ? o.box[0] + r() * o.box[2] : r() * W), y = (o.box ? o.box[1] + r() * o.box[3] : r() * H);
      const ph = r() * TAU, sp = 4 + r() * 6, s = (o.size ?? 18) * (0.4 + r() * 0.8) * Math.max(0, Math.sin(t * sp + ph));
      if (s < 1) continue;
      c.globalAlpha = 0.9; c.beginPath();
      c.moveTo(x, y - s); c.quadraticCurveTo(x, y, x + s, y); c.quadraticCurveTo(x, y, x, y + s); c.quadraticCurveTo(x, y, x - s, y); c.quadraticCurveTo(x, y, x, y - s); c.fill();
    }
    c.restore();
  }

  // パラ：畫面上疊一層漸層（上暗下亮或斜光），做空氣感、時段感
  function para(c, o = {}) {
    const [W, H] = size(c), a = o.angle ?? Math.PI / 2, cx = W / 2, cy = H / 2, L = Math.hypot(W, H) / 2;
    const g = c.createLinearGradient(cx - Math.cos(a) * L, cy - Math.sin(a) * L, cx + Math.cos(a) * L, cy + Math.sin(a) * L);
    g.addColorStop(0, o.from ?? 'rgba(40,20,90,0.55)'); g.addColorStop(1, o.to ?? 'rgba(255,170,90,0)');
    c.save(); c.globalCompositeOperation = o.blend ?? 'multiply'; c.fillStyle = g; c.fillRect(0, 0, W, H); c.restore();
  }

  // 網點（スクリーントーン）：45° 網點，density(x,y) 回傳 0–1 決定點大小
  function screentone(c, box, o = {}) {
    const [x0, y0, w, h] = box, step = o.step ?? 14, ang = o.angle ?? Math.PI / 4, ca = Math.cos(ang), sa = Math.sin(ang);
    const cx = x0 + w / 2, cy = y0 + h / 2, R = Math.hypot(w, h), dens = o.density ?? (() => 0.5);
    c.save(); c.beginPath(); c.rect(x0, y0, w, h); c.clip(); c.fillStyle = o.color ?? '#111'; c.beginPath();
    for (let v = -R / 2; v < R / 2; v += step) for (let u = -R / 2; u < R / 2; u += step) {
      const x = cx + u * ca - v * sa, y = cy + u * sa + v * ca, k = clamp(dens(x, y));
      if (k <= 0.02) continue; const rr = step * 0.55 * Math.sqrt(k); c.moveTo(x + rr, y); c.arc(x, y, rr, 0, TAU);
    }
    c.fill(); c.restore();
  }

  // 撕裂＋色偏（グリッチ）：拍點瞬間橫向帶狀錯位＋RGB 分離，strength 0–1
  function tear(c, t, strength, o = {}) {
    if (strength <= 0) return;
    const [W, H] = size(c), r = rng(Math.floor(t * (o.fps ?? 30)) + 3), tmp = document.createElement('canvas');
    tmp.width = W; tmp.height = H; tmp.getContext('2d').drawImage(c.canvas, 0, 0);
    const bands = o.bands ?? 9;
    for (let i = 0; i < bands; i++) {
      const y = r() * H, h = 8 + r() * H * 0.08, dx = (r() * 2 - 1) * 120 * strength;
      c.drawImage(tmp, 0, y, W, h, dx, y, W, h);
    }
    // RGB 分離：拆出三個通道，紅往左、藍往右，再用 lighter 加回來
    const s = (o.shift ?? 18) * strength, torn = document.createElement('canvas');
    torn.width = W; torn.height = H; torn.getContext('2d').drawImage(c.canvas, 0, 0);
    const chan = col => {
      const k = document.createElement('canvas'); k.width = W; k.height = H; const g = k.getContext('2d');
      g.drawImage(torn, 0, 0); g.globalCompositeOperation = 'multiply'; g.fillStyle = col; g.fillRect(0, 0, W, H); return k;
    };
    c.save(); c.fillStyle = '#000'; c.fillRect(0, 0, W, H); c.globalCompositeOperation = 'lighter';
    c.drawImage(chan('#f00'), -s, 0); c.drawImage(chan('#0f0'), 0, 0); c.drawImage(chan('#00f'), s, 0);
    c.restore();
  }

  // 砸字：文字從放大狀態砸進畫面並回彈（擬音字「ドン」「ゴゴゴ」、標題都可用）
  function slam(c, text, x, y, t, t0, o = {}) {
    if (t < t0 || (o.t1 != null && t > o.t1)) return;
    const u = clamp((t - t0) / (o.dur ?? 0.14)), s = lerp(o.from ?? 2.6, 1, ease.outBack(u)), fs = o.size ?? 160;
    c.save(); c.translate(x, y); c.rotate(o.rot ?? -0.08); c.scale(s * (o.sx ?? 1), s);
    c.font = `${o.weight ?? 900} ${fs}px ${o.font ?? '"Noto Sans TC", "Noto Sans CJK TC", sans-serif'}`;
    c.textAlign = 'center'; c.textBaseline = 'middle'; c.lineJoin = 'round'; c.globalAlpha = clamp(u * 3);
    if (o.shadow !== false) { c.fillStyle = o.shadow ?? '#111'; c.fillText(text, fs * 0.06, fs * 0.07); }
    c.lineWidth = o.stroke ?? fs * 0.12; c.strokeStyle = o.strokeColor ?? '#111'; c.strokeText(text, 0, 0);
    c.fillStyle = o.color ?? '#fff'; c.fillText(text, 0, 0);
    c.restore();
  }

  // 直書き標題：直排文字逐字出現，英數與「ー」自動轉 90°
  function tategaki(c, text, x, y, t, t0, o = {}) {
    const fs = o.size ?? 90, per = o.per ?? 0.06, chars = [...text];
    c.save(); c.font = `${o.weight ?? 900} ${fs}px ${o.font ?? '"Noto Serif TC", "Noto Serif CJK TC", serif'}`;
    c.fillStyle = o.color ?? '#fff'; c.textAlign = 'center'; c.textBaseline = 'middle';
    let yy = y;
    chars.forEach((ch, i) => {
      const u = clamp((t - t0 - i * per) / 0.12); if (u <= 0) return;
      const rot = /[A-Za-z0-9()%.\-!?]/.test(ch) || 'ー〜'.includes(ch);
      c.save(); c.globalAlpha = u; c.translate(x, yy + fs / 2); if (rot) c.rotate(Math.PI / 2); c.scale(1, lerp(1.4, 1, ease.outCubic(u))); c.fillText(ch, 0, 0); c.restore();
      yy += fs * (rot ? 0.72 : 1.04);
    });
    c.restore();
  }

  // 黑底極粗明朝字卡：大小字混排、橫向壓扁（sx 0.75 左右），做章節標題、關鍵句
  // rows: [{text, x, y, size, sx, align, color}]
  function minchoCard(c, rows, o = {}) {
    const [W, H] = size(c); c.save(); c.fillStyle = o.bg ?? '#0B0A09'; c.fillRect(0, 0, W, H);
    for (const r of rows) {
      c.save(); c.translate(r.x, r.y); c.scale(r.sx ?? 0.78, 1);
      c.font = `900 ${r.size}px ${o.font ?? '"Noto Serif TC", "Noto Serif CJK TC", serif'}`;
      c.textAlign = r.align ?? 'left'; c.textBaseline = 'alphabetic'; c.fillStyle = r.color ?? o.fg ?? '#F4F0E8';
      c.fillText(r.text, 0, 0); c.restore();
    }
    c.restore();
  }

  // カットイン：斜向色帶從畫面側邊切入，drawInside(ctx, u) 在帶內畫角色或文字
  function cutIn(c, t, t0, t1, drawInside, o = {}) {
    if (t < t0 || t > t1) return;
    const [W, H] = size(c), inU = ease.outCubic((t - t0) / 0.18), outU = ease.inCubic((t - (t1 - 0.15)) / 0.15);
    const u = inU - outU, bandH = o.height ?? H * 0.38, cy = o.y ?? H / 2, skew = o.skew ?? 0.12;
    const x = lerp(o.fromRight ? W : -W, 0, clamp(u));
    c.save(); c.translate(x, 0);
    c.beginPath(); c.moveTo(0, cy - bandH / 2 + W * skew / 2); c.lineTo(W, cy - bandH / 2 - W * skew / 2); c.lineTo(W, cy + bandH / 2 - W * skew / 2); c.lineTo(0, cy + bandH / 2 + W * skew / 2); c.closePath();
    c.fillStyle = o.color ?? '#E63946'; c.fill(); c.lineWidth = o.border ?? 10; c.strokeStyle = o.borderColor ?? '#fff'; c.stroke();
    c.clip(); drawInside && drawInside(c, clamp(u)); c.restore();
  }

  // 3回PAN：同一張圖在 dur 內分三段、每段往不同方向滑一次，段與段之間硬切
  // 回傳 {dx, dy, zoom, seg}；在畫圖前 translate/scale
  function sanKaiPan(t, t0, dur, o = {}) {
    const seg = Math.min(2, Math.floor(clamp((t - t0) / dur, 0, 0.9999) * 3)), u = ((t - t0) / (dur / 3)) - seg;
    const moves = o.moves ?? [[-60, 0, 1.0], [0, -40, 1.25], [50, 20, 1.6]], [mx, my, z] = moves[seg];
    return { dx: mx * (clamp(u) - 0.5) * 2, dy: my * (clamp(u) - 0.5) * 2, zoom: z, seg };
  }

  // 止め絵＋漸變：停格時畫面輕微推近，並疊紙紋，適合情緒高點
  function paperTexture(c, t, o = {}) {
    const [W, H] = size(c), r = rng(Math.floor(onTwos(t, o.twos ?? 2) * 24) + 99);
    c.save(); c.globalAlpha = o.alpha ?? 0.08; c.fillStyle = o.color ?? '#000';
    for (let i = 0; i < (o.n ?? 1400); i++) c.fillRect(r() * W, r() * H, 1 + r() * 2, 1 + r() * 2);
    c.restore();
  }

  window.AFX = { TAU, clamp, lerp, ease, rng, onTwos, speedLines, streaks, sunburst, shake, flash, impactFrame, tokaLight, sparkles, para, screentone, tear, slam, tategaki, minchoCard, cutIn, sanKaiPan, paperTexture };
})();
