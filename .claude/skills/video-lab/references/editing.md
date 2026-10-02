# 音樂驅動的剪輯文法與實拍配方

做 MV、節奏型蒙太奇（montage）、踩點剪（音ハメ）時讀這份。前置：`scripts/analyze.py` 產出 `data/audio.json`；歌詞 MV 另用 `scripts/align.py` 產出 `data/lyrics.json`。
- 概念與分鏡：`references/mv-direction.md`；色彩、字型排印、後製、輸出規格：`references/craft.md`
- 日系演出（集中線、衝擊格、白閃、止め絵、賽璐璐、3回PAN）：`references/anime.md`，這裡只引用不重寫
- 兩條路線、同一套文法：程式動畫用 `assets/mv-kit.js`（全域 `MV`）的 `MV.timeline` 排場景；實拍素材用 `templates/cuts.csv` 填剪點表 → `scripts/cutlist.py` 出 montage，單招用第三節的 ffmpeg 配方（全部在本機 ffmpeg 6.1.1 實測，紀錄在文末）

## 一、基本法則

### 1. 剪在哪裡
- 大切（換場景、換鏡頭）只有兩種時間點：段落邊界剪在 downbeat（小節第一拍）；歌詞驅動的剪點剪在「該行第一個字之前的最後一拍」，永遠不晚於字。觀眾要先看到新畫面再聽到字，反過來就是遲到。段內子剪與密度表的「每拍一刀」落在 beats（kick、snare，一.5），不在拍上的例外見一.9
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
- 實拍（Python，讀 audio.json 與 lyrics.json；實測見文末表最後一列）：
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
- 誤差標準：剪點落在拍點 ±1 格內（30fps 為 ±33 ms）。`scripts/qa.py` 算這個比例，門檻 ≥ 90%，低於 90% 回去修。這個數字只在本條維護，程式渲染與實拍 montage 同一門檻：`SKILL.md` C 段第 4 步與 G 段第 8 步、本文〈五、剪輯自檢清單〉第 1 題、`craft.md`〈六、視覺自檢清單〉第 6 題都引用這裡。不到 100% 的那 10% 留給〈9. 情緒優先於拍格的例外〉算好的例外名額，不是給誤差

### 2. 硬切為主，溶接極少
- 預設硬切：`MV.timeline` 的 entry 不寫 `transition` 就是硬切；cuts.csv 每列都是硬切
- 溶接（dissolve／crossfade）只用在三種地方：時間流逝、夢或回憶的進出、同一主體兩個時刻的疊影。一支 MV 不超過 3 處
- 轉場效果（白閃、擦、縮放）是語氣詞，整支片用同一套，不要每個剪點換一種

### 3. 剪輯密度表
每小節刀數 = 該段落平均每小節剪幾次（含段內子剪）。強度 = 刀數、鏡頭運動、特效、字級的整體刺激量，副歌 = 100%。強度數字以本表為準：anime.md 的 40／70／100 與 craft.md〈標點符號原則〉的 intro 40%、verse 70%、bridge 30% 都是本表範圍內的單點值，那兩處只引用、不另定。

先決定感知拍（tactus，聽的時候點頭的那一拍），表裡的「拍」與「小節」都指感知拍，不是 analyze.py 印出來的任何數字：
- analyze.py 的 tempo 用 `librosa.feature.tempo` 估，可能是感知速度的兩倍或一半（實測 170 BPM 的 testsong 被估成 84.96、70 BPM 估成 70.03）。印出的 tempo 與點頭的速度差一倍時用 `--bpm` 覆寫再跑，否則 beats／downbeats 整張表都是另一個尺度
- 歌 > 150 BPM、或鼓是 half-time（snare 只落第 3 拍）：把表的「一拍」當「兩拍」用（每拍一刀 → 每兩拍一刀），八分音符子剪不用
- 歌 < 80 BPM：把表的「一拍」當「半拍」用，否則主歌「每小節一刀」是 3 秒以上一鏡
- 最短鏡頭長度下限 6 格（30 fps 0.2 秒）：再短觀眾辨識不出畫面內容，只剩閃爍；170 BPM 的八分音符是 5 格，就是不能照表填的例子。例外只有刻意的三連 stutter（配方 6）與衝擊格

| 段落 | 每小節刀數 | 鏡頭語言 | 強度 |
|---|---|---|---|
| 前奏 intro | 0.25–0.5（每 2–4 小節一刀）或 0（不切） | 建立鏡頭、空景、慢推；第一格就要有主題（開場鉤子） | 30–40% |
| 主歌 verse | 1（每小節一刀，含子剪） | 中景跟人、對稱構圖、動作在畫面內不靠剪；大切每 2 小節在 downbeat，中間一次子剪 | 60–70% |
| 導歌 pre-chorus | 2（每 2 拍一刀），逐小節加密到每拍 | 越剪越近（中景→特寫），最後 2 小節每拍一個 punch-in，把能量推上副歌 | 80–90% |
| 副歌 chorus | 2–4（每 1–2 拍一刀） | 特寫與全景交替、符號鏡頭、招牌動作每次副歌重複；白閃只放第一個 downbeat | 100% |
| 間奏 interlude | 1 | 器樂主導：長鏡頭跟運動、鏡頭運動 ease 進 downbeat，少剪多動 | 70% |
| 橋段 bridge | 0–0.25（一鏡到底或 4 小節一刀） | 止め絵、慢動作、留白、靜止格、抽掉顏色；為最後一次副歌蓄力 | 30–50% |
| 最後副歌 final chorus | 4–8（每拍一刀，可加八分音符子剪） | 招牌動作的極限版、全片唯一的強調色；比第一次副歌密 | 100% |
| 尾奏 outro | 4（每拍一刀）或 0（一鏡到底） | 每拍一刀的回顧蒙太奇，或單一長鏡頭收回首格；首尾畫面呼應讓影片可以首尾相接重播 | 100% → 0% |

- 這是唯一的密度表；`mv-direction.md` 第五節〈段落能量 → 剪輯密度與鏡頭語言〉的段落列（含間奏）與數字與此相同，改動時以本表為準、兩表一起改
- 密度曲線要貼著能量曲線（anime-op 分鏡的做法：第三段主歌起加快、橋段放慢、尾奏每拍一刀）；最後一次副歌要比第一次密
- 同一段落內不要均勻：小節 1、3 重，2、4 輕，觀眾才感覺得到「拍」而不是「頻率」

### 4. 緩急：標點符號原則
- 止め絵、白閃、衝擊格、停格、反轉是標點符號，只放最重的拍：每段副歌的第一個 downbeat、橋段結尾、全曲最高點。上限只有一條、以 craft.md〈標點符號原則〉為準：一小節最多一次、一段落最多四次（跟 BPM 無關；做法見 anime.md〈節奏原則〉與〈實拍 2、4、6〉）
- 重拍前留一拍「吸氣」：副歌前最後一拍可以空（黑場、停格、靜止鏡頭），下一個 downbeat 的衝擊會放大（配方 17）

