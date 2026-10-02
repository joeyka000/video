# 音樂驅動的剪輯文法與實拍配方

做 MV、節奏型蒙太奇（montage）、踩點剪（音ハメ）時讀這份。前置：`scripts/analyze.py` 產出 `data/audio.json`；歌詞 MV 另用 `scripts/align.py` 產出 `data/lyrics.json`。
- 概念與分鏡：`references/mv-direction.md`；色彩、字型排印、後製、輸出規格：`references/craft.md`
- 日系演出（集中線、衝擊格、白閃、止め絵、賽璐璐、3回PAN）：`references/anime.md`，這裡只引用不重寫
- 兩條路線、同一套文法：程式動畫用 `assets/mv-kit.js`（全域 `MV`）的 `MV.timeline` 排場景；實拍素材用 `templates/cuts.csv` 填剪點表 → `scripts/cutlist.py` 出 montage，單招用第三節的 ffmpeg 配方（全部在本機 ffmpeg 6.1.1 實測，紀錄在文末）

## 一、基本法則

### 1. 剪在哪裡
- 剪點只有兩種：段落邊界剪在 downbeat（小節第一拍）；歌詞驅動的剪點剪在「該行第一個字之前的最後一拍」，永遠不晚於字。觀眾要先看到新畫面再聽到字，反過來就是遲到
- pdoom-video `app/src/timeline.ts` 的 `cut()` 與 `after()` 就是這兩條：`cut(q)` = `timeOfBeat(floor(beatAt(wordStart + 0.02)))`，0.02 秒容許值讓早 20 ms 壓在拍上的字仍取該拍；`after(q)` = 行尾最近的 downbeat
- 程式動畫（API 名稱以 mv-kit 為準）：
```js
const beatDur = 60 / MV.audio.tempo, barDur = beatDur * MV.audio.meter;
const cutBefore = (query, nth = 0, tol = 0.02) => {
  const s = MV.line(query, nth).words[0].start;          // 用內容找行，不寫死秒數
  return MV.timeOfBeat(Math.floor(MV.beatAt(s + tol)));  // 字前最後一拍
};
const afterLine = (query, nth = 0) => MV.timeOfBar(Math.round(MV.barAt(MV.line(query, nth).end)));
```
- 實拍（Python，讀 audio.json 與 lyrics.json；實測 R20）：
```python
import json, bisect
au = json.load(open('data/audio.json')); ly = json.load(open('data/lyrics.json'))
def cut(query, nth=0, tol=0.02):                       # 字前最後一拍
    s = [l for l in ly['lines'] if query in l['text']][nth]['words'][0]['start']
    return au['beats'][max(bisect.bisect_right(au['beats'], s + tol) - 1, 0)]
def after(query, nth=0):                               # 行尾最近的 downbeat
    e = [l for l in ly['lines'] if query in l['text']][nth]['end']
    return min(au['downbeats'], key=lambda d: abs(d - e))
```
- 誤差標準：剪點落在拍點 ±1 格內（30fps 為 ±33 ms）。`scripts/qa.py` 算這個比例，低於 90% 回去修

### 2. 硬切為主，溶接極少
- 預設硬切：`MV.timeline` 的 entry 不寫 `transition` 就是硬切；cuts.csv 每列都是硬切
- 溶接（dissolve／crossfade）只用在三種地方：時間流逝、夢或回憶的進出、同一主體兩個時刻的疊影。一支 MV 不超過 3 處
- 轉場效果（白閃、擦、縮放）是語氣詞，整支片用同一套，不要每個剪點換一種

### 3. 剪輯密度表
每小節刀數 = 該段落平均每小節剪幾次（含段內子剪）。強度 = 刀數、鏡頭運動、特效、字級的整體刺激量，副歌 = 100%（anime.md 的 40／70／100 規則延伸）。

| 段落 | 每小節刀數 | 鏡頭語言 | 強度 |
|---|---|---|---|
| 前奏 intro | 0.25–0.5（每 2–4 小節一刀） | 建立鏡頭、空景、慢推；第一格就要有主題（開場鉤子） | 30–40% |
| 主歌 verse | 0.5–1 | 中景跟人、對稱構圖；段內子剪每 2 小節一次 | 60–70% |
| 導歌 pre-chorus | 1–2，逐小節加密 | 越剪越近（中景→特寫），最後 2 小節每拍一個 punch-in，把能量推上副歌 | 80–90% |
| 副歌 chorus | 2–4（每 1–2 拍一刀） | 特寫與全景交替、符號鏡頭、招牌動作每次副歌重複；白閃只放第一個 downbeat | 100% |
| 間奏 interlude | 1 | 器樂主導：長鏡頭跟運動、鏡頭運動 ease 進 downbeat，少剪多動 | 70% |
| 橋段 bridge | 0.25–0.5 | 止め絵、慢動作、留白、靜止格；為最後一次副歌蓄力 | 40–50% |
| 尾奏 outro | 4（每拍一刀）或 0（一鏡到底） | 每拍一刀的回顧蒙太奇，或單一長鏡頭收尾；首尾畫面呼應讓影片可以首尾相接重播 | 100% → 0% |

- 密度曲線要貼著能量曲線（anime-op 分鏡的做法：第三段主歌起加快、橋段放慢、尾奏每拍一刀）；最後一次副歌要比第一次密
- 同一段落內不要均勻：小節 1、3 重，2、4 輕，觀眾才感覺得到「拍」而不是「頻率」

