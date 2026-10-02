# 工藝規格：色彩、字型排印、動態、後製、聲畫對位、輸出（craft）

把 SKILL.md「品質標準」的每一條拆成可量測、可執行的規則。做 MV、藝術影片、片頭、字卡時逐條對照。
- 思考與分鏡：`references/mv-direction.md`；剪輯技巧：`references/editing.md`；動漫風效果：`references/anime.md`（這裡不重複）
- 程式渲染工具庫：`assets/mv-kit.js`（全域 `MV`），輸出：`scripts/render.py`
- 文中每條 ffmpeg 指令、每個 Canvas 行為都在本機跑過（環境與指令見文末「實測紀錄」）；標「未測」者例外
- 以下 ffmpeg 範例以 1280×720 為例，實際尺寸請改成素材尺寸；`-vf` 的部分可直接放進自己的指令

## 一、色彩與調色

### 色票紀律
- 一支片只有一套色票，寫進 treatment 的〈5. 色票〉段（`templates/treatment.md`），之後任何畫面都從這裡取色，不臨時配色
- 四類顏色與比例（面積佔比，全片平均）：
  - 主色（dominant）：背景與大面積，60–70%。通常是極暗（`#0A0A0B` 這類接近黑）或極亮（紙色 `#EEE9DF` 這類接近白），不是中間灰
  - 輔色（secondary）：面板、第二層幾何，15–25%。主色的鄰近明度，不是另一個色相
  - 中性色（neutral）：文字與線條，2–3 階（例如 `#EEE9DF`／`#9C978F`／`#807C76`；第三階要能當標註，對比比門檻見〈不用描邊與光暈充數〉），10–15%
  - 強調色（accent）：一個色相，5% 以內。只給「這支片最重要的東西」（貫穿物、正在唱的字、數字）
  - 稀有強調色（rare accent）：可有可無的第二個色相，整支片只在一個段落出現（總長 ≤ 3 秒），之後不再用。它的作用是讓觀眾記得那一刻
- 色相（hue）總數 ≤ 4（含稀有強調色）。暗部可以往強調色偏（橘的暗部是深紅）、亮部往白偏，這不算新色相
- 檢查法（實測）：等距抽 20 格，每格縮到 8×8 畫素，橫排成一張色票再放大 8 倍看；若肉眼數得出超過 4 個色相，就有一個要砍
```bash
# DUR 換成片長秒數（fps=20/DUR 就是等距抽 20 格，小數也可）；輸出 1280×64（實測 6 秒片）
ffmpeg -i in.mp4 -vf "fps=20/DUR,scale=8:8:flags=area,tile=20x1,scale=iw*8:ih*8:flags=neighbor" -frames:v 1 -update 1 palette.png
```
- 不要：紫＋青霓虹、彩虹漸層、每段換一套配色、用飽和色當背景

### Canvas 2D 的色彩事實（實測，Chromium 141）
- Canvas 2D 預設是 sRGB、8 位元，所有運算都在 gamma 編碼的數值上做，不是線性光。`getContext('2d', {colorSpace:'display-p3'})` 可以開，但 `render.py` 截圖後進 ffmpeg 轉 yuv420p／bt709，整條管線以 sRGB 為準，不要開 P3
- `globalCompositeOperation = 'lighter'`：sRGB 值直接相加後截斷。實測兩個 `rgb(128,128,128)` 疊成 `rgb(255,255,255)`；強調色 `#FF4D12` 疊 50% 自己得 `rgb(255,116,27)`，色相往黃偏。結論：
  - `lighter` 只用在「本來就要燒到白」的東西（火花核心、閃光），並預期它會變白變黃
  - 要「加亮但保色相」用 `'screen'`（實測 64 疊 64 得 112，不會爆）
  - 疊加層的顏色用低 alpha（0.1–0.3）多畫幾層，比一層高 alpha 可控
- 顏色一律寫成 token（`PAL.ink`、`PAL.accent`），不在場景裡寫死十六進位；暗部與亮部變體用 `MV.lerp` 在 token 之間插值
- 畫面若要「反轉」（紙底墨線），不要用 `filter: invert()`，而是從色票的反轉版取色（墨→紙、紙→墨、強調色不變），這樣強調色在兩種版面都是同一個橘

### 發光規則
- 只有強調色會發光（bloom／halation）；中性色文字永遠銳利，不加 `shadowBlur`、不疊模糊副本。pdoom 的做法：只有亮度超過 0.85（線性）的畫素進 bloom，而紙色文字壓在 0.85 以下
- Canvas 2D 做「發光」的方式：同一形狀畫兩層，底層 `'screen'` 加 `ctx.filter = 'blur(Npx)'` 或預先模糊的貼圖，上層銳利。模糊半徑 = 形狀寬度的 0.5–1 倍，alpha 0.3–0.5。不要用 `shadowBlur` 當光暈（它每次繪製都重算，慢且不穩）
- 發光面積 ≤ 畫面 5%。整個畫面都在發光等於沒有東西在發光

### 膚色
- 實拍人臉：調色後用 ffmpeg `signalstats` 的 `HUEAVG` 看膚色。它不是一般 HSV 色相，是 `signalstats` 自己的色度座標（實測純色：綠 38、黃 99、紅 161、洋紅 218、藍 279、青 341）；膚色落在約 120–135（實測 `0xE0AC69` 127、`0xC68642` 130、`0x8D5524` 133、`0xFFDBAC` 126）。低於 115 往黃綠偏，高於 145 往紅與洋紅偏。只量臉的區域（先 crop 到臉），不要量全畫面
```bash
# 臉的區域 HUEAVG（crop 的位置與大小換成臉所在處）；目標 120–135
ffmpeg -i in.mp4 -vf "crop=200:200:540:260,signalstats,metadata=print:key=lavfi.signalstats.HUEAVG" -an -f null -
# 目視法：向量示波器抽一格，膚色應集中在圖上固定的一條斜線（skin tone line）附近
ffmpeg -ss 3 -i in.mp4 -vf "vectorscope=mode=color3:graticule=green:flags=name" -frames:v 1 vscope.png
```
- 全片風格化（單色、偏青橘）時，膚色允許跟著走，但臉的明度要比背景高 2 階以上，人要先於風格被看到
- 不要對人臉套 `unsharp` 正值銳化，也不要讓顆粒最大值落在臉上（顆粒在中間調最明顯，而臉常是中間調：用 `noise=alls=` 6–8 而不是 12）

### 反轉版面做明暗節奏
- 準備兩套版面：暗底亮線（ink）、紙底墨線（paper）。段落之間切換，讓剪輯有明暗節奏（例如 verse 暗、pre-chorus 轉紙、chorus 回暗）
- 一支 3 分鐘的片切換 3–6 次就夠；每次切換落在 downbeat，與剪點同步
- 紙底時：文字用墨色（`#0A0A0B` 這類），強調色不變，顆粒改成 `noise` 較弱（紙本來就有紋理，再加顆粒會髒），暈影改成四角微暗 0.15–0.2

### ffmpeg 調色配方（實測，1280×720、6 秒 testsrc2）
```bash
# 基本：對比 1.08、亮度 −0.02、飽和 0.9（先做這個，再做別的）
ffmpeg -i in.mp4 -vf "eq=contrast=1.08:brightness=-0.02:saturation=0.9:gamma=1.0" out.mp4

# curves 預設（vintage／cross_process／darker／lighter／increase_contrast／linear_contrast／medium_contrast／strong_contrast／negative）
ffmpeg -i in.mp4 -vf "curves=preset=vintage" out.mp4

# curves 自訂：主曲線輕 S（壓暗部、提亮部）、紅通道抬黑、藍通道壓白 = 陰影偏青、亮部偏暖的分離色調
ffmpeg -i in.mp4 -vf "curves=m='0/0 0.25/0.22 0.75/0.80 1/1':r='0/0.02 1/0.98':b='0/0.06 1/0.94'" out.mp4

# colorbalance：s=陰影、m=中間調、h=亮部；陰影加紅減藍（暖）、亮部減紅加藍（冷）。量級 ±0.03–0.08，超過 0.1 會像壞掉
ffmpeg -i in.mp4 -vf "colorbalance=rs=0.05:bs=-0.05:rh=-0.03:bh=0.03" out.mp4

# colortemperature：Kelvin 1000–40000，預設 6500；4500 偏暖、8000 偏冷；pl=1 保亮度
ffmpeg -i in.mp4 -vf "colortemperature=temperature=4500:mix=1" out.mp4

# colorchannelmixer 單色：三個輸出通道都用同一組 Rec.601 亮度權重
ffmpeg -i in.mp4 -vf "colorchannelmixer=.299:.587:.114:0:.299:.587:.114:0:.299:.587:.114" out.mp4
# 偏色單色（褐色調）：輸出 r/g/b 各用不同權重；要別的色調就把三列各乘上目標色的 r/g/b
ffmpeg -i in.mp4 -vf "colorchannelmixer=.393:.769:.189:0:.349:.686:.168:0:.272:.534:.131" out.mp4

# lut3d：用 .cube。先用 python 產生（下面的 make_cube.py，17³ 格）再套用。.cube 裡 r 跑最快、b 最慢
python make_cube.py teal_orange.cube
ffmpeg -i in.mp4 -vf "lut3d=file=teal_orange.cube" out.mp4
```
`make_cube.py`（實測可用）：
```python
import sys
size, out = 17, sys.argv[1]
def s_curve(x, k=0.15): return x + k * (x - 0.5) * (1 - abs(2 * x - 1)) * 2   # k=0 為直線
def grade(r, g, b):
    lum = 0.299 * r + 0.587 * g + 0.114 * b
    sh, hi = (1 - lum) ** 2, lum ** 2                      # 陰影權重、亮部權重
    r = r - 0.06 * sh + 0.06 * hi                          # 陰影減紅、亮部加紅
    g = g + 0.01 * sh
    b = b + 0.08 * sh - 0.06 * hi                          # 陰影加藍、亮部減藍
    return tuple(min(max(s_curve(v), 0.0), 1.0) for v in (r, g, b))
lines = ['TITLE "teal_orange"', f"LUT_3D_SIZE {size}", "DOMAIN_MIN 0 0 0", "DOMAIN_MAX 1 1 1"]
for bi in range(size):
    for gi in range(size):
        for ri in range(size):
            lines.append("%.6f %.6f %.6f" % grade(ri / (size - 1), gi / (size - 1), bi / (size - 1)))
open(out, "w").write("\n".join(lines) + "\n")
```
- 調色順序：曝光與對比（eq）→ 曲線（curves 或 lut3d）→ 色彩平衡（colorbalance）→ 風格層（單色、分離色調）。先把素材調到「正確」再調「風格」，否則每個鏡頭的風格層起點不同
- 多鏡頭一致：先各鏡頭用 eq 把亮度對齊（`signalstats` 的 YAVG 差 ≤ 10），再對全片套同一個 .cube

