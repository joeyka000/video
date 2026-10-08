# MV 與藝術影片的創作思考（direction）

接到「做一支 MV」「做一支藝術影片」「做一支歌詞影片」時先讀這份。先想清楚再動手：第 0–5 步（到分鏡表確認為止）走完、給我確認過，才開始寫程式或剪片。

- 本文只管「想什麼、依什麼順序決定、每步交出什麼、在哪裡停下來確認」。剪輯配方與對嘴對時見 `references/editing.md`；色彩、字型排印、動態、後製、聲畫對位、輸出規格見 `references/craft.md`；實拍與靜態照片的處理見 `references/footage.md`；日系手法見 `references/anime.md`；程式動畫參考見 `references/awesome-mv-index.md`。同一條配方只在一份參考檔維護，本文以章節名引用，不重抄。
- 填空範本：`templates/treatment.md`（風格聖經）、`templates/cuts.csv`（剪點表）。
- 路徑：本文與 `SKILL.md` 寫的 `scripts/`、`assets/`、`templates/`、`references/` 都相對於 `.claude/skills/video-lab/`（`python scripts/analyze.py` 就是 `python .claude/skills/video-lab/scripts/analyze.py`）；`data/`、`out/`、`media/`、`song.wav` 相對於專案（repo）根目錄，指令在那裡執行。
- 品質門檻與自檢方法沿用 `SKILL.md`〈品質標準〉；本文第七節是 MV 專用的加問。
- 工具的選項以各 script 的 `--help` 為準，本文列的指令是流程示意。

## 一、從 brief 到交付：九步（0–8）

每步寫明產出物、登場的工具、停下來給我確認的點。沒確認就不進下一步；回頭改比重做便宜。

### 0. 接 brief 時先問
一次問完，缺的先假設並標明：
- 歌：檔案、歌詞文字、是否有分軌（stem）。有分軌時把人聲軌給 `align.py`（辨識更準）、鼓軌給 `analyze.py`（拍點與 onset 更準）各跑一次：兩支工具都只吃一個音檔，換檔名即可。`mv-kit.js` 只讀一份 `audio.json`；用鼓軌那份時 `env` 反映的是鼓不是混音，要混音的能量曲線就用混音再跑。
- 演出者：有沒有人可拍、能拍幾天、能不能對嘴。
- 交付：平臺（YouTube／IG／TikTok）、比例（16:9、9:16、1:1，要幾種）、長度（全曲或 60 秒版）、死線。
- 素材：既有的實拍、照片、插畫、Logo、過去作品的色票或字型。
- 預算：能花在實拍、生成素材、渲染時間上的各是多少。
- 禁忌：客戶不要的畫面、顏色、競品、宗教與政治符號。
- 參考：客戶喜歡的三支片，各一句「喜歡的是什麼」（不是整支照搬）。

### 1. 聽歌拆結構
這一步全部靠程式輸出判斷，不靠耳朵（執行流程的是 Claude，聽不到聲音；需要人耳的只有最後「給我確認」那一點）。
- 跑 analyze.py，先不帶 `--bpm`（與 `SKILL.md` C 段第 1 步同一套流程），`--sections` 依這首歌寫完整的段落清單，不留省略號（寫 `...` 會被拒絕）：
  `python scripts/analyze.py song.mp3 -o data/audio.json --sections "intro:0,verse1:4,chorus1:12,verse2:20,chorus2:28"`
  數字是小節序（bar 0 = 第一個 downbeat）；還不知道段落在哪就先不給 `--sections`，看印出的自動分段 S1、S2… 與下面的每小節表，手標後重跑。
- 核對印出的摘要（不帶 `--bpm` 時它自己估 tempo，再用 kick 回歸修正；實測 120 BPM、25.5 秒的測試歌印「tempo 119.999 BPM（初估 120.2）… kick 殘差 sd 0.6 ms … 拍數 51」）：
  - 拍數 ≈ 歌長 × BPM ÷ 60（25.5 × 120 ÷ 60 ≈ 51）、小節數 ≈ 拍數 ÷ 4、「kick 殘差 sd」在幾毫秒內。
  - tempo 四捨五入後要像一首歌的速度：流行與舞曲常見的是 90／96／100／110／120／128／140。估成 2 倍或 1/2 倍是常事（慢歌估成雙倍、快歌估成一半）：印出的 tempo 與點頭的速度差一倍、或拍數對不上歌長，才用 `--bpm N` 覆寫重跑（`--bpm` 只固定 tempo，第一拍、downbeat 相位與段落照舊算；實測印「tempo 120.000 BPM（初估 120.0，--bpm 固定）」）。
  - 倍數錯誤只能靠拍數與人耳分辨，「kick 殘差 sd」分不出來：實測同一首歌 `--bpm 60` 印拍數 26、`--bpm 120` 印拍數 51，殘差 sd 都是 0.6 ms。
- 校對第一拍：鼓進來的第一個 kick 必須落在拍格上，而且通常是某小節的第一拍。前奏沒鼓時 `onsets.kick[0]` 不等於 `downbeats[0]`，這是正常的（實測測試歌：kick[0] = 8.493 秒，落在 bar 4 beat 1，離拍點 0 ms；downbeats[0] = 0.493 秒）：
```bash
/root/video-lab/.venv/bin/python - <<'EOF'
import json
a = json.load(open('data/audio.json')); k0 = a['onsets']['kick'][0]; bl = 60 / a['tempo']; m = a['meter']
n = (k0 - a['downbeats'][0]) / bl; near = round(n)
print(f"第一個 kick {k0:.3f} 秒 → bar {near // m} beat {near % m + 1}，離拍點 {(n - near) * bl * 1000:+.0f} ms")
EOF
```
  離拍點超過 ±30 ms、或落在 beat 2–4 而這首歌不是弱起（anacrusis）→ 用 `--first-beat` 重跑，值 = 第一個 kick 的秒數減去它前面整數個小節（`k0 − bar × 小節秒`）。整首沒鼓的歌改看 `env.low` 第一次抬起的時間。
- 段落與能量：讀三樣東西，三者一致的邊界就是段落邊界，不一致以歌詞為準。
  1. 每小節 RMS 與鼓點密度表（下面的程式；能量 1–5 直接依 RMS 分五級）：鼓進來的小節多半是 verse 起點、snare／hat 密度跳高的小節多半是副歌起點、RMS 最低且連續 4 小節以上的是 breakdown；「最大的一拍」= RMS 最高小節的第一個 downbeat。
  2. `lyrics.json`（有歌詞時）：重複出現的那幾句是副歌；第一句歌詞的 `start` 落在哪個小節，verse1 就從那裡起。
  3. `--plot out/structure.png` 的分析圖：直接出圖（numpy 畫、ffmpeg 編碼，不需 matplotlib；上欄 onset、下欄 env，標拍線、downbeat 與段落名，實測 75 KB），看整體形狀用它，貼進對話或 treatment 用下面的文字表。