### 5. 段內子剪（同一場景不換鏡）
- reframing：同一鏡頭硬切到另一個裁切（1.0 → 1.3 倍、換角落），落在拍上，長鏡頭不會悶（配方 10e）
- punch-in：拍點瞬間放大 4–8%（1.04–1.08）再指數回彈或停住，用在 kick、snare、重複的副歌字（配方 10b、13c）；幅度以 craft.md〈震動、閃爍、縮放、鏡頭〉為準，超過 1.1 像縮放錯誤。要更大的構圖跳變（1.3 倍、換角落）用 reframing：它是剪點，不受 punch-in 的上限
- roll：鏡頭從 −3° 轉回 0°，結束在 downbeat（配方 10d）
- 三者都是 t 的函式：程式動畫用 `ctx.translate／scale／rotate` 包住場景再畫；實拍的縮放類用 `zoompan`（配方 10a、10b、10e、13c），roll 用 `scale`＋`rotate`＋`crop`（配方 10d）。逐格變化的縮放不能用 `scale=eval=frame` 接 `crop`，理由見第三節約定
- 子剪也落在拍上（kick、snare）；八分音符子剪與拍間的反拍切在 cuts.csv 的 `beat` 填半拍（2.5）。反拍切（大切落在 beat 2、4 或拍間）一支片只用一兩次，當作「失衡」的語彙，cuts.csv 的 label 要註明是刻意的

### 6. 鏡頭運動要 ease 進 downbeat
- 運動「結束」在拍上，不是開始在拍上：推進、搖、轉用 `outCubic`／`outExpo` 讓終點正好落在 downbeat，觀眾把拍點感知為「到位」
- 程式動畫：`const z = 1 + 0.2 * MV.prog(f.t, t1 - beatDur * 2, t1, MV.ease.outCubic);`（t1 = 目標 downbeat）
- 實拍：配方 10a（`1-pow(1-min(time/2,1),3)` 就是 outCubic，2 秒正好停）

### 7. 不要改原片速度硬湊拍點
- 節奏不合就換素材或換 in-point。速度只為設計服務（刻意的慢動作、斜坡），不是對拍工具；cuts.csv 的 `speed` 欄同理
- 慢動作要補格（配方 3c）或用高格率原片（60 fps 以上）；快轉超過 2 倍要加動態模糊（配方 7 的 tmix 做法），不然像跳格

### 8. 動作接動作
- 兩個鏡頭在同一個動作的中途相接（action cut），動作本身蓋掉剪點，是最不被察覺的剪法；拍點上的剪接尤其要這樣，觀眾才覺得畫面「打在拍上」而不是「剛好換了」

### 9. 情緒優先於拍格的例外
- Murch 的六條優先序是情緒、故事、節奏、視線、畫面二維、三維空間（出處）。MV 的節奏由歌曲先決定，所以本文其餘條目都在講「服從節奏」；違背節奏的名額要先留好：一支片 2–3 處不剪在拍上、或跨過 downbeat 續留一鏡，每一處都要說得出理由，寫進 cuts.csv 的 label 或分鏡表備註
- 可以跨過 downbeat 續留一鏡的三種情況：
  - 表演高點：眼神、吸氣、一個動作做到一半。剪掉就是殺掉表演；續留到動作完成後的下一個拍點（beat 2、3、4 都可以）再切，不必等下一個 downbeat
  - 歌詞語意轉折：一行的意思在最後一個字才翻（「我以為你會留下」唱到「留下」才知道是沒有），畫面停在那張臉上直到字唱完，用 `after()`（行尾最近的 downbeat）而不是 `cut()`
  - 反應鏡頭：事件在拍上發生，但觀眾要看到「人看見了」；反應鏡頭可以晚 1–2 拍進，長度不必是整數拍
- 規則：不在拍上的那一刀，前後兩刀都要在拍上，觀眾才讀得出它是刻意的；連續兩刀都不在拍上只是鬆
- 量法：qa.py 的「±1 格內 ≥ 90%」（門檻見〈1. 剪在哪裡〉）留給這些例外，不是給誤差；例外以外的剪點要 100% 命中。例外的列在 label 寫「跨拍 理由」，看 report.md 時才對得起來

### 10. 對嘴鏡頭對時（lip-sync）
- 對嘴鏡頭的 `in` 不能用眼睛填：差 2 格（67 ms）口型就穿幫，差 1 格看得出「軟」。拍攝端的規則（每個 take 都用同一份回放、機內收音不關、起播小節寫進檔名、慢動作用 k 倍速回放）見 `mv-direction.md`〈表演型實拍規則〉
- 以主音軌為準：把 take 的機內收音抽出來，與現場實際回放的檔（母帶 `song.wav`；慢動作時是 `song_x2.wav` 這種 k 倍速版）做能量包絡的交叉相關（cross-correlation），得到 L = take 的 0 秒在回放檔的第幾秒；該列的 `in = T / k − L`，T 是那列 bar／beat 的歌曲秒（`downbeats[bar] + (beat − 1) × 拍長`），正常回放 k = 1。搜尋視窗限制在起播小節附近，不然歌的重複段會對到別處。`mv-direction.md`〈表演型實拍規則〉用另一個量 p（回放起點在 take 裡的秒數）寫成 `in = p + (T − S) / k`，S 是起播小節的歌曲秒；L = S / k − p，兩式相等（實測 k = 1 與 k = 2 各三列印出的 `in` 一致）。慢動作 take 一律跑本文的程式、讀現場實際放的 k 倍速回放檔，不要拿母帶量
- 多機位、多 take：每支檔各算一次 L；同一句的不同 take 在剪點表只換 `src` 與 `in`，`bar`／`beat` 不動
- 指令（實測：合成 take 在 k = 1 與 k = 2 都與真值差 0 ms，見文末表；`python -` 後面的引數依序是回放檔、take 音軌、起播小節、k）：
```bash
ffmpeg -i media/take.mp4 -vn -ac 1 -ar 44100 out/take.wav     # 抽機內收音；取樣率要與回放檔一樣
/root/video-lab/.venv/bin/python - song.wav out/take.wav 8 1 <<'EOF'
# 算 take 相對回放檔的位置，直接印出剪點表每列要填的 in
import json, sys, numpy as np, soundfile as sf
from scipy.signal import correlate
ref_path, take_path, start_bar, k = sys.argv[1], sys.argv[2], int(sys.argv[3]), float(sys.argv[4])
ref, sr = sf.read(ref_path); ref = ref.mean(axis=1) if ref.ndim > 1 else ref   # 現場實際回放的檔（母帶或 k 倍速版）
take, sr2 = sf.read(take_path); assert sr == sr2, '取樣率要一樣'
au = json.load(open('data/audio.json')); db = au['downbeats']; beat = 60 / au['tempo']
lead_max = 4.0                                                                  # 拍板前導最多幾秒
hop = sr // 1000                                                                # 1 kHz 能量包絡
env = lambda x: np.sqrt((x[:len(x) // hop * hop].reshape(-1, hop) ** 2).mean(axis=1))
er, et = env(ref), env(take); er -= er.mean(); et -= et.mean()
c = correlate(er, et, mode='full'); lags = (np.arange(len(c)) - (len(et) - 1)) * hop / sr
expect = db[start_bar] / k                                                      # 起播小節在回放檔裡的秒數
win = (lags > expect - lead_max) & (lags < expect + 1)                          # 只在起播小節附近找
L = lags[win][np.argmax(c[win])]
print(f'take 的 0 秒 = 回放檔 {L:.3f} 秒（起播小節在 take 的 {expect - L:.3f} 秒）')
for bar, b in [(8, 1), (10, 1), (12, 3)]:                                      # 這支 take 要用在哪幾列
    T = db[bar] + (b - 1) * beat
    print(f'bar {bar} beat {b}: 歌曲 {T:.3f} 秒 → in = {T / k - L:.3f}')
EOF
```
- 算出來的 `in` 直接填進 cuts.csv；慢動作列的 `speed` 填 1/k。交付前抽 3 個對嘴剪點做聲畫同格檢查。一張 PNG 看不到人聲在哪一格，要把畫面與音訊能量放在同一個格序上看：剪點前後各 5 格拼成一列、每格燒上格序，再列出同一區間每格（1/30 秒）的 RMS；人聲起點是 RMS 跳升的那格，要跟嘴張開的那格相同，差 1 格就是「軟」。實測合成「第 60 格起才有聲」的檔：拼圖上的格序 55–65，RMS 第 58 格 −inf、59 格 −78、60 格 −21 dB
```bash
N=600   # 剪點的格序 = round(影片秒 × 30)；影片秒 = 歌曲秒 − out/montage.cuts.json 的 offset
ffmpeg -i out/montage.mp4 -vf "select='between(n,$((N-5)),$((N+5)))',drawtext=text='%{eif\:t*30+0.5\:d}':x=10:y=10:fontsize=48:fontcolor=white:box=1:boxcolor=black,scale=320:-2,tile=11x1" -fps_mode passthrough -frames:v 1 out/lip_$N.png
ffmpeg -i out/montage.mp4 -af "aresample=48000,asetnsamples=n=1600,astats=metadata=1:reset=1,ametadata=mode=print:key=lavfi.astats.Overall.RMS_level:file=out/rms.txt" -f null -   # 1600 樣本 = 48 kHz 的 1/30 秒
awk -v a=$((N-5)) -v b=$((N+5)) '/pts_time/{split($0,p,"pts_time:");t=p[2]+0} /RMS_level/{split($0,r,"=");f=int(t*30+0.5);if(f>=a&&f<=b)printf "格 %d  %.3f 秒  RMS %s dB\n",f,t,r[2]}' out/rms.txt
```

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