### 電影感後製堆疊（實測）
量級參考 pdoom `post.ts` 預設：bloom 0.55（門檻 0.85 線性）、halation 0.25、色差 1.2 px（畫面邊緣）、顆粒 0.055（sRGB 單位，中間調最強）、暈影 0.35。ffmpeg 近似如下，單獨與整串都跑過：
```bash
# 顆粒：alls 0–100，8–12 看得見但不髒；t+u = 每格不同的均勻雜訊（沒有 t 會變成固定花紋）
ffmpeg -i in.mp4 -vf "noise=alls=10:allf=t+u" out.mp4
# 暈影：angle 越大越暗。PI/6 輕微、PI/5 預設、PI/4 明顯（角落亮度約剩 30%）、PI/3 角落近黑；畫面中央不受影響
# 實測左上角 64×64 的 YAVG：無暈影 62.4 → PI/6 37.6（60%）、PI/5 29.7（48%）、PI/4 18.7（30%）、PI/3 5.9（9%）；中央 125.5 → 125.3
ffmpeg -i in.mp4 -vf "vignette=angle=PI/5" out.mp4
# 量角落：接在 vignette 後面 crop 左上角再 signalstats（調自己的 angle 時用）
ffmpeg -i in.mp4 -t 0.1 -vf "vignette=angle=PI/4,crop=64:64:0:0,signalstats,metadata=print:key=lavfi.signalstats.YAVG" -an -f null -
# halation 近似：分流 → colorlevels 只留亮部（黑點 0.72）→ 高斯模糊 → 偏暖（加紅減藍）→ screen 疊回。opacity 0.3–0.5；0.55 在色條素材上已偏重
ffmpeg -i in.mp4 -filter_complex "[0:v]split[a][b];[b]colorlevels=rimin=0.72:gimin=0.72:bimin=0.72,gblur=sigma=18,colorbalance=rs=0.25:gs=-0.05:bs=-0.3[h];[a][h]blend=all_mode=screen:all_opacity=0.45" out.mp4
# 柔光版 bloom（沒有顏色偏移）：模糊副本 screen 疊回，opacity 0.15–0.25
ffmpeg -i in.mp4 -filter_complex "[0:v]split[a][b];[b]gblur=sigma=12[g];[a][g]blend=all_mode=screen:all_opacity=0.18" out.mp4
# 色差：rgbashift 整格位移（1–2 px 是「鏡頭感」，10 px 是故障效果，見 anime.md 實拍 7）；chromashift 只移色度、亮度不動，較不傷文字
ffmpeg -i in.mp4 -vf "rgbashift=rh=2:bh=-2" out.mp4
ffmpeg -i in.mp4 -vf "chromashift=cbh=3:crh=-3" out.mp4
# letterbox 2.39:1（裁上下再補黑；只裁不補就是改比例）。字幕與安全區要以有效畫面算、燒字幕放在這一步之後（見二、〈安全區與平臺遮擋區〉）
ffmpeg -i in.mp4 -vf "crop=iw:iw/2.39,pad=1280:720:0:(oh-ih)/2:black" out.mp4
# 輕微柔化：unsharp 給負值 = 柔焦；la −0.2～−0.4
ffmpeg -i in.mp4 -vf "unsharp=lx=7:ly=7:la=-0.35" out.mp4
# 全堆疊（順序：調色 → halation → 色差 → 暈影 → 柔化 → 顆粒 → letterbox）。顆粒一定在最後、letterbox 的黑邊上不能有顆粒與暈影；燒字幕接在 letterbox 之後
ffmpeg -i in.mp4 -filter_complex "[0:v]curves=m='0/0 0.25/0.22 0.75/0.80 1/1',colorbalance=rs=0.04:bs=-0.04:rh=-0.02:bh=0.02,split[a][b];[b]colorlevels=rimin=0.72:gimin=0.72:bimin=0.72,gblur=sigma=18,colorbalance=rs=0.25:gs=-0.05:bs=-0.3[h];[a][h]blend=all_mode=screen:all_opacity=0.5,rgbashift=rh=1:bh=-1,vignette=angle=PI/5,unsharp=lx=5:ly=5:la=-0.2,noise=alls=8:allf=t+u,crop=iw:iw/2.39,pad=1280:720:0:(oh-ih)/2:black" out.mp4
```
- 程式渲染（Canvas）走 `MV.post(ctx,{grain,vignette,flash,invert,fade,letterbox,tint,halation},t)`，同樣順序；顆粒貼圖預先產生、用 `MV.frameIdx(t)` 選種子（原因見三、動態模糊）
- 堆疊是全片常數，不隨段落變。段落變化用 flash／shake／invert／zoom 這些「事件」欄位，不是調顆粒量
- 每加一層就抽格對照「有／沒有」：看不出差別就拿掉

## 二、字型排印（中文為主）

### 可用字型（實測）
- 已裝：Noto Sans CJK TC（Regular、Bold）、Noto Serif CJK TC（Regular、Bold）、Noto Sans Mono CJK TC（Regular、Bold）。沒有 Light／Medium／Black
  - Canvas 要 `300` 得到 Regular、要 `900` 得到 Bold（實測寬度與外觀都相同），所以字重層級只有兩階；第三階用字級與顏色做，不要指望字重
- 別名：`Noto Sans TC` 在 fontconfig（ffmpeg drawtext／subtitles）與 Chromium 都解析到 Noto Sans CJK TC。`Noto Serif TC` **兩邊都沒有**：fc-match 落到 DejaVu Sans，Chromium 落到後備字型。明朝體一律寫全名 `Noto Serif CJK TC`
- 英數與等寬：Noto Sans CJK TC 自帶的 Latin 可用；要機器感用 `Noto Sans Mono CJK TC`（Latin 0.5 em 等寬、中文 1 em，中英對齊）或 `DejaVu Sans Mono`／`Liberation Mono`。只用 OFL 字型；要更多字重或 Latin 展示字型時下載 OFL 字型放 `assets/fonts/`，用 `@font-face` 載入並等 `document.fonts.ready`

### 字級層級（以 1080p 高度為基準，9:16 用寬度 1080 換算）
| 層 | 用途 | 字級 | 字重 | 顏色 |
|---|---|---|---|---|
| 主標 | 歌名、章節、歌詞全幅 | 96–220 px（8.9–20% 高） | Bold | 中性色最亮階或強調色 |
| 副標 | 歌詞側邊、說明句 | 40–60 px（3.7–5.6%） | Regular／Bold | 中性色第二階 |
| 標註 | 數值、座標、註腳、HUD | 18–24 px（1.7–2.2%） | Regular，等寬 | 中性色第三階 |
- 相鄰兩層字級比至少 1.6 倍，否則看不出層級（上表任一組合都滿足：96/60 = 1.6、40/24 = 1.67）；同一畫面最多三層，通常兩層
- 字級不要落在 25–39 px 與 61–95 px 這兩個「既不像上一層也不像下一層」的區間
- 字幕另算（見下）

### 字距與行距（實測）
- `ctx.letterSpacing` 在這個 Chromium 可用，接受 `'6px'`、`'0.1em'`、負值；`measureText().width` 會算進字距（實測 6 字加 6 px 得 +36 px）。字距改完記得歸零 `'0px'`，它是 context 狀態
- 中文字距：標題 −0.03～0 em（大字要收緊，Noto 的字面偏大）、內文 0～0.05 em、標註與直書 0.05–0.15 em、刻意拉開的「氣氛字」0.3–0.5 em（不超過一行 8 字）
- 行距（baseline 到 baseline）：中文標題 1.15–1.3 em、內文 1.5–1.8 em、歌詞兩行 1.4 em。Noto Sans CJK 的字框高 1.458 em（實測 ascent 1.167 + descent 0.292），實際墨跡高約 0.96 em，行距低於 1.1 em 會碰到
- 中文配對沒有 kerning（實測「測／試」「「／測」「字／，」都是 0），英文有（`To` −0.074 em、襯線 `AV` −0.13 em），所以中英混排時 Latin 段要走 `MV.layout`（見「kerning」）