```bash
/root/video-lab/.venv/bin/python - <<'EOF'
import json
a = json.load(open('data/audio.json')); rms, fps, db, on = a['env']['rms'], a['env']['fps'], a['downbeats'], a['onsets']
for i, t0 in enumerate(db):
    t1 = db[i + 1] if i + 1 < len(db) else a['duration']
    seg = rms[int(t0 * fps):int(t1 * fps)]; v = sum(seg) / max(1, len(seg))
    cnt = {k: sum(1 for x in on[k] if t0 <= x < t1) for k in ('kick', 'snare', 'hat')}
    print(f"bar {i:3d} {t0:7.2f}s {'#' * int(v * 40):<40} {v:.2f}  kick {cnt['kick']} snare {cnt['snare']} hat {cnt['hat']}")
EOF
```
  實測 120 BPM 測試歌：bar 0–3 RMS 0.13、無鼓（intro）；bar 4 起 0.35、每小節 kick 3–5（verse）；bar 12 起 0.59、每小節 snare 2 與 hat 6（chorus）；bar 16 0.03（曲末）。
- 有歌詞：`scripts/align.py song.mp3 lyrics.txt -o data/lyrics.json`。Whisper 模型下載不了時用 `--from-json` 吃現成的字級時間碼；再不行就先手標每行起訖，逐字用插值。
- **要把畫面切在某個字上之前，用人聲軌校一次**：Whisper 的字級時間會漂，而且越到後段漂越多（寶可夢主題曲實測：開頭差 0.2 秒，終段副歌差 0.6–1.0 秒，還整句掉字——「たとえ火の中」第一次出現那 16 秒完全沒轉出來）。做法：人聲軌（分離過的 `vocals.wav`）每個八分音符算一次 RMS 與 onset，排成「一小節一列」的表，有聲／停頓一眼看得出來；再對照旋律知識把每句擺回小節上（例：「なりたいな／ならなくちゃ／絶対なってやる」各佔一小節、句尾空半拍）。快歌的連續短詞（火の中 水の中…）用人聲包絡的峰值數音節，算出每個詞的長度（這首是附點四分＝0.75 秒，不是一拍）
- 還沒拿到歌或要先把流程跑通：`scripts/testsong.py -o out/test.wav --bpm 120 --bars 32` 合成測試歌，附 `test.truth.json` 的真實拍點。
- 產出物：段落表（名稱、起訖小節、起訖秒、能量、該段第一句歌詞）、tempo／拍號／第一拍、能量曲線（`--plot` 的圖與上面的每小節文字表）。
- 給我確認：段落表與能量曲線。必問三件事：副歌出現幾次、哪一次最大、哪裡是 breakdown（最安靜處）。BPM 與第一拍由我用耳朵核對（流程裡唯一需要人耳的點）。

### 2. 一句話概念
- 提三個互不相像的概念。每個一句話，必須同時說出「畫面是什麼」與「它怎麼隨歌變化」。例：「整支片是一張候車室的翻牌時刻表，每句歌詞是一班車，副歌時整張表翻面」。說不出「怎麼變化」的概念不成立。
- 每個概念附一段參考畫面的文字描述（不是連結），以及它適合哪種型態（見第二節）。
- 檢查：這個概念離開這首歌還成立嗎？成立就太泛，換掉。
- 三個概念要拉開距離，例如針對虛構曲目《候車室》（等待與末班車）：
  - 概念型：「整支片是一張候車室的翻牌時刻表，每句歌詞是一班車，副歌時整張表翻面」。
  - 表演型：「演出者在空月臺唱完整首歌，每次副歌月臺燈多亮一排，最後一次全亮後瞬間全滅」。
  - 敘事型：「一個人反覆錯過同一班車，每次錯過畫面少一種顏色，最後一次他沒有上車」。
- 產出物：三個概念，各一句話加一段描述。
- 給我確認：三選一，或要求重提。選定前不做任何視覺。

### 3. 母題與貫穿物
- 選一個貫穿全片的母題（motif）：一個物件、一個圖形或一個動作，片頭出現、每次副歌回來、片尾收束，而且每次回來都有變化（長大、翻面、碎掉、換材質），不是原樣重複。
- 列出母題在每個段落「變成什麼」：寫成一行「段落 → 母題狀態」的表。
- 決定歌詞怎麼進畫面（見第五節）：每段落一種圖形方式，先寫在這張表的第三欄。
- 產出物：母題表（段落 → 母題狀態 → 歌詞整合方式）。
- 給我確認：母題表。問：母題與歌名、歌詞核心意象的關係說得清楚嗎？

### 4. 風格聖經（treatment）
- 填 `templates/treatment.md`：語氣、色票（主色＝背景大面積、輔色、中性色 2–3 階、強調色＝母題與亮字、稀有強調色；各一個 hex、用途與面積比例，角色定義與比例照 `references/craft.md`〈色票紀律〉）、字型系統（標題／歌詞／標註三個角色，但字型家族最多兩個：中文一個 Sans 或 Serif，加一個等寬；標題與歌詞用字重分，不換家族）、質地與後製、禁止清單、逐段 treatment。
- 色票、字型、顆粒的具體選法與數值見 `references/craft.md`；這一步只決定「角色」與「規則」，不調數值。
- 逐段 treatment 每段一小段文字：這段的視覺語言、母題狀態、歌詞模式、能量，以及該段「唯一的大招」（一段只能有一個）。
- 產出物：填好的 treatment.md，一頁以內讀完。
- 給我確認：整份 treatment。重點看色票（色相 ≤ 4，含稀有強調色；面積比例見 `references/craft.md`〈色票紀律〉）、字型家族是否 ≤ 2、語氣是否只有一種、禁止清單是否具體。