### 4. 緩急：標點符號原則
- 止め絵、白閃、衝擊格、停格、反轉是標點符號，只放最重的拍：每段副歌的第一個 downbeat、橋段結尾、全曲最高點。一分鐘不超過 4 個（做法見 anime.md〈節奏原則〉與〈實拍 2、4、6〉）
- 重拍前留一拍「吸氣」：副歌前最後一拍可以空（黑場、停格、靜止鏡頭），下一個 downbeat 的衝擊會放大（配方 18）

### 5. 段內子剪（同一場景不換鏡）
- reframing：同一鏡頭硬切到另一個裁切（1.0 → 1.3 倍、換角落），落在拍上，長鏡頭不會悶（配方 10e）
- punch-in：拍點瞬間放大 8–25% 再彈回或停住，用在 kick、snare、重複的副歌字（配方 10b、13c）
- roll：鏡頭從 −3° 轉回 0°，結束在 downbeat（配方 10d）
- 三者都是 t 的函式：程式動畫用 `ctx.translate／scale／rotate` 包住場景再畫；實拍用 `scale`＋`crop`／`rotate` 的表示式

### 6. 鏡頭運動要 ease 進 downbeat
- 運動「結束」在拍上，不是開始在拍上：推進、搖、轉用 `outCubic`／`outExpo` 讓終點正好落在 downbeat，觀眾把拍點感知為「到位」
- 程式動畫：`const z = 1 + 0.2 * MV.prog(f.t, t1 - beatDur * 2, t1, MV.ease.outCubic);`（t1 = 目標 downbeat）
- 實拍：配方 10a（`1-pow(1-min(t/2,1),3)` 就是 outCubic，2 秒正好停）

### 7. 不要改原片速度硬湊拍點
- 節奏不合就換素材或換 in-point。速度只為設計服務（刻意的慢動作、斜坡），不是對拍工具；cuts.csv 的 `speed` 欄同理
- 慢動作要補格（配方 3c）或用高幀率原片；快轉超過 2 倍要加動態模糊（配方 7 的 tmix 做法），不然像跳格

### 8. 動作接動作
- 兩個鏡頭在同一個動作的中途相接（action cut），動作本身蓋掉剪點，是最不被察覺的剪法；拍點上的剪接尤其要這樣，觀眾才覺得畫面「打在拍上」而不是「剛好換了」

## 二、招式表

每招三段：何時用 → 程式動畫（`MV.timeline`）→ 實拍（ffmpeg 配方編號，指令在第三節）。`MV.timeline` 的骨架：

```js
const W = 1920, H = 1080;
const tl = MV.timeline([
  { id: 'intro',   start: 0,                end: MV.timeOfBar(8),  render: introScene },
  { id: 'verse1',  start: MV.timeOfBar(8),  end: MV.timeOfBar(16), render: verseScene },   // 不寫 transition = 硬切
  { id: 'chorus1', start: MV.timeOfBar(16), end: MV.timeOfBar(24), render: chorusScene, transition: 'flash' },
], { W, H });
function render(t) { tl.render(ctx, t); }   // 頁面入口，render.py 逐格呼叫
window.CUTS = tl.cuts;                       // render.py --cuts 出剪點拼圖
```
場景拿到的 `f` = `{t, lt, p, beat, bar, beatPhase, barPhase, W, H, a:{rms,low,mid,high,kick,snare,hat}}`；場景可回傳後製覆寫 `{shake:[x,y], flash, invert, zoom, fade, grain, vignette}`。下面的 `t0`、`tEnd` 都是用 `MV.timeOfBar()` 或 `cutBefore()` 算出來的絕對秒數。

### J cut／L cut
- 何時用：J cut（聲音先進）用在新段落的第一個字、音效比畫面早到，觀眾「先聽到再看到」；L cut（畫面先走）用在人聲延音還在時已切到反應鏡頭。MV 的音樂連續不斷，所以 J／L cut 在 MV 裡是「元素先進」：下一場的標題、色塊、字在前一場的最後一拍就出現
- 程式動畫：
```js
function verseScene(ctx, f) {
  drawVerse(ctx, f);
  const lead = MV.prog(f.t, tEnd - beatDur, tEnd, MV.ease.outExpo);   // 最後一拍
  if (lead > 0) drawChorusTitle(ctx, f, lead);                         // 下一場的標題先進來
}
```
- 實拍：配方 12a（J cut，concat 版）、12b（L cut，adelay＋amix 版）

### match cut（對位接）
- 何時用：兩個鏡頭用相同形狀、相同動作方向、相同畫面位置相接（圓→圓、往右揮→往右走、左上亮點→左上路燈），眼睛不用重新找焦點，剪點放在很重的拍也不覺得硬
- 程式動畫：兩場景共用一個 anchor，主體在 A 的最後一格與 B 的第一格位置、大小一致
```js
const anchor = (f) => ({ x: f.W * 0.5, y: f.H * 0.42, r: 160 });
function sceneA(ctx, f) { const a = anchor(f); drawMoon(ctx, a.x, a.y, a.r * (1 + 0.1 * f.p)); }
function sceneB(ctx, f) { const a = anchor(f); drawClock(ctx, a.x, a.y, a.r * 1.1); }   // 接上 A 的尾
```
- 實拍：沒有濾鏡能代勞，靠選 in-point；用配方 19 把 A 最後一格與 B 第一格並排看位置與明暗

### 跳接 jump cut
- 何時用：同一鏡頭去掉中間一段直接相接，表示時間跳躍、焦躁、重複；主歌的對嘴鏡頭每小節跳一次很常見
- 程式動畫：同一場景、本地時間每小節跳一段：`drawTalk(ctx, f.lt + Math.floor(f.lt / barDur) * 1.5);`
- 實拍：配方 16