### 中英數混排
- 中英之間留 0.25 em；半形空格實測 Noto Sans CJK TC 0.224 em、Serif 0.256 em（直接打空格略小於 0.25 em，可接受），等寬字型 0.5 em（太寬，不用空格隔中英）；要精準用 `letterSpacing` 或 `MV.layout` 的 `tracking` 補。數字與單位之間不留
- 數字用 tabular（等寬數字）才不會在滾動時跳動：Noto Sans CJK TC 的數字實測已是等寬（0、1、8 都 0.555 em），Serif 0.55 em；等寬字型 0.5 em。不要用 `canvas.style.fontFeatureSettings` 控制（實測對 ctx 文字無效）
- 大數字（計數器、年份、百分比）用等寬或 Serif 數字，不用中文字型的數字當主角；小數點後位數固定
- 英文大寫標題字距 +0.05–0.1 em，小寫不要加

### 標點
- 中文用全形標點（，。、：；「」『』）；全形標點實測佔 1 em，句尾標點在視覺上會留一個空字，標題可以把句尾標點拿掉或用 `letterSpacing` 負值收回（標點擠壓）
- 避頭尾：行首不能是 ，。、；：」』）；行尾不能是 「『（。自己斷行時先切字、再把違規標點推到上一行末或下一行首
- 引號用「」，不用 “”；省略號用「……」（兩個全形）；破折號用「——」；英文裡用 ’ “ ” … – —，不用打字機引號 ' "
- 歌詞不加句尾標點（除了問號與驚嘆號有語氣作用時）

### 直書（縦書き）
- Canvas 沒有直排模式；逐字 `fillText`，y 每字加 1.0–1.1 em，`textAlign='center'`（實測可用）。標點用直排形：︐（U+FE10 逗號）︑（U+FE11 頓號）︒（U+FE12 句號）︓（U+FE13 冒號）︕（U+FE15 驚嘆號）︖（U+FE16 問號）；Noto Sans／Serif CJK TC 都有這些字形（`fc-list ':charset=fe10 fe11 fe12'`）。不要旋轉橫排標點
- Latin 與數字在直書裡：兩位數橫放（縱中橫），單字母旋轉 90°（`ctx.rotate(Math.PI/2)`）
- 直書一行 ≤ 12 字，行與行間距 1.5–2 em，從右往左排

### 安全區與平臺遮擋區
- 通用：標題安全區 90%（`MV.safeArea(W,H,0.9)`），動作安全區 93%（`MV.safeArea(W,H,0.93)`）；字幕距邊 ≥ 5%。`mv-kit.js` 的 `safeArea` 註解寫「0.9 動作、0.8 字幕」，與本文不一致，以本文（廣播慣例：動作 93、標題 90）為準
- 有 letterbox 時以有效畫面計算（實測）：`bar = (H − W / ratio) / 2`（1080p、2.39 → 138 px；720p → 92 px），安全區與字幕位置都以 `[0, bar, W, H − 2·bar]` 為外框，不是整張畫布。`MV.post` 的 `letterbox` 只畫黑邊、不改安全區，要自己算：
```js
const RATIO = 2.39;                                                 // 與 MV.post 的 letterbox 同值；沒有 letterbox 時 bar = 0
const bar = Math.max(0, (H - W / RATIO) / 2), Ha = H - 2 * bar;     // 1080p：bar 138、Ha 803
const safe = MV.safeArea(W, Ha, 0.9); safe[1] += bar;               // 標題安全區 = 有效畫面的 90%，整個往下移 bar
const subBaseline = H - bar - 0.08 * Ha;                            // 字幕基線 = 有效畫面底邊上方 8%
```
  實測（1080p、2.39）：照整張畫布算的頁面，安全區左上的標註（y 54）與距底 8% 的字幕（y 994）渲染後都被黑邊蓋住、看不到；改以有效畫面算之後標註在 182–197 列、字幕 832–881 列，都在有效畫面 138–941 列內
  - ffmpeg：字幕放在 crop/pad **之後**，`y` 減掉 bar；`subtitles` 的 `MarginV` 加 `bar / (h/288)`（libass 的 MarginV 單位是 PlayResY=288 的刻度：720p 每單位 2.5 px、1080p 3.75 px；實測 MarginV 40 → 80 字底上移 100 px）
```bash
# drawtext：先 letterbox 再畫字；底邊 = 有效畫面底邊 − 8% × 有效高（w/2.39 就是有效高）。實測字在 546–583 列，有效畫面 92–627 列
ffmpeg -i in.mp4 -vf "crop=iw:iw/2.39,pad=1280:720:0:(oh-ih)/2:black,drawtext=font='Noto Sans TC':fontsize=h*0.055:fontcolor=white:text='夜行列車駛過山谷':x=(w-text_w)/2:y=h-(h-w/2.39)/2-w/2.39*0.08-text_h" out.mp4
# subtitles：720p 黑邊 92 px → MarginV 40 + 92/2.5 ≈ 77（實測字底從 611 列上移到 519 列；黑邊從 628 列起）
ffmpeg -i in.mp4 -vf "crop=iw:iw/2.39,pad=1280:720:0:(oh-ih)/2:black,subtitles=sub.srt:force_style='FontName=Noto Sans TC,FontSize=22,Bold=1,PrimaryColour=&H00FFFFFF,OutlineColour=&HD9000000,BorderStyle=1,Outline=2,Shadow=1,MarginV=77,Alignment=2'" out.mp4
# 反例（實測）：drawtext 放在 crop/pad 之前且 y=h-h*0.08-text_h → 字幕上半被 crop 掉，只剩 4 列壓在黑邊上緣
```
- 9:16 短影音（1080×1920）的介面遮擋，保守值（平臺會改版，交付前用該平臺當時的官方範本套一次）：
  - 上方 14%（約 270 px）：狀態列與標題
  - 下方 25%（約 480 px）：說明文、音樂、互動列
  - 右側 12%（約 130 px）：按鈕列（讚、留言、分享）
  - 動態牆預覽會裁成 4:5（1080×1350，上下各去 285 px）：主體與主標放在中央 4:5 內
  - 所以文字區實際是 x 5–85%、y 15–72%
- 16:9 YouTube：右下角 12%×10% 有資訊卡與片尾建議；進度列佔下方 3%，字幕距底 ≥ 8%
- 1:1 與 4:5：沒有固定遮擋，守 90% 安全區即可

### 版面網格與構圖
對應 SKILL.md 品質標準的「排版：網格與對齊一致」與「留白：每個畫面只有一個重點」。網格看不見，但每個 x、y 都從它來，不用眼睛猜。
- 欄格（column grid）：以標題安全區（有 letterbox 時是有效畫面的安全區，見上節）為外框分 12 欄；欄距（gutter）= 副標字級的 1 em（1080p 副標 40–60 px → 欄距 40–60 px），整支片一個值；欄寬 = (安全區寬 − 11 × 欄距) / 12
- 文字塊的左緣一律落在欄線上，右對齊的貼第 12 欄右緣，置中的以安全區中線為軸；側邊歌詞佔 4–5 欄、主標跨 8–12 欄、標註佔 2–3 欄。數值、座標這類成組的標註共用同一條欄線，上下對齊
- 基線網格（baseline grid）：垂直方向以副標行距為一格（1080p 副標 48 px × 1.5 = 72 px），同一畫面所有文字的基線（baseline）都落在格線上，基線差是 72 的整數倍；主標行距照〈字距與行距〉，但第一行基線仍落在格上
- 主體落點只選一種、全片一致：中心（對稱、正面、儀式感；主標與貫穿物置中）或三分交點（有方向、有留白；主體在交點、文字在對側的欄位）。一個段落只用一種，換段落才能換
- 一個畫面一個重心：遮住強調色與主標後，畫面剩下的東西不能有第二個同等吸引視線的物件；兩個東西要並列時用對稱構圖，否則把次要的縮到主要的 1/1.6 以下或降到中性色第三階
- 負空間（negative space）≥ 40%：單格裡主色（背景）面積至少四成（〈色票紀律〉的 60–70% 是全片平均，單格下限 40%）；字幕模式與全幅歌詞也不例外。量法（實測）：`neg_space.py` 把一格縮成 192×108、找出現最多的顏色、算與它相近的畫素佔比；影片路徑時只量第一格，要量某一秒先 `ffmpeg -ss 秒 -i in.mp4 -frames:v 1 f.png`
```python
# neg_space.py 檔案（PNG 或影片）：印負空間比例（與主色歐氏距離 ≤ 24 的畫素佔比）
import numpy as np, subprocess, sys
p = sys.argv[1]
r = subprocess.run(["ffmpeg", "-v", "error", "-i", p, "-vf", "scale=192:108:flags=area", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True).stdout
a = np.frombuffer(r, np.uint8).reshape(-1, 3).astype(int)
q = (a // 16) * 16 + 8                                        # 量化到 16 階再找眾數
keys, counts = np.unique(q, axis=0, return_counts=True)
mode = keys[counts.argmax()]
d = np.sqrt(((a - mode) ** 2).sum(axis=1))
print(f"{p}: 主色 ≈ rgb{tuple(int(v) for v in mode)}，負空間 {(d <= 24).mean() * 100:.0f}%")
```
  實測：本節示範頁（主標＋標註＋字幕）96%；testsrc2 色條 16%（沒有主色，不及格）