### 5. 依小節的分鏡表
- 依第六節的欄位寫分鏡表（絵コンテ，storyboard）。時間以「小節／拍」為主鍵，秒數由 `data/audio.json` 換算，不手算。
- 剪點密度照第五節的能量對照表排；每一列只做一件事。
- 要程式動畫的鏡頭，到 `references/awesome-mv-index.md` 挑 1–3 支做法參考，寫在備註欄；只借做法，內容自創。
- 日系表現（止め絵、衝擊格、カットイン）要用時，在備註欄標 `AFX.*` 名稱，規則見 `references/anime.md`。
- 產出物：分鏡表（表格，一列一鏡）、每段一張草圖或文字畫面（可省）。
- 給我確認：分鏡表。這是最後一次大改便宜的機會；確認後只做小幅調整。

### 6. 素材計畫
- 把分鏡表的「來源」欄統計成三類：實拍、靜圖（含 AI 生成或插畫，再做視差與處理）、程式動畫（Canvas 2D，`assets/mv-kit.js`）。
- 分配原則：
  - 有演出者、有場景、有預算 → 實拍為主，程式動畫做字與轉場。
  - 只有幾張圖或 AI 生成素材 → 靜圖加視差與質地處理為主，程式動畫補節奏；靜圖一律過一層統一的處理（下面〈靜圖處理〉）才不會看起來是素材庫。
  - 沒素材、純音樂、預算低 → 程式動畫為主；此時概念必須是「規則」而不是「場景」（見第四節）。
- 每個實拍鏡頭寫：場景、動作、鏡頭運動、要拍幾個 take、長度至少幾秒（剪點密度高的段落每個 take 要留 2 小節以上；素材比剪點表需要的短時 cutlist.py 會用最後一格停格補足，停格看得出來，見第 7 步）。
- 每個程式動畫鏡頭寫：用到哪些 `MV.*` 函式、資料來源（`audio.json`／`lyrics.json`）、是否需要靜圖。

表演型實拍規則（對嘴，lip-sync）。這裡只有拍攝端的規則；`in` 的計算（抽機內收音、交叉相關、印出每列的 `in`）只在 `references/editing.md`〈10. 對嘴鏡頭對時〉維護，本文不另列程式：
- 現場回放（playback）：每個 take 都用同一份回放檔，演出者對著回放唱；整首從頭放，或從指定小節起播。起播小節寫進檔名（`A1_bar08_take2.mp4`），回放前留 1–2 秒拍板或口頭倒數。
- 同時錄下回放音軌：機內麥克風收到的回放就是對齊參考，不要關機內收音。
- 慢動作對嘴：回放改用 k 倍速檔（`ffmpeg -i song.wav -af atempo=2.0 song_x2.wav`，1.5 倍用 `atempo=1.5`；實測 33.5 秒的歌 → 16.74／22.32 秒），演出者跟著快版唱；剪點表 `speed` 填 1/k（0.5／0.67），畫面回到正常速、口型仍對得上。這支 take 對時的參考檔就是現場實際放的這個 k 倍速檔，不是母帶：拿母帶去對，包絡的時間尺度差 k 倍，算出來的位置是錯的。
- 多 take 對齊到同一小節：同一句的不同 take 在剪點表只換 `src` 與 `in`，`bar`／`beat` 不動；每個 take 各自對時一次。
- `in` 的意思（T = 目標小節秒、S = 起播小節秒，都查 `audio.json` 的 `downbeats`；p = 回放起點在 take 裡的秒數；k = 回放倍速，正常回放 k = 1）：`in = p + (T − S) / k`。editing.md 的程式量的不是 p 而是 L（take 的 0 秒在回放檔的第幾秒，L = S/k − p），再算 `in = T/k − L`；兩式相等（實測 k = 1 與 k = 2 各三個剪點，兩式印出的 `in` 全部一致）。p 與 L 都不用眼睛讀波形，交給那段程式。
- 產出物：每支 take 的 L 與它用到的每列 `in`，直接填進 `templates/cuts.csv`；慢動作列的 `speed` 填 1/k。
- 確認點：交付前抽 3 個對嘴剪點抽格，看口型與人聲是否同一格（做法見同一節）。

靜圖處理（照片、插畫、AI 生成圖；每張至少做「色票對映＋顆粒＋一種動態」三件事，不原樣上畫面）：
- 色票對映：靜圖先調成色票的色調（去飽和後只留強調色一個色相，或主色／強調色雙色調），配方見 `references/craft.md`〈ffmpeg 調色配方〉；任一張靜圖與程式動畫段落並排要像同一支片。
- 顆粒與暈角全片一套：程式動畫路線用 `MV.post` 的 `grain`／`vignette`，數值與其他段落相同；實拍路線用 `references/craft.md`〈電影感後製堆疊〉。
- 動態（每張靜圖至少一種）：
  - 單張推軌（Ken Burns）：`footage.py kenburns`，選項與限制見 `references/footage.md`〈五、靜態照片在 MV 裡〉（實測 `K1.png -o out/K1_kb.mp4 --dur 4 --size 1280x720 --fps 30` 出 120 格）。要進 `cutlist.py` 當 `src` 的靜圖就用這個先轉成影片；用 `references/editing.md` 配方 10c 的 zoompan 也行，輸入換成 `-loop 1 -framerate 30 -i K1.png -t 8`、`on/60` 改成 `on/240`、濾鏡尾加 `,format=yuv420p`（實測 8 秒 240 格）。濾鏡本身只在 editing.md 維護。
  - 分層視差（parallax）：ffmpeg 兩層最小版見 `references/footage.md` 同一節；要多層、隨節拍與能量走的就用下面的 Canvas 版（程式動畫路線；這段程式只放在本文，其他參考檔引用這裡）。把圖拆成 2–3 層（背景、主體、前景；去背存 PNG），每層放大 1.10 倍置中（邊緣外推 10%，位移時不露黑），依 `MV.barPhase` 左右緩移、依 `MV.env('rms')` 微抬，前景位移是背景的 2 倍。
  - 圖一律轉成 data URL 經 `--data` 注入，不用 `<img src="bg.png">` 或 `new Image()` 直接載本機檔：render.py 以 `file://` 開頁面，本機 PNG 畫進 canvas 後畫布被判定跨來源汙染（tainted），之後任何 `getImageData` 都丟 `SecurityError`；`MV.post` 的 `grain` 與 `render.py --samples` 都走 `getImageData`，所以 render.py 會印 `[render error] … SecurityError: … The canvas has been tainted by cross-origin data.` 與「輸出不可信」、以非 0 結束、不出圖（實測）。先轉 data URL：