mv-kit 引數慣例（寫錯不一定報錯，先記住）：
- 緩動可傳 `MV.ease.*` 函式或名稱字串（`'outCubic'`）：`MV.keys`／`MV.prog` 用 `easeOf()` 查表，兩種寫法結果相同（實測 `MV.prog(0.5,0,1,'outCubic')` = 0.875）。寫錯不會中止：名稱拼錯 `console.error` 一次就退回預設（`prog` 退 linear、`keys` 退 inOutCubic），render.py 會把它印到 stderr（`[console.error] MV：沒有這個緩動「nope」，可用：…`）但 exit 0，所以每次渲染都要看 stderr；`MV.ease.outCubik` 這種拼錯的函式路徑是 `undefined`，連這行都沒有、exit 0，畫面只是「沒有緩動」。自檢：頁面載入時加 `for (const n of ['outCubic', 'outExpo']) if (!MV.ease[n]) throw new Error('沒有緩動 ' + n);`，拼錯就是 pageerror、render.py 以非 0 結束（實測 `[pageerror] 沒有緩動 outCubik`）
- Canvas 字型用 fontconfig 全名 `Noto Sans CJK TC`／`Noto Serif CJK TC`；別名只有 `Noto Sans TC` 可用，`Noto Serif TC` 會落到後備字型（無襯線）而且不報錯，實測與 `NoSuchFont` 畫出的畫素完全相同（craft.md〈可用字型〉）
- `MV.layout` 的 `tracking` 是每字額外間距的 px，不是 em：8% 字距寫 `size * 0.08`，或改傳 `trackingEm: 0.08`（layout／karaoke 會乘上字級；實測「第二章」160 px 兩種寫法都是 505.6 px 寬，不傳是 480）。用 `MV.fitSize` 算字級時第 6 個引數要傳同一個 tracking（固定 px 傳數字、em 傳 `px => px * 0.08`）：不傳算出 166.7 px，加上字距後整行 526.6 px 塞不進 maxW 500；傳了算出 158.2 px，整行 500.0
- `MV.drawGlyphs` 的顏色鍵是 `fill`／`stroke`（還有 `align`、`alpha`、`each`），沒有 `color`

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
- 實拍：沒有濾鏡能代勞，靠選 in-point；用配方 18 把 A 最後一格與 B 第一格並排看位置與明暗

### 跳接 jump cut
- 何時用：同一鏡頭去掉中間一段直接相接，表示時間跳躍、焦躁、重複；主歌的對嘴鏡頭每小節跳一次很常見
- 程式動畫：同一場景、本地時間每小節跳一段：`drawTalk(ctx, f.lt + Math.floor(f.lt / barDur) * 1.5);`
- 實拍：配方 15

### 速度斜坡 speed ramp
- 何時用：正常速度衝向拍點、拍點後瞬間變慢（或相反），用在副歌進入、動作高點；斜坡的轉折點要在 downbeat
- 程式動畫：把本地時間 warp 一次，場景照常畫（對應配方 3a）。緩動傳 `MV.ease.*` 函式或名稱字串，第 i 個關鍵格的緩動管「走向它」那一段，所以加速用的 `inCubic` 掛在 3 秒那格；`keys` 在最後一格之後保持端點值，要續播就再給一格
```js
const lt = MV.keys(f.lt, [[0, 0], [2, 2, MV.ease.linear], [3, 6, MV.ease.inCubic], [6, 18, MV.ease.linear]]);
drawRun(ctx, lt);   // 0–2 秒 1 倍；2–3 秒 inCubic 加速，走完 4 秒份的素材；3 秒後 4 倍續播（實測 lt 2.5→2.5、3→6、4→10）
```
- 實拍：配方 3a（連續 setpts 表示式）、3b（分段 concat）、3c（慢動作補格）；音樂會取代原音軌，一律 `-an`

### 停格 freeze
- 何時用：情緒高點、字卡落下、止め絵；停的長度是整數拍
- 程式動畫：`const lt = f.lt < 2 ? f.lt : f.lt < 3 ? 2 : f.lt - 1;`（2 秒處停 1 秒再續）
- 實拍：配方 4（兩段 concat，音訊同步補靜音）；片尾停格直接用 anime.md〈實拍 2〉