- 輔助線（除錯用，交付時關）：
  - Canvas：下面的 `drawGrid` 畫 12 欄（半透明強調色）、安全區外框、有效畫面三分線、中心十字。在 `render(t)` 最後、`MV.post` 之後呼叫；用 `render.py --data cfg=grid.json`（內容 `{"grid":1}`）開關，頁面以 `window.DATA.cfg` 讀，不改程式碼（實測；同一機制可切 halation，見三、〈動態模糊與取樣〉）
```js
const CFG = Object.assign({ grid: 0, halation: 0 }, (window.DATA && window.DATA.cfg) || {});   // render.py --data cfg=xxx.json 覆寫
// 版面網格輔助線：安全區 12 欄（gutter 以 px 給，= 副標 1 em）、有效畫面三分線、中心十字；safe 與 bar 見上節
function drawGrid(ctx, [sx, sy, sw, sh], bar = 0, cols = 12, gutter = 48) {
  ctx.save();
  const cw = (sw - gutter * (cols - 1)) / cols, Ha = H - 2 * bar;
  ctx.fillStyle = 'rgba(255,77,18,0.12)';
  for (let i = 0; i < cols; i++) ctx.fillRect(sx + i * (cw + gutter), sy, cw, sh);
  ctx.strokeStyle = 'rgba(255,255,255,0.6)'; ctx.lineWidth = 2; ctx.strokeRect(sx, sy, sw, sh);
  ctx.strokeStyle = 'rgba(255,255,255,0.35)'; ctx.lineWidth = 1; ctx.beginPath();
  for (let i = 1; i < 3; i++) { ctx.moveTo(W * i / 3, bar); ctx.lineTo(W * i / 3, H - bar); ctx.moveTo(0, bar + Ha * i / 3); ctx.lineTo(W, bar + Ha * i / 3); }
  ctx.moveTo(W / 2 - 20, H / 2); ctx.lineTo(W / 2 + 20, H / 2); ctx.moveTo(W / 2, H / 2 - 20); ctx.lineTo(W / 2, H / 2 + 20);
  ctx.stroke(); ctx.restore();
}
// render(t) 的最後：MV.post(ctx, {...}, t); if (CFG.grid) drawGrid(ctx, safe, bar);
```
  - ffmpeg（實測）：`drawgrid` 會鋪滿整格，安全區外框用 `drawbox` 另畫；欄線是 12 等分（沒有欄距），文字左緣對到線即可
```bash
# 三分線
ffmpeg -i in.mp4 -vf "drawgrid=w=iw/3:h=ih/3:t=2:c=white@0.5" -frames:v 1 -update 1 grid_thirds.png
# 90% 安全區外框 ＋ 從安全區左緣起算的 12 欄線 ＋ 三分線
ffmpeg -i in.mp4 -vf "drawbox=x=iw*0.05:y=ih*0.05:w=iw*0.9:h=ih*0.9:c=white@0.7:t=2,drawgrid=x=iw*0.05:y=ih*0.05:w=iw*0.9/12:h=ih*0.9:t=1:c=0xFF4D12@0.7,drawgrid=w=iw/3:h=ih/3:t=2:c=white@0.4" -frames:v 1 -update 1 grid_12col.png
```

### 字幕規格
本節是「壓在實拍或靜圖上的可讀性字幕」（紀錄片式、日常剪片的燒字幕）的規格。程式渲染的歌詞字幕模式只取這裡的字級、位置與行數，不取描邊／陰影／底板（見〈歌詞作為畫面的三種模式〉）。
- 每行 ≤ 14 字（短影音）、≤ 18 字（橫式），最多兩行，不跨句斷行；一句顯示 ≥ 1 秒、≤ 7 秒；兩句之間至少 2 格空檔
- 字級：9:16 用畫面寬度的 4.5–5.5%（1080 寬 → 48–60 px）；16:9 用高度的 4.5–5.5%（1080 高 → 48–60 px）；1080p 下 Noto Sans TC Bold
- 位置：底部，距底 8–12%（9:16 要避開 25% 遮擋區 → 放在 y 65–72%）；有 letterbox 時距底以有效畫面高度計、從黑邊上緣算起（〈安全區與平臺遮擋區〉）；不壓人臉與主體，鏡頭構圖低時字幕往上移
- 描邊：寬 = 字級 × 0.06–0.08（48 px → 3–4 px），黑 85% 透明度；陰影 y +2、模糊 0–4、黑 50%；底板（box）只在背景雜亂時用，黑 40–50%、內距 0.25 em。三者選一到兩個，不全開
- Canvas 做法（實測）：先 `lineJoin='round'`、`lineWidth = 字級×0.12`（stroke 有一半在字內，所以是描邊寬的兩倍）`strokeText`，再 `fillText`；陰影用 `shadowBlur`，不與描邊同時用
- ffmpeg 做法（實測）：
```bash
# drawtext：fontsize 可用運算式，borderw 是整數畫素（不能寫運算式）
ffmpeg -i in.mp4 -vf "drawtext=font='Noto Sans TC':fontsize=h*0.055:fontcolor=white:borderw=3:bordercolor=black@0.85:shadowx=0:shadowy=2:shadowcolor=black@0.5:text='夜行列車駛過山谷，窗外只剩燈火':x=(w-text_w)/2:y=h-h*0.08-text_h" out.mp4
# 半透明底板
ffmpeg -i in.mp4 -vf "drawtext=font='Noto Sans TC':fontsize=h*0.05:fontcolor=white:box=1:boxcolor=black@0.5:boxborderw=12:text='我們在黎明前抵達':x=(w-text_w)/2:y=h-h*0.08-text_h" out.mp4
# 章節字卡用明朝體：全名
ffmpeg -i in.mp4 -vf "drawtext=font='Noto Serif CJK TC':fontsize=h*0.09:fontcolor=0xEEE9DF:text='第一章　夜行':x=w*0.08:y=h*0.12" out.mp4
# SRT 燒錄＋樣式（ASS 顏色是 &HAABBGGRR；FontSize 不是畫素，以實測墨跡高換算：720p 下 FontSize 22 的中文墨跡高 35 px ≈ drawtext fontsize 37；要 48 px 字幕（墨跡約 46 px）用 FontSize 28–29，實測 28 → 45 px、29 → 47 px）
ffmpeg -i in.mp4 -vf "subtitles=sub.srt:force_style='FontName=Noto Sans TC,FontSize=22,Bold=1,PrimaryColour=&H00FFFFFF,OutlineColour=&HD9000000,BackColour=&H80000000,BorderStyle=1,Outline=2,Shadow=1,MarginV=40,Alignment=2'" out.mp4
```

### 歌詞作為畫面的三種模式
| 模式 | 用途 | 規格 |
|---|---|---|
| 全幅 | 副歌、hook、一句一畫面 | 主標層級；一行 ≤ 8 字，可逐字或逐行；`MV.fitSize` 算字級填滿安全區的 70–90% 寬；每字進場對齊該字的 `start` |
| 側邊 | 主歌、畫面另有主體 | 副標層級；靠左或靠右 1/3，與主體不重疊；兩行以內；`MV.karaoke` 逐字亮字 |
| 字幕 | 需要可讀性優先、紀錄片式；一支片只在一個段落用（mv-direction 的 SUBTITLE 模式） | 字級、位置、行數照〈字幕規格〉。程式渲染、背景可控（純色或色票裡的實色帶）時不描邊、不加陰影、不加底板，可讀性走〈不用描邊與光暈充數〉；壓在實拍或靜圖上時才依〈字幕規格〉選描邊／陰影／底板一到兩個。不做逐字動畫，只做整句淡入 2–4 格 |
- 一支片以一種模式為主、第二種為輔，第三種只在一個段落用；每段切換模式要有理由（段落變化）
- 逐字亮字（`MV.karaoke`）：亮字永不超前人聲；可以提前 ≤ 0.4 秒把整行以未唱色顯示。未唱色 = 中性色 30–40% 不透明度（不是描邊），已唱色 = 強調色或最亮中性色

### kerning 與逐字排版
- 整串 `fillText` 自動套 kerning；逐字繪製（逐字亮字、逐字進場）會失去 kerning，必須用 `MV.layout(ctx,text,{font,size,tracking})` 取得每字 x 再 `MV.drawGlyphs`。`font` 給 `MV.font(family,px,weight)` 的字串，或 `px => MV.font(family,px,weight)` 的函式（`MV.fitSize`／`MV.karaoke` 的 `fontFn`／`font` 同此）；只給家族名 `'Noto Sans CJK TC'` 不是合法的 CSS 字型字串，`ctx.font` 會維持原值（新 context 是 10 px sans-serif），實測 200 px 主標只畫出 192 px 寬的小字。原理：`kern = measureText(a+b).width − measureText(a).width − measureText(b).width`，每字前進量 = 自身寬 + kern + tracking
- 實測：逐字＋kern 的 `TAVERN To Yo` 與整串 `fillText` 完全對齊；不用 kern 時 `To` 會多 3.5 px（48 px 字級）
- 一個字拆成兩段（已唱／未唱各半）時，第二段的 x 要用 layout 的字位置，不要用 `measureText(text.slice(0,i))`，那會掉前後的 kern
- 不同字型或字級相鄰（中文主標接英文副標）之間沒有 kerning，用眼睛調間距（通常 0.15–0.25 em）