### 速度斜坡 speed ramp
- 何時用：正常速度衝向拍點、拍點後瞬間變慢（或相反），用在副歌進入、動作高點；斜坡的轉折點要在 downbeat
- 程式動畫：把本地時間 warp 一次，場景照常畫：`drawRun(ctx, MV.keys(f.lt, [[0, 0, 'linear'], [2, 2, 'inCubic'], [3, 6, 'linear']]));`（2 秒後加速到 4 倍）
- 實拍：配方 3a（連續 setpts 表示式）、3b（分段 concat）、3c（慢動作補格）；音樂會取代原音軌，一律 `-an`

### 停格 freeze
- 何時用：情緒高點、字卡落下、止め絵；停的長度是整數拍
- 程式動畫：`const lt = f.lt < 2 ? f.lt : f.lt < 3 ? 2 : f.lt - 1;`（2 秒處停 1 秒再續）
- 實拍：配方 4（兩段 concat，音訊同步補靜音）；片尾停格直接用 anime.md〈實拍 2〉

### 倒放 reverse
- 何時用：回溯、乒乓來回（正放→倒放）填滿一個小節、動作「收回」接下一拍
- 程式動畫：`const lt = f.lt < d ? f.lt : 2 * d - f.lt;`（乒乓，d = 來回一趟的一半）
- 實拍：配方 5a（整段）、5b（乒乓）

### 三連 stutter
- 何時用：snare roll、三連音、副歌前的 fill；同一小段重複 3 次，每次可放大一點（出崎統 3回PAN 的變體）
- 程式動畫：
```js
const len = beatDur / 2;                                   // 八分音符
const lt = f.lt < 3 * len ? f.lt % len : f.lt - 2 * len;   // 前三段重複，之後續播
const k = Math.min(Math.floor(f.lt / len), 2);             // 第幾次 0、1、2
ctx.translate(f.W / 2, f.H / 2); ctx.scale(1 + 0.15 * k, 1 + 0.15 * k); ctx.translate(-f.W / 2, -f.H / 2);
```
- 實拍：配方 6a（loop）、6b（放回原片）、6c（每次放大）

### whip（甩鏡）
- 何時用：兩個空間、兩個人之間的高速轉場，動作喜劇感（Edgar Wright）；方向要一致：A 往右甩出，B 也從右甩入
- 程式動畫：`transition: 'whip', overlap: 0.2`；自己做：A 最後 0.2 秒 `ctx.translate(-f.W * MV.prog(f.t, tEnd - 0.2, tEnd, MV.ease.inQuad), 0)` 並回傳 `{shake: [6, 0]}`
- 實拍：配方 7（crop 位移＋tmix 動態模糊）

### 閃白 flash
- 何時用：副歌第一個 downbeat、衝擊、回憶切入；2 格全白，或瞬白後 0.25 秒衰減；一分鐘不超過 4 次
- 程式動畫：`transition: 'flash'`；拍點白閃回傳 `{flash: MV.pulse(f.t, t0, 0.08)}`，跟 kick 走回傳 `{flash: 0.8 * MV.hit('kick', f.t, 0.06)}`
- 實拍：配方 8a（2 格全白）、8b（瞬白衰減）、8c（剪點處白閃接下一鏡）、13（依 audio.json 的 downbeat 自動產 enable）

### 反轉 invert
- 何時用：衝擊格的簡化版，1–3 格負片，放在 snare 或字落下的瞬間；黑白高反差版見 anime.md〈實拍 4〉
- 程式動畫：`transition: 'invert'`；或 `{invert: MV.pulse(f.t, t0, 0.05) > 0.5 ? 1 : 0}`
- 實拍：配方 9、13b

### 遮罩擦 wipe
- 何時用：空間轉移、章節切換、分割畫面的進出；擦的方向跟著畫面裡的運動方向
- 程式動畫：`transition: 'wipe', overlap: beatDur`；自訂形狀用 `ctx.clip()`：
```js
const p = MV.prog(f.t, t0, t0 + beatDur, MV.ease.inOutCubic);
ctx.save(); ctx.beginPath(); ctx.rect(0, 0, f.W * p, f.H); ctx.clip(); drawNext(ctx, f); ctx.restore();
```
- 實拍：配方 2（xfade 內建：wipeleft、slideleft、circleopen、radial、smoothleft、pixelize、hblur、zoomin）、17（custom expr 斜向擦）

### 縮放衝擊 zoom punch
- 何時用：kick 上的 punch-in（放大 5–10% 指數回彈）、副歌進入的 25% 推進停住
- 程式動畫：`transition: 'zoom'`；拍點版回傳 `{zoom: 1 + 0.08 * MV.hit('kick', f.t, 0.1)}`
- 實拍：配方 10b（單次）、13c（每個 kick）、10c（zoompan 緩推）

### 分割畫面 split screen
- 何時用：兩條線同時進行、對比（過去／現在）、合唱；分割線要在拍上進出
- 程式動畫：
```js
const p = MV.prog(f.t, t0, t0 + beatDur, MV.ease.outCubic);                                    // 右半從右側滑入
ctx.save(); ctx.beginPath(); ctx.rect(0, 0, f.W / 2, f.H); ctx.clip(); drawLeft(ctx, f); ctx.restore();
ctx.save(); ctx.translate(f.W / 2 * (2 - p), 0); ctx.beginPath(); ctx.rect(0, 0, f.W / 2, f.H); ctx.clip(); drawRight(ctx, f); ctx.restore();
```
- 實拍：配方 11a（hstack）、11b（xstack 2×2）、11c（第二格在拍點滑入）