```bash
# 把 bg.png、fg.png 轉成 data/images.json（{"bg": "data:image/png;base64,…", "fg": …}）
/root/video-lab/.venv/bin/python -c "import base64,json;json.dump({k:'data:image/png;base64,'+base64.b64encode(open(k+'.png','rb').read()).decode() for k in ('bg','fg')},open('data/images.json','w'))"
```
  - 頁面（骨架同第六節的 animatic.html：1920×1080 的 canvas 加 `mv-kit.js`）：
```js
MV.setData({ audio: window.DATA.audio });
const W = 1920, H = 1080, ctx = document.getElementById('c').getContext('2d');
const OVER = 1.10;                                                     // 邊緣外推 10%
const layer = (im, t, k) => {                                          // k = 視差倍率：背景 1、前景 2
  const dx = (MV.barPhase(t) - 0.5) * W * 0.03 * k;                    // 每小節左右緩移
  const dy = -MV.env('rms', t) * H * 0.02 * k;                         // 能量高時整層微抬
  ctx.drawImage(im, (W - W * OVER) / 2 + dx, (H - H * OVER) / 2 + dy, W * OVER, H * OVER);
};
let n = 0; const bg = new Image(), fg = new Image();
const ready = () => { if (++n < 2) return;                             // 兩層都載好才定義 render（render.py 等 window.render 存在才開始截圖）
  window.render = t => { ctx.fillStyle = '#000'; ctx.fillRect(0, 0, W, H); layer(bg, t, 1); layer(fg, t, 2); MV.post(ctx, { grain: 0.12, vignette: 0.3 }, t); };
};
bg.onload = ready; fg.onload = ready; bg.src = window.DATA.images.bg; fg.src = window.DATA.images.fg;
```
  - 渲染加 `--data images=data/images.json`（實測：`python scripts/render.py para.html -o out/para_sheet.png --sheet 0.5,1.5,25.0,26.0 --data audio=data/audio.json --data images=data/images.json` 出圖，拼圖上前景位移是背景的 2 倍；`--samples 2 --shutter 0.5` 也能跑；1080p 兩層加顆粒每格 render 約 60–200 ms）。
- 產出物：素材清單（三類各一表）、拍攝或生成的清單、預算與時程。
- 給我確認：素材清單與預算。沒素材的鏡頭要在這裡決定改程式動畫還是刪。

### 7. 剪輯與輸出
- 程式動畫：複製 `assets/mv-template.html` 起手，一段一個 `MV.timeline` entry，歌詞用 `MV.line('歌詞片段')` 以內容找行，不寫死秒數。先 `scripts/render.py page.html -o out/sheet.png --sheet 0.5,5.52,10.52 --data audio=data/audio.json --data lyrics=data/lyrics.json` 看拼圖，再 `--cuts` 出剪點拼圖，再 `--dur 10` 試渲染，確認後才渲全片加 `--audio song.mp3`。
- 實拍與靜圖：剪點表填 `templates/cuts.csv`（bar、beat、src、in、speed、label），`python scripts/cutlist.py cuts.csv --audio-json data/audio.json -o out/montage.mp4 --music song.mp3 --sheet`，先看印出的剪點表再轉檔。轉檔後必做：`ffprobe -v error -show_entries format=duration -of default=nw=1 out/montage.mp4` 的長度要等於剪點表印出的「共 N 格 S 秒」（= 末列結束秒 − 第一列秒）；不等就是有段落掉了。素材不夠長時 cutlist.py 會印「警告：X 只有 a 秒，需要到 b 秒，不足的 n 格用最後一格停格補足」，用最後一格停格（tpad）補到該段長度，逐段用 ffprobe 核對格數，輸出長度仍與表一致（實測：2 秒素材的段需要 4 秒，表印 180 格 6.000 秒，ffprobe duration=6.000000、nb_read_frames=180，同時寫出 `out/montage.cuts.json`）。停格會被看出來，所以剪點密度高的段落每個 take 仍要留 2 小節以上，不夠就改 `in` 或換 take；`in` 超過素材末格（長度 − 1/fps）會直接報錯。混用時 montage 當底，程式動畫輸出 `--alpha` 疊上去。
- 剪輯配方（節奏、J／L cut、速度、實拍處理、合成）見 `references/editing.md`；後製與輸出規格見 `references/craft.md`。
- 試渲染段落的選法：最大副歌進場前 2 小節加進場後 2 小節，要含一次轉場、一次全幅歌詞、一次母題變化；這 10 秒不對，全片不會對。
- 渲染時間先量再估：跑 10 格加 `--profile`，`python scripts/render.py page.html -o out/t10.mp4 --fps 10 --dur 1 --from 24 --profile --data audio=data/audio.json --data lyrics=data/lyrics.json`；render.py 結尾印「每格 render 平均 X ms（最大 …）  截圖平均 Y ms（最大 …）  共 10 格」（跑滿 10 格不加 `--profile` 也印這行，`--profile` 另外逐格印到 stderr）。每格耗時 ≈ (X + Y) ms，乘全片格數。實測 `assets/mv-template.html` 1920×1080、4 核心、從第 24 秒起 10 格：render 89 ms＋截圖 470 ms ≈ 0.56 秒/格（別次量到 0.7–1.1 秒/格，隨機器負載浮動，估時取 1 秒/格）；3 分鐘 30 fps 全片 5400 格 ≈ 1–1.5 小時，`--scale 2`、`--samples N` 再往上乘。超過半小時就先給我看拼圖再決定要不要開 `--scale 2` 或 `--samples`。
- 產出物：10 秒試渲染（含最大副歌）、剪點表、全片輸出。
- 給我確認：10 秒試渲染。沒看過試渲染不渲全片（4 核心機器上全片渲染很貴）。

### 8. 自檢
- 跑 qa.py，`--cuts` 依路線給（兩種格式 qa.py 都收，實測）：
  - 實拍 montage：`python scripts/qa.py out/montage.mp4 --audio-json data/audio.json -o out/qa --cuts out/montage.cuts.json`。`out/montage.cuts.json` 是 cutlist.py 轉檔時自動寫在輸出檔旁的 `OUT.cuts.json`，不用自己做。
  - 程式動畫：`render.py --cuts` 只出拼圖不寫檔，先用下面的程式把頁面的 `window.CUTS` 匯出成 `out/cuts.json`（實測；這段程式只放在本文，其他參考檔引用這裡），再 `python scripts/qa.py out/final.mp4 --audio-json data/audio.json -o out/qa --cuts out/cuts.json`：