### 不用描邊與光暈充數
- 標題與歌詞不描邊、不加光暈、不加投影。可讀性靠：對比（文字色與它壓著的底色的 WCAG 相對亮度對比比 contrast ratio：主標 ≥ 3:1，副標、標註、字幕 ≥ 4.5:1；實測本文色票對 `#0A0A0B`：`#EEE9DF` 16.4、`#9C978F` 6.8、`#807C76` 4.8、`#FF4D12` 6.0；紙底 `#EEE9DF` 上 `#FF4D12` 只有 2.8，強調色在紙底只當線條，要當主標得改深到 `#C23A0B` 4.4）、留白（文字四周 ≥ 0.5 em 淨空）、放在畫面較平的區域、必要時在文字下方壓一塊色票裡的實色帶（對比以色帶的顏色算）
```bash
# 對比比：兩個十六進位色（不含 #），印一個數字；每對「文字色／底色」各算一次（實測 EEE9DF 0A0A0B → 16.36）
python -c "import sys;f=lambda c:[(v/255/12.92 if v/255<=0.04045 else ((v/255+0.055)/1.055)**2.4) for v in bytes.fromhex(c)];L=lambda c:sum(a*b for a,b in zip((0.2126,0.7152,0.0722),f(c)));a,b=sorted(map(L,sys.argv[1:3]),reverse=True);print(round((a+0.05)/(b+0.05),2))" EEE9DF 0A0A0B
```
- 唯一例外：壓在實拍或靜圖上的字幕（〈字幕規格〉）與實拍上的小標註；程式渲染、背景可控的歌詞字幕模式不在例外內。SKILL.md B 段的「白字黑描邊」就是這個例外（燒進實拍的字幕）
- 不混用超過兩個字型家族；中文一個（Sans 或 Serif）＋ 等寬一個就夠

## 三、動態與緩動

### 緩動語彙（`MV.ease.*`）
| 緩動 | 用在 | 不用在 |
|---|---|---|
| `outExpo`、`outQuint` | snap：字砸進來、數字跳到位、剪接後的位置修正（0.25–0.5 秒） | 鏡頭推拉（會像被拉住） |
| `inOutCubic` | 鏡頭運動、橫移、焦段變化（0.5–2 秒）；`MV.keys` 的預設 | 快速事件 |
| `MV.spring(t,t0,{freq,damp})` | 物件落地後安定：freq 3–5、damp 0.7–0.8（第一峰過衝 +5%／+2%、可見過衝 1 次，對應〈動作結構〉的過頭 2–5%）；面板彈出 damp 0.5–0.6（+16%／+9%、1 次）；damp < 0.5 只給刻意的物理彈跳（0.4 → +25%、0.3 → +37%，各 2 次過衝）。2% 內安定時間：freq 3 約 0.2–0.45 秒、freq 5 約 0.12–0.3 秒 | 文字（過衝會讓字抖）；大面積物件用 damp < 0.7（過衝像錯誤） |
| `outBack` | 小物件彈出（圖示、標註、按鈕），過衝 ≤ 10% | 大面積（過衝看起來像錯誤） |
| `inExpo`、`inCubic` | 離場（加速離開）、倒數到爆點 | 進場 |
| `outElastic`、`outBounce` | 幾乎不用；只給刻意搞笑或一次性的物理 | 任何重複出現的動作 |
| `linear` | 等速物理：滾動的字幕帶、轉動的唱片、時間軸遊標 | 任何「有意圖」的動作 |
- 一支片只用 3–4 種緩動，每種對應固定的動作種類；觀眾不會說出來，但會感覺「這支片的動作有個性」

### 動作結構：預備—動作—安定
- 預備（anticipation）：反方向 3–6% 的小動作，1–3 格；超越（overshoot）：到位後過頭 2–5%，2–4 格；安定（settle）：回到位，用 spring 或 outCubic。大物件三段都要，小物件可省預備
- hold 再 snap：靜止 ≥ 半拍，然後 ≤ 4 格到位。比「從頭到尾慢慢動」有力十倍。ffmpeg 實拍版：
```bash
# 前 1.5 秒停格，再開始動（tpad 複製首格）
ffmpeg -i in.mp4 -vf "trim=0:4.5,setpts=PTS-STARTPTS,tpad=start_mode=clone:start_duration=1.5" out.mp4
```
- 不要飄浮：沒有理由的連續慢速縮放、慢速旋轉、上下漂移就是螢幕保護程式。靜止是合法的，大多數時間畫面可以不動，只在拍點上動
- 每個動作有起點與終點，寫成 `MV.keys(t,[[t0,v0],[t1,v1,ease]])`；不寫 `Math.sin(t)` 這種沒有終點的運動（除了等速物理）

### 對齊拍點
- 動作的「到位時刻」（不是開始時刻）落在拍點：`t1 = MV.timeOfBeat(i)`，`t0 = t1 − 時長`
- 時長用拍的分數：snap 1/4 拍、進場 1/2 拍、鏡頭 1–2 拍、段落轉場 1 拍；不用秒數硬寫
- 預備動作的起點也在拍上（前一個八分音符）
- 剪點（`MV.timeline` 的 `cuts`）全部在 downbeat 或拍上；偏差 ≤ 1 格（30 fps 下 33 ms），用 `qa.py` 核對

### 一拍二（12 fps）何時用
- 手繪感、停格動畫感、刻意的「廉價」質感：整段用 `MV.frameIdx(t,12)` 把 t 量化，所有運動都會變成 12 fps（12 只在 24 fps 輸出時是每 2 格一換；30 fps 輸出改 15 或 10，見五、〈fps 選擇〉）
- 不用在：文字滾動、鏡頭運動、任何與實拍 30 fps 素材同框的東西（會像掉格）
- 混用時以「層」為單位：角色層 12 fps、背景與鏡頭 30 fps（動畫的標準做法，見 anime.md）

### 動態模糊與取樣（`render.py --samples N --shutter S`）
- 原理：每格在 `shutter × 1/fps` 的時間窗內（以該格時間為中心）取 N 個子格，各呼叫 `render(t)` 後平均畫素。shutter 0.5 = 180° 快門（實拍的標準）；0.2 乾淨、1.0 拖影重
- N 的選法：靜態或慢動作 4；一般動作 8–12；whip、slam、快速縮放 24+。先用 4 做預覽，交付時整支用 12，只有快動作段落另外以 24–36 渲染後接回
- 代價：先量自己的場景再估，不要套本文或別人的數字。`render.py PAGE.html -o t.mp4 --dur 0.2 --profile` 跑 6 格，stderr 印每格「render／截圖」毫秒與平均；第一格含暖機（最大值）不算；整支片時間 ≈ 格數 × (render 平均 × N + 截圖平均)（截圖與編碼不隨 N 變）。`--profile` 的 render 欄是 `render(t)` 的 JS 時間，光柵化可能延到截圖欄才做，所以估時兩欄相加、不單看 render 欄；自己在頁面裡量 `render(t)` 要在每次呼叫後 `ctx.getImageData(0,0,1,1)` 強制光柵化，否則量到的數字偏小
  - 實測（4 核心 swiftshader、1080p、機器同時有其他工作，數字浮動 ±50%）：本文示範頁（160 px 主標＋blur 發光線＋標註＋字幕＋grain＋vignette＋letterbox）halation 0 時 render 平均 202 ms、截圖 189 ms；halation 0.25 時 render 365 ms（halation 一層約 160 ms）。另一個場景 N=1 0.92 秒/格（30 格 27.7 秒）、N=12 4.5 秒/格（15 格 66.9 秒）：N=12 的總時間約是 N=1 的 5 倍，不是 12 倍，因為截圖與編碼的固定開銷不隨 N 變
- 預覽（`--sheet`、N=1 試跑）時把 `MV.post` 的 `halation` 設 0，交付時再開：頁面用 `const CFG = Object.assign({halation: 0}, (window.DATA && window.DATA.cfg) || {})` 讀設定、`MV.post(ctx, {halation: CFG.halation, ...}, t)`，交付時 `render.py ... --data cfg=deliver.json`（內容 `{"halation": 0.25}`）注入，不改程式碼（實測，頁面讀到 `window.DATA.cfg`）
- 閃爍、抖動、顆粒種子一律用 `MV.frameIdx(t)`：它在整個快門窗內是常數，一格只有一個狀態。用 `Math.floor(t*fps)` 會在格的中心切換，每格都重曝兩個狀態（pdoom ENGINE.md 的教訓）。用連續 t 當雜訊種子則會被子格平均掉
- 實拍素材的動態模糊近似：`tmix=frames=3`（三格平均，實測可用）；真正的光流模糊 `minterpolate` 很慢，未測