### 文字作為轉場
- 何時用：章節名、歌詞關鍵字、數字當兩場之間的黑卡，長度 1 拍（或 2 格的瞬間字卡）；字卡本身就是剪點，下一場從字卡後的 downbeat 開始
- 程式動畫：
```js
{ id: 'card', start: t0, end: t0 + beatDur, render(ctx, f) {
    ctx.fillStyle = '#000'; ctx.fillRect(0, 0, f.W, f.H);
    const lay = MV.layout(ctx, '第二章', { font: MV.font('Noto Serif TC', 160, 900), size: 160, tracking: 0.08 });
    MV.drawGlyphs(ctx, lay, (f.W - lay.width) / 2, f.H / 2 + 60, { color: '#fff' });
} }
```
- 實拍：配方 14（drawtext 黑卡 concat）、18（剪點前 3 格黑場）

## 三、實拍 ffmpeg 配方

約定：素材 `a.mp4`、`b.mp4`、`c.mp4` 為 1280×720、30fps、6 秒（合成法在文末）；輸出一律 `-c:v libx264 -crf 18`；表示式裡 `t` 是秒、`n` 是格序；`between(t,a,b)` 含兩端，要剛好 N 格寫 `between(t,b,b+(N-0.5)/fps)`。

```bash
# 1 精準到格的剪段（重編碼；-ss 放在 -i 前面也精準，因為會解碼再丟棄）
ffmpeg -ss 1.5 -to 3.5 -i a.mp4 -c:v libx264 -crf 18 -c:a aac out/cut.mp4
# 1b 同一件事用 trim／atrim（要接濾鏡鏈時用這個）
ffmpeg -i a.mp4 -filter_complex "[0:v]trim=1.5:3.5,setpts=PTS-STARTPTS[v];[0:a]atrim=1.5:3.5,asetpts=PTS-STARTPTS[a]" -map "[v]" -map "[a]" -c:v libx264 -crf 18 -c:a aac out/cut.mp4
# 1c 直接指定格序 45–104（60 格）
ffmpeg -i a.mp4 -vf "select='between(n,45,104)',setpts=N/30/TB" -af "atrim=1.5:3.5,asetpts=PTS-STARTPTS" -c:v libx264 -crf 18 -c:a aac out/cut.mp4

# 2 xfade 轉場：offset = A 的長度 − duration；transition 換成 fade、fadewhite、fadeblack、wipeleft、slideleft、circleopen、pixelize、hblur、zoomin、radial、smoothleft（全名單 ffmpeg -h filter=xfade）
ffmpeg -i a.mp4 -i b.mp4 -filter_complex "[0:v][1:v]xfade=transition=fadewhite:duration=0.5:offset=5.5[v];[0:a][1:a]acrossfade=d=0.5[a]" -map "[v]" -map "[a]" -c:v libx264 -crf 18 -c:a aac out/xfade.mp4

# 3a 速度斜坡（連續）：2 秒前 1 倍，2–3 秒 1 倍線性加到 4 倍，之後 4 倍；輸出 pts 是速度倒數的積分，所以中段是 log
ffmpeg -i a.mp4 -vf "setpts='if(lt(T,2),T,if(lt(T,3),2+log(1+3*(T-2))/3,2+log(4)/3+(T-3)/4))/TB',fps=30" -an -c:v libx264 -crf 18 out/ramp.mp4
# 3b 分段速度（0.5 倍 → 1 倍 → 3 倍）再 concat
ffmpeg -i a.mp4 -filter_complex "[0:v]trim=0:1,setpts=(PTS-STARTPTS)*2[s];[0:v]trim=1:3,setpts=PTS-STARTPTS[n];[0:v]trim=3:6,setpts=(PTS-STARTPTS)/3[f];[s][n][f]concat=n=3:v=1:a=0,fps=30[v]" -map "[v]" -an -c:v libx264 -crf 18 out/ramp_seg.mp4
# 3c 慢動作要補格：先 minterpolate 到 60fps 再放慢 2 倍（慢，只對需要的短段做；-t 放在 -i 前面才是限制輸入）
ffmpeg -t 2 -i a.mp4 -vf "minterpolate=fps=60:mi_mode=mci,setpts=2*PTS,fps=30" -an -c:v libx264 -crf 18 out/slow.mp4

# 4 停格：2.0 秒停 1 秒再續播；音訊同步補靜音
ffmpeg -i a.mp4 -filter_complex "[0:v]trim=0:2,setpts=PTS-STARTPTS,tpad=stop_mode=clone:stop_duration=1[v0];[0:v]trim=2,setpts=PTS-STARTPTS[v1];[v0][v1]concat=n=2:v=1:a=0[v];[0:a]atrim=0:2,asetpts=PTS-STARTPTS,apad=pad_dur=1[a0];[0:a]atrim=2,asetpts=PTS-STARTPTS[a1];[a0][a1]concat=n=2:v=0:a=1[a]" -map "[v]" -map "[a]" -c:v libx264 -crf 18 -c:a aac out/freeze.mp4

# 5a 倒放整段（reverse 會把整段讀進記憶體，只對短段用）
ffmpeg -i a.mp4 -vf reverse -af areverse -c:v libx264 -crf 18 -c:a aac out/rev.mp4
# 5b 乒乓：2–3 秒正放再倒放
ffmpeg -i a.mp4 -filter_complex "[0:v]trim=2:3,setpts=PTS-STARTPTS,split[f][r0];[r0]reverse[r];[f][r]concat=n=2:v=1:a=0[v]" -map "[v]" -an -c:v libx264 -crf 18 out/pingpong.mp4

# 6a 三連 stutter：第 60 格起 8 格重複 3 次（loop=2 表示再放 2 次）
ffmpeg -i a.mp4 -filter_complex "[0:v]trim=start_frame=60:end_frame=68,setpts=PTS-STARTPTS,loop=loop=2:size=8:start=0[v]" -map "[v]" -an -c:v libx264 -crf 18 out/stutter.mp4
# 6b 放回原片：前段 + 三連 + 後段
ffmpeg -i a.mp4 -filter_complex "[0:v]trim=0:2,setpts=PTS-STARTPTS[pre];[0:v]trim=start_frame=60:end_frame=68,setpts=PTS-STARTPTS,loop=loop=2:size=8:start=0[st];[0:v]trim=start_frame=68,setpts=PTS-STARTPTS[post];[pre][st][post]concat=n=3:v=1:a=0[v]" -map "[v]" -an -c:v libx264 -crf 18 out/stutter_full.mp4
# 6c 每次放大（1.0 → 1.15 → 1.3）
ffmpeg -i a.mp4 -filter_complex "[0:v]trim=start_frame=60:end_frame=68,setpts=PTS-STARTPTS,split=3[s1][s2][s3];[s2]scale=iw*1.15:-2,crop=1280:720[z2];[s3]scale=iw*1.3:-2,crop=1280:720[z3];[s1][z2][z3]concat=n=3:v=1:a=0[v]" -map "[v]" -an -c:v libx264 -crf 18 out/stutter_zoom.mp4

# 7 whip：先放大 1.4 倍，A 最後 0.2 秒 crop 視窗加速甩到右邊、B 前 0.2 秒從左邊減速甩回中央，硬切；concat 後 split，tmix 整流做動態模糊，只在剪點前後 0.2 秒用 overlay 疊回
#   （tmix 直接加 enable 會少掉最後一格，所以用 split＋overlay）
ffmpeg -i a.mp4 -i b.mp4 -filter_complex "[0:v]trim=0:3,setpts=PTS-STARTPTS,scale=iw*1.4:-2,crop=1280:720:x='(iw-1280)/2+(iw-1280)/2*if(gt(t,2.8),pow((t-2.8)/0.2,2),0)':y='(ih-720)/2'[va];[1:v]trim=0:3,setpts=PTS-STARTPTS,scale=iw*1.4:-2,crop=1280:720:x='(iw-1280)/2*if(lt(t,0.2),1-pow(1-t/0.2,2),1)':y='(ih-720)/2'[vb];[va][vb]concat=n=2:v=1:a=0,split[o][m];[m]tmix=frames=4[blur];[o][blur]overlay=enable='between(t,2.8,3.2)'[v]" -map "[v]" -an -c:v libx264 -crf 18 out/whip.mp4

# 8a 閃白：2.0 秒起剛好 2 格全白
ffmpeg -i a.mp4 -vf "drawbox=color=white@1:t=fill:enable='between(t,2,2.05)'" -c:v libx264 -crf 18 -c:a copy out/flash.mp4
# 8b 瞬白後 0.25 秒退回畫面（fade in from white）
ffmpeg -i a.mp4 -vf "fade=t=in:st=2:d=0.25:c=white" -c:v libx264 -crf 18 -c:a copy out/flash_decay.mp4
# 8c 剪點處白閃接下一鏡：B 的開頭從白衰減進來
ffmpeg -i a.mp4 -i b.mp4 -filter_complex "[0:v]trim=0:3,setpts=PTS-STARTPTS[v0];[1:v]trim=0:3,setpts=PTS-STARTPTS,fade=t=in:st=0:d=0.2:c=white[v1];[v0][v1]concat=n=2:v=1:a=0[v]" -map "[v]" -an -c:v libx264 -crf 18 out/flash_cut.mp4

# 9 反轉：2.0 秒起 3 格負片
ffmpeg -i a.mp4 -vf "negate=enable='between(t,2,2.083)'" -c:v libx264 -crf 18 -c:a copy out/invert.mp4

# 10a 緩推 ease 進 downbeat：0→2 秒 outCubic 放大到 1.2，2 秒正好停（scale 要 eval=frame 才吃 t）
ffmpeg -i a.mp4 -vf "scale=w='iw*(1+0.2*(1-pow(1-min(t/2,1),3)))':h=-2:eval=frame,crop=1280:720" -c:v libx264 -crf 18 -c:a copy out/easein.mp4
# 10b punch-in：2.0 秒瞬間 1.25 倍，指數回彈到 1.1 停住
ffmpeg -i a.mp4 -vf "scale=w='iw*if(lt(t,2),1,1.1+0.15*exp(-(t-2)*10))':h=-2:eval=frame,crop=1280:720" -c:v libx264 -crf 18 -c:a copy out/punch.mp4
# 10c zoompan 版緩推：每格推一點，60 格內到 1.3 倍，中心不動
ffmpeg -i a.mp4 -vf "zoompan=z='min(1+0.3*on/60,1.3)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s=1280x720:fps=30" -c:v libx264 -crf 18 -c:a copy out/zoompan.mp4
# 10d roll：−3° 轉回 0°，2 秒正好停；先放大 1.1 遮掉旋轉露出的邊
ffmpeg -i a.mp4 -vf "scale=iw*1.1:-2,rotate=a='-3*PI/180*pow(1-min(t/2,1),3)':c=black,crop=1280:720" -c:v libx264 -crf 18 -c:a copy out/roll.mp4
# 10e 段內 reframing：2 秒硬切到 1.3 倍、裁右上角
ffmpeg -i a.mp4 -vf "scale=w='iw*if(lt(t,2),1,1.3)':h=-2:eval=frame,crop=1280:720:x='iw-1280':y=0" -c:v libx264 -crf 18 -c:a copy out/reframe.mp4

# 11a 左右分割（各取中間 640 寬）
ffmpeg -i a.mp4 -i b.mp4 -filter_complex "[0:v]crop=640:720:320:0[l];[1:v]crop=640:720:320:0[r];[l][r]hstack=inputs=2[v]" -map "[v]" -map 0:a -c:v libx264 -crf 18 -c:a copy out/split2.mp4
# 11b 2×2 四格（各縮到 640×360）
ffmpeg -i a.mp4 -i b.mp4 -i c.mp4 -i a.mp4 -filter_complex "[0:v]scale=640:360[s0];[1:v]scale=640:360[s1];[2:v]scale=640:360[s2];[3:v]scale=640:360,negate[s3];[s0][s1][s2][s3]xstack=inputs=4:layout=0_0|w0_0|0_h0|w0_h0[v]" -map "[v]" -map 0:a -c:v libx264 -crf 18 -c:a copy out/split4.mp4
# 11c 第二格在拍點滑入：右半從畫面外滑到位，2 秒到位（outCubic）
ffmpeg -i a.mp4 -i b.mp4 -filter_complex "[1:v]crop=640:720:320:0[r];[0:v][r]overlay=x='1280-640*(1-pow(1-min(t/2,1),3))':y=0:shortest=1[v]" -map "[v]" -map 0:a -c:v libx264 -crf 18 -c:a copy out/split_slide.mp4

# 12a J cut：畫面 3 秒才切到 B，B 的聲音 2 秒就先進（B 的畫面從它的第 1 秒開始，才跟聲音同步）
ffmpeg -i a.mp4 -i b.mp4 -filter_complex "[0:v]trim=0:3,setpts=PTS-STARTPTS[v0];[1:v]trim=1:4,setpts=PTS-STARTPTS[v1];[v0][v1]concat=n=2:v=1:a=0[v];[0:a]atrim=0:2,asetpts=PTS-STARTPTS[a0];[1:a]atrim=0:4,asetpts=PTS-STARTPTS[a1];[a0][a1]concat=n=2:v=0:a=1[a]" -map "[v]" -map "[a]" -c:v libx264 -crf 18 -c:a aac out/jcut.mp4
# 12b L cut：畫面 3 秒切到 B，A 的聲音延到 4 秒才淡出；B 的聲音用 adelay 推到 3 秒，amix 疊接（normalize=0 才不會壓低音量）
ffmpeg -i a.mp4 -i b.mp4 -filter_complex "[0:v]trim=0:3,setpts=PTS-STARTPTS[v0];[1:v]trim=0:3,setpts=PTS-STARTPTS[v1];[v0][v1]concat=n=2:v=1:a=0[v];[0:a]atrim=0:4,asetpts=PTS-STARTPTS,afade=t=out:st=3.5:d=0.5[a0];[1:a]atrim=0:3,asetpts=PTS-STARTPTS,adelay=3000:all=1,afade=t=in:st=3:d=0.3[a1];[a0][a1]amix=inputs=2:duration=longest:normalize=0[a]" -map "[v]" -map "[a]" -c:v libx264 -crf 18 -c:a aac out/lcut.mp4

# 13 依 audio.json 的拍點產 enable 表示式（Python 一行）：每個 downbeat 白閃 2 格
EXPR=$(/root/video-lab/.venv/bin/python -c "import json;d=json.load(open('data/audio.json'));N=2;fps=30;print('+'.join(f'between(t,{b:.3f},{b+(N-0.5)/fps:.3f})' for b in d['downbeats']))")
ffmpeg -i a.mp4 -vf "drawbox=color=white@1:t=fill:enable='$EXPR'" -c:v libx264 -crf 18 -c:a copy out/flash_downbeats.mp4
# 13b 同一招：每個 snare 負片 1 格
EXPR=$(/root/video-lab/.venv/bin/python -c "import json;d=json.load(open('data/audio.json'));N=1;fps=30;print('+'.join(f'between(t,{b:.3f},{b+(N-0.5)/fps:.3f})' for b in d['onsets']['snare']))")
ffmpeg -i a.mp4 -vf "negate=enable='$EXPR'" -c:v libx264 -crf 18 -c:a copy out/invert_snare.mp4
# 13c 每個 kick 瞬間放大 1.08 指數回彈（表示式相加，用在 scale 的 w）
EXPR=$(/root/video-lab/.venv/bin/python -c "import json;d=json.load(open('data/audio.json'));print('+'.join(f'gte(t,{b:.3f})*exp(-(t-{b:.3f})*12)' for b in d['onsets']['kick']))")
ffmpeg -i a.mp4 -vf "scale=w='iw*(1+0.08*($EXPR))':h=-2:eval=frame,crop=1280:720" -c:v libx264 -crf 18 -c:a copy out/kick_punch.mp4

# 14 文字作為轉場：A → 黑底字卡 0.4 秒 → B（字型用 fontconfig 名稱；要指定檔案改 fontfile=/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc）
ffmpeg -i a.mp4 -i b.mp4 -f lavfi -i "color=black:s=1280x720:r=30:d=0.4" -filter_complex "[0:v]trim=0:3,setpts=PTS-STARTPTS[v0];[2:v]drawtext=font='Noto Serif CJK TC':fontsize=120:fontcolor=white:text='第二章':x=(w-tw)/2:y=(h-th)/2[card];[1:v]trim=0:3,setpts=PTS-STARTPTS[v1];[v0][card][v1]concat=n=3:v=1:a=0[v]" -map "[v]" -an -c:v libx264 -crf 18 out/textcard.mp4

# 16 跳接：同一鏡 0–1.5 秒與 3–4.5 秒直接相接
ffmpeg -i a.mp4 -filter_complex "[0:v]trim=0:1.5,setpts=PTS-STARTPTS[v0];[0:v]trim=3:4.5,setpts=PTS-STARTPTS[v1];[v0][v1]concat=n=2:v=1:a=0[v];[0:a]atrim=0:1.5,asetpts=PTS-STARTPTS[a0];[0:a]atrim=3:4.5,asetpts=PTS-STARTPTS[a1];[a0][a1]concat=n=2:v=0:a=1[a]" -map "[v]" -map "[a]" -c:v libx264 -crf 18 -c:a aac out/jumpcut.mp4

# 17 自訂遮罩擦：xfade custom expr，P 是進度 0→1，A／B 是兩邊畫素；這條是斜向擦
ffmpeg -i a.mp4 -i b.mp4 -filter_complex "[0:v][1:v]xfade=transition=custom:duration=0.3:offset=5.7:expr='if(lt((X+Y)/(W+H),P),B,A)'[v]" -map "[v]" -an -c:v libx264 -crf 18 out/diagwipe.mp4

# 18 剪點前「吸氣」：A → 3 格黑 → B
ffmpeg -i a.mp4 -i b.mp4 -f lavfi -i "color=black:s=1280x720:r=30:d=0.1" -filter_complex "[0:v]trim=0:3,setpts=PTS-STARTPTS[v0];[1:v]trim=0:3,setpts=PTS-STARTPTS[v1];[v0][2:v][v1]concat=n=3:v=1:a=0[v]" -map "[v]" -an -c:v libx264 -crf 18 out/blackgap.mp4

# 19 match cut 對位檢查：A 最後一格與 B 第一格並排；再用 signalstats 看兩格平均亮度（YAVG）是否刻意對比或連續
ffmpeg -sseof -0.034 -i a.mp4 -frames:v 1 out/a_last.png
ffmpeg -i b.mp4 -frames:v 1 out/b_first.png
ffmpeg -i out/a_last.png -i out/b_first.png -filter_complex "[0][1]hstack" out/matchcheck.png
ffmpeg -i out/a_last.png -vf "signalstats,metadata=print:key=lavfi.signalstats.YAVG" -f null - 2>&1 | grep YAVG
```

