// mv-kit.js — MV 工具庫（Canvas 2D，掛在 window.MV）
// 原則：畫面全部是 t（秒）的純函式。這裡沒有 Math.random、Date.now、requestAnimationFrame，也不累加狀態，
// 所以瀏覽器預覽、render.py 逐格輸出、子格取樣動態模糊（--samples）看到的都是同一張圖。
// 用法：
//   <script src="mv-kit.js"></script>
//   MV.setData({ audio, lyrics });                        // analyze.py／align.py 產的 audio.json／lyrics.json
//   MV.setGrid({ bpm: 120, meter: 4, duration: 64 });     // 沒有資料時改用等拍格
//   const ctx = canvas.getContext('2d', MV.ctxAttrs);     // 主畫布與工具庫的離屏畫布用同一組屬性（見下「成本」）
//   const tl = MV.timeline([{ id, start, end, render(ctx, f) }, ...], { W: 1920, H: 1080 });
//   window.render = t => tl.render(ctx, t); window.CUTS = tl.cuts; window.TRANSITIONS = tl.transitions;
// 慣例：
//   錯誤與提示：render.py 只轉印 console.error 與 pageerror（console.warn 看不到），所以本檔所有「找不到／不認得」的提示
//     （MV.line 查不到歌詞、緩動名稱打錯）都用 console.error、每種只印一次；audio.json／lyrics.json 形狀不對（陣列、沒有 beats／tempo、
//     沒有 lines）時 setData 直接 throw，不靜默退回等拍格——render.py 會以 pageerror 非 0 結束，拍點全錯的片不會「成功」產出。
//     要寬鬆就自己 try／catch 後改呼叫 MV.setGrid
//   MV.audio：setData／setGrid 之前第一次讀取就自動建立 120 BPM、4/4、60 秒的等拍格，不會是 null；節拍函式同樣
//   緩動：MV.keys、MV.prog 收函式（MV.ease.outCubic）或 MV.ease 的名稱字串（'outCubic'）；不認得的字串退回預設並警告一次
//   tracking：單位是 px；要用 em 寫 size * 0.08，或改傳 trackingEm: 0.08（layout／karaoke 會乘上字級）。fitSize 的第 6 個引數
//     接同一個 tracking（數字或 px => px），算出來的字級才真的塞得進 maxW
//   MV.fps：預設 window.RENDER_FPS（render.py --fps 注入）或 30；frameIdx 的預設格率、post 的顆粒換圖、timeline 都用它。
//     頁面裡「每格換一次」的東西（抖動方向、閃爍、打字）一律 MV.frameIdx(t)，不要寫死 30，--fps 60 輸出才不會每兩格才變一次
// 成本（4 核心、swiftshader、1920×1080，mv-template.html 每格 render＋PNG 截圖，與 render.py 相同路徑；同機同時段、其他代理同時在跑）：
//   每格平均（7 個代表格）：舊版（createPattern + overlay 顆粒、GPU 畫布）0.97 秒 → 本版 0.57 秒；頁面 grain 設 0 時 0.35 秒；後製全關 0.25 秒
//   本版的做法：顆粒走 CPU 路徑（getImageData → 逐畫素加噪 → putImageData，1080p 約 23 ms）；所有畫布用 MV.ctxAttrs
//   （willReadFrequently: true）讓 Chromium 走 CPU 光柵，離屏畫布 drawImage 到主畫布不必跨 GPU 搬圖
//   頁面本身的 JS 每格只佔 25–90 ms（halation 約 16 ms）；剩下的是 render.py 的 PNG 截圖：畫面有顆粒時 PNG 壓不下去，
//   同一格截圖從約 0.2 秒變 0.45 秒（grainSize 1 更慢，0.8 秒；grainSize 4 約 0.33 秒）。這段在 render.py，頁面端省不掉，
//   所以長片把 grain 設 0、顆粒改在 ffmpeg 加最省（10 秒 1080p 片約 39 秒）：
//   ffmpeg -i mv.mp4 -vf "noise=alls=12:allf=t+u" -c:v libx264 -crf 16 -pix_fmt yuv420p out.mp4
//   流程：--sheet／--cuts 看拼圖（幾秒）→ --dur 10 試渲（分鐘級）→ 全片用 run_in_background；--samples 8 約 2.7 倍、--scale 2 約 3 倍
//   （render.py 實測數字與全片估時見 mv-template.html 檔頭「成本」）
// 可與 anime-fx.js（AFX）並用，但本檔不依賴它。完整示範見 mv-template.html。
(() => {
  'use strict';
  const TAU = Math.PI * 2;
  const MV = {};
  // 每種提示只印一次，而且用 console.error：render.py 只轉印 console.error，用 console.warn 的話逐格輸出時整個看不到
  const warned = new Set();
  const warnOnce = (key, msg) => { if (!warned.has(key)) { warned.add(key); console.error(msg); } };
  // 輸出格率：render.py --fps 會注入 window.RENDER_FPS；瀏覽器預覽或沒注入時 30。可用 MV.fps = 60 改
  let FPS = +((typeof window !== 'undefined' && window.RENDER_FPS) || 30) || 30;
  // 畫布屬性：主畫布與離屏畫布都用它。willReadFrequently 讓 Chromium 用 CPU 光柵，顆粒的 getImageData 與 render.py --samples 都不必從 GPU 讀回
  const ctxAttrs = { willReadFrequently: true };

  // ================================================================ 數學
  // 把 x 夾在 [a, b]（預設 0..1）
  const clamp = (x, a = 0, b = 1) => (x < a ? a : x > b ? b : x);
  // 線性內插：u = 0 回 a、u = 1 回 b
  const lerp = (a, b, u) => a + (b - a) * u;
  // 把 x 從區間 [a, b] 映到 [c, d]；clampIt = false 時允許外推
  const remap = (x, a, b, c, d, clampIt = true) => {
    const u = a === b ? 0 : (x - a) / (b - a);
    return lerp(c, d, clampIt ? clamp(u) : u);
  };
  // 平滑階梯：x 從 a 走到 b 時輸出 0→1，兩端斜率為 0；a = b 時退化成硬階梯
  const smoothstep = (a, b, x) => {
    if (a === b) return x < a ? 0 : 1;
    const u = clamp((x - a) / (b - a));
    return u * u * (3 - 2 * u);
  };
  // 緩動函式表（輸入輸出都是 0..1）：進場用 out 系列、退場用 in 系列、往返用 inOut
  const ease = {
    linear: u => u,
    inQuad: u => u * u,
    outQuad: u => 1 - (1 - u) * (1 - u),
    inOutQuad: u => (u < 0.5 ? 2 * u * u : 1 - Math.pow(-2 * u + 2, 2) / 2),
    inCubic: u => u * u * u,
    outCubic: u => 1 - Math.pow(1 - u, 3),
    inOutCubic: u => (u < 0.5 ? 4 * u * u * u : 1 - Math.pow(-2 * u + 2, 3) / 2),
    outQuart: u => 1 - Math.pow(1 - u, 4),
    outQuint: u => 1 - Math.pow(1 - u, 5),
    outExpo: u => (u >= 1 ? 1 : 1 - Math.pow(2, -10 * u)),
    inOutExpo: u => (u <= 0 ? 0 : u >= 1 ? 1 : u < 0.5 ? Math.pow(2, 20 * u - 10) / 2 : (2 - Math.pow(2, -20 * u + 10)) / 2),
    outBack: (u, s = 1.70158) => 1 + (s + 1) * Math.pow(u - 1, 3) + s * Math.pow(u - 1, 2),
    inBack: (u, s = 1.70158) => (s + 1) * u * u * u - s * u * u,
    outElastic: u => (u <= 0 ? 0 : u >= 1 ? 1 : Math.pow(2, -10 * u) * Math.sin((u * 10 - 0.75) * (TAU / 3)) + 1),
    outBounce: u => {
      const n = 7.5625, d = 2.75;
      if (u < 1 / d) return n * u * u;
      if (u < 2 / d) return n * (u -= 1.5 / d) * u + 0.75;
      if (u < 2.5 / d) return n * (u -= 2.25 / d) * u + 0.9375;
      return n * (u -= 2.625 / d) * u + 0.984375;
    },
  };
  // 緩動引數：函式直接用；字串查 ease 表（'outCubic'）；省略或不認得的名稱用 fallback（不認得時警告一次）
  function easeOf(e, fallback) {
    if (typeof e === 'function') return e;
    if (typeof e === 'string') {
      if (ease[e]) return ease[e];
      warnOnce('ease:' + e, `MV：沒有這個緩動「${e}」，可用：${Object.keys(ease).join(' ')}`);
    }
    return fallback;
  }
  // x 在 [a, b] 內的進度（夾在 0..1）再套緩動：「從 t0 起 0.3 秒內做完」就寫 prog(t, t0, t0 + 0.3, ease.outCubic) 或 prog(t, t0, t0 + 0.3, 'outCubic')
  const prog = (x, a, b, fn = ease.linear) => easeOf(fn, ease.linear)(clamp(a === b ? (x < a ? 0 : 1) : (x - a) / (b - a)));
  // 關鍵格：[[時間, 值, 緩動?], ...]；第 i 個關鍵格的緩動決定「走向它」那一段（預設 inOutCubic；可給函式或名稱字串）；首尾之外保持端點值
  function keys(t, ks) {
    if (!ks || ks.length === 0) return 0;
    if (t <= ks[0][0]) return ks[0][1];
    for (let i = 1; i < ks.length; i++) {
      const k = ks[i];
      if (t <= k[0]) {
        const p = ks[i - 1], u = (t - p[0]) / (k[0] - p[0]);
        return lerp(p[1], k[1], easeOf(k[2], ease.inOutCubic)(u));
      }
    }
    return ks[ks.length - 1][1];
  }
  // 阻尼彈簧的階躍響應（解析解，不積分）：t0 起從 0 彈到 1 並過衝收斂；freq 每秒振盪次數、damp 阻尼比 0..1（越小彈越久）
  function spring(t, t0 = 0, o = {}) {
    const x = t - t0;
    if (x <= 0) return 0;
    const w = TAU * (o.freq ?? 3), z = clamp(o.damp ?? 0.4, 0.01, 1);
    if (z >= 1) return 1 - (1 + w * x) * Math.exp(-w * x);        // 臨界阻尼：不過衝
    const wd = w * Math.sqrt(1 - z * z);
    return 1 - Math.exp(-z * w * x) * (Math.cos(wd * x) + (z * w / wd) * Math.sin(wd * x));
  }
  // 事件脈衝：t0 瞬間 1，之後每 halfLife 秒減半；t0 之前 0。拍點抖動、閃光的基本單位
  const pulse = (t, t0, halfLife = 0.12) => (t < t0 ? 0 : Math.pow(0.5, (t - t0) / halfLife));
  // 最接近 t 的輸出格序號（格率預設 MV.fps）：閃爍、抖動、顆粒的種子都用它，子格取樣（動態模糊）內才不會每個子格換一種狀態
  const frameIdx = (t, fps = FPS) => Math.round(t * fps);
  // 可重現亂數：同一個 seed 永遠給同一串 0..1（xorshift32）；粒子的固定屬性、顆粒貼圖用
  function rng(seed) {
    let s = ((Math.floor(seed * 1000003) ^ 0x9e3779b9) >>> 0) || 0x1234567;
    return () => { s ^= s << 13; s >>>= 0; s ^= s >>> 17; s ^= s << 5; s >>>= 0; return s / 4294967296; };
  }
  // 無狀態雜湊：任意幾個數字 → 0..1；「第 i 條線的位置」「第 n 格的抖動方向」這類查表用，不必建亂數器
  function hash(...xs) {
    let h = 2166136261 >>> 0;
    for (const x of xs) {
      h ^= Math.floor(x * 1000003) | 0;
      h = Math.imul(h, 16777619); h ^= h >>> 13;
      h = Math.imul(h, 0x5bd1e995); h ^= h >>> 15;
    }
    return (h >>> 0) / 4294967296;
  }
  // 一維值雜訊 −1..1：x 連續變化時平滑（飄移、手持感），seed 換一條不同的曲線
  function noise1(x, seed = 0) {
    const i = Math.floor(x), f = x - i, u = f * f * f * (f * (f * 6 - 15) + 10);
    return lerp(hash(i, seed) * 2 - 1, hash(i + 1, seed) * 2 - 1, u);
  }
  // 時間窗：a 之前 0，fadeIn 秒內升到 1，b 前 fadeOut 秒內降回 0。元素的進出場一行搞定
  const window01 = (t, a, b, fadeIn = 0.2, fadeOut = 0.2) =>
    Math.min(smoothstep(a, a + fadeIn, t), 1 - smoothstep(b - fadeOut, b, t));

  // ================================================================ 資料
  const D = { audio: null, lyrics: null };
  const num = a => (Array.isArray(a) ? a.map(x => (Array.isArray(x) ? +x[0] : +x)).filter(x => Number.isFinite(x)) : []);
  // 描述一個值的形狀（錯誤訊息用）：「陣列（長度 3）」「物件（鍵：foo,bar）」「undefined」
  const shapeOf = v => (Array.isArray(v) ? `陣列（長度 ${v.length}）` : v === null ? 'null'
    : typeof v === 'object' ? `物件（鍵：${Object.keys(v).join(',') || '無'}）` : typeof v);
  // 驗證 audio.json：純物件、beats 是 ≥ 2 個秒數的陣列、tempo（或 bpm）是正數。不符就 throw，不靜默退回等拍格——
  // 退回等拍格的片 render.py 會 exit 0，使用者不會知道資料根本沒載進來
  function checkAudio(a) {
    const bad = why => { throw new Error(`MV.setData：audio.json 格式不對（需要 beats 陣列（≥ 2 個秒數）與 tempo）：${why}；拿到 ${shapeOf(a)}`); };
    if (!a || typeof a !== 'object' || Array.isArray(a)) bad('不是物件');
    if (!Array.isArray(a.beats)) bad(`beats 不是陣列（${shapeOf(a.beats)}）`);
    const beats = num(a.beats);
    if (beats.length < 2) bad(`beats 只有 ${beats.length} 個有效秒數`);
    const tempo = +(a.tempo ?? a.bpm);
    if (!(Number.isFinite(tempo) && tempo > 0)) bad(`tempo 不是正數（${a.tempo ?? a.bpm}）`);
  }
  // 驗證 lyrics.json：純物件且 lines 是陣列（可以是空陣列：沒有歌詞的歌）
  function checkLyrics(l) {
    if (!l || typeof l !== 'object' || Array.isArray(l) || !Array.isArray(l.lines))
      throw new Error(`MV.setData：lyrics.json 格式不對（需要 {lines:[{text,start,end,words:[{w,start,end}]}]}）；拿到 ${shapeOf(l)}`);
  }
  // 把 audio.json 整理成固定形狀（缺的欄位補空，onsets 若是 [秒, 強度] 只取秒）；形狀驗證在 checkAudio（setData 與 MV.audio = … 會先跑）
  function normAudio(a) {
    const out = { ...a };
    out.tempo = +(a.tempo ?? a.bpm);
    out.meter = +a.meter || 4;
    out.beats = num(a.beats);
    out.downbeats = num(a.downbeats);
    out.duration = +a.duration || (out.beats.length ? out.beats[out.beats.length - 1] : 60);
    out.sections = (a.sections || []).map(s => ({ ...s, start: +s.start, end: +s.end }));
    out.env = { fps: 100, ...(a.env || a.features || {}) };
    out.onsets = {};
    for (const k of Object.keys(a.onsets || {})) out.onsets[k] = num(a.onsets[k]);
    return out;
  }
  // 沒有 audio.json 時用等拍格：bpm、拍號 meter、長度 duration、第一拍時間 firstBeat；回傳產生的 audio 物件
  function setGrid(o = {}) {
    const bpm = o.bpm ?? 120, meter = o.meter ?? 4, duration = o.duration ?? 60, first = o.firstBeat ?? 0, per = 60 / bpm;
    const beats = [], downbeats = [];
    for (let i = 0; first + i * per <= duration + 1e-6; i++) {
      const t = +(first + i * per).toFixed(6);
      beats.push(t); if (i % meter === 0) downbeats.push(t);
    }
    D.audio = normAudio({ duration, sr: 44100, tempo: bpm, meter, beats, downbeats, sections: o.sections || [], env: {}, onsets: {} });
    return D.audio;
  }
  // 把 lyrics.json 整理成固定形狀，並算出每個 word 在整行文字裡的字元位置（karaoke 與 lineCharProgress 用）
  function normLyrics(l) {
    const lines = (l.lines || []).map((ln, i) => {
      const words = (ln.words || []).map(w => ({ w: String(w.w ?? w.word ?? ''), start: +w.start, end: +w.end }));
      const text = ln.text != null ? String(ln.text) : words.map(w => w.w).join('');
      const start = ln.start != null ? +ln.start : (words[0]?.start ?? 0);
      const end = ln.end != null ? +ln.end : (words[words.length - 1]?.end ?? start);
      const chars = Array.from(text), lower = chars.map(ch => ch.toLowerCase());
      let cursor = 0;
      for (const w of words) {                                    // 依序在整行裡找到這個 word 的字元區間
        const wc = Array.from(w.w.toLowerCase()), n = wc.length;
        let ci = -1;
        for (let p = cursor; p + n <= chars.length && n > 0; p++) {
          let ok = true;
          for (let k = 0; k < n; k++) if (lower[p + k] !== wc[k]) { ok = false; break; }
          if (ok) { ci = p; break; }
        }
        if (ci < 0) ci = Math.min(cursor, chars.length);          // 找不到（標點差異）就接在上一個 word 後面
        w.ci = ci; w.n = n; cursor = ci + n;
      }
      return { ...ln, i, text, start, end, words, chars };
    });
    return { ...l, lines };
  }
  // 載入資料：{audio, lyrics} 任一可省略；之後 MV.audio／MV.lyrics 可直接讀。形狀不對直接 throw（見檔頭「錯誤與提示」）
  function setData(d = {}) {
    if (d.audio != null) { checkAudio(d.audio); D.audio = normAudio(d.audio); }
    if (d.lyrics != null) { checkLyrics(d.lyrics); D.lyrics = normLyrics(d.lyrics); }
    return D;
  }
  // 完全沒資料時自動用 120 BPM 等拍格，節拍函式才不會回 NaN
  const A = () => D.audio || setGrid();

  // ================================================================ 節拍
  // 遞增陣列裡最後一個 <= x 的索引（二分搜尋）；全部 > x 時回 −1
  function lastLE(arr, x) {
    let lo = 0, hi = arr.length;
    while (lo < hi) { const m = (lo + hi) >> 1; if (arr[m] <= x) lo = m + 1; else hi = m; }
    return lo - 1;
  }
  // 時間 → 連續索引（陣列兩端用相鄰間隔外推）；indexAt 與 timeAt 互為反函式
  function indexAt(arr, t, period) {
    const n = arr.length;
    if (n === 0) return t / period;
    if (n === 1) return (t - arr[0]) / period;
    if (t <= arr[0]) return (t - arr[0]) / (arr[1] - arr[0]);
    if (t >= arr[n - 1]) return n - 1 + (t - arr[n - 1]) / (arr[n - 1] - arr[n - 2]);
    const i = lastLE(arr, t);
    return i + (t - arr[i]) / (arr[i + 1] - arr[i]);
  }
  function timeAt(arr, i, period) {
    const n = arr.length;
    if (n === 0) return i * period;
    if (n === 1) return arr[0] + i * period;
    if (i <= 0) return arr[0] + i * (arr[1] - arr[0]);
    if (i >= n - 1) return arr[n - 1] + (i - (n - 1)) * (arr[n - 1] - arr[n - 2]);
    const k = Math.floor(i);
    return arr[k] + (arr[k + 1] - arr[k]) * (i - k);
  }
  const beatPeriod = () => 60 / A().tempo;
  const barPeriod = () => (60 / A().tempo) * A().meter;
  // 連續拍序（小數）：第一拍為 0；拍與拍之間線性內插，第一拍前為負
  const beatAt = t => indexAt(A().beats, t, beatPeriod());
  // 連續小節序（小數）：第一個 downbeat 為 0
  const barAt = t => indexAt(A().downbeats, t, barPeriod());
  // 拍內相位 0..1（拍點處 0）：做「每拍一次」的呼吸、脈衝
  const beatPhase = t => { const b = beatAt(t); return b - Math.floor(b); };
  // 小節內相位 0..1
  const barPhase = t => { const b = barAt(t); return b - Math.floor(b); };
  // 第 i 拍（可小數）的時間；排程「第 17 拍做某事」用它，不寫死秒數
  const timeOfBeat = i => timeAt(A().beats, i, beatPeriod());
  // 第 i 小節（可小數）的時間
  const timeOfBar = i => timeAt(A().downbeats, i, barPeriod());
  // 最接近 t 的拍點時間：把任意事件吸附到拍上
  const nearestBeat = t => timeOfBeat(Math.round(beatAt(t)));
  // t 所在段落 {name, start, end, p}（p = 段內進度 0..1）；沒有段落資料時整首算一段 'all'
  function sectionAt(t) {
    const a = A(), ss = a.sections;
    if (!ss || ss.length === 0) return { name: 'all', start: 0, end: a.duration, p: clamp(t / (a.duration || 1)) };
    let s = ss.find(x => t >= x.start && t < x.end);
    if (!s) s = t < ss[0].start ? ss[0] : ss.reduce((best, x) => (x.start <= t ? x : best), ss[0]);
    return { ...s, p: clamp((t - s.start) / Math.max(1e-6, s.end - s.start)) };
  }
  // 包絡線（rms／low／mid／high…）在 t 的值，線性內插；沒有資料回 0
  function env(name, t) {
    const e = A().env, arr = e && e[name];
    if (!arr || !arr.length) return 0;
    const fps = e.fps || 100, x = t * fps, i = Math.floor(x);
    if (i < 0) return arr[0];
    if (i >= arr.length - 1) return arr[arr.length - 1];
    return arr[i] + (arr[i + 1] - arr[i]) * (x - i);
  }
  // 最近一次 onset（kick／snare／hat）起的指數衰減脈衝 0..1；沒有 onset 資料回 0
  function hit(kind, t, halfLife = 0.12) {
    const list = A().onsets[kind];
    if (!list || !list.length) return 0;
    const i = lastLE(list, t);
    return i < 0 ? 0 : pulse(t, list[i], halfLife);
  }

  // ================================================================ 歌詞
  const fold = s => String(s).toLowerCase().replace(/\s+/g, '');
  // 用內容找歌詞行（不寫死時間）：MV.line('雨點') → 第一個含「雨點」的行；nth 取第幾個（0 起）
  // 找不到回 null 並警告一次：完全沒有這句、或有這句但 nth 超出命中數，兩種訊息分開
  function line(query, nth = 0) {
    const q = fold(query), hits = (D.lyrics?.lines || []).filter(l => fold(l.text).includes(q));
    const l = hits[nth] || null;
    if (!l) warnOnce(`line:${q}#${nth}`, hits.length === 0
      ? `MV.line：找不到歌詞「${query}」`
      : `MV.line：歌詞「${query}」只命中 ${hits.length} 行，nth=${nth} 超出（nth 從 0 起）`);
    return l;
  }
  // 單字（中文一字、英文一單字）的演唱進度 0..1：start 前 0、end 後 1、中間線性
  function wordProgress(w, t) {
    if (!w || t <= w.start) return 0;
    if (t >= w.end) return 1;
    return (t - w.start) / Math.max(1e-3, w.end - w.start);
  }
  // 整行已唱到第幾個字元（0..字數，可小數）：逐字 wipe 用；word 之間的標點隨下一個 word 開唱時一起亮
  function lineCharProgress(ln, t) {
    if (!ln) return 0;
    const len = (ln.chars || Array.from(ln.text)).length;
    let lit = 0;
    for (const w of ln.words) {
      const p = wordProgress(w, t);
      if (p <= 0) break;
      const ci = w.ci ?? 0, n = w.n ?? Array.from(w.w).length;
      lit = ci + p * n;
      if (p < 1) return Math.min(lit, len);
    }
    if (ln.words.length && wordProgress(ln.words[ln.words.length - 1], t) >= 1) lit = len;
    return Math.min(lit, len);
  }
  // t 時正在唱的行（可能多行重疊，依 start 排序）
  const linesAt = t => (D.lyrics?.lines || []).filter(l => t >= l.start && t < l.end);

  // ================================================================ 字型排印
  // 組 Canvas 字型字串：MV.font('Noto Sans TC', 120, 900)；family 已含逗號或引號時原樣使用（可傳整串 fallback）
  const font = (family, px, weight = 400) =>
    `${weight} ${px}px ${/[,"']/.test(family) ? family : `"${family}"`}`;
  const asFont = (f, size) => (typeof f === 'function' ? f(size) : f);
  // 逐字排版（含字距調整 kerning）：{font: 字型字串或 px=>字型字串, size, tracking | trackingEm} → {glyphs:[{ch,x,w}], width, ascent, descent}
  // kerning = measureText(前字+此字) − measureText(前字) − measureText(此字)；CJK 之間通常為 0
  // tracking 為每字額外間距，單位 px（不是 em）；要用 em 寫 tracking: size * 0.08 或 trackingEm: 0.08
  function layout(ctx, text, o = {}) {
    const chars = Array.from(String(text ?? '')), size = o.size ?? 100, tracking = o.tracking ?? (o.trackingEm != null ? o.trackingEm * size : 0);
    ctx.save();
    if (o.font) ctx.font = asFont(o.font, size);
    const fontStr = ctx.font, m = ch => ctx.measureText(ch).width;
    const glyphs = [];
    let x = 0, prev = null, prevW = 0;
    for (const ch of chars) {
      const w = m(ch);
      if (prev !== null) x += prevW + (m(prev + ch) - prevW - w) + tracking;
      glyphs.push({ ch, x, w });
      prev = ch; prevW = w;
    }
    const last = glyphs[glyphs.length - 1], width = last ? last.x + last.w : 0;
    const mm = ctx.measureText('國Hg');
    const ascent = mm.fontBoundingBoxAscent || size * 0.88, descent = mm.fontBoundingBoxDescent || size * 0.12;
    ctx.restore();
    return { text: String(text ?? ''), glyphs, width, ascent, descent, size, font: fontStr, tracking };
  }
  // 把 layout 的字一個一個畫出來：align left|center|right；each(g, i) 可回 {dx, dy, alpha, scale, rot, fill, stroke} 做逐字動畫，回 null 跳過
  // 回傳文字左緣 x0（之後要畫底線、打字 caret 時用）
  function drawGlyphs(ctx, lay, x, y, o = {}) {
    const align = o.align || 'left';
    const x0 = x - (align === 'center' ? lay.width / 2 : align === 'right' ? lay.width : 0);
    ctx.save();
    ctx.font = lay.font; ctx.textAlign = 'left'; ctx.textBaseline = o.baseline || 'alphabetic';
    if (o.alpha != null) ctx.globalAlpha = o.alpha;
    lay.glyphs.forEach((g, i) => {
      const e = o.each ? o.each(g, i, lay) : {};
      if (e === null) return;
      const cx = x0 + g.x + g.w / 2;
      ctx.save();
      if (e.alpha != null) ctx.globalAlpha *= clamp(e.alpha);
      ctx.translate(cx + (e.dx || 0), y + (e.dy || 0));
      if (e.rot) ctx.rotate(e.rot);
      if (e.scale != null || e.sx != null || e.sy != null) ctx.scale((e.sx ?? e.scale ?? 1), (e.sy ?? e.scale ?? 1));
      const stroke = e.stroke ?? o.stroke, fill = e.fill ?? o.fill;
      if (stroke) { ctx.lineWidth = o.lineWidth ?? lay.size * 0.08; ctx.lineJoin = 'round'; ctx.strokeStyle = stroke; ctx.strokeText(g.ch, -g.w / 2, 0); }
      if (fill !== false) { ctx.fillStyle = fill || '#fff'; ctx.fillText(g.ch, -g.w / 2, 0); }
      ctx.restore();
    });
    ctx.restore();
    return x0;
  }
  // 讓文字塞進 maxW × maxH 的最大字級：fontFn 是 px => 字型字串；回傳 px
  // tracking 要和之後 layout 用的一樣：數字 = 固定 px；函式 px => px * 0.04 = 隨字級放大（em）。省略時當 0，整行寬度會比 maxW 多 n×tracking
  function fitSize(ctx, text, maxW, maxH, fontFn, tracking = 0) {
    const s = String(text ?? ''), gaps = Math.max(0, Array.from(s).length - 1);
    ctx.save(); ctx.font = fontFn(100);
    const w = ctx.measureText(s).width / 100;                 // 每 1px 字級的文字寬
    ctx.restore();
    if (!(w > 0)) return maxH;
    // 隨字級放大：size × (w + gaps × k) = maxW；固定 px：size × w = maxW − gaps × tracking
    const k = typeof tracking === 'function' ? tracking(100) / 100 : 0, fixed = typeof tracking === 'function' ? 0 : +tracking || 0;
    return Math.max(0, Math.min(maxH, (maxW - gaps * fixed) / (w + gaps * k)));
  }
  // 卡拉 OK 逐字亮字：亮字由 wordProgress 決定，永遠不會超前人聲。opts：{x, y, size, font(px=>字型), sung, unsung, align, maxW, tracking | trackingEm, baseline, each}
  // maxW 給了而整行太寬時自動縮字。回 {layout, lit, size, x0}
  function karaoke(ctx, ln, t, o = {}) {
    if (!ln) return null;
    let size = o.size ?? 64, tracking = o.tracking ?? (o.trackingEm != null ? o.trackingEm * size : 0);
    const fontFn = typeof o.font === 'function' ? o.font : (px => o.font || font('sans-serif', px, 700));
    let lay = layout(ctx, ln.text, { font: fontFn, size, tracking });
    if (o.maxW && lay.width > o.maxW) {
      const k = o.maxW / lay.width;
      size = Math.floor(size * k); tracking *= k;
      lay = layout(ctx, ln.text, { font: fontFn, size, tracking });
    }
    const lit = lineCharProgress(ln, t), sung = o.sung || '#fff', unsung = o.unsung || 'rgba(255,255,255,0.35)';
    const x0 = drawGlyphs(ctx, lay, o.x ?? 0, o.y ?? 0, { align: o.align || 'center', baseline: o.baseline, each: o.each,
      fill: unsung, stroke: o.stroke, lineWidth: o.lineWidth });
    // 已唱部分：每個字依自己的亮度比例 clip 後用 sung 色再畫一次
    ctx.save();
    ctx.font = lay.font; ctx.textAlign = 'left'; ctx.textBaseline = o.baseline || 'alphabetic';
    const top = (o.baseline === 'middle' ? -lay.ascent / 2 : -lay.ascent) - lay.size * 0.1, hgt = lay.ascent + lay.descent + lay.size * 0.2;
    lay.glyphs.forEach((g, i) => {
      const p = clamp(lit - i);
      if (p <= 0) return;
      const e = o.each ? o.each(g, i, lay) : {};
      if (e === null) return;
      ctx.save();
      if (e.alpha != null) ctx.globalAlpha *= clamp(e.alpha);
      ctx.translate(x0 + g.x + g.w / 2 + (e.dx || 0), (o.y ?? 0) + (e.dy || 0));
      if (e.rot) ctx.rotate(e.rot);
      if (e.scale != null) ctx.scale(e.scale, e.scale);
      ctx.beginPath(); ctx.rect(-g.w / 2 - 2, top, (g.w + 4) * p, hgt); ctx.clip();
      ctx.fillStyle = sung; ctx.fillText(g.ch, -g.w / 2, 0);
      ctx.restore();
    });
    ctx.restore();
    return { layout: lay, lit, size, x0 };
  }
  // 安全區 [x, y, w, h]：pct 0.9 = 動作安全、0.8 = 字幕安全；標題與字幕不要超出
  const safeArea = (W, H, pct = 0.9) => { const w = W * pct, h = H * pct; return [(W - w) / 2, (H - h) / 2, w, h]; };

  // ================================================================ 後製
  const POST = { tiles: null, n: 6, size: 512, scratch: null, xs: null };
  // 預先產生 6 張顆粒貼圖（512×512 的 Float32Array，三角分佈 −1..1），之後每格輪流用、隨格位移，不必逐格產亂數
  function grainTiles() {
    if (POST.tiles) return POST.tiles;
    const tiles = [], S = POST.size;
    for (let k = 0; k < POST.n; k++) {
      const a = new Float32Array(S * S), r = rng(1000 + k * 7);
      for (let i = 0; i < a.length; i++) a[i] = r() + r() - 1;
      tiles.push(a);
    }
    return (POST.tiles = tiles);
  }
  // 顆粒（CPU 路徑）：讀回整張畫布 → 每個畫素 v += amount × n × min(v, 255 − v) → 寫回
  // 這條式子就是 overlay 疊中性灰顆粒貼圖的解析解：中間調最強、純黑純白不動，和舊的 createPattern + overlay 看起來一樣，
  // 但在 swiftshader 上不必做全幅 overlay 合成。gsDev = 顆粒邊長（裝置畫素）、fi = 格序（選貼圖與位移）
  function grainCPU(ctx, amount, gsDev, fi) {
    const cv = ctx.canvas, Wd = cv.width, Hd = cv.height, S = POST.size, M = S - 1;
    const tiles = grainTiles(), tile = tiles[((fi % tiles.length) + tiles.length) % tiles.length];
    const ox = Math.floor(hash(fi, 1) * S), oy = Math.floor(hash(fi, 2) * S), g = Math.max(1, Math.round(gsDev));
    const xs = POST.xs && POST.xs.length === Wd ? POST.xs : (POST.xs = new Int32Array(Wd));
    for (let x = 0; x < Wd; x++) xs[x] = (((x / g) | 0) + ox) & M;
    const img = ctx.getImageData(0, 0, Wd, Hd), d = img.data, k = clamp(amount);
    for (let y = 0; y < Hd; y++) {
      const row = ((((y / g) | 0) + oy) & M) * S;
      let i = y * Wd * 4;
      for (let x = 0; x < Wd; x++, i += 4) {
        const n = tile[row + xs[x]] * k;
        let v = d[i]; d[i] = v + n * (v < 128 ? v : 255 - v);
        v = d[i + 1]; d[i + 1] = v + n * (v < 128 ? v : 255 - v);
        v = d[i + 2]; d[i + 2] = v + n * (v < 128 ? v : 255 - v);
      }
    }
    ctx.putImageData(img, 0, 0);
  }
  // 一次套全部後製，每個選項 0／省略 = 關：
  //   grain 顆粒 0..1（0.06–0.14 像底片；grainSize 顆粒邊長，邏輯 px，預設 2，--scale 2 時自動乘 2）、vignette 暈影 0..1、
  //   flash 閃白 0..1、invert 反轉 0..1、fade 淡黑 0..1、letterbox 目標長寬比（如 2.39）、tint 疊色（CSS 色，soft-light）、
  //   halation 亮部暈光 0..1（量要小，紙底請關；每格約 +0.1 秒，預設關、只在需要的場景回傳覆寫）
  //   t 用來決定這一格用哪張顆粒貼圖（依 MV.fps 或 p.fps 取格序）；W／H 省略時從 ctx 的 transform 推回邏輯尺寸
  //   順序：halation → tint → invert → vignette → flash → fade → grain → letterbox（黑邊上沒有顆粒）
  function post(ctx, p = {}, t = 0) {
    const cv = ctx.canvas, m = ctx.getTransform();
    const W = p.W ?? cv.width / (m.a || 1), H = p.H ?? cv.height / (m.d || 1);
    ctx.save();
    if (p.halation > 0) {                                       // 亮部萃取 → 模糊 → 暖色 → screen 疊回
      const sw = Math.max(2, Math.round(W / 4)), sh = Math.max(2, Math.round(H / 4));
      const s = POST.scratch || (POST.scratch = document.createElement('canvas'));
      if (s.width !== sw || s.height !== sh) { s.width = sw; s.height = sh; }
      const sc = s.getContext('2d', ctxAttrs);
      sc.save(); sc.globalCompositeOperation = 'source-over'; sc.clearRect(0, 0, sw, sh);
      sc.filter = 'brightness(0.6) contrast(4) blur(5px)';
      sc.drawImage(cv, 0, 0, sw, sh);
      sc.filter = 'none'; sc.globalCompositeOperation = 'multiply'; sc.fillStyle = p.halationColor || '#ffb37a'; sc.fillRect(0, 0, sw, sh);
      sc.restore();
      ctx.globalCompositeOperation = 'screen'; ctx.globalAlpha = clamp(p.halation); ctx.drawImage(s, 0, 0, W, H);
      ctx.globalCompositeOperation = 'source-over'; ctx.globalAlpha = 1;
    }
    if (p.tint) { ctx.globalCompositeOperation = 'soft-light'; ctx.fillStyle = p.tint; ctx.fillRect(0, 0, W, H); ctx.globalCompositeOperation = 'source-over'; }
    if (p.invert > 0) { ctx.globalCompositeOperation = 'difference'; ctx.fillStyle = `rgba(255,255,255,${clamp(p.invert)})`; ctx.fillRect(0, 0, W, H); ctx.globalCompositeOperation = 'source-over'; }
    if (p.vignette > 0) {
      const g = ctx.createRadialGradient(W / 2, H / 2, Math.min(W, H) * 0.3, W / 2, H / 2, Math.hypot(W, H) * 0.52);
      g.addColorStop(0, 'rgba(0,0,0,0)'); g.addColorStop(1, `rgba(0,0,0,${clamp(p.vignette)})`);
      ctx.fillStyle = g; ctx.fillRect(0, 0, W, H);
    }
    if (p.flash > 0) { ctx.fillStyle = p.flashColor || '#fff'; ctx.globalAlpha = clamp(p.flash); ctx.fillRect(0, 0, W, H); ctx.globalAlpha = 1; }
    if (p.fade > 0) { ctx.fillStyle = '#000'; ctx.globalAlpha = clamp(p.fade); ctx.fillRect(0, 0, W, H); ctx.globalAlpha = 1; }
    if (p.grain > 0) {                                          // 依格序輪流貼圖＋隨格位移；整張畫布（含 transform 外的裝置畫素）
      const gs = p.grainSize ?? p.grainScale ?? 2;
      grainCPU(ctx, p.grain, gs * (m.a || 1), frameIdx(t, p.fps || FPS));
    }
    if (p.letterbox > 0) {
      const bar = Math.max(0, (H - W / p.letterbox) / 2);
      if (bar > 0) { ctx.fillStyle = '#000'; ctx.fillRect(0, 0, W, bar); ctx.fillRect(0, H - bar, W, bar); }
    }
    ctx.restore();
  }

  // ================================================================ 時間軸
  const DEF_OVERLAP = { cut: 0, crossfade: 0.5, wipe: 0.4, zoom: 0.5, whip: 0.25, flash: 0.12, invert: 0.1 };
  const PRE = { crossfade: 1, wipe: 1, zoom: 1, whip: 1 };     // 在 start 之前完成、新畫面於 start 這一拍落定的轉場
  // 兩組後製覆寫依 u 混合（轉場中用）
  function mixOv(a, b, u) {
    const out = {};
    for (const k of new Set([...Object.keys(a), ...Object.keys(b)])) {
      const x = a[k], y = b[k];
      if (Array.isArray(x) || Array.isArray(y)) out[k] = [lerp(x?.[0] ?? 0, y?.[0] ?? 0, u), lerp(x?.[1] ?? 0, y?.[1] ?? 0, u)];
      else if (typeof x === 'number' || typeof y === 'number') out[k] = lerp(x ?? (k === 'zoom' ? 1 : 0), y ?? (k === 'zoom' ? 1 : 0), u);
      else out[k] = u < 0.5 ? x : y;
    }
    return out;
  }
  // 兩張離屏畫面依轉場種類合成到 ctx：A 舊、B 新，u 0→1
  function compose(ctx, kind, u, Acv, Bcv, W, H) {
    const e = ease.inOutCubic(u);
    const at = (cv, s = 1, dx = 0) => ctx.drawImage(cv, W / 2 - (W * s) / 2 + dx, H / 2 - (H * s) / 2, W * s, H * s);
    if (kind === 'crossfade') { at(Acv); ctx.globalAlpha = e; at(Bcv); ctx.globalAlpha = 1; }
    else if (kind === 'wipe') { at(Acv); ctx.save(); ctx.beginPath(); ctx.rect(0, 0, W * e, H); ctx.clip(); at(Bcv); ctx.restore(); }
    else if (kind === 'zoom') { at(Acv, 1 + 0.3 * e); ctx.globalAlpha = e; at(Bcv, 1 + 0.25 * (1 - e)); ctx.globalAlpha = 1; }
    else if (kind === 'whip') {                                 // 甩鏡：舊畫面往左甩出、新畫面從右甩入，拖影長度跟著速度走
      const k = ease.inOutExpo(u), n = 10;
      const vel = (ease.inOutExpo(Math.min(1, u + 0.02)) - ease.inOutExpo(Math.max(0, u - 0.02))) / 0.04;
      const smear = Math.min(W * 0.16, W * vel * 0.03);
      // n 份位移不同的畫面取真平均：第 i 份用 source-over 以 1/(i+1) 疊上（累計平均），不用 lighter，深色底不會被疊亮
      ctx.save(); ctx.globalCompositeOperation = 'source-over';
      for (let i = 0; i < n; i++) {
        const d = (i / (n - 1) - 0.5) * smear;
        ctx.globalAlpha = 1 / (i + 1);
        at(Acv, 1, -W * k + d); at(Bcv, 1, W * (1 - k) + d);
      }
      ctx.restore();
    }
    else at(Bcv);
  }
  // 剪接時間軸：entries = [{id, start, end, render(ctx, f), transition?, overlap?}]；opts {W, H, scale, post}
  //   transition：'cut'（預設）|'crossfade'|'flash'|'wipe'|'invert'|'whip'|'zoom'；overlap 秒（省略用預設）
  //   crossfade／wipe／whip／zoom 在 start 前 overlap 秒開始、在 start 落定；flash／invert 從 start 開始並在 overlap 內衰減
  //   f = {t, lt, p, beat, bar, beatPhase, barPhase, W, H, a:{rms,low,mid,high,kick,snare,hat}, entry, i}
  //   scene 的 render 可回傳後製覆寫 {shake:[x,y], zoom, flash, invert, fade, grain, vignette, halation, tint, letterbox}
  //   回 {render(ctx, t), cuts:[秒...], transitions:[...], entries, entryAt(t)}
  //   cuts 是「新畫面落定的拍點」：第 2 個 entry 起每個 start（第 1 個 entry 的 start 不算剪點）。PRE 類轉場（crossfade／wipe／whip／zoom）
  //     的畫面從 start − overlap 就開始變，所以 render.py --cuts 拼圖的 −2f／−1f 已是轉場中段、ffmpeg 偵測到的剪點會比 cuts 早最多 overlap 秒；
  //     要比對剪點用 transitions：[{at, kind, overlap, from, to, id, prev}]，from～to 是畫面變化的時間區間（cut：from = to = at；
  //     PRE 類：from = at − overlap、to = at；flash／invert：from = at、to = at + overlap），偵測到的剪點落在 [from, to] 內就算對
  //   scale 給 2 時離屏畫布為 2 倍（配合 render.py --scale 2，主 ctx 也要先 setTransform(2,0,0,2,0,0)）
  function timeline(entries, o = {}) {
    const W = o.W ?? 1920, H = o.H ?? 1080, S = o.scale ?? 1;
    const list = entries.slice().sort((a, b) => a.start - b.start).map((e, i) => {
      const transition = e.transition || 'cut';
      return { ...e, i, transition, overlap: transition === 'cut' ? 0 : (e.overlap ?? DEF_OVERLAP[transition] ?? 0.3) };
    });
    const cuts = list.slice(1).map(e => e.start);
    const transitions = list.slice(1).map(e => ({
      at: e.start, kind: e.transition, overlap: e.overlap, id: e.id, prev: list[e.i - 1].id,
      from: PRE[e.transition] ? e.start - e.overlap : e.start,
      to: PRE[e.transition] ? e.start : e.start + e.overlap,
    }));
    let cvA = null, cvB = null;
    const off = () => { const cv = document.createElement('canvas'); cv.width = Math.round(W * S); cv.height = Math.round(H * S); cv.getContext('2d', ctxAttrs); return cv; };
    // 每格資料：場景 render 的第二個引數
    const frameFor = (e, t) => ({
      t, lt: t - e.start, p: clamp((t - e.start) / Math.max(1e-6, e.end - e.start)),
      beat: beatAt(t), bar: barAt(t), beatPhase: beatPhase(t), barPhase: barPhase(t), W, H, entry: e, i: e.i,
      a: { rms: env('rms', t), low: env('low', t), mid: env('mid', t), high: env('high', t), kick: hit('kick', t, 0.12), snare: hit('snare', t, 0.14), hat: hit('hat', t, 0.06) },
    });
    // 把一個 entry 畫進離屏畫布，回傳它的後製覆寫
    function draw(e, t, cv) {
      const c = cv.getContext('2d', ctxAttrs);
      c.setTransform(S, 0, 0, S, 0, 0); c.clearRect(0, 0, W, H);
      c.save(); const ov = e.render(c, frameFor(e, t)) || {}; c.restore();
      return ov;
    }
    // 目前作用中的 entry（start <= t < 下一個 start；頭尾之外取最近的）
    function entryAt(t) {
      let cur = list[0];
      for (const e of list) { if (t >= e.start) cur = e; else break; }
      return cur;
    }
    function render(ctx, t) {
      if (!list.length) return;
      cvA = cvA || off(); cvB = cvB || off();
      const cur = entryAt(t), next = list[cur.i + 1];
      let ov, extra = {};
      ctx.save();
      ctx.fillStyle = '#000'; ctx.fillRect(0, 0, W, H);
      const place = v => {                                      // shake 用 translate、zoom 以畫面中心縮放
        const [sx, sy] = v.shake || [0, 0], z = v.zoom || 1;
        ctx.translate(W / 2 + sx, H / 2 + sy); ctx.scale(z, z); ctx.translate(-W / 2, -H / 2);
      };
      if (next && PRE[next.transition] && t >= next.start - next.overlap) {
        const u = clamp((t - (next.start - next.overlap)) / next.overlap);
        const ovA = draw(cur, t, cvA), ovB = draw(next, t, cvB);
        ov = mixOv(ovA, ovB, u);
        place(ov); compose(ctx, next.transition, u, cvA, cvB, W, H);
      } else {
        ov = draw(cur, t, cvB);
        place(ov); ctx.drawImage(cvB, 0, 0, W, H);
        if (!PRE[cur.transition] && cur.overlap > 0 && t < cur.start + cur.overlap) {
          const u = clamp((t - cur.start) / cur.overlap);
          if (cur.transition === 'flash') extra.flash = Math.pow(1 - u, 2);
          if (cur.transition === 'invert') extra.invert = 1;
        }
      }
      ctx.restore();
      const p = { ...(o.post || {}), ...ov, W, H };
      p.flash = Math.max(p.flash || 0, extra.flash || 0);
      p.invert = Math.max(p.invert || 0, extra.invert || 0);
      post(ctx, p, t);
    }
    return { render, cuts, transitions, entries: list, entryAt };
  }

  // ================================================================ 匯出
  Object.assign(MV, {
    TAU, clamp, lerp, remap, smoothstep, ease, easeOf, prog, keys, spring, pulse, frameIdx, rng, hash, noise1, window01,
    setData, setGrid, beatAt, barAt, beatPhase, barPhase, timeOfBeat, timeOfBar, nearestBeat, sectionAt, env, hit,
    line, wordProgress, lineCharProgress, linesAt,
    font, layout, drawGlyphs, fitSize, karaoke, safeArea,
    post, timeline, ctxAttrs,
  });
  // MV.audio：沒 setData／setGrid 時第一次讀取就建立 120 BPM 等拍格（與節拍函式一致，不回 null）；設 null 會回到這個預設；設值會先驗證形狀
  Object.defineProperty(MV, 'audio', { get: () => A(), set: v => { if (v != null) checkAudio(v); D.audio = v != null ? normAudio(v) : null; } });
  Object.defineProperty(MV, 'lyrics', { get: () => D.lyrics, set: v => { if (v != null) checkLyrics(v); D.lyrics = v != null ? normLyrics(v) : null; } });
  // MV.fps：輸出格率（見檔頭）；設定時同步改 frameIdx 的預設
  Object.defineProperty(MV, 'fps', { get: () => FPS, set: v => { FPS = +v || 30; } });
  (typeof window !== 'undefined' ? window : globalThis).MV = MV;
})();