### 震動、閃爍、縮放、鏡頭
- 震動一定衰減：位移 = 振幅 × e^(−k·Δt) × sin(ω·Δt)，k 6–10（0.3 秒內停）、振幅 8–24 px（1080p）、ω 60–90 rad/s；用 `MV.pulse(t,t0,halfLife)` 當振幅包絡。場景回傳 `{shake:[x,y]}` 給 `MV.timeline` 做
- 閃白衰減：`flash = MV.hit('kick',t,0.06)`，峰值 0.4–0.8，半衰期 0.05–0.08 秒（2 格內消失）；全白格最多 1 格
- 縮放推進（punch-in）：1.00 → 1.04～1.08，到位 2–4 格，之後停住或極慢回彈；超過 1.1 像縮放錯誤。段落內的慢推 1.00 → 1.06 可以跨 8 小節
- 鏡頭運動要有目的：推向主體（揭露）、拉開（放進脈絡）、橫移跟隨（連結兩物）、甩鏡（換場）。沒有目的就不動；一個鏡頭一個目的
- 甩鏡（whip）：橫移距離 ≥ 半個畫面、時長 ≤ 4 格、`--samples 24+`，中點可以接剪點
- ffmpeg 實拍版（實測）：
```bash
# 慢推 1.00→1.06：用 editing.md 配方 10c 的 zoompan，z 改成 '1+0.06*on/N'（N = 推進的格數，6 秒 30 fps 是 180；on = 輸出格序）；同一條濾鏡只在 editing.md 維護，這裡不重複
# 衰減震動：t=2 起，振幅 24/16 px、k=6（先放大 6% 避免露邊）
ffmpeg -i in.mp4 -vf "scale=iw*1.06:-2,crop=1280:720:x='(iw-1280)/2+if(gte(t,2),24*exp(-(t-2)*6)*sin((t-2)*90),0)':y='(ih-720)/2+if(gte(t,2),16*exp(-(t-2)*6)*cos((t-2)*70),0)'" out.mp4
# 衰減閃白：t=2 起亮度 +0.6，半衰期 0.08 秒（eq 要 eval=frame 才會逐格算）
ffmpeg -i in.mp4 -vf "eq=brightness='if(gte(t,2),0.6*pow(0.5,(t-2)/0.08),0)':eval=frame" out.mp4
```
實際使用時把 `2` 換成拍點秒數（從 `audio.json` 的 `onsets.kick` 取），多個拍點就把 `if` 疊加或用 `cutlist.py` 分段處理

## 四、聲畫對位

### 包絡驅動什麼（`MV.env(name,t)`，0..1）
| 訊號 | 驅動 | 不驅動 |
|---|---|---|
| `rms` | 整體尺寸、整體亮度、顆粒量的微調（±20%） | 位置（會抖） |
| `low` | 大面積：背景明度、主體尺寸、鏡頭推進量、暈影 | 細節 |
| `mid` | 中景：線條粗細、面板展開程度、人聲相關的字形變化 | 背景 |
| `high` | 細節：小粒子、閃爍密度、HUD 數字跳動、hat 的點 | 大面積（會像閃爍故障） |
- 包絡先做時間平滑再對應：`MV.env` 是線性內插的 100 fps 資料，逐格直接對應會抖（實測合成 rms 的每格平均變化 0.108）。平滑用「往前取窗平均」，仍是 t 的純函式、子格取樣也安全：
```js
// 取 t−win～t 內 n 個點的 MV.env 平均；win 0.05–0.10 秒（實測每格變化降到 0.037／0.028）。往前取不往後取，才不會搶拍
const envSmooth = (name, t, win = 0.08, n = 8) => { let s = 0; for (let k = 0; k < n; k++) s += MV.env(name, t - win * k / (n - 1)); return s / n; };
```
- 門檻另外做：平滑後再 `MV.smoothstep(0.2,0.8,v)`，低於 0.2 不動、0.8 以上飽和。只套 smoothstep 不平滑會把中段的抖動放大（實測 0.154 > 原始 0.108）；要「打擊後衰減」的形狀用 `MV.hit`，不用包絡
- 對應量級：尺寸 ±5–10%、亮度 ±15%、線寬 ±30%。觀眾要「感覺到」而不是「看到」畫面在呼吸

### 打擊事件（`MV.hit(kind,t,halfLife)`，指數衰減脈衝）
| 事件 | 典型反應 | 半衰期 |
|---|---|---|
| kick | flash 0.3–0.6、shake 8–16 px、scale punch 1.03–1.06、主體亮一下 | 0.06–0.12 秒 |
| snare | 剪點、翻面（flip）、反轉（invert）一格、換色、換字 | 事件本身無衰減 |
| hat | 細節閃爍、粒子噴一下、HUD 數字滾動、線條抖 | 0.03–0.05 秒 |
- 低頻與高頻分工：低頻（kick、bass）動「大的東西」，高頻（hat、人聲齒音）動「小的東西」。反過來（kick 動粒子、hat 動鏡頭）會顯得不對勁，觀眾說不出為什麼
- 人聲 onset 驅動歌詞：字的進場綁 `lyrics.json` 的 `words[].start`，不綁 kick；人聲的強弱（`env.mid`）可以驅動字重或字寬的變化，但不驅動位置

### 標點符號原則
- flash、impact frame、全畫面 invert、whip 是標點符號，一小節最多一次，一段落最多四次；每拍都用等於沒有重音
- 強度分級跟段落走：intro 40%、verse 70%、chorus 100%（anime.md 的規則）；bridge 可以降到 30% 製造落差
- 每個段落選一組「主反應」：例如 verse 只有 hat 細節＋歌詞，pre-chorus 加 kick scale，chorus 加 snare 剪點與 flash。段落內不換組
- 靜音與留白也是對位：drop 前的空拍畫面全黑或全停，drop 落下才動

## 五、輸出規格（實測）

### 交付指令
```bash
# 第一段：量響度（印 JSON，抓 input_i / input_tp / input_lra / input_thresh 四個值）
ffmpeg -i in.mp4 -af "loudnorm=I=-14:TP=-1.5:LRA=11:print_format=json" -f null -
# 第二段：1080p 母帶。libx264 crf 18 slow、High 4.1、GOP 60、yuv420p、bt709 三件套＋tv 範圍、loudnorm 帶量測值（linear=true 才是線性增益，不會壓動態）、AAC 192k 48 kHz、faststart
# <input_i> 等四個佔位符換成第一段 JSON 的值，每支片都不同；套錯值輸出就不是 −14 LUFS（testsrc2 測試素材量到 −21.76／−14.46／0.10／−31.76，只是範例）
ffmpeg -i in.mp4 -vf "scale=1920:1080:flags=lanczos" \
  -c:v libx264 -preset slow -crf 18 -pix_fmt yuv420p -profile:v high -level 4.1 -g 60 -bf 2 \
  -color_primaries bt709 -color_trc bt709 -colorspace bt709 -color_range tv \
  -af "loudnorm=I=-14:TP=-1.5:LRA=11:measured_I=<input_i>:measured_TP=<input_tp>:measured_LRA=<input_lra>:measured_thresh=<input_thresh>:linear=true:print_format=summary" \
  -c:a aac -b:a 192k -ar 48000 -movflags +faststart deliver_1080p.mp4
# 自動代入（bash）：第一段的四個值抓進變數再組第二段
read I TP LRA TH <<<$(ffmpeg -i in.mp4 -af "loudnorm=I=-14:TP=-1.5:LRA=11:print_format=json" -f null - 2>&1 | grep -E '"input_(i|tp|lra|thresh)"' | grep -oE '"-?[0-9.]+"' | tr -d '"' | tr '\n' ' ')
# 之後 -af 寫 "loudnorm=I=-14:TP=-1.5:LRA=11:measured_I=$I:measured_TP=$TP:measured_LRA=$LRA:measured_thresh=$TH:linear=true:print_format=summary"
# 4K H.264：crf 20 slow、level 5.1、AAC 256k（實測 2 秒 testsrc2 轉 16.6 秒；整支片以此估時間）
ffmpeg -i in.mp4 -vf "scale=3840:2160:flags=lanczos" \
  -c:v libx264 -preset slow -crf 20 -pix_fmt yuv420p -profile:v high -level 5.1 -g 60 \
  -color_primaries bt709 -color_trc bt709 -colorspace bt709 -color_range tv \
  -c:a aac -b:a 256k -ar 48000 -movflags +faststart deliver_4k.mp4
# 4K HEVC（檔案約小 25%，hvc1 標籤給 Apple 裝置；x265 要另外寫色彩設定）
ffmpeg -i in.mp4 -vf "scale=3840:2160:flags=lanczos" \
  -c:v libx265 -preset medium -crf 22 -pix_fmt yuv420p -tag:v hvc1 \
  -color_primaries bt709 -color_trc bt709 -colorspace bt709 -color_range tv \
  -x265-params "colorprim=bt709:transfer=bt709:colormatrix=bt709:range=limited" \
  -c:a aac -b:a 256k -ar 48000 -movflags +faststart deliver_4k_hevc.mp4
```
- crf 參考：1080p 社群 18（母帶 16）；4K 20；YouTube 會再壓一次，給它高一點的位元率比省檔案重要。preset slow 比 medium 小多少依素材而異（本機 6 秒 testsrc2 實測只小 1.7%：3,203,475 → 3,148,809 bytes；實拍素材差距通常較大，未測），時間實測 1.3–2.5 倍（受機器負載影響）；趕時間用 medium，不要 fast 以下
- 音訊：MV 與音樂片 −14 LUFS、TP −1.5 dBTP。−14 是 YouTube 公開的響度正規化參考值；IG／TikTok 沒有公開規格，−14 是經驗值（未測：平臺端的正規化本機量不到）；母帶另存一份不做 loudnorm 的版本；`linear=true` 是整段同一增益，`dynamic` 會逐段壓縮，音樂片不要 dynamic。單聲道來源要加 `dual_mono=true`
- 程式渲染：`render.py` 的 PNG 序列是 sRGB，ffmpeg 會以 bt709 矩陣轉 yuv420p，上面的三個色彩標記就是告訴播放器「照 bt709 解」；少了標記在某些播放器會偏灰或偏飽和
- `-g 60`（30 fps 兩秒一個 keyframe；改 fps 時 `-g` = 2 × fps，見〈fps 選擇〉）讓平臺拖曳順暢；`-bf 2`：x264 預設是 3 個 B 格（實測不給 `-bf` 時連續 B 最長 3，給 2 後最長 2），寫 2 稍利拖曳與舊裝置相容，不在意可省