## 四、剪點表工作流程

1. `python scripts/analyze.py song.mp3 -o data/audio.json --sections "intro:0,verse1:4,chorus1:12"`：拿到 tempo、beats、downbeats、段落表；對照段落摘要表確認小節序沒偏（第一個 downbeat 抓錯整張表就錯）
2. 複製 `templates/cuts.csv`，依密度表填剪點。欄位：
   - `bar`：小節序，從 0 起（bar 0 = audio.json 的第一個 downbeat）
   - `beat`：該小節第幾拍，1–4（`meter` 為 4 時）；段落邊界一律 1，子剪可以落在 2、3、4
   - `src`：素材路徑，建議相對路徑（`media/a.mp4`），在 repo 根目錄執行 cutlist.py
   - `in`：從 src 的第幾秒開始播（秒，小數）；這列會從該拍的時間播到下一列為止，最後一列播到下一個 downbeat
   - `speed`：播放速度，預設 1；只為設計用（刻意慢動作 0.5、快轉 2），不是對拍工具
   - `label`：備註，自由文字，不要含逗號；寫段落名與鏡頭意圖，qa 報告會帶出來
   - 第一列上方不要加註解，cutlist.py 直接讀表頭
3. **先把剪點表給我確認**，再 `python scripts/cutlist.py cuts.csv --audio-json data/audio.json -o out/montage.mp4 --music song.mp3 --sheet`：它會先印出絕對秒數、長度、來源的剪點表，再精準到格重編碼
4. `python scripts/qa.py out/montage.mp4 --audio-json data/audio.json -o out/qa`：看 `report.md` 的剪點誤差（±1 格內比例）、黑場與閃白次數，和每段落在 downbeat 抽格的 `sheet_<section>.png`；拼圖逐張看，找最弱的三處改 in-point 再跑一次
5. 選 in-point 的原則（每列的 `in` 怎麼挑）：
   - 動作接動作：in-point 落在動作中途（抬手到一半、轉身到一半），不要在靜止點
   - 視線方向：上一鏡人物看右，下一鏡的主體在右；相反就是刻意的衝突，要有理由
   - 明暗交替：亮鏡接暗鏡、暗接亮，拍點會更明顯；連續三個同明度的鏡頭會糊成一片（配方 19 的 YAVG 可以量）
   - 主體位置連續：主體在前一鏡結束的位置附近出現（或正好對角，做對比）；眼睛不用重新搜尋
   - 剪點前後各留 2 格以上的穩定畫面，不要剪在模糊格、閉眼格、過曝格上