### 倒放 reverse
- 何時用：回溯、乒乓來回（正放→倒放）填滿一個小節、動作「收回」接下一拍
- 程式動畫：`const lt = f.lt < d ? f.lt : 2 * d - f.lt;`（乒乓，d = 來回一趟的一半；只在長度正好 2d 的 entry 內用，lt 超過 2d 會變負）。要重複來回用 `const u = f.lt % (2 * d); const lt = u < d ? u : 2 * d - u;`（實測 d = 1：lt 0.5／1.5／2.5 → 0.5／0.5／0.5，單趟版第三個是 −0.5）
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
- 何時用：兩個空間、兩個人之間的高速轉場，動作喜劇感（Edgar Wright）；方向要一致：A 的畫面往左甩出，B 的畫面也從右往左甩入（同一個 pan 方向；mv-kit 的 `whip` 與配方 7 都是這個方向）
- 規格只有一條、以 craft.md〈震動、閃爍、縮放、鏡頭〉為準：whip 總長 ≤ 4 格（30 fps 0.13 秒）、橫移 ≥ 半個畫面、渲染 `--samples 24`。mv-kit 的 `whip` 預設 overlap 0.25 秒 = 7.5 格，超過規格，一定明寫 `overlap: 4 / MV.fps`（實測 4/30：3 格在動、第 4 格落定）
- 程式動畫：`transition: 'whip', overlap: 4 / MV.fps`；自己做：A 最後 4 格 `ctx.translate(-f.W * MV.prog(f.t, tEnd - 4 / MV.fps, tEnd, MV.ease.inQuad), 0)` 並回傳衰減的震動 `{shake: [6 * MV.pulse(f.t, tEnd - 4 / MV.fps, 0.05) * Math.sin((f.t - tEnd + 4 / MV.fps) * 80), 0]}`（craft.md：震動一定衰減；實測逐格 → 0、1.7、−1.9、1.5、−0.9 px，到剪點時剩不到 1 px）
- 實拍：配方 7（crop 位移＋tmix 動態模糊）

### 閃白 flash
- 何時用：副歌第一個 downbeat、衝擊、回憶切入；規格引用 craft.md：全白最多 1 格、之後 2 格內衰減完（〈震動、閃爍、縮放、鏡頭〉）；次數上限一小節最多一次、一段落最多四次（〈標點符號原則〉）
- 程式動畫：`transition: 'flash'`；拍點白閃回傳 `{flash: MV.pulse(f.t, t0, 0.08)}`，跟 kick 走回傳 `{flash: 0.8 * MV.hit('kick', f.t, 0.06)}`
- 實拍：配方 8b（1 格全白後 0.1 秒衰減，首選）、8a（只有 1 格全白、不衰減）、8c（剪點處白閃接下一鏡）、13（依 audio.json 的 downbeat 自動產 1 格全白）

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
- 實拍：配方 2（xfade 內建：wipeleft、slideleft、circleopen、radial、smoothleft、pixelize、hblur、zoomin）、16（custom expr 斜向擦）

### 縮放衝擊 zoom punch
- 何時用：kick 上的 punch-in（放大 4–8% 指數回彈，上限見 craft.md）；副歌進入要「跳一級」用 reframing（硬切到 1.3 倍的構圖，配方 10e），那是剪點不是 punch-in
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
    const size = 160;   // 字型用 fontconfig 全名；tracking 是每字 px，8% 字距寫 size * 0.08 或 trackingEm: 0.08；顏色鍵是 fill
    const lay = MV.layout(ctx, '第二章', { font: MV.font('Noto Serif CJK TC', size, 900), size, tracking: size * 0.08 });
    MV.drawGlyphs(ctx, lay, (f.W - lay.width) / 2, f.H / 2 + 60, { fill: '#fff' });
} }
```
- 實拍：配方 14（drawtext 黑卡 concat）、14b（fontfile 版）、17（剪點前 3 格黑場）

## 三、實拍 ffmpeg 配方

約定：素材 `a.mp4`、`b.mp4`、`c.mp4` 為 1280×720、30fps、6 秒（合成法在文末）；輸出一律 `-c:v libx264 -crf 18`；表示式裡 `t` 是秒、`n` 是格序；`between(t,a,b)` 含兩端，要剛好 N 格寫 `between(t,b,b+(N-0.5)/fps)`。逐格變化的縮放一律用 `zoompan`：它的變數是 `time`（輸出秒）、`on`（輸出格序）、`zoom`（本格倍率），沒有 `t`；置中寫 `x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'`、裁右上角寫 `x='iw-iw/zoom':y=0`。不要用 `scale=…:eval=frame` 接 `crop`：crop 的 `iw` 與邊界夾限用的是濾鏡鏈建立時的尺寸，scale 之後變大的格 x／y 全被夾成 0，永遠裁左上角，置中與「裁右上角」都做不到（實測 1.3 倍那格對左上參考 48 dB、對右上 7 dB；1.03 倍對左上 46 dB、對置中 18 dB）。

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

# 7 whip：總長 4 格（craft.md：時長 ≤ 4 格、中點接剪點）。先放大 1.4 倍（scale 是常數，crop 的 x 表示式才正確），A 最後 2 格 crop 視窗加速甩到右邊、B 前 2 格從左邊減速甩回中央，硬切；
#   concat 後 split，tmix 整流做動態模糊，只在剪點前後這 4 格用 overlay 疊回（tmix 直接加 enable 會少掉最後一格，所以用 split＋overlay）
#   甩的距離各 256 px（1.4 倍的餘裕）；要 craft.md 的「≥ 半個畫面」把 1.4 改 2（各 640 px），代價是整段放大 2 倍
ffmpeg -i a.mp4 -i b.mp4 -filter_complex "[0:v]trim=0:3,setpts=PTS-STARTPTS,scale=iw*1.4:-2,crop=1280:720:x='(iw-1280)/2+(iw-1280)/2*if(gt(t,2.92),pow((t-2.9)/0.1,2),0)':y='(ih-720)/2'[va];[1:v]trim=0:3,setpts=PTS-STARTPTS,scale=iw*1.4:-2,crop=1280:720:x='(iw-1280)/2*if(lt(t,0.05),1-pow(1-(t+0.033)/0.1,2),1)':y='(ih-720)/2'[vb];[va][vb]concat=n=2:v=1:a=0,split[o][m];[m]tmix=frames=4[blur];[o][blur]overlay=enable='between(t,2.92,3.05)'[v]" -map "[v]" -an -c:v libx264 -crf 18 out/whip.mp4

# 8a 閃白：2.0 秒起剛好 1 格全白（craft.md 規格：全白最多 1 格；要 N 格寫 between(t,2,2+(N-0.5)/30)）
ffmpeg -i a.mp4 -vf "drawbox=color=white@1:t=fill:enable='between(t,2,2.016)'" -c:v libx264 -crf 18 -c:a copy out/flash.mp4
# 8b 瞬白後衰減（首選）：fade d=0.1 = 3 格，含 2.0 秒那格全白；全白後 2 格內退回畫面（實測 60 全白、61–62 衰減、63 回到畫面），符合 craft.md「全白最多 1 格、之後 2 格內衰減完」；指數衰減版用 craft.md 的 eq eval=frame 配方
#   fade=t=in 在 st 之前的每一格都會是純色（實測 0–2 秒全白），所以一定要加 enable='gte(t,st)' 只在閃白起點之後套
ffmpeg -i a.mp4 -vf "fade=t=in:st=2:d=0.1:c=white:enable='gte(t,2)'" -c:v libx264 -crf 18 -c:a copy out/flash_decay.mp4
# 8c 剪點處白閃接下一鏡：B 的第一格全白，0.1 秒內衰減進來
ffmpeg -i a.mp4 -i b.mp4 -filter_complex "[0:v]trim=0:3,setpts=PTS-STARTPTS[v0];[1:v]trim=0:3,setpts=PTS-STARTPTS,fade=t=in:st=0:d=0.1:c=white[v1];[v0][v1]concat=n=2:v=1:a=0[v]" -map "[v]" -an -c:v libx264 -crf 18 out/flash_cut.mp4