### fps 選擇（實測）
- 預設 30。24：電影感，只在素材本身是 24 fps 或全片程式渲染時用（30 fps 實拍轉 24 會掉格）；25：PAL 廣播交付；60：只給短影音的高速鏡頭（運動、whip 多的片），渲染時間與檔案約兩倍
- 改 fps 時一起改四件事：
  - `-g` = 2 × fps（24 → 48、25 → 50、60 → 120；實測 24 fps `-g 48` 的 I 格在 0.000 與 2.000 秒）
  - `render.py --fps N`：會注入 `window.RENDER_FPS`，`MV.fps` 與 `MV.frameIdx(t)` 的預設跟著走（實測 `--fps 24` → `MV.fps` 24、`MV.frameIdx(1.0)` 24、輸出 `r_frame_rate=24/1`）；頁面不要寫死 30
  - ±1 格的秒數：30 fps 33 ms、24 fps 41.7 ms、25 fps 40 ms、60 fps 16.7 ms；`qa.py` 用影片自己的 fps 算門檻，本文其他地方寫的 33 ms 都指 30 fps
  - 交付核對表的 `r_frame_rate` 改成對應值
- 一拍二（12 fps）只在 24 fps 輸出時是每 2 格一換；30 fps 輸出時 `MV.frameIdx(t,12)` 會變成 2、2、3 格不等的停格（實測第 0–9 格 → 0 0 1 1 2 2 2 3 3 4；24 fps → 0 1 1 2 2 3 3 4 4 5），要均勻就改 15 fps（每 2 格）或 10 fps（每 3 格）

### 多比例交付（從 1080p 母帶裁）
```bash
# 9:16 中央裁（構圖偏側時改 crop 的 x）；1:1；4:5
ffmpeg -i deliver_1080p.mp4 -vf "crop=ih*9/16:ih,scale=1080:1920:flags=lanczos" -c:v libx264 -preset slow -crf 18 -pix_fmt yuv420p -color_primaries bt709 -color_trc bt709 -colorspace bt709 -color_range tv -c:a copy -movflags +faststart deliver_9x16.mp4
ffmpeg -i deliver_1080p.mp4 -vf "crop=ih:ih,scale=1080:1080:flags=lanczos" -c:v libx264 -preset slow -crf 18 -pix_fmt yuv420p -color_primaries bt709 -color_trc bt709 -colorspace bt709 -color_range tv -c:a copy -movflags +faststart deliver_1x1.mp4
ffmpeg -i deliver_1080p.mp4 -vf "crop=ih*4/5:ih,scale=1080:1350:flags=lanczos" -c:v libx264 -preset slow -crf 18 -pix_fmt yuv420p -color_primaries bt709 -color_trc bt709 -colorspace bt709 -color_range tv -c:a copy -movflags +faststart deliver_4x5.mp4
```
- 程式渲染的片不要裁：直接用 `render.py --w 1080 --h 1920` 重新排版輸出，字級與安全區照 9:16 的規則重算；裁 16:9 成 9:16 會把主標切掉
- 實拍裁切時先出 `--sheet` 看主體有沒有出框；模糊背景填滿的做法見 SKILL.md A 段

### 縮圖格（封面）
- 選格原則：主體完整、對比最高、有強調色、不是動態模糊中、沒有字幕壓著；通常是副歌第一個 downbeat 後 2–4 格（動作剛到位）或片頭主標完整的那格。不選第 0 格（常是黑）
- 平臺會在縮圖上疊時長與標題：主體放中央 70%，左下與右下留空
```bash
# 指定秒數抽一格（PNG 無損；-ss 放在 -i 前面是快速定位）
ffmpeg -ss 3.5 -i deliver_1080p.mp4 -frames:v 1 cover_3.5s.png
# 讓 thumbnail 濾鏡在前 90 格裡挑一張代表格（統計上最接近平均的格；當候選用，不當最終）
ffmpeg -i deliver_1080p.mp4 -vf "thumbnail=90" -frames:v 1 -update 1 cover_auto.png
# JPG 版（q 2 ≈ 最高品質）
ffmpeg -ss 3.5 -i deliver_1080p.mp4 -frames:v 1 -q:v 2 cover_3.5s.jpg
```

### 交付前核對（實測）
```bash
# 視訊流：codec、profile、尺寸、fps、pix_fmt、色彩標記、位元率
ffprobe -v error -select_streams v:0 -show_entries stream=codec_name,profile,width,height,r_frame_rate,pix_fmt,color_range,color_space,color_transfer,color_primaries,bit_rate -of default=nw=1 deliver_1080p.mp4
# 音訊流與容器
ffprobe -v error -select_streams a:0 -show_entries stream=codec_name,sample_rate,channels,bit_rate -of default=nw=1 deliver_1080p.mp4
ffprobe -v error -show_entries format=duration,size,bit_rate -of default=nw=1 deliver_1080p.mp4
# faststart：moov 要先於 mdat
ffprobe -v trace deliver_1080p.mp4 2>&1 | grep -oE "type:'(moov|mdat)'" | head -2
# 響度回量：Integrated 要是 −14.0 LUFS 上下 0.5、True peak ≤ −1.5
ffmpeg -i deliver_1080p.mp4 -af "ebur128=peak=true" -f null - 2>&1 | grep -A12 "Summary:"
# 黑場（d 秒以上、亮度低於 pix_th）、每格平均亮度、剪點位置（給 qa.py 比對）
ffmpeg -i deliver_1080p.mp4 -vf "blackdetect=d=0.05:pix_th=0.10" -an -f null -
ffmpeg -i deliver_1080p.mp4 -vf "signalstats,metadata=print:key=lavfi.signalstats.YAVG:file=yavg.txt" -an -f null -
ffmpeg -i deliver_1080p.mp4 -vf "select='gt(scene,0.3)',showinfo" -an -f null - 2>&1 | grep -oE "pts_time:[0-9.]+"
```
- 核對表：`h264/High`、`yuv420p`、`color_space=bt709 color_transfer=bt709 color_primaries=bt709 color_range=tv`、`r_frame_rate=30/1`（或〈fps 選擇〉決定的 fps）、`aac 48000`、時長 = 歌長 ± 0.1 秒、moov 在前、−14 LUFS
- 把 ffprobe 輸出貼在交付訊息裡；`qa.py VIDEO --audio-json data/audio.json` 的 `report.md` 一起附

## 六、視覺自檢清單（11 題，交付前逐題寫答案）
1. 色相：抽 20 格縮成色票，色相數 ≤ 4；稀有強調色只出現在一個段落、總長 ≤ 3 秒
2. 發光：只有強調色的物件有光暈；文字（除壓在實拍或靜圖上的字幕）沒有描邊、光暈、投影，程式渲染的歌詞字幕模式也不描邊；發光面積每格 ≤ 5%
3. 層級：每個畫面的文字最多三層，相鄰層字級比 ≥ 1.6；一眼知道先看哪裡（遮住強調色後畫面仍有主體）
4. 字距行距：標題字距在 −0.03～0 em、行距 ≥ 1.15 em；中英之間有 0.25 em；數字等寬；沒有行首標點
5. 安全區：所有文字在 90% 安全區內；字幕距邊 ≥ 5%、距底 8–12%；有 letterbox 時以有效畫面（bar 到 H−bar）量，不是整張畫布；9:16 的文字在 y 15–72%、x 5–85%；沒有壓到人臉
6. 拍點：`qa.py` 報告裡剪點與最近拍點誤差 ±1 格內的比例 ≥ 95%；每個動作的到位時刻在拍上
7. 緩動：全片用的緩動 ≤ 4 種且各有固定用途；沒有無終點的 `sin(t)` 漂移；震動與閃白都在 0.3 秒內衰減完
8. 標點符號：flash／invert／impact frame 一小節 ≤ 1 次、一段落 ≤ 4 次；intro／verse／chorus 的強度是 40／70／100
9. 後製：顆粒、暈影、halation、色差是全片常數；letterbox 黑邊乾淨；抽格比對「有／無」每一層都看得出存在理由
10. 輸出：ffprobe 核對表全部符合；縮圖格主體完整、無字幕、無動態模糊；每個比例版本都看過 `--sheet`
11. 網格與構圖：文字塊左緣都在欄線上、基線在基線格上；主體落點全片一種；每段抽一格跑 `neg_space.py`，負空間都 ≥ 40%；文字與底色的對比比達門檻