## 五、剪輯自檢清單（交付前逐題回答）

1. 每個剪點都在 downbeat 或字前最後一拍？qa.py 報告 ±1 格內比例 ≥ 90%？
2. 密度曲線跟能量曲線一致？最後一次副歌比第一次密？橋段真的放慢了？
3. 標點符號（白閃、停格、反轉、衝擊格）一分鐘 ≤ 4 個，而且都在最重的拍？
4. 有沒有為了湊拍改原片速度？有就換素材或換 in-point
5. 每個 in-point 檢查過動作、視線、明暗、主體位置四項？
6. 鏡頭運動結束在拍上（不是開始在拍上）？
7. 轉場語言一支片一套？硬切為主、溶接 ≤ 3 處？
8. 關掉聲音看一次還看得出拍嗎？只聽聲音想像畫面，剪點落在你預期的地方嗎？

## 出處

- Walter Murch, *In the Blink of an Eye*（Silman-James Press）：Rule of Six，剪點優先序為情緒 51%、故事 23%、節奏 10%、視線 7%、畫面二維 5%、三維空間 4%；本文的「動作接動作」「視線方向」「主體位置連續」是第四到第六條的實作
- Tony Zhou, Every Frame a Painting《Edgar Wright – How to Do Visual Comedy》（2014）：whip pan、聲畫同步的喜劇剪法、用剪點取代鏡頭內的動作
- Karen Pearlman, *Cutting Rhythms*（Focal Press）：剪輯節奏的脈動、緩急與速度
- pdoom-video `app/src/timeline.ts`（剪點 = 字前最後一拍、段尾最近 downbeat）、`docs/TREATMENT.md` Tone 段（大變化落在拍上、運動 ease 進 downbeat、強緩動＋停＋snap）；anime-op `STORYBOARD.md`（密度曲線跟能量曲線）
- `references/anime.md` 已列的出崎統演出、撮影處理、MAD 十條
- ffmpeg 濾鏡手冊 https://ffmpeg.org/ffmpeg-filters.html（xfade、tmix、tpad、loop、zoompan、xstack、setpts、drawbox、drawtext、minterpolate、amix）