# 9 反轉：2.0 秒起 3 格負片
ffmpeg -i a.mp4 -vf "negate=enable='between(t,2,2.083)'" -c:v libx264 -crf 18 -c:a copy out/invert.mp4

# 10a 緩推 ease 進 downbeat：0→2 秒 outCubic 放大到 1.2 置中，2 秒正好停（zoompan 的 time 是輸出秒；d=1 每個輸入格只產生一個輸出格、fps 要等於素材格率）
ffmpeg -i a.mp4 -vf "zoompan=z='1+0.2*(1-pow(1-min(time/2,1),3))':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s=1280x720:fps=30" -c:v libx264 -crf 18 -c:a copy out/easein.mp4
# 10b punch-in：2.0 秒瞬間 1.08 倍置中，指數回彈到 1.03 停住（craft.md 上限 1.08；表示式 2.0／2.1／2.3 秒 = 1.080／1.048／1.033）
ffmpeg -i a.mp4 -vf "zoompan=z='if(lt(time,2),1,1.03+0.05*exp(-(time-2)*10))':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s=1280x720:fps=30" -c:v libx264 -crf 18 -c:a copy out/punch.mp4
# 10c zoompan 版緩推：每格推一點，60 格內到 1.3 倍，中心不動
ffmpeg -i a.mp4 -vf "zoompan=z='min(1+0.3*on/60,1.3)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s=1280x720:fps=30" -c:v libx264 -crf 18 -c:a copy out/zoompan.mp4
# 10d roll：−3° 轉回 0°，2 秒正好停；先放大 1.1 遮掉旋轉露出的邊
ffmpeg -i a.mp4 -vf "scale=iw*1.1:-2,rotate=a='-3*PI/180*pow(1-min(t/2,1),3)':c=black,crop=1280:720" -c:v libx264 -crf 18 -c:a copy out/roll.mp4
# 10e 段內 reframing：2 秒硬切到 1.3 倍、裁右上角（整支 montage 上只做某一列用第四節步驟 4 的限時版）
ffmpeg -i a.mp4 -vf "zoompan=z='if(lt(time,2),1,1.3)':x='iw-iw/zoom':y=0:d=1:s=1280x720:fps=30" -c:v libx264 -crf 18 -c:a copy out/reframe.mp4

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

# 13 依 audio.json 的拍點產 enable 表示式（Python 一行）：每個 downbeat 白閃 1 格（N 可改，但 craft.md 規定全白最多 1 格）
#    時間是歌曲秒：套在 cutlist.py 的 montage 上要先減 offset（第四節步驟 4）；真片只挑幾個 downbeat（標點符號原則），這裡 3 個全閃是為了測試
EXPR=$(/root/video-lab/.venv/bin/python -c "import json;d=json.load(open('data/audio.json'));N=1;fps=30;print('+'.join(f'between(t,{b:.3f},{b+(N-0.5)/fps:.3f})' for b in d['downbeats']))")
ffmpeg -i a.mp4 -vf "drawbox=color=white@1:t=fill:enable='$EXPR'" -c:v libx264 -crf 18 -c:a copy out/flash_downbeats.mp4
# 13b 同一招：每個 snare 負片 1 格
EXPR=$(/root/video-lab/.venv/bin/python -c "import json;d=json.load(open('data/audio.json'));N=1;fps=30;print('+'.join(f'between(t,{b:.3f},{b+(N-0.5)/fps:.3f})' for b in d['onsets']['snare']))")
ffmpeg -i a.mp4 -vf "negate=enable='$EXPR'" -c:v libx264 -crf 18 -c:a copy out/invert_snare.mp4
# 13c 每個 kick 瞬間放大 1.08 置中、指數回彈（表示式相加，用在 zoompan 的 z；變數是 time 不是 t）
EXPR=$(/root/video-lab/.venv/bin/python -c "import json;d=json.load(open('data/audio.json'));print('+'.join(f'gte(time,{b:.3f})*exp(-(time-{b:.3f})*12)' for b in d['onsets']['kick']))")
ffmpeg -i a.mp4 -vf "zoompan=z='1+0.08*($EXPR)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s=1280x720:fps=30" -c:v libx264 -crf 18 -c:a copy out/kick_punch.mp4

# 14 文字作為轉場：A → 黑底字卡 0.4 秒 → B（字型用 fontconfig 全名，見 craft.md〈可用字型〉）
ffmpeg -i a.mp4 -i b.mp4 -f lavfi -i "color=black:s=1280x720:r=30:d=0.4" -filter_complex "[0:v]trim=0:3,setpts=PTS-STARTPTS[v0];[2:v]drawtext=font='Noto Serif CJK TC':fontsize=120:fontcolor=white:text='第二章':x=(w-tw)/2:y=(h-th)/2[card];[1:v]trim=0:3,setpts=PTS-STARTPTS[v1];[v0][card][v1]concat=n=3:v=1:a=0[v]" -map "[v]" -an -c:v libx264 -crf 18 out/textcard.mp4
# 14b 字卡本身、指定字型檔（不經 fontconfig）：fontfile 用絕對路徑；粗體在 NotoSerifCJK-Bold.ttc／NotoSansCJK-Bold.ttc
ffmpeg -f lavfi -i "color=black:s=1280x720:r=30:d=0.4" -vf "drawtext=fontfile=/usr/share/fonts/opentype/noto/NotoSerifCJK-Bold.ttc:fontsize=120:fontcolor=white:text='第二章':x=(w-tw)/2:y=(h-th)/2" -c:v libx264 -crf 18 out/textcard_file.mp4

# 15 跳接：同一鏡 0–1.5 秒與 3–4.5 秒直接相接
ffmpeg -i a.mp4 -filter_complex "[0:v]trim=0:1.5,setpts=PTS-STARTPTS[v0];[0:v]trim=3:4.5,setpts=PTS-STARTPTS[v1];[v0][v1]concat=n=2:v=1:a=0[v];[0:a]atrim=0:1.5,asetpts=PTS-STARTPTS[a0];[0:a]atrim=3:4.5,asetpts=PTS-STARTPTS[a1];[a0][a1]concat=n=2:v=0:a=1[a]" -map "[v]" -map "[a]" -c:v libx264 -crf 18 -c:a aac out/jumpcut.mp4

# 16 自訂遮罩擦：xfade custom expr，P 是進度 0→1，A／B 是兩邊畫素；這條是斜向擦
ffmpeg -i a.mp4 -i b.mp4 -filter_complex "[0:v][1:v]xfade=transition=custom:duration=0.3:offset=5.7:expr='if(lt((X+Y)/(W+H),P),B,A)'[v]" -map "[v]" -an -c:v libx264 -crf 18 out/diagwipe.mp4