答不出「是」的題目，修完再看一次整片；三題以上答「否」不交付。

## 七、實測紀錄
- 環境：Linux x86_64、4 核心、ffmpeg 6.1.1-3ubuntu5（libx264、libx265 3.5、libvpx、libass、libfreetype、libfontconfig、libharfbuzz）、Chromium HeadlessChrome/141.0.7390.37（playwright 1.56，`--use-gl=angle --use-angle=swiftshader`）、Python 3（`/root/video-lab/.venv`）、字型 Noto Sans／Serif／Sans Mono CJK TC 各 Regular＋Bold
- 素材：`ffmpeg -f lavfi -i "testsrc2=s=1280x720:r=30:d=6" -f lavfi -i "sine=f=440:r=44100:d=6" -c:v libx264 -preset veryfast -crf 18 -pix_fmt yuv420p -c:a aac -b:a 128k -shortest src.mp4`
- 色彩（一、全部 OK，各 1–3 秒；halation 5 秒、全堆疊 8.6 秒）：eq、curves preset、curves 自訂、colorbalance、colortemperature、colorchannelmixer 單色與褐色、lut3d（python 產 17³ .cube）、noise、vignette、halation、rgbashift、chromashift、letterbox、unsharp 柔化、柔光 bloom、全堆疊、negate；抽第 3 秒格拼 6 格對照確認效果方向正確
- Canvas（二，playwright 跑 JS 探測）：`letterSpacing`／`wordSpacing`／`fontKerning`／`fontStretch`／`fontVariantCaps`／`textRendering`／`filter` 屬性都存在；`letterSpacing='6px'` 6 字寬 288→324、`'0.1em'` →316.8、`'-3px'` →270；kerning `To`（Sans）−3.55 px、`AV`（Serif）−6.34 px、中文配對 0；數字寬 Sans 26.64／Serif 26.40／Mono 24.00（48 px）；`canvas.style.fontFeatureSettings='"tnum"'` 不影響 ctx；字框 ascent 56／descent 14（48 px）；`lighter` 128+128→255、`screen` 64+64→112；`display-p3` context 可建立。字型解析：`Noto Sans TC` 與 `Noto Sans CJK TC` 同寬（404.26），`Noto Serif TC` 與 `NoSuchFont` 同寬（393.73）≠ `Noto Serif CJK TC`（427.68）；字重 300／400 與 700／900 各同寬。視覺圖 `type_visual.png`：字重、字距、Serif 兩種寫法、描邊與陰影、直書、逐字 kern 對齊整串
- 補測（一、二）：halation opacity 0.45、`vignette=angle=PI/6`／`PI/5`／`PI/4`／`PI/3` 左上角 64×64 YAVG 37.6／29.7／18.7／5.9（無暈影 62.4；中央 125.5 → 125.3，angle 越大越暗）、`signalstats` HUEAVG 純色 64×64（綠 38、黃 99、紅 161、洋紅 218、藍 279、青 341；膚色 `0xE0AC69` 127、`0xC68642` 130、`0x8D5524` 133、`0xFFDBAC` 126）、`crop,signalstats` 量 HUEAVG 與 `vectorscope=mode=color3:graticule=green:flags=name` 抽格、`colortemperature=temperature=8000:mix=1:pl=1`、curves 九個 preset 名稱各轉 1 秒都 OK；Canvas `ctx.filter='blur(8px)'` 在 swiftshader 下有效（方塊外 4 px 讀到 `rgb(83,25,6)` 的光暈），讀回值為 `none` 表示 filter 是即時狀態、畫完要歸零
- fontconfig：`fc-match "Noto Sans TC"` → NotoSansCJK-Regular.ttc；`fc-match "Noto Serif TC"` → DejaVuSans.ttf；`fc-match "Noto Serif CJK TC"` → NotoSerifCJK-Regular.ttc
- 字幕（二）：drawtext 描邊＋陰影（`borderw` 給運算式會報 `Undefined constant`，改整數後 OK）、box 底板、`Noto Serif CJK TC` 字卡、`subtitles=test.srt:force_style=...` 都 OK，抽格拼成 `sub_sheet.png` 目視確認；字級換算（720p 黑底、Outline=0、numpy 量白畫素列數）：libass FontSize 22／28／29／30 → 墨跡高 35／45／47／48 px，drawtext fontsize 37／41／48／55 → 35／39／46／52 px
- Canvas 補測（二、三、四，playwright）：半形空格 Sans 0.224 em、Serif 0.256 em、Mono 0.5 em；`MV.layout` 的 `font` 只給家族名時 `ctx.font` 不變（200 px 字量到 192 px 寬，給 `MV.font` 字串或函式得 800 px）；`MV.spring` freq 3 的峰值 damp 0.3／0.4／0.5／0.6／0.7 → 1.372／1.254／1.163／1.095／1.046；合成 100 fps rms（慢波＋逐格亂數）每格平均變化：原始 0.108、只套 smoothstep 0.154、往前 50 ms 平均 0.037、100 ms 平均 0.028
- 輸出補測（五）：libx264 不給 `-bf` 時 ffprobe `pict_type` 連續 B 最長 3、`-bf 2` 最長 2；6 秒 testsrc2 `-preset medium` 3,203,475 bytes／`slow` 3,148,809 bytes，時間 1.3–2.5 倍（兩次量測）；loudnorm 第二段用 bash 變數代入四個量測值後 ebur128 回量 I −14.0 LUFS
- 動態（三）：zoompan 慢推（配方已改為引用 editing.md 10c）、crop 運算式衰減震動、eq `eval=frame` 衰減閃白、tmix 三格、tpad 停格（輸出 6.000 秒）都 OK
- 輸出（五）：loudnorm 第一段對 testsrc2＋sine 素材量到 I −21.76／TP −14.46／LRA 0.10／thresh −31.76（這組值只屬於測試素材，交付指令裡是佔位符）；第二段 linear，輸出 I −14.0、TP −6.7；1080p 交付 9.2 秒、4K H.264 2 秒素材 16.6 秒、4K HEVC 14.4 秒、9:16／1:1／4:5 各 5–7 秒；ffprobe 全部讀到 `bt709/bt709/bt709/tv`、`yuv420p`、`aac 48000`；`type:'moov'` 先於 `type:'mdat'`；ebur128 回量 I −14.0 LUFS、peak −6.8 dBFS；blackdetect 在無黑場素材無輸出（正常）、signalstats YAVG 可讀、scene 偵測在兩段 concat 的素材抓到 `pts_time:3`；縮圖三種指令 OK
- 渲染時間（三，playwright 量 `render(t)`，每次後 `getImageData` 強制光柵化，5 次平均）：空白填色 5 ms、發光主標場景 132 ms、紙底場景 48 ms、`MV.post` grain 12／vignette 8／halation 86／三者 154 ms、整格含後製 150–203 ms；`render.py perf.html --dur 0.5 --fps 30 --samples 12 --shutter 0.5` 15 格 66.9 秒、`--dur 1`（N=1）30 格 27.7 秒、`--sheet 0.5,1,2.5,5` 5.6 秒；機器同時有其他工作，數字會浮動 ±50%
- 補測（二、三、五）：色票條 `fps=20/6`（與 `20/6.5`、`20/187.3`）`,scale=8:8:flags=area,tile=20x1,scale=iw*8:ih*8:flags=neighbor` → 1280×64；letterbox 字幕順序（720p、2.39、黑邊 92 列、有效畫面 92–627 列，numpy 量白畫素列）：drawtext 在 crop/pad 之前 → 字只剩 624–627 列，之後且 y 減 bar → 546–583 列；libass `MarginV` 40／77／80 → 字底 611／519／511 列（2.5 px/單位）；Canvas 示範頁（1080p、2.39、bar 138）整張畫布算 → 標註（y 54）與字幕（y 994）被黑邊蓋住，有效畫面算 → 標註 182–197、字幕 832–881 列；`drawgrid` 三分線、12 欄＋`drawbox` 外框、Canvas `drawGrid` 輔助線都出圖；`neg_space.py` 示範頁 96%、testsrc2 16%；WCAG 對比比一行 Python（`EEE9DF`/`0A0A0B` 16.36、`807C76` 4.77、`5E5B57` 2.93）；`render.py --profile` 示範頁 halation 0／0.25 → render 平均 202／365 ms、截圖 189／202 ms；`--data cfg=xxx.json` 注入後頁面讀到 `window.DATA.cfg`；`--fps 24` → `r_frame_rate=24/1`、`MV.fps` 24；24 fps `-g 48` I 格在 0 與 2 秒；`MV.frameIdx(t,12)` 在 30 fps 為 2、2、3 格不等；`MV.safeArea(1920,1080,0.93)` → [67.2, 37.8, 1785.6, 1004.4]
- 未測：`minterpolate` 光流動態模糊（太慢，未跑）；平臺介面遮擋區數值為保守經驗值，未對照各平臺當日官方範本；平臺端響度正規化（YouTube 的 −14 LUFS 為其公開參考值、IG／TikTok 的 −14 為經驗值，都無法在本機驗證）