## 實測紀錄

- 環境：ffmpeg 6.1.1-3ubuntu5（Ubuntu，libx264、libfreetype、libfontconfig）；字型 Noto Sans CJK TC／Noto Serif CJK TC
- 素材：`ffmpeg -f lavfi -i testsrc2=size=1280x720:rate=30 -f lavfi -i "sine=frequency=440:sample_rate=48000" -t 6 -pix_fmt yuv420p a.mp4`；b.mp4 用 `smptebars=size=1280x720:rate=30` 與 660 Hz；c.mp4 用 testsrc2 加 `-vf hue=h=120` 與 880 Hz。三支都是 h264 1280×720 30fps 180 格、aac 48 kHz 單聲道
- 驗證方法：`ffprobe -show_entries stream=nb_frames,duration`；指定格的亮度用 `select='between(n,a,b)',scale=1:1` 加 `-fps_mode passthrough` 輸出 gray rawvideo（不加 passthrough 會補格，看不出真相）；音訊切換用 `astats` 的零交越率（440 Hz ≈ 0.018、660 Hz ≈ 0.028）
- 測試用 audio.json：tempo 120、beats 每 0.5 秒、downbeats 0.5／2.5／4.5、snare 整數秒；lyrics.json 兩行，字起 2.56 與 4.48