```bash
/root/video-lab/.venv/bin/python - page.html out/cuts.json audio=data/audio.json lyrics=data/lyrics.json <<'EOF'
import json, os, sys
from playwright.sync_api import sync_playwright
page_html, out = sys.argv[1], sys.argv[2]
data = {k: json.load(open(p, encoding='utf-8')) for k, p in (x.split('=', 1) for x in sys.argv[3:])}
with sync_playwright() as p:
    b = p.chromium.launch(); pg = b.new_page(viewport={'width': 1920, 'height': 1080})
    pg.add_init_script('window.DATA = ' + json.dumps(data, ensure_ascii=False) + ';')   # 與 render.py --data 同一種注入
    pg.goto('file://' + os.path.abspath(page_html))
    pg.wait_for_function('Array.isArray(window.CUTS)', timeout=30000)
    json.dump(pg.evaluate('window.CUTS'), open(out, 'w')); b.close()
print(out)
EOF
```
- 讀 `out/qa/report.md`：剪點與拍點的誤差、落在 ±1 格內的比例、黑場與閃白次數；逐張看 `out/qa/sheet_<section>.png`。
- 答第七節十題；答不出來的回到對應步驟改。
- 依 `SKILL.md`〈品質標準〉逐項自檢，找出最弱三處修掉再看一次全片。
- 產出物：自檢結果（十題答案、qa 報告重點、修了什麼）。
- 給我確認：交付時附自檢結果與拼圖。

## 二、MV 的三種型態

| 型態 | 核心 | 適合的歌 | 成本重心 | 風險 |
|---|---|---|---|---|
| 表演（performance） | 演出者唱、演、跳；鏡頭與剪輯是主角 | hook 強、節奏強、演出者有魅力 | 實拍：場景、燈光、多機或多 take | 沒有概念就只是「拍到了」 |
| 敘事（narrative） | 一條故事線，歌是配樂 | 歌詞有人物、事件、轉折 | 實拍：演員、場景、連戲 | 字面化：歌詞唱什麼就演什麼 |
| 概念（concept） | 一個視覺規則貫穿全片，隨歌變化 | 純音樂、抽象歌詞、電子、預算低 | 設計時間；程式動畫或靜圖 | 規則太弱撐不到三分鐘 |

- 混合是常態：表演放進概念的世界（演出者在翻牌板前唱）、敘事只在副歌閃回、概念片用一段實拍當錨。混合時仍要能一句話說出主型態。
- 依歌選：先看歌詞是否有具體人物與事件（有 → 敘事可行），再看 hook 是否靠人聲魅力（是 → 表演要佔比），其餘走概念。
- 依預算選：沒有演出者可拍 → 不做表演型；沒有演員與場景 → 敘事改成「物件敘事」（用物件的狀態變化說故事）；什麼都沒有 → 概念型，且概念必須是程式能生成的規則。
- 混合時先定主型態的佔比，常見組合：
  - 表演 70%＋概念 30%：演出者在概念的世界裡唱，程式動畫做字、儀表與轉場。
  - 概念 80%＋實拍錨 20%：規則驅動的畫面為主，一兩個實拍鏡頭讓觀眾知道這是真的人與地方。
  - 敘事＋表演：verse 講故事，每次副歌回到同一個表演機位，副歌本身就是「回家」。
- 藝術影片（非 MV）一律是概念型；差別在不需要服務歌詞，見第四節。

## 三、概念思考方法

- 視覺雙關與轉化，不要字面插圖：唱到「燈」不畫燈，問「燈在這首歌裡代表什麼」，再找一個能「變成」它的東西（燈的熄滅順序變成歌詞的進度；時鐘變成翻牌板）。一個鏡頭要能說出「A 變成 B」，只說「畫 A」就重想。
- 一個貫穿全片的母題：見第一節第 3 步。母題要能承受三種操作：放大（佔滿畫面）、拆解（碎成部件）、換材質（紙→金屬→光），副歌遞進就靠這三種。
- 每段落一種視覺語言，全片共用一套色票、字型、顆粒：verse 可以是實拍、chorus 可以是全幅翻牌板、bridge 可以是手繪，但任一格截圖，色票、字型角色、顆粒都要認得出是同一支片。換語言的次數上限：段落數；一段內不換。
- 副歌多次出現時的遞進：每次副歌用一個詞定義差異，常用序列是「乾淨 → 加重 → 反轉（或抽空）→ 極限」。第三次副歌通常是 breakdown 後的回歸，可以最小（只剩母題與一行字），把力氣留給最後一次。不要四次副歌一樣，也不要只是「越來越多特效」。
- 明暗版面交替：安排一到兩個段落反白（深色底換淺色底，或反過來），讓全片有明暗節奏，也讓副歌進場時「換底色」本身就是衝擊。強調色在深底與淺底上都要站得住。
- 稀有強調色只屬於一個瞬間：色票裡留一個與強調色不同色相的顏色，全片只在一個段落的一個瞬間出現（通常是最後副歌的高點或關鍵歌詞；總長上限見 `references/craft.md`〈色票紀律〉）。其他地方一律不用；用了第二次它就不稀有。
- 一致的語氣：幽默、冷、溫柔三擇一，寫在 treatment 的第一行；全片的字型、鏡頭速度、轉場都服從它。幽默靠反差不靠表情：用最正經的形式（報表、說明書、公告的版面與用語）講荒唐的事，不用搞笑字型、不用音效式的誇張動態；冷就不要暖濾鏡救場；溫柔就不要衝擊格。
- 「不是 slop」清單（在地化、具體；`templates/treatment.md` §8 已預填這 8 條原文，填 treatment 時不刪不改，再加只屬於這支片的）：
  - 不用一眼就是「AI 生成感」的視覺：臺灣接案最常見的是半透明玻璃質感的 3D 字、滿版紫藍漸層底加漂浮光點、磨皮到沒毛孔的人像、每個角落都打了光的夜景、沒有光源的體積光（volumetric light）；每個畫素都要像有人決定過，說得出它為什麼在那裡。
  - 不用預設淡入淡出湊轉場；不用每拍都白閃；不用全片 shake。
  - 不用素材庫的城市縮時、無人機空拍開場、慢動作水花與灑金粉。
  - 不用 AI 生成的人臉與手當主體；靜圖素材不原樣上畫面，一律過處理。
  - 不用免費書法字型配大留白當文青；不用圓角色塊加陰影的簡報感；不用每字彈跳的短影音字幕。
  - 不把夜市、霓虹招牌、機車、101 當臺灣符號硬塞，除非它在概念裡有角色。
  - 不用現成的 lo-fi 動畫、賽博龐克、蒸氣波整套風格；風格要從母題長出來。
  - 不描邊、不加光暈的歌詞字（字幕模式例外，規格見 `references/craft.md`〈字幕規格〉）；不置中疊在人臉上的字幕式歌詞。