# 17 剪點前「吸氣」：A → 3 格黑 → B
ffmpeg -i a.mp4 -i b.mp4 -f lavfi -i "color=black:s=1280x720:r=30:d=0.1" -filter_complex "[0:v]trim=0:3,setpts=PTS-STARTPTS[v0];[1:v]trim=0:3,setpts=PTS-STARTPTS[v1];[v0][2:v][v1]concat=n=3:v=1:a=0[v]" -map "[v]" -an -c:v libx264 -crf 18 out/blackgap.mp4

# 18 match cut 對位檢查：A 最後一格與 B 第一格並排；再用 signalstats 看兩格平均亮度（YAVG）是否刻意對比或連續
ffmpeg -sseof -0.034 -i a.mp4 -frames:v 1 out/a_last.png
ffmpeg -i b.mp4 -frames:v 1 out/b_first.png
ffmpeg -i out/a_last.png -i out/b_first.png -filter_complex "[0][1]hstack" out/matchcheck.png
ffmpeg -i out/a_last.png -vf "signalstats,metadata=print:key=lavfi.signalstats.YAVG" -f null - 2>&1 | grep YAVG
```

## 四、剪點表工作流程

1. `python scripts/analyze.py song.mp3 -o data/audio.json --bpm 120 --first-beat 0.5 --sections "intro:0,verse1:4,chorus1:12"`（數字換成自己這首歌的）：拿到 tempo、beats、downbeats、段落表；對照段落摘要表確認小節序沒偏（第一個 downbeat 抓錯整張表就錯）。tempo 已知時給 `--bpm` 與 `--first-beat` 最穩；印出的 tempo 與感知拍差一倍（170 BPM 被估成 85）就用 `--bpm` 改回來（一.3）。截至本版（2026-10-02）某些歌不給 `--bpm` 會崩潰，見實測紀錄；scripts 任務修好後刪這句
2. 複製 `templates/cuts.csv`，依密度表填剪點。欄位：
   - `bar`：小節序，從 0 起（bar 0 = audio.json 的第一個 downbeat）
   - `beat`：該小節第幾拍，1–4（`meter` 為 4 時），可填 2.5 這種半拍（八分音符子剪、拍間反拍切）；段落邊界一律 1，子剪可以落在 2、3、4 或半拍
   - `src`：素材路徑，建議相對路徑（`media/a.mp4`），在 repo 根目錄執行 cutlist.py
   - `in`：從 src 的第幾秒開始播（秒，小數）；這列會從該拍的時間播到下一列為止，最後一列播到下一個 downbeat
   - `in` 超過素材最後一格（in > 長度 − 1/fps）時 cutlist.py 會在轉檔前報錯並指出第幾行、不出檔（實測「剪點表有錯，未轉檔：第 3 行（列 2）：in 7.000 超過 b.mp4 的最後一格 5.967 秒」）；`in` 在範圍內但 `in + 該列長度 × speed` 超過素材長度時，用最後一格停格（tpad）補足並印警告（實測「不足的 30 格用最後一格停格補足」，總格數仍正確）。停格看得出來，只是保底：每支素材仍要比剪點表需要的長；範本的 `in` 值已配合第三節的 6 秒測試素材（120 BPM）
   - 對嘴鏡頭的 `in` 用一.10 的交叉相關算出來，不手填
   - 同一來源、`in` 接續上一列的子剪（範本 bar 5:3、9、11）畫面不會換，只是把剪點登記進 cuts.json；reframing／punch-in 本身在步驟 4 用「限定在該列時間區間」的版本後製。不要把第三節的 10e／10b 直接套在 montage 上：那兩條沒有結束時間（10e 的 `if(lt(time,2),1,1.3)` 從 2 秒起永遠 1.3、10b 停在 1.03），之後所有鏡頭都跟著放大
   - `speed`：播放速度，預設 1；只為設計用（刻意慢動作 0.5、快轉 2），不是對拍工具
   - `label`：備註，自由文字，不要含逗號；寫段落名與鏡頭意圖，cutlist.py 的剪點表與 `OUT.cuts.png` 會帶出來；qa.py 不讀 label
   - 第一列上方不要加註解，cutlist.py 直接讀表頭
3. **先把剪點表給我確認**，再 `python scripts/cutlist.py cuts.csv --audio-json data/audio.json -o out/montage.mp4 --music song.mp3 --sheet`：它會先印出絕對秒數、長度、來源的剪點表，再精準到格重編碼；同時寫出 `out/montage.cuts.json`（影片 0 秒對歌曲的 offset、各列絕對秒）
4. 拍點效果後製（白閃、負片、kick punch 套到 montage 上）：`out/montage.mp4` 的 0 秒 = 第一列的歌曲秒，就是 `out/montage.cuts.json` 的 `offset`；audio.json 裡全是歌曲秒，所以配方 13 系列的時間一律先減 offset、丟掉負的（範本第一列在 bar 0，offset = 第一個 downbeat，測試歌是 0.5 秒 = 一拍；不減就整支片閃在第 2 拍）。cuts.csv 沒有效果欄、cutlist.py 不做效果，label 的「配方 13 後製」只是提醒。只閃挑出來的小節（標點符號原則），不要每個 downbeat：
```bash
OFF=$(/root/video-lab/.venv/bin/python -c "import json;print(json.load(open('out/montage.cuts.json'))['offset'])")
EXPR=$(/root/video-lab/.venv/bin/python -c "import json;d=json.load(open('data/audio.json'));off=$OFF;bars=[12];N=1;fps=30;print('+'.join(f'between(t,{b-off:.3f},{b-off+(N-0.5)/fps:.3f})' for i,b in enumerate(d['downbeats']) if i in bars and b>=off))")
ffmpeg -i out/montage.mp4 -vf "drawbox=color=white@1:t=fill:enable='$EXPR'" -c:v libx264 -crf 18 -c:a copy out/montage_fx.mp4
```
   負片（配方 13b）與 kick punch（13c）同樣把 `b` 換成 `b-off`、加 `if b>=off`；實測見文末表
   子剪（reframing、punch-in）只限該列：T0 = 該列的 `t` − offset、T1 = 下一列的 `t` − offset（最後一列用 `end`），都從 `out/montage.cuts.json` 的 `rows` 查，T1 再減半格讓下一列的第一格回到 1 倍；這裡以範本 bar 9:1 的 reframing、bar 5:3 的 punch-in 為例（實測 T0／T1 = 18.000／19.983 與 11.000／11.983，區間外的格與原 montage 相同）：
```bash
row() { /root/video-lab/.venv/bin/python -c "import json,sys;d=json.load(open('out/montage.cuts.json'));r=d['rows'];i=[j for j,x in enumerate(r) if (x['bar'],x['beat'])==(float(sys.argv[1]),float(sys.argv[2]))][0];t0=r[i]['t']-d['offset'];t1=(r[i+1]['t'] if i+1<len(r) else d['end'])-d['offset'];print(f'{t0:.3f} {t1-0.5/d[\"fps\"]:.3f}')" "$@"; }
read T0 T1 <<< $(row 9 1)    # reframing：bar 9 beat 1 那列 1.3 倍裁右上角，T1 起回到 1（配方 10e 的 montage 版）
ffmpeg -i out/montage.mp4 -vf "zoompan=z='if(between(time,$T0,$T1),1.3,1)':x='iw-iw/zoom':y=0:d=1:s=1280x720:fps=30" -c:v libx264 -crf 18 -c:a copy out/montage_reframe.mp4
read T0 T1 <<< $(row 5 3)    # punch-in：T0 瞬間 1.08 置中、回彈到 1.03 停住，T1 起回到 1（配方 10b 的 montage 版）
ffmpeg -i out/montage.mp4 -vf "zoompan=z='if(between(time,$T0,$T1),1.03+0.05*exp(-(time-$T0)*10),1)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s=1280x720:fps=30" -c:v libx264 -crf 18 -c:a copy out/montage_punch.mp4
```
   白閃、負片、子剪要疊在同一支上就串著做（上一條的輸出當下一條的輸入），時間都已經是影片秒，不必再減 offset
5. `python scripts/qa.py out/montage_fx.mp4 --audio-json data/audio.json -o out/qa --cuts out/montage.cuts.json`：一定帶 `--cuts`，不帶時 qa.py 只靠 `scene` 偵測，同一來源的子剪（reframing、punch-in）幾乎抓不到，±1 格比例就只對抓到的剪點算。看 `report.md` 的預期剪點命中數、剪點誤差（±1 格內比例）、黑場與閃白次數，和每段落在 downbeat 抽格的 `sheet_<section>.png`；拼圖逐張看，找最弱的三處改 in-point 再跑一次
6. 選 in-point 的原則（每列的 `in` 怎麼挑；對嘴鏡頭的 `in` 由一.10 算出，不在此列）：
   - 動作接動作：in-point 落在動作中途（抬手到一半、轉身到一半），不要在靜止點
   - 視線方向：上一鏡人物看右，下一鏡的主體在右；相反就是刻意的衝突，要有理由
   - 明暗交替：亮鏡接暗鏡、暗接亮，拍點會更明顯；連續三個同明度的鏡頭會糊成一片（配方 18 的 YAVG 可以量）
   - 主體位置連續：主體在前一鏡結束的位置附近出現（或正好對角，做對比）；眼睛不用重新搜尋
   - 剪點前後各留 2 格以上的穩定畫面，不要剪在模糊格、閉眼格、過曝格上

## 五、剪輯自檢清單（交付前逐題回答）

1. 每個剪點都在 downbeat 或字前最後一拍？qa.py（帶 `--cuts`）報告預期剪點全部命中、±1 格內比例 ≥ 90%（門檻見〈1. 剪在哪裡〉）？
2. 密度曲線跟能量曲線一致？最後一次副歌比第一次密？橋段真的放慢了？
3. 標點符號（白閃、停格、反轉、衝擊格）一小節 ≤ 1 次、一段落 ≤ 4 次（craft.md〈標點符號原則〉），而且都在最重的拍？
4. 有沒有為了湊拍改原片速度？有就換素材或換 in-point
5. 每個 in-point 檢查過動作、視線、明暗、主體位置四項？
6. 鏡頭運動結束在拍上（不是開始在拍上）？
7. 轉場語言一支片一套？硬切為主、溶接 ≤ 3 處？
8. 關掉聲音看一次還看得出拍嗎？只聽聲音想像畫面，剪點落在你預期的地方嗎？
9. 不在拍上的剪點 ≤ 3 處？每處 label 寫了理由，前後兩刀都在拍上？（一.9）
10. 對嘴鏡頭的 `in` 全部用交叉相關算出來（一.10），不是手填？抽 3 個對嘴剪點用一.10 的拼圖＋每格 RMS 看過口型與人聲同一格？

## 出處

- Walter Murch, *In the Blink of an Eye*（Silman-James Press）：Rule of Six，剪點優先序為情緒 51%、故事 23%、節奏 10%、視線 7%、畫面二維 5%、三維空間 4%；一.9 的例外名額就是前三條的順序；「視線方向」「主體位置連續」是第四到第六條的實作，「動作接動作」是連戲剪接（continuity cutting）的基本法，不在六條之內
- Tony Zhou, Every Frame a Painting《Edgar Wright – How to Do Visual Comedy》（2014）：whip pan、聲畫同步的喜劇剪法、用剪點取代鏡頭內的動作
- Karen Pearlman, *Cutting Rhythms*（Focal Press）：剪輯節奏的脈動、緩急與速度
- pdoom-video `app/src/timeline.ts`（剪點 = 字前最後一拍、段尾最近 downbeat）、`docs/TREATMENT.md` Tone 段（大變化落在拍上、運動 ease 進 downbeat、強緩動＋停＋snap）；anime-op `STORYBOARD.md`（密度曲線跟能量曲線）
- `references/anime.md` 已列的出崎統演出、撮影處理、MAD 十條
- ffmpeg 濾鏡手冊 https://ffmpeg.org/ffmpeg-filters.html（xfade、tmix、tpad、loop、zoompan、xstack、setpts、drawbox、drawtext、minterpolate、amix）

## 實測紀錄

- 環境：ffmpeg 6.1.1-3ubuntu5（Ubuntu，libx264、libfreetype、libfontconfig）；字型 Noto Sans CJK TC／Noto Serif CJK TC
- 素材：`ffmpeg -f lavfi -i testsrc2=size=1280x720:rate=30 -f lavfi -i "sine=frequency=440:sample_rate=48000" -t 6 -pix_fmt yuv420p a.mp4`；b.mp4 用 `smptebars=size=1280x720:rate=30` 與 660 Hz；c.mp4 用 testsrc2 加 `-vf hue=h=120` 與 880 Hz。三支都是 h264 1280×720 30fps 180 格、aac 48 kHz 單聲道
- 驗證方法：`ffprobe -show_entries stream=nb_frames,duration`；指定格的亮度用 `select='between(n,a,b)',scale=1:1` 加 `-fps_mode passthrough` 輸出 gray rawvideo（不加 passthrough 會補格，看不出真相）；音訊切換用 `astats` 的零交越率（440 Hz ≈ 0.018、660 Hz ≈ 0.028）
- 測試用 audio.json：tempo 120、beats 每 0.5 秒、downbeats 0.5／2.5／4.5、kick 0.5／1.5／2.5、snare 整數秒；lyrics.json 兩行，字起 2.56 與 4.48
- 16 小節測試歌（第四節、一.10 用）：`testsong.py -o song.wav --bpm 120 --bars 16`，`analyze.py song.wav -o data/audio.json --bpm 120 --first-beat 0.5 --sections "intro:0,verse1:4,chorus1:12"` → downbeats 0.5、2.5、…（2026-10-02 用修好的 analyze.py 重測：這首不給 `--bpm` 也過，印 tempo 119.988（初估 120.2）、拍數 66、downbeats 0.5、2.5、4.5；同法合成的 70 與 170 BPM 測試歌不給 `--bpm` 估成 70.000 與 169.998，沒有半頻）；對嘴 take 合成法：1.5 秒前導雜訊 + 回放檔從起播小節（bar 8）起的一段 ×0.6 加雜訊，與 testsrc2 合成 mp4

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
| 7 | 180 格；84–95 格縮成 64×36 灰階看相鄰格平均差，只有剪點前後 4 格在動 | 180 格；相鄰格差 2 2 2 5 10 16 17 35 0 0 0（88、89 格 A 甩出 11%／44%，90、91 格 B 甩入 55%／89%，92 格落定）；tmix 直接加 enable 得 179 格（掉最後一格），改 split＋overlay 後 180 |
| 8a | 第 60 格白，59、61 不白 | 131 255 131 131；`between(t,2,2.033)` 會多一格（含兩端），改 2.016 |
| 8b | 第 0–3 格不變、第 60 格白、之後 3 格內退回 | 130 130 130 130；58–64 格 130 130 255 229 179 130 130（60 全白、61–62 衰減、63 回到畫面）；沒加 enable 時 0–59 格全是 255 |
| 8c | 第 90 格（B 第一格）白後衰減、180 格 | 180；90 格起 255 → 衰減 |
| 9 | 第 60–62 格負片 | 131 135 135 135 131（三格變了） |
| 10a–10e | 輸出仍是 1280×720、180 格；zoompan 版的錨點用 PSNR 對靜態參考（同一條 zoompan 常數 z） | 五條都是 1280×720、180 格；10a 第 150 格對 z=1.2 置中 41.9 dB；10b 第 150 格對 z=1.03 置中 42.5 dB；10e 第 150 格對右上 1.3 參考 43.8 dB、對左上 7.4 dB；z=1 的格對原片 51 dB。棄用的 `scale=eval=frame`＋`crop` 寫法：10e 對左上 48.2 dB、對右上 7.4 dB，10b 對左上 45.7 dB、對置中 18.2 dB（crop 夾在左上角） |
| 11a、11b、11c | 1280×720、180 格；抽格看四宮格 | 三條都是；11b 四格正確 |
| 12a | 1.9 秒 440 Hz、2.1 秒 660 Hz | 零交越率 0.0183 → 0.0275，聲音比畫面早 1 秒進 |
| 12b | 2.5 秒 440、3.2 秒混合、4.5 秒 660 | 0.0183 → 0.0271 → 0.0275 |
| 13 | 第 15、75、135 格各 1 格白，前後不白 | 131 255 131 … 全對；原本 `b+N/fps` 多一格，改 `(N-0.5)/fps` |
| 13b | 第 30、60 格各一格負片 | 131 134 131 131 131 135 131 131 |
| 13c | 1280×720、180 格；第 75 格（第三個 kick 2.5 秒）對 z=1.08 置中參考 | 是；41.8 dB（對原片 18.8 dB） |
| 14、14b | 90+12+90 格；fontfile 版 12 格；抽格看到「第二章」明朝體白字 | 192；12；字正確 |
| 15 | 45+45 格 | 90 格、3.000 秒 |
| 16 | 12−0.3 秒；抽格看到斜向分界 | 351 格、11.700 秒；分界正確 |
| 17 | 90+3+90 格 | 183 格、6.100 秒 |
| 18 | 並排圖、YAVG | 產出 matchcheck.png；YAVG 125.5 與 95.8 |
| 一.1 Python | cut 夜色 = 2.5、cut 我們 = 4.5（4.48+0.02 在容許內）、after 夜色 = 4.5 | 全對 |
| 一.10 對嘴 | k = 1 真值 L 15.000（bar 8 → in 1.500、bar 12:3 → 10.500）；k = 2（`atempo=2.0` 的回放檔）真值 6.750（bar 10 → 3.500、bar 12:3 → 6.000）；同三列用 mv-direction 的 `p + (T − S)/k` 再算一次 | 兩種都 0 ms 誤差，每列 in 與真值一致；兩式六列全部相同 |
| 一.10 抽格檢查 | 合成 2.0 秒（第 60 格）才有聲的 4 秒檔：11 格拼圖燒格序、每格 RMS；同兩條指令套在 montage.mp4（44.1 kHz）上 | 拼圖上的格序 55–65；RMS 第 58 格 −inf、59 格 −78.0、60 格 −21.1 dB，之後 −21；montage 跑通 |
| 二 緩動引數 | playwright 載 mv-kit.js；render.py `--sheet` 跑含 `'nope'` 與 `MV.ease.outCubik` 的頁面；載入自檢版 | `'outCubic'` 與函式版都 0.875，`'nope'` 0.5 加一次 console.error；render.py exit 0、stderr 一行 `[console.error] MV：沒有這個緩動「nope」，可用：…`，`outCubik` 那條沒有任何輸出；自檢版 exit 1、`[pageerror] 沒有緩動 outCubik` |
| 二 tracking | layout「第二章」160 px：tracking 12.8／trackingEm 0.08／不傳；fitSize maxW 500：不傳／傳 `px => px * 0.08`／傳 12.8 | 505.6／505.6／480 px；166.67 px（加字距後整行 526.6，超出）／158.23 px（整行 500.0）／158.13 px（整行 500.0） |
| 二 乒乓、whip | d = 1 兩種寫法 lt 0.5／1.5／2.5；mv-kit `whip` overlap 4/30 用紅／藍兩場量每格 R／B 平均；shake 表示式剪點前 4 格逐格取 | 0.5／0.5／0.5 與 0.5／0.5／−0.5；預設 overlap 0.25，明寫後 0.133：剪點前 4 格 R 255（純 A）、前 3 格 251、前 2 格 127、前 1 格 4、剪點 0（純 B），3 格在動；shake 0、1.73、−1.94、1.48、−0.89 |
| 四.2 in 檢查 | in 7.0（素材 6 秒）要報錯不出檔；in 5.0 需要播到 7 秒要停格補足 | 「剪點表有錯，未轉檔：第 3 行（列 2）：in 7.000 超過 b.mp4 的最後一格 5.967 秒」exit 1、無輸出；「不足的 30 格用最後一格停格補足」、180 格 |
| 四.4 offset | 範本 cuts.csv（12 列）+ 16 小節測試歌：offset 0.5、bars=[12] → 歌曲 24.5 秒 = 影片 24.0 秒 = 第 720 格 | 840 格；第 718–722 格灰階 131 131 255 93 93（只有 720 白）、第 0–2 格 131（bar 0 不在 bars 內）；不減 offset 的對照組白在第 735 格 = 晚一拍；qa.py 報「閃白 1 次：24.00s（1 格）」、report.md 不含 label |
| 四.4 子剪限時版 | 同一支 montage：reframing bar 9:1（T0 18.000、T1 19.983）、punch-in bar 5:3（T0 11.000、T1 11.983）；PSNR 對原 montage 與對靜態參考 | 都 840 格 1280×720；reframing 第 570 格對右上 1.3 參考 61.7 dB、對原 montage 12.2 dB，第 525／600／750 格對原 montage 76／55／56 dB（區間外回到原片）；punch-in 第 330 格對置中 1.08 參考 41.7 dB、對原 montage 19.0 dB，第 329／360 格對原 montage 49 dB |