| 配方 | 檢查 | 結果 |
|---|---|---|
| 1、1b、1c | 60 格、2.000 秒 | 三種寫法都是 60 格 |
| 2 | 11 種 transition 各跑一次 | 都成功，345 格、11.5 秒（6+6−0.5） |
| 3a | 預期 2+ln4/3+0.75 = 3.21 秒 | 96 格、3.200 秒 |
| 3b | 2+2+1 秒 | 150 格、5.000 秒 |
| 3c | 2 秒放慢成 4 秒 | 120 格、4.000 秒（`-t` 要放在 `-i` 前） |
| 4 | 180+30 格、音訊同長 | 210 格、7.000 秒；音訊 7.016 秒（aac 補尾） |
| 5a、5b | 180 格；30+30 格 | 180 格；60 格 |
| 6a、6b、6c | 24 格；180+16 格；24 格 | 24；196；24 |
| 7 | 180 格、抽格看到拖影 | 180 格；tmix 直接加 enable 得 179 格（掉最後一格），改 split＋overlay 後 180 |
| 8a | 第 60、61 格白，62 恢復 | 131 255 255 131；`between(t,2,2.066)` 會多一格（含兩端），改 2.05 |
| 8b、8c | 跑通、格數 | 180；180 |
| 9 | 第 60–62 格負片 | 131 135 135 135 131（三格變了） |
| 10a–10e | 輸出仍是 1280×720、180 格 | 五條都是 1280×720、180 格；10b 抽格看到瞬間放大再回彈 |
| 11a、11b、11c | 1280×720、180 格；抽格看四宮格 | 三條都是；11b 四格正確 |
| 12a | 1.9 秒 440 Hz、2.1 秒 660 Hz | 零交越率 0.0183 → 0.0275，聲音比畫面早 1 秒進 |
| 12b | 2.5 秒 440、3.2 秒混合、4.5 秒 660 | 0.0183 → 0.0271 → 0.0275 |
| 13 | 第 15、16 格白、17 不白；75、76；135、136 | 131 255 255 131 … 全對；原本 `b+2/30` 多一格，改 `(N-0.5)/fps` |
| 13b | 第 30、60 格各一格負片 | 131 134 131 131 131 135 131 131 |
| 13c | 跑通、1280×720、180 格 | 是 |
| 14、14b | 90+12+90 格；fontfile 版 12 格；抽格看到「第二章」白字 | 192；12；字正確 |
| 16 | 45+45 格 | 90 格、3.000 秒 |
| 17 | 12−0.3 秒；抽格看到斜向分界 | 351 格、11.700 秒；分界正確 |
| 18 | 90+3+90 格 | 183 格、6.100 秒 |
| 19 | 並排圖、YAVG | 產出 matchcheck.png；YAVG 125.5 與 95.8 |
| 20 | cut 夜色 = 2.5、cut 我們 = 4.5（4.48+0.02 在容許內）、after 夜色 = 4.5 | 全對 |