## 四、藝術影片／實驗影片的做法

沒有歌詞要服務、或者 brief 是「一支作品」而不是「一支 MV」時，從下面挑一種當骨架；一支片一種骨架。

- 結構主義（structural film）：一個規則貫穿全片，觀眾看的是規則被執行到底。例：單一鏡頭連續推進三分鐘；畫面只在每個 downbeat 換一次且每次只換一個元素；按字母表順序出現的物件。規則要在 10 秒內讓人看懂，之後靠規則的變奏撐住。
- 生成藝術（generative art）：一組規則加一個種子決定全部畫面，用 `MV.rng(seed)`、`MV.noise1`，種子寫死在 treatment。每段落換的是數值不是規則；數值隨 `MV.env`、`MV.sectionAt` 走，讓音樂「可見」。
- 資料驅動（data-driven）：畫面由一組真實資料（氣溫、潮汐、字數、心跳）畫出，音樂只負責節奏。先決定資料的對映規則（哪個欄位對映大小、哪個對映位置、哪個對映顏色），寫進 treatment；資料來源與單位要在片尾標。
- 字型影片（typographic film）：片頭思路。Saul Bass 的做法是一個圖形概念用到底（剪紙、單一線條、一種形狀），字是圖形的一部分；Kyle Cooper 的做法是質地與手工痕跡（刮痕、重拍、錯位的字）定義角色。做這類片時先決定「字是什麼材質、字怎麼到位、字怎麼離開」三件事，排印細節見 `references/craft.md`。
- 轉描（rotoscope）與版畫／riso 質感：實拍重畫成線條與平塗，再加套色偏移與紙紋，觀眾看到的是印刷品不是錄影。做法與限制見 `references/anime.md`（風格方向表與 `studio/gl.js` 的參考）；色盤限定在三到四色油墨。
- 單一限制作品：全片只用一種顏色、一個形狀、一個鏡頭、一種字、或一個長度（每鏡恰好一小節）。限制要寫在片名或第一格，讓觀眾知道規則，然後把限制逼到極端。
- 首尾相接（loop）：末格等於首格（或末段倒帶回首格），可無限播放。設計時先決定首格，再反推最後 4 小節怎麼回到它；社群平臺的自動重播會讓這個設計被看見。

藝術影片走第一節的九步（0–8），差別如下：
- 第 1 步沒有歌詞就不跑 `align.py`；純音樂仍要 `analyze.py`，段落用 `--sections` 手標，因為自動分段對無人聲音樂常失準。
- 第 2 步的一句話改成「規則是什麼、規則怎麼隨時間變」；規則本身就是概念。
- 第 3 步的母題表第三欄改成「資料或數值怎麼對映到畫面」。
- 第 5 步的分鏡表「歌詞」欄改成「規則狀態」（例：第 8 小節起每 downbeat 多一條線）。
- 第 7 步優先程式動畫；實拍只當素材輸入（轉描、取樣、遮罩），不當畫面本身。
- 第 8 步多問一題：規則有沒有被打破？打破的那一次是不是設計好的唯一例外？

## 五、依音樂結構設計

### 段落能量 → 剪輯密度與鏡頭語言

| 段落（能量） | 剪點密度 | 鏡頭語言 | 歌詞模式 |
|---|---|---|---|
| intro（1–2） | 2–4 小節一切，或不切 | 鎖定機位、慢推、母題登場 | 無或片名 |
| verse（2–3） | 1 小節一切 | 平穩，動作在畫面內，不靠剪 | 側邊或字幕 |
| pre-chorus（3–4） | 2 拍一切，越接近副歌越密 | 推進、收緊、元素聚攏 | 側邊 → 全幅 |
| chorus（4–5） | 每拍或每 2 拍一切；最大的一拍放最大的畫面 | 全幅、母題放大、換底色 | 全幅 |
| 間奏 interlude（2–3） | 1 小節一切 | 器樂主導：長鏡頭跟運動、運動 ease 進 downbeat，少剪多動 | 無 |
| breakdown／bridge（1–2） | 一鏡到底或 4 小節一切 | 慢、空、抽掉顏色或聲音 | 字幕或無 |
| 最後副歌（5） | 每拍一切，可加 8 分音符的子切 | 母題極限狀態、稀有強調色 | 全幅 |
| outro（1） | 一鏡到底收回首格，或每拍一刀的回顧蒙太奇（二選一） | 收束到首格 | 無 |

- 密度跟能量走，但不要全片線性上升：breakdown 的「慢」是讓最後副歌更大的手段。
- 每段落只在 downbeat 大切；拍內的小動作（推、閃、翻）放在 kick 與 snare。反拍切（beat 2、4 或拍間）一支片只用一兩次，當作「失衡」的語彙。
- 轉場語言一支片一套：預設硬切；白閃、擦除、反白各自對應一種意義（白閃＝進副歌、擦除＝母題帶走畫面），不混用。
- 聲畫對位（哪種聲音對哪種動作）的具體做法見 `references/craft.md`。

### 注意力裝置
每支片挑兩到三個，寫進 treatment；多了互相打架。
- 開場 hook：第一格就是作品（片名或一行全幅歌詞或母題特寫），不從黑場淡入。社群平臺前 1 秒決定留不留。
- 持續的計數器或儀表：一個小元件全片在固定位置，隨歌推進（日期、距離、倒數、溫度）；每次副歌它跳一大格，breakdown 時它停住或出錯。
- 招牌動作：每次副歌的同一拍做同一個動作或同一種鏡頭（推進、翻面、手勢），第三次起觀眾會等它。
- 段落標題卡：段落切換處插一張字卡（章節號、地名、時間），讓結構被看見；縮圖尺寸要讀得出來。
- 唯一例外：全片守一個規則，只在一個地方打破（反拍切、唯一的彩色、唯一的人聲清唱），打破處就是記憶點。

### 歌詞如何「成為畫面」而不是字幕

- 卡拉OK規則：逐字同步，字在 `lyrics.json` 的 `start` 出現或亮起，在 `end` 前完成；可以提前約 0.4 秒暗示（整行先以暗色出現），但亮字永遠不超前人聲。中文一字一個 word，英文一個單字一個 word。
- 每段落用不同的圖形方式整合歌詞，寫在母題表第三欄。可用的方式：被寫出（筆跡、燈管逐一亮起）、在路徑上（沿曲線、沿邊緣）、是物件（字就是翻牌、磁磚、車票上的印字）、被蓋章或打字、被遮罩（先是色塊再揭開）、是標籤（連線指向畫面裡的東西）、被帶走（被車身、被手、被擦除）。一段一種，整支片不重複。
- 三種版面模式：
  - 全幅（FULL）：字就是畫面，佔滿安全區，用在 hook 與副歌。
  - 側邊（SIDE）：畫面主體在一側、字在另一側，兩者有關係（字指向、字反映），用在 verse。
  - 字幕（SUBTITLE）：只在 breakdown 或對白式段落用，且只在一個段落用。字級、位置、描邊或底板的選法全照 `references/craft.md`〈字幕規格〉與〈歌詞作為畫面的三種模式〉（字幕是唯一可以描邊的字，只為可讀性），本文不另訂數字。
- 無歌詞的段落讓畫面休息，不補字。
- 歌詞永遠在標題安全區內、不壓人臉與主體；工具：`MV.karaoke`、`MV.layout`、`MV.safeArea`（排印規則見 `references/craft.md`）。

## 六、分鏡表規格

欄位（一列一鏡，時間主鍵是小節／拍）：

| 欄 | 寫什麼 |
|---|---|
| 小節／拍 | `bar/beat`，bar 從 0 起（第一個 downbeat），beat 1–4 |
| 秒 | 由 `data/audio.json` 換算，寫到小數兩位 |
| 歌詞 | 這一鏡涵蓋的歌詞；間奏寫「（間奏）」 |
| 鏡頭內容 | 畫面是什麼、動什麼、母題在什麼狀態；一句話 |
| 來源 | `實拍 A1`／`靜圖 K1`／`JS`，可混用 `靜圖 K1＋JS` |
| 歌詞模式 | 全幅／側邊／字幕／無，加一句整合方式 |
| 轉場 | 進這一鏡的轉場：硬切／白閃／擦除／反白／翻牌 |
| 備註 | 參考做法（awesome slug、`AFX.*`）、安全區、禁止事項 |

範例：虛構曲目《候車室》，96 BPM、4/4、第一拍 0.52 秒、一小節 2.5 秒。一句話概念：「整支片是一張候車室的翻牌時刻表，每句歌詞是一班車，副歌時整張表翻面」。母題：翻牌板。稀有強調色：到站綠燈，只在最後副歌亮一次。只節錄 8 列。

| 小節／拍 | 秒 | 歌詞 | 鏡頭內容 | 來源 | 歌詞模式 | 轉場 | 備註 |
|---|---|---|---|---|---|---|---|
| 0/1 | 0.52 | （片名） | 黑。空的翻牌板，每拍掉下一字「候」「車」「室」 | JS | 全幅 | 硬切進 | 首格即片名；末格要回到這一格 |
| 2/1 | 5.52 | 月臺的燈一盞一盞睡著 | 月臺燈管逐一熄滅，每熄一盞對一個字；鏡頭鎖定 | 實拍 A1 | 側邊：字排在左，隨對應的燈熄滅變暗 | 硬切 | 字的「亮→暗」就是歌詞進度，不另做亮字 |
| 4/1 | 10.52 | 我把名字寫在車票背面 | 車票背面特寫，筆跡隨人聲寫出，寫到「名字」處只畫一個符號 | 靜圖 K1＋JS | 全幅：字＝筆跡 | 擦除：車票從右滑入 | 不寫實名；筆跡用 `MV.lineCharProgress` 控長度 |
| 6/3 | 16.77 | 末班車從來不等誰 | 列車進站，鏡頭不動，車身把畫面上的字帶走 | 實拍 A2 | 側邊 → 被車身擦掉 | 硬切（反拍進） | 全片唯一一次反拍切，做「沒等到」 |
| 8/1 | 20.52 | 留下來 留下來 | 翻牌板全幅，三字逐格翻出；第二次「留下來」翻牌卡住抖動 | JS | 全幅 | 白閃 1 格 | 副歌 1：乾淨，只翻牌，不加別的 |
| 12/1 | 30.52 | 直到廣播念出我的站 | 翻牌板翻成站名清單，站名全空白；翻到「我的站」整板翻黑 | JS | 全幅 | 翻牌即轉場 | 明暗交替：這格從淺底翻回深底 |
| 16/1 | 40.52 | （間奏） | 空候車室，鐘的秒針倒走；每小節鏡頭推進一段 | 實拍 A3 | 無 | 硬切 | 不補字，讓畫面休息 |
| 20/1 | 50.52 | 留下來（最後副歌） | 翻牌板撐滿畫面，到站綠燈亮約 2 秒；之後翻回首格的片名 | JS | 全幅 | 翻牌 → 硬切回首格 | 稀有強調色只在這裡；末格＝首格可接回開頭 |

寫法原則：
- 一列一鏡、一鏡一件事；鏡頭內容寫「畫面是什麼、動什麼」，不寫形容詞。
- 每段落的第一列標段落名與能量，方便對照第五節的密度表。
- 來源欄的代號在素材計畫沿用（實拍 A1 = 第一個實拍場景的第一個鏡頭；靜圖 K1 = 第一張靜圖）。
- 備註欄寫「不要做什麼」比「要做什麼」更有用（不壓臉、不用第二種顏色、不切反拍）。
- 分鏡表確認後，程式動畫鏡頭直接對映成 `MV.timeline` 的 entries（id、start、end 由小節換算），實拍鏡頭直接對映成 `templates/cuts.csv` 的列。
- 要做動態分鏡（animatic，Vコン）時，先把分鏡表渲染成灰底字卡影片配歌，看節奏對不對再做畫面。做法（實測：10 fps、100 格 17.7 秒，剪點拼圖落在正確的小節／拍）：
  1. 分鏡表存成 `data/shots.json`：`[{"bar": 0, "beat": 1, "text": "片名：候車室。空翻牌板，每拍掉一字"}, {"bar": 2, "beat": 1, "text": "月臺燈管逐一熄滅"}, ...]`，只寫小節／拍與鏡頭內容，秒數由頁面換算。
  2. 在 `mv-kit.js` 旁存 `animatic.html`（整頁如下；每拍灰底亮一下，左上印 bar／beat／秒）：
```html
<!doctype html><meta charset="utf-8"><title>animatic</title>
<body style="margin:0;background:#000"><canvas id="c" width="1920" height="1080"></canvas>
<script src="mv-kit.js"></script>
<script>
MV.setData({ audio: window.DATA.audio });
const shots = window.DATA.shots, meter = MV.audio.meter;
const at = s => MV.timeOfBar(s.bar + (s.beat - 1) / meter);          // bar/beat → 秒（timeOfBar 可吃小數小節）
const tl = MV.timeline(shots.map((s, i) => ({
  id: 'k' + i, start: at(s), end: shots[i + 1] ? at(shots[i + 1]) : MV.timeOfBar(s.bar + 1),
  render(c, f) {
    c.fillStyle = f.beatPhase < 0.12 ? '#505050' : '#3A3A3A'; c.fillRect(0, 0, f.W, f.H);
    c.fillStyle = '#BDBDBD'; c.font = MV.font('"Noto Sans Mono CJK TC"', 36, 400);   // 本機 Noto CJK 只有 Regular（400）與 Bold（700）
    c.fillText(`bar ${Math.floor(f.bar)}  beat ${Math.floor(f.beat % meter) + 1}  ${f.t.toFixed(2)} s`, 120, 140);
    c.fillStyle = '#FFFFFF'; c.font = MV.font('"Noto Sans TC"', 64, 700);
    c.fillText(`${s.bar}/${s.beat}  ${s.text}`, 120, 560);
  },
})), { W: 1920, H: 1080 });
window.CUTS = tl.cuts; window.DURATION = tl.entries[tl.entries.length - 1].end;
const ctx = document.getElementById('c').getContext('2d');
window.render = t => tl.render(ctx, t);
</script>
```
  3. 輸出配歌：`python scripts/render.py animatic.html -o out/animatic.mp4 --fps 10 --data audio=data/audio.json --data shots=data/shots.json --audio song.mp3`（試一段加 `--dur 10`）；剪點拼圖：`python scripts/render.py animatic.html -o out/animatic_cuts.png --cuts --fps 10 --data audio=data/audio.json --data shots=data/shots.json`，每個剪點前後各 2 格，核對拼圖上的 bar／beat 與分鏡表一致。
  4. 分鏡表改了就改 `shots.json` 重渲；確認後同一份 entries 換成真畫面就是第 7 步的 `MV.timeline`。

## 七、思考自檢清單

答不出來的題，回到對應的步驟改，不要往下做。

1. 一句話概念能不能同時說出「畫面是什麼」與「它怎麼隨歌變化」？（第 2 步）
2. 關掉聲音看，能不能從畫面看出副歌在哪裡、最大的一拍在哪裡？（第 5 步）
3. 母題在片頭、每次副歌、片尾都出現了嗎？每次回來有變化嗎，還是原樣重複？（第 3 步）
4. 任一格截圖，能不能一眼認出是這支片？色票、字型角色、顆粒是否全片一套？（第 4 步）
5. 每次副歌的差異能用一個詞說出來嗎（乾淨／加重／反轉／極限）？（第 3、5 步）
6. 稀有強調色是不是僅出現在一個瞬間？其他地方有沒有偷用？（第 4 步）
7. 歌詞是畫面的一部分，還是貼在上面的字幕？亮字有沒有超前人聲？字有沒有壓到主體？（第 5 步）
8. 有沒有任何一鏡是字面插圖（唱到月亮就畫月亮）？改成雙關或轉化了嗎？（第 3 步）
9. 剪點密度曲線跟能量曲線一致嗎？breakdown 有沒有真的慢下來？反拍切是不是僅用了一兩次？（第 5 步）
10. 逐條對「不是 slop」清單，有沒有踩到任何一條？把歌拿掉，這支片還像任何現成的模板或風格包嗎？像就回頭。（第 4 步）

## 八、出處

只列確定存在的來源；細節請自行查證再引用。

- Walter Murch，《In the Blink of an Eye》：剪點的 Rule of Six（情緒 51%、故事 23%、節奏 10%、視線 7%、畫面二維平面 5%、動作三維空間 4%）。剪 MV 時情緒與節奏的權重更高，但順序不變：先問這一刀的情緒對不對，再問對不對拍。
- Saul Bass：《The Man with the Golden Arm》（1955）、《Vertigo》（1958）、《Psycho》（1960）、《Anatomy of a Murder》（1959）的片頭；一個圖形概念用到底。
- Kyle Cooper：《Se7en》（1995）片頭；手工質地與錯位的字定義角色。
- Michel Gondry：Daft Punk〈Around the World〉（1997）每個樂器一組舞者、The Chemical Brothers〈Star Guitar〉（2002）窗外景物對映每個音、Kylie Minogue〈Come Into My World〉（2002）同一條街反覆走且每輪多疊一個人、The White Stripes〈Fell in Love with a Girl〉（2002）樂高定格；規則驅動的概念型範例。
- Spike Jonze：Beastie Boys〈Sabotage〉（1994）、Weezer〈Buddy Holly〉（1994）、Fatboy Slim〈Weapon of Choice〉（2001）；一個清楚的語氣與一個貫穿的玩笑。
- Hype Williams：Missy Elliott〈The Rain (Supa Dupa Fly)〉（1997）；魚眼、色票與服裝即母題，表演型的範例。
- D. A. Pennebaker 拍攝的 Bob Dylan〈Subterranean Homesick Blues〉字卡段落（1965 年拍攝，收錄於《Dont Look Back》）：歌詞成為畫面裡的物件，字型影片的早期範例。
- Norman McLaren：《Begone Dull Care》（1949）直接在底片上作畫對映爵士樂；聲畫對位與單一限制作品的範例。
- Michael Snow《Wavelength》（1967）、Hollis Frampton《Zorns Lemma》（1970）：結構主義影片的規則式做法。
- Vimeo Staff Picks（vimeo.com/channels/staffpicks）：短片與 MV 的當代水準；找參考時以它為基準。
- Awwwards（awwwards.com）：動態與排印的網頁水準，`SKILL.md`〈品質標準〉以它為門檻。
- `/root/video-lab/refs/pdoom-video/docs/TREATMENT.md`：treatment 結構（一段話概念 → 語氣 → 色票 → 字型 → 卡拉OK規則 → 母題 → 逐段 → 技術慣例）的典範，第三節「不是 slop」清單的分類方式（語氣一致、禁止清單寫具體視覺而非形容詞）也借自它；只借結構與分類，條目與內容不可用。
- `/root/video-lab/refs/anime-op/STORYBOARD.md`：依 BPM 排的分鏡表與注意力裝置（持續的 HUD、招牌動作、歌詞三種尺度、剪輯密度跟能量走）的典範；只借做法。
