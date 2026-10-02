# 實拍照片與影片：打光與精修

接到真人照片或實拍影片要做成 MV／藝術影片時讀這份。目標：拍攝時知道怎麼打光、後製時知道怎麼重新打光與精修，做到 MV 等級，但膚色自然、不過度美化（SKILL.md 品質標準）。
- 工具：`scripts/footage.py`（配方包成子命令，每次執行先印實際跑的 ffmpeg／convert 指令，`--dry-run` 只印不跑，`--preview 10` 只做前 10 秒）。輸出不能與輸入（含 `--ref`、`--mask-out`）同一個檔案，程式會擋下來；`-y` 覆寫既有輸出時先寫到 `NAME.partial.EXT`、成功才改名蓋回，失敗只刪 .partial、原檔不動（ffmpeg -y 在濾鏡失敗時會先把既有輸出截成 0 byte，本機實測）
- 動漫化濾鏡（一拍二、停格、畫面動、衝擊格、柔光、白閃、RGB 色偏、賽璐璐、パラ）在 `references/anime.md`〈二、實拍素材的 ffmpeg 做法〉，本文只引用不重寫
- 除了標「未測」的四條（HEIC 轉檔、`-profile` 轉 sRGB、libplacebo 放大、AI 去背與 AI 放大工具）以外，本文第二到第五節的每條指令都在本機實測過（環境與耗時見文末〈九、實測紀錄〉）；第一節是拍攝知識，只寫業界公認原則，數值給範圍
- 範例尺寸 1280×720、30fps；換素材時把 geq 裡的畫素座標換算

## 一、拍攝階段的打光（on-set）

### 1 光的三個變數
- 硬軟：光源「相對於主體的面積」決定，面積越大越軟。靠近變大（軟）、拉遠變小（硬）；柔光布、反射傘、白牆反彈都是在加大面積。硬光＝邊緣銳利的影子、毛孔與紋理明顯；軟光＝影子漸層、皮膚平滑
- 方向：正面光扁平、45° 側光有立體感、側光（90°）出紋理、背光出輪廓、底光詭異。先決定主光方向，其他燈服從它
- 色溫：鎢絲燈約 3200K（暖）、日光與多數 LED 約 5600K（冷）、陰天 6500K 以上、黃昏 2500–3500K。光的強度隨距離平方衰減（距離加倍，亮度剩四分之一），所以燈離人越近，臉與背景的亮度差越大

### 2 三點打光與光比（key : fill）
- 主光（key）定方向與光型；補光（fill）控制影子有多深；輪廓光（rim／back）把人從背景分出來
- 光比用亮面與暗面的曝光差算：2:1（差 1 檔）柔和、商業、美妝；4:1（差 2 檔）一般劇情、MV 常用；8:1（差 3 檔）陰鬱、黑色電影；16:1 以上接近剪影。用測光表或攝影機的波形圖（waveform）量，不要用眼睛猜
- 補光常用反光板或大面積柔光，位置在主光對側、靠近攝影機軸線、比主光低；補光不能產生第二組影子

### 3 臉部光型（主光位置）
| 光型 | 主光位置 | 特徵 | 適合 |
|---|---|---|---|
| Rembrandt | 側上 45°、高 45° | 暗面臉頰出現小三角亮區 | 戲劇、男性、MV 主歌 |
| Butterfly／Paramount | 正前上方 | 鼻下蝴蝶形影子、顴骨立體 | 美妝、女性特寫 |
| Loop | 前側 30–45°、略高 | 鼻影小而向下斜，不連到臉頰影 | 最通用、訪談 |
| Split | 正側 90° | 半臉亮半臉暗 | 衝突、神秘、副歌爆點 |
| Short（窄光） | 打在離鏡頭遠的那半臉 | 臉顯瘦、立體 | 多數人像 |
| Broad（寬光） | 打在靠鏡頭的那半臉 | 臉顯寬、明亮 | 高調、歡快 |

### 4 動機光、實用光、負填、輪廓光
- 動機光（motivated light）：畫面裡看得到或合理推得出光源（窗、檯燈、招牌），燈的方向與色溫要跟那個來源一致。觀眾不會問「為什麼這裡有光」
- 實用光（practicals）：入鏡的檯燈、霓虹、蠟燭、手機螢幕。換成可調光燈泡（2700K），曝光讓它不爆白，再用鏡頭外的燈補同方向的光
- 負填（negative fill）：在暗面放黑旗、黑布吸掉環境反彈，光比自然拉大；白天外景、白牆室內最需要
- 輪廓光（rim）與髮光：從後方 45° 或正後上方打，亮度比主光高 0–1 檔；深色頭髮、深色背景一定要有；小心鏡頭進光產生眩光
- 背光剪影：曝光對準亮背景，人不打正面光，只留輪廓光；用在副歌轉折、結尾

### 5 混色溫
- 鎢絲 3200K 與日光 5600K 同場時，攝影機白平衡鎖在主光的色溫，另一邊自然偏暖或偏冷，形成互補色對比（橘藍）。控制原則：膚色一定落在主光下、偏色只給背景與邊光；兩邊色差越大，膚色越容易被帶成偏青或偏橘，開拍前先拍一張測試看膚色再定
- 用色溫片（CTO 加暖、CTB 加冷）或雙色溫 LED 對齊；手機與相機都要手動 K 值，不要自動白平衡

### 6 MV 常用光法
- 硬光＋煙霧：硬光源從後方或側後方打，加薄霧（haze）讓光束可見；煙要均勻、薄，開拍前讓它散開
- 單色光：RGB LED 或色片打滿畫面。飽和單色很容易讓某一色版（channel）爆掉，拍時飽和度留三成餘地，後製再推；要讓臉看得清楚就留一盞中性白主光
- 頻閃對拍：頻閃燈（strobe）同步 BPM 的拍點或半拍，副歌用、主歌不用；成品要標光敏警語
- 窗光與人造月光：大面積柔光從窗外打進來當主光；人造月光照電影慣例做成冷藍（用 4500–6000K 的燈或加 CTB），實際月光接近 4100K，偏藍是觀眾習慣不是物理；低亮度、硬一點的背光，夜景可以先拍再用日轉夜（見第二節 9）
- 剪影：見本節 4

### 7 小預算與手機
- 一盞雙色溫 LED 燈＋五合一反光板＋一扇窗就夠拍：窗當主光（人側對窗 45°，距窗 1–2 公尺），反光板在對側補光（白色面柔、銀色面亮），LED 從後側當輪廓光；白天靠窗拍，晚上 LED 隔白床單或柔光布當主光、窗外路燈當背景
- 手機：鎖定曝光與對焦（長按畫面），手動白平衡，關閉自動 HDR 與美顏，4K 30 或 24，慢動作用 60／120。部分機型可錄 Log（看機型）；錄不了就用最平的風格並降一點對比
- 不要讓人臉離背景牆太近（至少 1.5 公尺），否則影子打到牆上、背景也跟著亮

### 8 拍給後製用（影片）
- 曝光：寧可欠 1/3–2/3 檔也不要爆白，亮部爆掉救不回、暗部抬得回；開啟斑馬紋（zebra）設 95–100% 看爆白，膚色在波形圖的位置依膚色深淺不同：淺膚色約 55–70 IRE、中等 45–60、深膚色 35–50（Log 檔案整體再低，依廠牌）；跨膚色通用的判準是向量示波器的膚色線（第三節 13），波形圖只用來看有沒有爆白或死黑
- 白平衡鎖定：手動 K 值，一場一個值，不要自動；後製統一比較容易
- 快門 180° 規則：快門速度 ＝ 1／（2×幀率）。24p 用 1/48（或 1/50）、30p 用 1/60、60p 用 1/120；太快的快門會讓動作像停格
- 幀率：敘事 24／25，正常速度上社群 30，要慢動作拍 60 或 120（`footage.py slowmo` 不加 `--interp` 時輸出 fps ÷ 倍率：60 ÷ 2、120 ÷ 4 都是 30fps 的真慢動作，每格都是實拍格；60 ÷ 4 = 15 低於 24，程式補到 24fps、部分格重複，見第三節 12）
- Log 或平坦風格：動態範圍多 1–2 檔，代價是暗部雜訊多、8-bit 容易色帶（banding）、一定要調色才能用；能選 10-bit 就選；Log 常見建議是比正常多曝 0.7–2 檔（依廠牌，照廠商給的值），把暗部雜訊壓下去
- 解析度與裁切餘裕：交付 1080 就拍 4K，穩定、重新構圖各要 5–15% 的裁切空間
- 構圖：字幕區（下方 15%）與社群介面遮擋區不放臉；人像留天頭、不切關節
- 每個鏡頭前後各留 3 秒，剪接與穩定（需要前後格）才有料
- 拍乾淨的空鏡：天空、街景、紋理、空椅，各 5–10 秒，做轉場與蓋瑕疵用

### 9 拍照同理
- RAW：白平衡與曝光可以後改，JPEG 不行
- 曝光包圍（bracketing）：高反差場景拍 −1／0／+1 EV，後製選或合成
- 眼神光（catchlight）：主光要在眼睛裡反射出亮點，位置約 10 點或 2 點鐘方向；沒有眼神光的臉像沒有生命
- 背景距離：人離背景 2–3 公尺，背景比臉暗 1–2 檔，淺景深自然分離

### 10 參考
- Blain Brown《Cinematography: Theory and Practice》（打光章節）；Ansel Adams 的 Zone System（曝光區間思考，拍照與波形圖判讀通用）

## 二、後製重新打光（relighting in post）

全部用 ffmpeg 實測。基本原理：做一張「光圖」（0–255 的灰階或彩色漸層），先用 multiply 乘上原圖的亮度、再 screen 疊回畫面：黑位不動、本來有反射的地方才被打亮（光 ∝ 反射率）。光圖直接 screen 會把黑背景一律抬成灰（實測見表第 1 列與第九節）；multiply 單獨用是壓暗。光圖只產生一次（PNG）再 `-loop 1` 疊，比每格跑 geq 快 5–7 倍。
- 一鍵版：`footage.py relight IN -o OUT [--key X,Y,R,強度] [--fill 強度] [--rim 方向,強度] [--temp 偏移] [--vignette 0-1] [--mode masked|screen|gain] [--light-out light.png]`；key 與 vignette 可單獨用；預設 `masked`（乘亮度再 screen），光圖寫在暫存目錄、完成後刪除，要檢查加 `--light-out`。例：`footage.py relight in.mp4 -o out/in_relit.mp4 --key 0.42,0.4,0.14,0.6 --fill 0.15 --rim right,0.35 --temp -600 --vignette 0.5`
- 白光會沖淡膚色：screen 疊中性白光（masked 或 screen 模式）等於把畫素往白色推，臉頰 R/G 一定下降（本文測試臉、臉頰 160×120 區：原片 1.40 → key 0.6 單獨 1.25、key 0.3 單獨 1.32、上面那個範例全套 1.29）。修前修後 R/G 降超過 0.1 就是光太白太強：先把強度降到 ≤ 0.3；要完全保住膚色比例改 `--mode gain`（輸出 ＝ 原圖 × (1 + 光圖)，三個色版等比放大：暗臉 `dim.mp4` 臉頰 1.61 → 1.60（key 0.4）、1.60（key 0.6）），代價是亮部先爆 R（key 0.6 時亮點 R 252、R/G 1.43 → 1.32；0.4 時 R 241、1.43 不變），只給臉頰 Y < 140 的偏暗素材、強度 ≤ 0.4、跑完量 YMAX < 250，亮臉（Y > 160）用 gain 比 screen 更糟（1.40 → 1.19）。打完再補救的效果都小：`--temp -600` 拉回 0.05（背景一起變暖、眼白 G/B 1.05）、`selectivecolor=reds=-0.15 0 0.1 0` 0.03、`vibrance=intensity=0.3` 0.10 但背景也一起加飽和
- `--key` 的第三個數 R 以高斯 σ 解釋（佔畫寬比），不是硬邊半徑：光斑看得見的範圍約 2σ、強度在 σ 處剩 61%；特寫 0.1–0.15、半身 0.15–0.25。0.28 等於 σ 358 px，光會鋪滿整張 720p
- `--fill` 是均勻加光（0–1，程式內部乘 0.35 寫進光圖）。預設 masked 模式下光圖先乘原圖亮度，所以亮的地方被提得多、黑位幾乎不動（實測 `--fill 1`：暗角 Y 20 → 27、臉頰 167 → 187），它不是「提亮暗部」；要抬暗部用 `--mode screen`（同一組 `--fill 1`：暗角 20 → 103、整張灰掉）或 `eq=brightness`

| # | 何時用 | 配方 | 量級 | 過頭的徵兆 |
|---|---|---|---|---|
| 1 | 徑向漸層當虛擬主光：臉太平、想補一盞側上方的光 | 下方 R1 | 強度 0.3–0.6、σ 0.1–0.25 倍畫寬（光斑範圍約 2σ） | 光圈邊緣看得見；膚色 R/G 比修前降 > 0.1（白光沖淡：R1 強度 0.6 臉頰 1.40 → 1.25，降強度到 0.3 → 1.32，或暗臉改 `--mode gain`，見表上方）；背景黑位被抬成灰只有直接 screen 才會（R1 先乘亮度就不會：實測 YLOW 33 → 33，直接 screen → 36、左上背景 52 → 62） |
| 2 | 線性漸層做窗光、單側方向光 | 下方 R2 | opacity 0.4–0.7，色用 0xFFE2B0 暖或 0xB0C8FF 冷 | 一半臉變色、鼻影方向跟漸層打架 |
| 3 | 暈影：邊角壓暗引導視線 | `vignette=angle=PI/6`（R3） | angle PI/8 角落剩約 70–75%、PI/6 約 55–60%、PI/5 約 42–46%、PI/4 約 23–28%、PI/3 幾乎全黑（白圖 1280×720、左上角 40×40 平均 ÷ 中央 40×40 平均，第一格；兩輪獨立重量差 1–3 個百分點） | 四角發黑像望遠鏡 |
| 4 | 背景壓暗、主體提亮（亮度遮罩） | 下方 R4 | 先量 SRC 的 YLOW：壓暗量上限 (YLOW−20)/255，從它的七成起跳（YLOW 33 的片 → −0.03～−0.04；eq 的 brightness 壓掉的級數比 ×255 多一到兩成）；跑完量 YLOW ≥ 20 才再加。提亮 +0.03～+0.08 | 主體邊緣有亮暈、暗髮被當成背景、背景塌成全黑（YLOW < 20） |
| 5 | 光漏（light leak）：回憶、夢、副歌進場 | 下方 R5（快） | opacity 0.5–0.8、移動 150–300 px/s | 整段都在漏、顏色蓋過膚色 |
| 6 | 霧化與柔光 | anime.md〈實拍 5〉（gblur 25 + screen 0.6） | opacity 0.3–0.6 | 皮膚沒有毛孔、眼睛失焦 |
| 7 | 色溫重設 | `colortemperature=temperature=6000:pl=1`（R6） | 每次 ±300–800K（6500 → 5700–6200 變暖、7300–8500 變冷）；`pl=1` 保持亮度。跑完量臉頰 R/G：超過 1.45 就退回；原片膚色已在 1.4 附近（本文測試臉 1.40）幾乎沒有變暖的餘地，改只給背景變暖（R2 或 R7）。0x808080 灰卡實測：3200K → U 103／V 152、5000K → 121／135、6500K → 127／129、9000K → 137／124 | 眼白、牙齒跟著變黃或變藍（實測眼白：4500K → RGB 253/234/199，7500K → 230/233/249、B 高於 R）；膚色 R/G > 1.5（4500K → 1.65） |
| 8 | 選區調色：只動膚色或天空 | 下方 R7 | 每個數值 ±0.05–0.15 | 膚色邊緣出現色塊、嘴唇變紫 |
| 9 | 日轉夜（day-for-night）；只用在白天亮素材（原片 YLOW ≥ 40） | 下方 R8 | 亮度 −0.2～−0.3、飽和 0.5–0.7、往藍 0.15–0.2。跑完量 YLOW ≥ 20，不夠先把 curves 黑點 `0/0` 改 `0/0.03`（testsrc2 原片 YLOW 41：R8 → 27，改黑點 → 30），再把 brightness 從 −0.25 收到 −0.15（→ 32）。本文的暗測試片（YLOW 33、背景 Y 44）套 R8 背景直接塌成 Y 0、YLOW 16，收到 −0.15 還是 16、改黑點 19，怎麼收都不到 20：原片本來就暗的不要用這條 | 天空還是白的、影子方向像中午、背景塌成全黑（YLOW < 20） |

```bash
# R1 徑向主光：高斯光圖用 lavfi 產生（中心 (538,288)、σ 180px ≈ 0.14 倍畫寬、強度 0.6），先乘原圖亮度再 screen
ffmpeg -i in.mp4 -f lavfi -i "color=black:s=1280x720,format=gray,geq=lum='255*0.6*exp(-((X-538)^2+(Y-288)^2)/(2*180^2))'" \
  -filter_complex "[0]format=gbrp,split=2[a][a2];[a2]format=gray,format=gbrp[lum];[1]format=gbrp[b];[lum][b]blend=all_mode=multiply:shortest=1[b2];[a][b2]blend=all_mode=screen,format=yuv420p" out.mp4
# 直接 screen（會抬黑位，背景本來就不黑時才用）：-filter_complex "[0]format=gbrp[a];[1]format=gbrp[b];[a][b]blend=all_mode=screen:shortest=1,format=yuv420p"

# R2 線性漸層窗光：左側暖光，opacity 0.7
ffmpeg -i in.mp4 -f lavfi -i "color=0xFFE2B0:s=1280x720,format=gbrp,geq=r='r(X,Y)*clip(1-X/W*1.4,0,1)':g='g(X,Y)*clip(1-X/W*1.4,0,1)':b='b(X,Y)*clip(1-X/W*1.4,0,1)'" \
  -filter_complex "[0]format=gbrp[a];[1]format=gbrp[b];[a][b]blend=all_mode=screen:all_opacity=0.7:shortest=1,format=yuv420p" out.mp4
# （R2 是直接 screen，漸層那一側的黑位會抬；要保黑位就照 R1 先把漸層乘上亮度再 screen）

# R3 暈影
ffmpeg -i in.mp4 -vf "vignette=angle=PI/6" out.mp4

# R4 背景壓暗、主體提亮：lumakey 抓亮部做遮罩（主體比背景亮時），羽化後 maskedmerge
# lumakey 是把抓到的亮部變「透明」，alphaextract 後主體是黑、背景是白，一定要 negate 主體才會拿到 [bright]（漏掉就反過來：實測臉頰 167 → 154、背景 46 → 60）
# threshold 0.7、tolerance 0.3 抓 Y 0.4–1.0 的主體，softness 0.15 往下漸變到 0.25；原本的 0.9:0.6:0.3 會把 Y 0.2 的背景也抓進一半
# 壓暗 -0.04 是給背景已暗（YLOW 30 左右）的片：實測 YLOW 33 的片 -0.03 → 24、-0.04 → 22、-0.05 → 17、-0.08 → 12（後兩個低於第六節的 20 門檻）；跑完量 YLOW ≥ 20 才再加
ffmpeg -i in.mp4 -filter_complex "[0]split=3[a][b][c];[a]format=yuva420p,lumakey=threshold=0.7:tolerance=0.3:softness=0.15,alphaextract,negate,gblur=sigma=12,format=yuv420p[m];[b]eq=brightness=-0.04:saturation=0.9[dark];[c]eq=brightness=0.06[bright];[dark][bright][m]maskedmerge" out.mp4

# R5 光漏：先產一張橘色光斑 PNG，再用 overlay 表示式讓它隨時間往左移，最後 screen
ffmpeg -f lavfi -i "color=black:s=900x900,format=gbrp,geq=r='255*0.9*exp(-((X-450)^2+(Y-450)^2)/(2*220^2))':g='255*0.45*exp(-((X-450)^2+(Y-450)^2)/(2*220^2))':b='255*0.15*exp(-((X-450)^2+(Y-450)^2)/(2*220^2))'" -frames:v 1 -update 1 leak.png
ffmpeg -i in.mp4 -loop 1 -i leak.png -filter_complex "color=black:s=1280x720:r=30[bg];[bg][1]overlay=x='W*0.8-200*t-450':y='H*0.2-450':shortest=1,format=gbrp[lm];[0]format=gbrp[v];[v][lm]blend=all_mode=screen:all_opacity=0.8:shortest=1,format=yuv420p" out.mp4
# （每格用 geq 畫移動光斑的寫法也能跑，但 3 秒片要 30 秒；上面這版 4 秒）

# R6 色溫重設（變暖 500K）：測試臉 R/G 1.40 → 1.46（已在上限邊緣；5800 → 1.48、5500 → 1.51、4500 → 1.65）。4500 只給刻意偏橘的風格用，膚色一定超標
ffmpeg -i in.mp4 -vf "colortemperature=temperature=6000:pl=1" out.mp4

# R7 選區調色：膚色（reds／yellows）減青加黃，天空（blues）反向；四個數字是 C M Y K 的增減
ffmpeg -i in.mp4 -vf "selectivecolor=reds=-0.15 0 0.05 0:yellows=-0.1 0 0.1 0:blues=0.1 0 -0.1 0" out.mp4

# R8 日轉夜：壓暗、降飽和、往藍、壓高光、暈影。只給白天亮素材（原片 YLOW ≥ 40）；跑完量 YLOW（第三節 13 的 signalstats），< 20 就把黑點改 0/0.03、brightness 收到 -0.15（表第 9 列有實測值）
ffmpeg -i in.mp4 -vf "eq=brightness=-0.25:contrast=1.15:saturation=0.6,colorbalance=rh=-0.15:bh=0.2:rm=-0.1:bm=0.15,curves=all='0/0 0.5/0.42 1/0.85',vignette=angle=PI/5" out.mp4
```
- 注意 `colorbalance` 在 ffmpeg 6.1 的區段偏暗：`rm/gm/bm`（midtones）對中灰 128 完全沒作用、對 64 左右才動；`rh/gh/bh`（highlights）從約 80 起就動到。整體偏色用 `rh/gh/bh`，暗部用 `rm/gm/bm`（灰卡實測）。要精準移動色度平均值改用 `lutyuv=u=val+10:v=val-10`

## 三、影片精修

順序原則：降噪 → 穩定 → 鏡頭校正 → 一級調色（曝光、白平衡、對比）→ 二級（皮膚、選區）→ 打光 → 銳化 → 顆粒 → 輸出。理由：降噪在穩定前（穩定的插值會把雜訊抹成條紋）、銳化在最後（任何幾何處理都會軟化）、顆粒蓋在銳化之後統一質感。每一步各輸出一檔，加字尾，才能回退。
- 速度量級（本機 4 核、720p、另一工作流同時在跑）：hqdn3d／atadenoise／deflicker／deband／cas 約 1–1.5 倍即時時間；bilateral 約 1.5 倍；vidstab 兩段約 3 倍；skin（含遮罩輸出）約 4–6 倍（6 秒片 28 s，三分鐘片約 14 分鐘，程式會提示）；bm3d 約 6 倍；nlmeans 約 10–25 倍；minterpolate 約 15–25 倍。慢的先 `--preview 10`

### 1 降噪
- `footage.py denoise IN -o OUT --level light|medium|heavy --method hqdn3d|nlmeans|atadenoise`
- 量雜訊：裁一塊靜止平坦區，`signalstats` 的 YDIF（逐格差）除以 1.13 約等於雜訊 σ（實測 σ≈13 的片逐格 YDIF 12.4–12.6，÷1.13 ≈ 11，低估一到兩成，當量級看）。片裡有重複格（照片做的片、掉格）時那幾格 YDIF=0，略過不要平均進去（平均進去會變 9）
```bash
ffmpeg -t 2 -i in.mp4 -vf "crop=200:200:40:40,signalstats,metadata=print" -f null - 2>&1 | grep -oE 'YDIF=[0-9.]+'
```
- 以 σ≈13 的 720p 平坦臉場景實測 PSNR（對乾淨原圖，原始 27.1 dB）：

| 濾鏡 | 選項 | PSNR | 2 秒片耗時 | 說明 |
|---|---|---|---|---|
| hqdn3d | `4:3:6:4.5`（light） | 27.3 | 3 s | 空間＋時間，快，保守 |
| hqdn3d | `8:6:12:9`（medium） | 28.5 | 3 s | 預設 |
| hqdn3d | `12:9:20:15`（heavy） | 30.6 | 3 s | 開始糊細節 |
| atadenoise | `0a=0.08:0b=0.16…:s=15`（medium） | 28.5 | 3 s | 純時間域，靜態場景用，會動的東西會拖影 |
| atadenoise | `0a=0.15:0b=0.3…:s=33`（heavy） | 33.0 | 3 s | 門檻 a≈2σ/255、b≈4σ/255 |
| nlmeans | `s=4:p=7:r=11` | 27.4 | 26 s | s 低於 σ 的一半幾乎沒效 |
| nlmeans | `s=6:p=7:r=11`（medium） | 38.4 | 28 s | 乾淨、毛孔仍在，MV 特寫用這個 |
| nlmeans | `s=10:p=7:r=15`（heavy） | 45.7 | 50 s | 很慢 |
| bm3d | `sigma=20` | 30.1 | 12 s | 不如 nlmeans |
| dctdnoiz | `sigma=8` | 24.4 | 22 s | 比不處理還糊，不用 |

### 2 穩定
- `footage.py stabilize IN -o OUT [--strength 1-3] [--zoom 0-10] [--lock] [--report] [--keep-trf]`：vidstab 兩段式，先 `vidstabdetect` 寫 transforms 檔，再 `vidstabtransform`；`--report` 用 detect 再量一次輸出，印前後逐格位移。transforms 檔預設寫在暫存目錄、完成後刪除；要調 smoothing 重跑第二段就加 `--keep-trf`（存成 OUT.trf，下面手動指令的 in.trf）
```bash
ffmpeg -i in.mp4 -vf "vidstabdetect=shakiness=6:accuracy=15:stepsize=6:result=in.trf" -f null -
ffmpeg -i in.mp4 -vf "vidstabtransform=input=in.trf:smoothing=20:zoom=5:optzoom=0:crop=keep:interpol=bicubic" out.mp4
# 一段式（快但弱）
ffmpeg -i in.mp4 -vf "deshake=rx=48:ry=48:edge=mirror:blocksize=8" out.mp4
```
- 實測（靜態場景＋慢漂移＋高頻抖動，逐格位移平均 5.1 px、連續格 PSNR 29.2 dB）：smoothing=20 → 1.2 px／35.8 dB；smoothing=30 → 1.1 px；smoothing=0（`--lock`，固定機位）→ 0.2 px／39.3 dB；deshake → 1.7 px／33.1 dB
- `smoothing` 越大越像滑軌但需要更多放大；0 把所有位移抵銷，只適合固定機位。`--zoom` 是放大百分比避免黑邊，detect 之後程式會印「最大位移佔畫寬幾 %」提示該放大多少；`crop=keep` 用邊緣畫素補洞、`crop=black` 露黑邊讓你看得見
- 裁切放大的取捨：放大 5% 損失約 10% 畫面與一點銳度；大於 10% 先考慮換素材。畫面裡有大面積移動物（人走過鏡頭前）時偵測會跟著物體跑，用 `tripod` 或 `--lock` 也救不了，改手動 keyframe 或換鏡頭

### 3 去閃爍
- `footage.py deflicker IN -o OUT`（`deflicker=size=10:mode=am`）。實測亮度每秒抖 4 次、幅度 ±0.12 的片：逐格 YAVG 標準差 21.5 → 5.6（乾淨片 0.4）
- 適合日光燈頻閃、縮時曝光跳動；畫面本來就有閃燈效果（頻閃對拍）不要用

### 4 鏡頭變形
```bash
ffmpeg -i in.mp4 -vf "lenscorrection=k1=-0.12:k2=0.02:i=bilinear" out.mp4
```
- k1 負值修桶狀（廣角、運動相機），正值修枕狀；每次調 0.02，看直線（門框、地平線）直了就停。會露黑邊，之後 `crop` 或 `scale` 補

### 5 去色帶
```bash
ffmpeg -i in.mp4 -vf "deband=1thr=0.03:2thr=0.03:3thr=0.03:range=24:blur=1" -crf 14 out.mp4
```
- 用在天空、牆面、Log 轉出來的漸層。實測一段 crf 40 壓出來的漸層：全畫面 Y 水平相鄰畫素差 ≥ 2 的比例約放大 4–5 倍（第 0／1／2 秒各一格：0.41–0.42% → 1.99–2.02%；階梯被打散成微顆粒，絕對值依取樣格與量法會變）。之後輸出 crf 要低（≤ 16），否則再壓一次又回來
- 過頭：細節邊緣變糊、門檻超過 0.05 就會吃掉真的細線

### 6 銳化（放最後）
- `footage.py sharpen IN -o OUT --amount 0.5`（`cas=strength=0.5`，對比自適應銳化，影片與照片皆可）
- 實測同一張 8-bit 臉（`face8.png`；雜訊量 ＝ 平坦背景 100×100 區對高斯 σ1 模糊的殘差標準差）：原圖 4.1 → `cas=0.6` 6.8（約 +65%）、`cas=0.4` 6.0（+45%）、`unsharp=5:5:1.2` 8.7（×2.1）；臉上緣的邊緣過衝（該區最大值）200 → cas 205、unsharp 245。兩者都會放大雜訊，cas 少三成、邊緣幾乎不過衝，所以預設用 cas；unsharp 只在要「假銳」的風格用
- 16-bit PNG（`identify` 顯示 16-bit，ffmpeg 讀成 rgba64）直接丟進 `unsharp` 幾乎不動作：ffmpeg 自動轉成 yuva444p16le 後輸出對原圖 PSNR 65 dB、背景雜訊 4.9 → 4.9；先 `format=rgb24,unsharp=5:5:1.2` 才是真的有銳化（PSNR 33 dB）。`cas` 對 16-bit 直接有效（36.3 dB，與先轉 rgb24 的 36.3 相同），`footage.py sharpen` 不用管位深
- 過頭：毛孔變成黑點、髮絲有白邊、雜訊像砂紙。amount 0.3–0.5 就夠

### 7 皮膚（柔膚但保留毛孔）
- `footage.py skin IN -o OUT --strength 0.5 --mask-out mask.mp4`。正常範圍 0.3–0.5；> 0.7 髮際線、眉毛旁會滲出陰影（程式會提示，證據見下方實測）。做法：
  1. 膚色遮罩：輸入先 `gblur=sigma=3`（畫素雜訊會讓單一畫素的 Cb／Cr 跳出窗外，遮罩變成破洞：臉頰區遮罩平均 55 → 169，上限 180），再用 geq 算 YCbCr 三角窗 `Cr 155±30、Cb 106±20、Y 40–245` 得到軟遮罩；另外把遮罩二值化（> 32）、`erosion` 三次收 3 px、乘回軟遮罩——只在皮膚／非皮膚的硬邊界（髮際線、背景）收邊，斑塊造成的遮罩凹陷不受影響；最後羽化 σ4、`mergeplanes` 複製到三平面。可調範圍：Cr 中心 145–160、寬 20–35；Cb 中心 100–115、寬 15–25；亮度下限依膚色深淺 30–60
  2. 頻率分離：低頻 ＝ `gblur=sigma=3`；高頻 ＝ 原圖 − 低頻（`blend=all_mode=grainextract`，結果以 128 為中心）；低頻用 `bilateral`（保邊）抹平斑塊，σS 15→40、σR 0.06→0.10 隨強度；合回 ＝ 低頻' ＋ 高頻（`blend=all_mode=grainmerge`）。ffmpeg 的 bilateral 色差權重是指數型 exp(−|Δ|/(σR·255))，所以 σR 決定髮際線的暗部會不會被拉進額頭（0.22 明顯滲、≤ 0.10 幾乎沒有），σS 只決定抹得平多大的斑塊；只壓 σS 不壓 σR 沒有用
  3. `maskedmerge` 只在遮罩內換成合回的結果
```bash
# 遮罩（看 --mask-out 的輸出：只有皮膚是白的，眼白、牙齒、背景要是黑的）；照片 0.5 秒
ffmpeg -i in.png -vf "format=yuv444p,gblur=sigma=3,geq=lum='255*clip(1-abs(cr(X,Y)-155)/30,0,1)*clip(1-abs(cb(X,Y)-106)/20,0,1)*between(lum(X,Y),40,245)':cb=128:cr=128,format=gray,split=2[ms][mb];[mb]lut=c0='if(gt(val,32),255,0)',erosion,erosion,erosion[mbe];[ms][mbe]blend=all_mode=multiply,gblur=sigma=4" mask.png
# hsvkey 版遮罩（快，但眼白嘴唇會混進來，適合粗用）：hue 15–30、sat 0.3–0.5、val 0.6–0.95
ffmpeg -i in.png -vf "format=yuva444p,hsvkey=hue=22:sat=0.38:val=0.85:similarity=0.25:blend=0.15,alphaextract,negate" mask_hsv.png
```
- 實測（合成臉 `face.png`：低頻斑塊＋細雜訊當毛孔，臉頰 160×120 區域）：低頻標準差 16.5 → 14.8（0.5）、12.5（1.0）；高頻標準差 5.3 → 5.0（毛孔保留 95%）。遮罩：臉頰 233／255、背景 0、眼睛 18。6 秒 720p 含遮罩輸出約 30–40 秒、照片 0.6 秒
- 沒有新增斑塊的證據（同款臉但無斑塊的 `flatface.png`，額頭 160×100 平坦區的低頻標準差；髮際線正上方是深色背景）：原圖 0.24 → 0.39（0.5）、0.49（1.0）；髮際線下 30 px 帶 0.25 → 0.12、0.40。舊設定（σS 40、σR 0.22、不收邊、不預模糊）同區 0.53（0.5）、1.51（1.0），髮際線帶 2.01——對比拉高後看得到額頭上緣一整圈變暗，就是第六節寫的「髮際線與臉交界有光暈」。σS／σR 掃描（遮罩全開）：額頭 bleed 由 σR 決定（σR 0.08 時 σS 17.5→40 只從 0.38 到 0.43；σR 0.22 時 0.63 → 1.51），斑塊抹平由 σS 決定（σS 40 時 13.6 → 10.7 隨 σR 0.08 → 0.22）
- 膚色遮罩的限制：棕髮、木頭、磚牆、皮沙發會被抓到；斑塊顏色離膚色中心太遠時遮罩在斑塊處會凹下去（遮罩圖看得到灰斑），抹不乾淨就把 Cr／Cb 窗加寬。先看遮罩，有問題就 `crop` 限制範圍或降強度

### 8 眼睛、牙齒細部提亮
```bash
ffmpeg -i in.png -filter_complex "[0]format=yuv444p,split=3[a][b][c];[a]format=yuva444p,lumakey=threshold=1:tolerance=0.12:softness=0.08,alphaextract,negate,gblur=sigma=1.5,split=3[m0][m1][m2];[m0][m1][m2]mergeplanes=0x001020:yuv444p[m];[b]eq=brightness=0.06:saturation=0.7[br];[c][br][m]maskedmerge,format=rgb24" out.png
```
- 亮度遮罩只抓最亮的 12%，提亮 +0.06、降飽和 0.7（去黃）。過頭：眼白發藍、牙齒像瓷磚。影片同一條，把 `format=rgb24` 換成 `format=yuv420p`

### 9 去背
```bash
# 綠幕：chromakey 抓 0x00B140，despill 去綠邊（mix 0.5、expand 0 就是濾鏡預設，寫出來是提醒不要亂加 expand），疊到新背景
ffmpeg -i green.mp4 -i bg.mp4 -filter_complex "[0]format=yuva444p,chromakey=0x00B140:0.12:0.08,despill=type=green:mix=0.5:expand=0[fg];[1][fg]overlay=format=auto,format=yuv420p" out.mp4
# 綠邊還在就收邊：alphaextract 後 erosion 一次收 1 px，再 alphamerge 放回（實測邊緣內縮 2 px；原本沾綠的過渡畫素 RGB 100/108/91 被切掉，新的過渡畫素 110/97/92 是膚色比例）
ffmpeg -i green.mp4 -i bg.mp4 -filter_complex "[0]format=yuva444p,chromakey=0x00B140:0.12:0.08,despill=type=green,split=2[c][d];[d]alphaextract,erosion,erosion[al];[c][al]alphamerge[fg];[1][fg]overlay=format=auto,format=yuv420p" out.mp4
# 非綠幕、背景全程不動、主體會動：backgroundkey
ffmpeg -i in.mp4 -i bg.mp4 -filter_complex "[0]format=yuva420p,backgroundkey=threshold=0.15:similarity=0.3[fg];[1][fg]overlay=format=auto,format=yuv420p" out.mp4
```
- chromakey 的第二個數 similarity 0.08–0.15、第三個 blend 0.05–0.1（blend 0.15 實測連眼白都變二成透明，不要用加大 blend 來壓邊）；綠幕打光要平均、人離綠幕 2 公尺以上才不會沾綠
- despill 的門檻是 G − (R×mix + B×(1−mix)×(1−expand))，超過的部分從 G 扣掉。`expand` 留 0：它連中性色一起扣，眼白牙齒會變粉紅（實測 mix 0.6、expand 0.3：眼白 RGB 244/241/238 → 244/212/238，G/B 0.89，一眼看得出）。`mix` 要大於臉頰的 (G−B)/(R−B)（本文測試臉 0.39），太低連皮膚本身的 G 都被扣、整張偏橘紅（mix 0.3：臉頰 R/G 1.30 → 1.37、眼白不動）；mix 0.4–0.5 臉頰與眼白都不動，臉緣 2 px 欄的 R/G 1.20（沾綠）→ 1.29–1.31（原片皮膚 1.27）。做完用滴管量眼白 G 不低於 B、臉頰 R/G 修前修後差 ≤ 0.03
- backgroundkey 實測：門檻 0.02 時主體前一格的位置會留下殘影輪廓，0.15／0.3 才乾淨；頭髮絲、半透明都做不好。要高品質的非綠幕去背用 AI 工具（本環境未裝，選用、未測）

### 10 兩支片段的顏色匹配
- `footage.py match SRC --ref REF -o OUT`，影片與照片都可。原理：
  1. 兩支都 `format=yuv420p,fps=1,signalstats,metadata=print:file=…` 每秒取樣（照片 `format=yuv444p`），平均 YAVG／UAVG／VAVG／YMIN／YMAX／YLOW／YHIGH／SATAVG。一定先 `format` 成 8-bit：signalstats 用輸入的原生刻度回報，10-bit 影片（Log 素材幾乎都是）報 0–1023、16-bit PNG 報 0–65535，不轉就會算出 lutyuv 位移 −193、−9779 這種數，輸出整張單色或全綠（實測）；程式偵測到位深 > 8 會印提示。JPEG 是全範圍（yuvj），`format=yuv444p` 順便壓成 16–235，跟影片同一把尺
  2. 對比 ＝ REF 的 (YHIGH−YLOW) ÷ SRC 的（用 10%／90% 分位，YMIN／YMAX 常被單一畫素帶偏），限 0.6–1.6；飽和 ＝ REF 的 SATAVG ÷ SRC「去偏色後」的 SATAVG：SATAVG 是色度向量長度 hypot(U−128, V−128) 的平均，SRC 整體偏色時向量被偏色撐長（純偏色片 18.3 對原片 10.5），直接相除會算出 x0.575、把輸出壓到 5.4、比 REF 淡一半，而 Y／U／V 平均值殘差完全看不出來（修正前的版本就是這樣判定通過的）；所以程式先用 `lutyuv=u=val+ΔU:v=val+ΔV` 把 SRC 的 U／V 平均移到 REF 的位置再量一次 SATAVG（18.3 → 10.1）當分母，得到 x1.04。兩個乘法進 `eq=contrast:saturation`（以 128 為軸）
  3. 縮放後剩下的平均值差 ΔY、ΔU、ΔV 用 `lutyuv=y=val+ΔY:u=val+ΔU:v=val+ΔV` 加上去（整數查表，精確）。不用 `eq` 的 brightness：它量化成 1% 一格（每格 2.5 級），灰卡實測 0.0861 只加 19、應加 22，系統性短少 15–30%；也不用 `colorbalance`：權重隨畫素亮度變，中低調素材幾乎不動（第二節末的灰卡實測）。`lutyuv` 三個分量都要寫，沒寫的分量預設是 `clipval`，會被夾到 16–235
  4. 套用後量 OUT 的殘差（OUT−REF）：Y／U／V 平均值任一軸 |Δ| > 3、或 SATAVG |Δ| > 1.5，就把殘差加回位移、飽和倍率乘上 REF/OUT 的 SATAVG 比，從 SRC 再跑一次（最多三次，每次從 SRC 重跑，不會重複壓縮）。四個殘差都在門檻內肉眼分不出；交付前再量一次臉頰 R/G（自檢第 8 條，差 ≤ 0.05）
- 實測（殘差順序 ΔY／ΔU／ΔV／ΔSAT）：故意偏暗偏藍的片（`lutyuv=y=val-22:u=val+10:v=val-8` 做的）一次就到 −1.8／−1.0／−0.7／−0.1，SATAVG 10.4 對 REF 10.5，臉頰 R/G 1.40 對 1.40、G/B 1.32 對 1.27（修正前用 SRC 原始 SATAVG 當分母：x0.575、輸出 SATAVG 5.4、R/G 1.31、G/B 1.17，Y／U／V 殘差卻全部 ≤ 3）；亮度、對比、飽和都偏的片兩次收斂 −0.2／−0.6／−0.5／−0.4，SATAVG 10.1、R/G 1.40；黑位被壓死的暗片（SRC YLOW 1）第一次 ΔY +3.7 → 第二次 −0.3／+0.1／+0.1／−0.2（壓死的黑位補不回來，平均值對上的代價是黑位被抬到 44）；照片（JPEG 對 JPEG）一次 −1.2／−1.0／−1.0／−0.2；10-bit 影片（yuv420p10le）當 SRC 一次 −2.0／−1.9／−1.5／+0.2（R/G 1.41）、16-bit PNG 當 SRC 一次 −0.1／−1.0／−1.0／−0.2。3 秒片一次或兩次都約 5 秒（去偏色多量一次約 +0.5 秒）、6 秒片兩次約 14 秒

### 11 放大
- `footage.py upscale IN -o OUT --size 3840x2160 --method lanczos|spline|placebo`
- 實測照片縮到一半再放大回去對原圖的 PSNR：lanczos 33.96、spline 33.95、bicubic 33.92、bilinear 33.71 dB；差距小，lanczos 略銳、spline 略柔，放大後再 `cas=0.4` 看起來更實但 PSNR 不變
- `libplacebo`（`upscaler=ewa_lanczos`）需要 Vulkan 裝置，本機失敗（未測）；AI 放大工具（Real-ESRGAN 等）未裝，選用、未測

### 12 慢動作補格
- `footage.py slowmo IN -o OUT --factor 2|4 [--interp]`：不加 `--interp` 只有 `setpts=2*PTS`，輸出 fps 看來源：來源 ≥ 48fps（拍 60／120 的片）時輸出 `-r fps÷倍率`（下限 24），每格都是實拍格，是真慢動作（60fps 1 秒 x2 → 30fps 60 格 2.0 秒；120fps x4 → 30fps 120 格 4.0 秒；60fps x4 = 15 低於 24 → 輸出 24fps 96 格、部分格重複）；來源 < 48fps 時保留來源 fps、每格重複（30fps 2 秒 x2 → 30fps 119 格 3.97 秒）。加了 `--interp` 用 `minterpolate=fps=60:mi_mode=mci:mc_mode=aobmc:me_mode=bidir:vsbmc=1` 補中間格再放慢，輸出維持來源 fps
- 副作用（實測快速橫移的主體）：主體邊緣出現拖影與撕裂、背景在主體周圍扭曲；慢速、方向單純的動作才好看。1 秒 720p 要 15–20 秒

### 13 示波器檢查膚色與曝光
```bash
ffmpeg -i in.png -vf "format=yuv444p,vectorscope=mode=color3:graticule=green:flags=name:intensity=0.1,scale=512:512:flags=neighbor" vs.png
ffmpeg -i in.png -vf "format=yuv444p,waveform=mode=column:intensity=0.1:graticule=green:flags=numbers,scale=1280:-1" wf.png
ffmpeg -i in.png -vf "format=yuv444p,signalstats=stat=brng,metadata=print" -f null -   # YMIN/YMAX/YLOW/YHIGH、BRNG=超出 16–235 的比例；format 不能省：16-bit PNG 不轉會報 YLOW=8432 這種 16-bit 刻度的數（影片用 format=yuv420p）
```
- 向量示波器（vectorscope）：膚色應成一團落在 R 與 Yl 之間那條線上（約 11 點鐘方向）；偏向 R 太紅、偏向 Yl／G 偏黃綠、偏向 Mg 偏紫（常見於過度補色）。實測膚色 0xE0AC8B 就落在那條線
- 波形圖（waveform）：臉的亮度帶在 128–180（16–235 刻度）、背景黑位不貼 16、亮部不貼 235；BRNG 大於 1% 代表有爆白或死黑

## 四、照片修圖（ImageMagick 為主）

- 一鍵版：`footage.py photo IN -o OUT [--preset portrait|product|landscape] [--exposure ±EV] [--wb ±K] [--skin 0-1] [--sharpen 0-1] [--max-size 畫素] [--keep-exif]`。管線：convert（`-auto-orient`、`-strip` 去 EXIF 與 GPS、線性光域曝光、S 曲線、飽和）→ ffmpeg（`colortemperature`、第三節 7 的柔膚、`cas`）→ convert（`-quality 92`、`-strip`）。預設去 EXIF；`--keep-exif` 只在 JPEG→JPEG 時把來源 APP1 段原樣寫回（含 GPS，且不轉正）。輸入嵌有 ICC 描述檔（`identify -format '%[profiles]'` 列出 icc）時程式會提示：`-strip` 只丟掉描述檔、不做色彩轉換，Display P3 的手機照片會略偏色，正確做法見下方「輸出」
- 預設值：portrait ＝ S 曲線 2.5、柔膚 0.45、銳化 0.25；product ＝ S 曲線 3、銳化 0.6；landscape ＝ S 曲線 3.5、飽和 +12%、銳化 0.5
```bash
# 讀規格與 EXIF／GPS（交付前一定看一次 GPS 有沒有）
identify -format '%wx%h %m Q%Q %[EXIF:Make] %[EXIF:Model] %[EXIF:GPSLatitude]\n' in.jpg
identify -verbose in.jpg | grep -E 'exif:GPS|Colorspace|Geometry|Quality|icc:'
convert in.jpg -strip out.jpg                                       # 去 EXIF、GPS、ICC；嵌有 Display P3 描述檔的照片要先轉 sRGB 再 strip，見下方「輸出」
# HEIC：`convert -list format` 顯示 HEIC 只能讀（r--）；指令是 convert in.heic out.jpg，本機產不出 HEIC 測試檔，未測
# 曝光與對比
convert in.jpg -level 5%,97%,1.05 out.jpg                           # 黑點、白點、gamma
convert in.jpg -sigmoidal-contrast 3x50% out.jpg                     # S 曲線，3 是強度、50% 是中點；+sigmoidal 反向
convert in.jpg -modulate 105,110,100 out.jpg                         # 亮度、飽和、色相（100 不變）
# 白平衡：分色版乘，或 ffmpeg 色溫處理單張
convert in.jpg -channel R -evaluate multiply 1.06 -channel B -evaluate multiply 0.94 +channel out.jpg
ffmpeg -i in.jpg -vf "colortemperature=temperature=5800:pl=1" -update 1 -q:v 2 out.jpg
# 曲線（ffmpeg curves 處理單張；四點：黑、暗部、亮部、白）
ffmpeg -i in.jpg -vf "curves=all='0/0 0.25/0.22 0.75/0.78 1/1'" -update 1 -q:v 2 out.jpg
# 區域加亮壓暗（dodge & burn）：徑向漸層 screen 提亮中央、multiply 壓暗邊緣
convert in.jpg \( -size 1600x1067 radial-gradient:'#505050-black' \) -compose Screen -composite \( -size 1600x1067 radial-gradient:white-'#808080' \) -compose Multiply -composite out.jpg
# 橢圓遮罩只提亮臉（座標換成臉的位置）
convert in.jpg \( -size 1600x1067 xc:black -fill '#404040' -draw 'ellipse 800,540 260,340 0,360' -blur 0x60 \) -compose Screen -composite out.jpg
# 皮膚（頻率分離）：低頻 -blur、高頻 = 原圖 − 低頻 + 50%、低頻保邊柔化、合回、臉遮罩
convert in.jpg -blur 0x6 low.png
convert in.jpg low.png -compose Mathematics -define compose:args=0,-1,1,0.5 -composite high.png
ffmpeg -i low.png -vf "bilateral=sigmaS=40:sigmaR=0.2" -update 1 low2.png        # IM 的 -selective-blur 0x25+12% 同樣效果要 88 秒，這條 0.5 秒；σR 0.2 在髮際線旁會滲（第三節 7），橢圓遮罩要離髮際線遠一點或改 sigmaR=0.1
convert low2.png high.png -compose Mathematics -define compose:args=0,1,1,-0.5 -composite smooth.png
convert -size 1600x1067 xc:black -fill white -draw 'ellipse 800,540 215,295 0,360' -blur 0x20 mask.png
convert in.jpg smooth.png mask.png -composite out.jpg
# 銳化：-unsharp 半徑x標準差+強度+門檻（門檻 0.02 讓平坦區不被銳化）
convert in.jpg -unsharp 0x1.5+0.8+0.02 out.jpg
# 降噪
convert in.jpg -despeckle out.jpg                                   # 輕、快、只去孤立點
ffmpeg -i in.jpg -vf "nlmeans=s=6:p=7:r=11" -update 1 -q:v 2 out.jpg  # 強，1600px 約 1.5 秒
# 放大與裁切
convert in.jpg -filter Lanczos -resize 200% out.jpg
convert in.jpg -gravity center -crop 1200x800+0+0 +repage -fill none -stroke '#00FF88' -strokewidth 2 -draw 'line 400,0 400,800 line 800,0 800,800 line 0,267 1200,267 line 0,533 1200,533' thirds.jpg   # 三分線輔助，看完再去掉 -draw
# 批次輸出到 out/（原檔不動）；拿掉 -path out/ 才是原地覆寫，那時要先備份
mogrify -path out/ -auto-orient -strip -resize '1200x1200>' -quality 88 -format jpg *.jpg
# 本節的 ffmpeg 指令都在 8-bit JPEG 上測；給 16-bit PNG（convert 從 16-bit 來源存出來的 PNG 也是 16-bit）時 unsharp 幾乎不動作（第三節 6），先 convert -depth 8 或在濾鏡鏈最前面加 format=rgb24
# 輸出（-colorspace sRGB 在 ImageMagick 6 只改標籤、不做 ICC 轉換，這裡拿掉）
convert in.png -strip -quality 90 -sampling-factor 4:2:0 -interlace JPEG out.jpg
# 來源嵌有 Display P3 描述檔（iPhone 常見）：-profile 給目標描述檔會「從嵌入的描述檔轉到 sRGB」再 strip；需要一個 sRGB .icc 檔，本機沒有任何 .icc，這條未測
convert in.jpg -profile /path/sRGB.icc -strip out.jpg
# 直方圖與膚色檢查
convert in.jpg -define histogram:unique-colors=false histogram:hist.png
convert in.jpg -crop 120x120+740+540 +repage -resize 1x1\! -format '%[fx:r*255] %[fx:g*255] %[fx:b*255] R/G=%[fx:r/g] G/B=%[fx:g/b]\n' info:
```
- 實測頻率分離（臉頰 200×150）：低頻標準差 17.7 → 13.9、高頻 10.1 → 9.6；斑塊淡了、毛孔還在
- 自然的檢查：直方圖兩端不貼牆（貼 0 是死黑、貼 255 是爆白）；臉頰平均色 R > G > B，R/G 約 1.15–1.45、G/B 約 1.1–1.4（淺到中等膚色的經驗範圍；深膚色飽和度高、比值會偏大，一樣以向量示波器的膚色線為準）。R/G > 1.5 偏橘紅、G/B < 1.05 偏青藍（眼白會發藍）、G 接近 R 偏綠。實測原圖 1.34／1.25，portrait 預設跑完 1.34／1.34，仍在範圍內

## 五、靜態照片在 MV 裡

- Ken Burns：`footage.py kenburns in.jpg -o out/in_kb.mp4 --dur 4 --from 0.5,0.5,1.0 --to 0.55,0.42,1.3 --size 1920x1080 --fps 30 --ease inOut`。x,y 是視窗中心的 0–1 相對座標、zoom ≥ 1；程式先把照片縮放裁切成輸出比例的 2 倍（抑制 zoompan 的整數抖動）再做緩動推軌。推 1.1–1.3 倍、4–8 秒最自然；超過 1.5 倍會看到畫素
- 2.5D 視差：前景（去背的人或物）與背景（放大 1.2 倍、模糊）分層，用不同速度移動。ffmpeg 最小版（實測）：
```bash
ffmpeg -loop 1 -t 3 -i photo.png -filter_complex "[0]split=2[a][b];[a]scale=1536:864,gblur=sigma=6,crop=1280:720:x='128-40*t':y=72[bg];[b]colorkey=0x1c2230:0.25:0.1[fg];[bg][fg]overlay=x='-20+60*t':y=0,format=yuv420p" -r 30 out.mp4
```
  要做得好（多層、透視、緩動）走 SKILL.md D 段的程式動畫：每層一張 PNG，`render(t)` 依層深用不同位移，再 `scripts/render.py` 輸出
- 照片與實拍混剪的統一：同一條調色鏈（curves＋eq＋colortemperature）、同樣的顆粒（`noise=alls=5:allf=t+u`）、同樣的黑位，套在兩種素材上；再用 `signalstats` 比兩者的 YLOW（10% 分位）差 ≤ 5、膚色 R/G 差 ≤ 0.05
```bash
GRADE="curves=all='0/0.02 0.5/0.5 1/0.96',eq=saturation=0.92,colortemperature=temperature=6000:pl=1,noise=alls=5:allf=t+u"
ffmpeg -i photo_kb.mp4 -vf "$GRADE" a.mp4 && ffmpeg -i live.mp4 -vf "$GRADE" b.mp4
```

## 六、「不過度美化」的判斷準則

| 處理 | 過頭的徵兆 | 回退值 |
|---|---|---|
| 柔膚 | 毛孔消失、臉像塑膠、髮際線與臉交界有光暈（bilateral 把暗髮拉進額頭） | strength 降到 0.3–0.5；看 100% 放大的臉頰，要看得到顆粒；額頭平坦區修前修後低頻標準差上升不超過 0.3 |
| 眼白牙齒 | 眼白發藍或發白到像貼紙、牙齒比眼白亮 | brightness ≤ 0.06、saturation 0.7–0.85 |
| 調色 | 膚色向量離開 R–Yl 線、R/G > 1.5 或 G/B < 1.05 | 先回 `colortemperature` 到中性，再加選區調色 |
| 虛擬打光 | 光圈邊緣看得見、背景黑位抬成灰、鼻影與新光方向相反、膚色 R/G 比修前降 > 0.1（白光 screen 把膚色沖淡：key 0.6 實測 1.40 → 1.25） | 強度 ≤ 0.3（0.3 時 1.40 → 1.32）；臉偏暗（臉頰 Y < 140）改 `--mode gain` 等比增益（1.61 → 1.60，量 YMAX < 250）；黑位被抬是用了 `--mode screen`，改回預設 masked（光圖先乘亮度）；修前修後背景 YLOW 差 ≤ 5 |
| 暈影 | 四角發黑像望遠鏡 | angle ≤ PI/6 |
| 銳化 | 髮絲白邊、雜訊像砂紙 | cas ≤ 0.5；不要用 unsharp |
| 降噪 | 牆面像塑膠、布紋消失、動作拖影（時間域） | 降一級；動的畫面不用 atadenoise |
| 穩定 | 畫面邊緣果凍般扭曲、放大超過 10% | smoothing 降、改 `--lock` 或換素材 |
| 日轉夜 | 天空仍亮、影子像中午 | 天空另外壓（R4 的亮度遮罩）或換黃昏素材 |
| 背景 | 背景被壓到全黑「塌掉」、沒有層次 | 壓暗量 ≤ (原片 YLOW−20)/255，保留 YLOW ≥ 20 |

判斷方法：膚色向量（第三節 13）、100% 放大看毛孔、眼白用滴管看 B 不高於 R、背景 YLOW 不貼 16、修前修後並排看三秒。

## 七、工作流程

1. 接到素材：`ffprobe -v error -show_entries stream=codec_name,width,height,r_frame_rate,pix_fmt,color_transfer -of default=nw=1 in.mp4`、照片 `identify -verbose in.jpg | head -40`；確認 Log／HDR（color_transfer 是 arib-std-b67 或 smpte2084 要先轉 Rec.709）、EXIF 有沒有 GPS
2. 挑最難的一段做 10 秒試跑：每個子命令加 `--preview 10`，輸出到 `./out/`，字尾 `_stab`、`_dn`、`_skin`、`_relit`、`_match`、`_photo`、`_sharp`、`_kb`
3. 拼圖給我看：`ffmpeg -i out/x.mp4 -vf "fps=8/10,scale=320:-1,tile=4x2" -frames:v 1 out/x_sheet.png`，修前修後各一張，加上向量示波器與波形圖。fps 要算成 8 ÷ 片長秒數（10 秒試跑片 8/10、6 秒片 8/6；片長用 `ffprobe -v error -show_entries format=duration -of csv=p=0 out/x.mp4`），`-frames:v 1` 只出一張；寫死 `fps=1/0.75` 配 `-update 1` 的話 4×2 只裝得下 6 秒，10 秒片會產生兩張、`-update 1` 只留最後一張，交出去的拼圖缺前 6 秒（實測 `frame=2`、下排三格全黑）
4. 確認後跑全片；一步一檔，順序照第三節；最後一步統一輸出 H.264 yuv420p faststart（footage.py 預設）
5. 交付前跑第八節自檢，附量測值（位移前後、PSNR 或 YDIF、膚色 R/G、殘差）

## 八、自檢清單

1. 膚色在向量示波器落在 R–Yl 線附近，R/G 在 1.15–1.45？
2. 100% 放大看臉頰，毛孔與髮絲還在？
3. 眼白用滴管量，B 不高於 R、不比牙齒暗？
4. 背景 YLOW ≥ 20、沒有塌成全黑；亮部 YMAX < 250、BRNG < 1%？
5. 虛擬打光的方向與原片的鼻影、眼神光方向一致？
6. 穩定後的片邊緣沒有果凍扭曲、放大 ≤ 10%？
7. 降噪後靜態牆面還有布紋或顆粒，動作沒有拖影？
8. 兩支片段（或照片與實拍）並排，YAVG 差 ≤ 5、SATAVG 差 ≤ 1.5、膚色 R/G 差 ≤ 0.05？
9. 銳化放在最後一步，髮絲沒有白邊？
10. 照片輸出沒有 EXIF／GPS（`identify -verbose | grep -c exif:` 為 0）、色彩空間 sRGB？

## 九、實測紀錄

- 環境：Ubuntu 容器、4 核心、另一個工作流同時在跑（時間偏保守）；ffmpeg 6.1.1、ImageMagick 6.9.12 Q16（無 `magick`、無 exiftool、無 heif-enc）；Python 3 標準函式庫（量測用 numpy／scipy）
- 素材（全部合成，不含真人）：`clip.mp4` testsrc2 1280×720 30fps 6 秒；`skin.mp4`／`face.png` 合成臉（深色漸層背景＋膚色橢圓 0xE0AC8B＋眼睛牙齒＋低頻斑塊＋細雜訊當毛孔）；`dim.mp4` 暗版；`noisy_face.mp4` 乾淨臉＋`noise=alls=20:allf=t`（實測 σ≈13）；`hand_face.mp4` 乾淨臉＋慢漂移＋高頻抖動；`shaky.mp4`／`noisy.mp4`／`flicker.mp4` 依 clip 加 random 裁切／`noise=alls=30`／`eq=brightness=0.12*sin(2πt·4)`；`flatface.png` 同款臉但沒有斑塊（平坦額頭，量柔膚有沒有新增陰影）；`dim2.mp4` 用 `lutyuv=y=val-22:u=val+10:v=val-8` 做的偏暗偏藍片；`photo.jpg` 1600×1067 同款臉，用 Python 手寫 APP1 寫入 Make／Model／GPS；`green.mp4` 綠幕 0x00B140；`banding.mp4` crf 40 漸層；`mover.mp4` 臉橫移
- footage.py 子命令（720p 6 秒，除非另註）：

| 子命令 | 耗時 | 量化結果 |
|---|---|---|
| stabilize（strength 2，含 --report） | 19 s | 逐格位移 5.14 → 1.23 px（−76%），連續格 PSNR 29.2 → 35.8 dB；transforms 檔預設跑完即刪，`--keep-trf` 才留 OUT.trf |
| stabilize --lock | 21 s | 5.14 → 0.22 px（−96%），39.3 dB |
| denoise hqdn3d light／medium／heavy（2 秒） | 3 s | PSNR 27.1 → 27.3／28.5／30.6 dB |
| denoise nlmeans medium（2 秒） | 28 s | 38.4 dB |
| denoise atadenoise medium（2 秒） | 3 s | 28.5 dB |
| sharpen cas 0.6 | 3.8 s（照片 0.25 s） | 放大細部比較見第三節 6 |
| deflicker | 3.2 s | 逐格 YAVG 標準差 21.5 → 5.6 |
| skin 0.5（含遮罩輸出） | 30–40 s（照片 0.6 s） | 臉頰低頻標準差 16.5 → 14.8（1.0 時 12.5）；高頻 5.3 → 5.0；平坦額頭低頻 0.24 → 0.39（1.0 時 0.49；舊設定 0.53／1.51）；遮罩圖只有皮膚是白的 |
| relight key σ0.14＋fill＋rim＋temp＋vignette（3 秒） | 5.6 s | 光圖 1 張 PNG；背景 YLOW 32.9 → 32.7、臉頰 170 → 193、額頭 177 → 198、左上背景 52 → 50（暈影）；膚色（臉頰 160×120 區）R/G 1.40 → 1.29、G/B 1.27 → 1.19，白光沖淡的降幅 0.11 已到第二節的 0.1 門檻（key 0.6 單獨 → 1.25、0.3 → 1.32；暗臉 `dim.mp4` 改 `--mode gain` key 0.4：1.61 → 1.61、亮點 R 241 不爆，key 0.6：1.60 但亮點 R 252；亮臉用 gain 0.6：1.19）。同一組數值改 `--mode screen`：YLOW 50、左上背景 63；舊範例（σ 0.28＋fill＋screen）：YLOW 85、左上背景 105、整張灰掉 |
| match（偏暗偏藍的片對原片） | 4.7 s（3 秒一次，含去偏色量測）／4.9 s（3 秒兩次）／13.7 s（6 秒兩次） | 殘差 ΔY／ΔU／ΔV／ΔSAT 見第三節 10：純偏色片一次 −1.8／−1.0／−0.7／−0.1，SATAVG 10.4 對 REF 10.5、臉頰 R/G 1.40 對 1.40（修正前飽和用原始 SATAVG 相除：x0.575、輸出 SATAVG 5.4、R/G 1.31，Y／U／V 殘差卻通過）；亮度對比飽和都偏的片兩次 −0.2／−0.6／−0.5／−0.4、SATAVG 10.1；黑位壓死的片兩次 −0.3／+0.1／+0.1／−0.2；照片 −1.2／−1.0／−1.0／−0.2；10-bit 片 −2.0／−1.9／−1.5／+0.2；16-bit PNG −0.1／−1.0／−1.0／−0.2（更早的版本這兩種輸出整張單色，見第三節 10） |
| photo portrait（+0.3EV、−500K） | 1.4 s | 輸出 exif 標籤 0 個；--keep-exif 寫回 226 bytes（Make、GPS 都在） |
| kenburns 4 秒 1280×720 | 2.7 s | 120 格、30fps、終點放大 1.3 位置正確 |
| upscale lanczos 2 秒→1080p | 2.7 s | 放大濾鏡 PSNR 見第三節 11 |
| upscale placebo | — | 無 Vulkan，印出改用 lanczos 的錯誤訊息 |
| slowmo x2（30fps 2 秒）／x2 --interp（60fps 1 秒） | 1.3 s／14.5 s | 30fps 來源：時長 3.97 s、119 格、30fps（重複格）；--interp：1.95 s、117 格、60fps。來源 ≥ 48fps 不重複格：60fps 1 秒 x2 → 30fps 60 格 2.0 s、120fps x4 → 30fps 120 格 4.0 s、60fps x4 → 24fps 96 格 4.0 s（15 低於 24，補到 24）、25fps x2 → 25fps 49 格 |

- 第二節配方（3 秒 720p）：R1 乘亮度版 7.8 s（直接 screen 版 6.9 s）：YLOW 33 → 33、臉頰 170 → 191、左上背景 52 → 54（直接 screen：36／199／62）；R2 9.9 s（彩色 geq 每格算）、R3 2.9 s；R4 3.5 s（壓暗 −0.04）：臉頰 167 → 180、左上背景 46 → 33、YLOW 33 → 22（−0.03 → 24；−0.05 → 17、−0.08 → 12 低於門檻；−0.12 → 2 塌掉；沒有 negate 的舊版整個反過來：臉頰 167 → 154、左上背景 46 → 60）、R5 每格 geq 版 29.8 s → PNG＋overlay 版 4.0 s、R6 3.3 s（6000K 臉頰 R/G 1.40 → 1.46、G/B 1.27 → 1.32；5800 → 1.48／1.33、5500 → 1.51、4500 → 1.65／1.47、7500 → 1.38 但眼白 B 高於 R）、R7 3.2 s、R8 3.9 s（暗測試片 YLOW 33 → 16、左上與天空區 Y 0，brightness 收到 −0.15 仍 16、curves 黑點 0/0.03 → 19；亮片 testsrc2 YLOW 41 → 27、黑點 0/0.03 → 30、再收 brightness −0.15 → 32）；`colortemperature` 0x808080 灰卡（64×64 一格，signalstats）：3200K → U 103／V 152，5000K → 121／135，6500K → 127／129，8000K → 135／125，9000K → 137／124，不加濾鏡 128／128；`vignette` 白圖 1280×720 左上角 40×40 ÷ 中央 40×40：PI/8 72.7%、PI/6 55.7%、PI/5 41.7%、PI/4 22.7%、PI/3 1.3%（另一輪 74.5／58.7／45.7／27.9，差在取樣區域，所以正文寫範圍）；`colorbalance` 灰卡 0x808080：rm/gm/bm/rs ±0.2 無變化，rh=0.2 → V +16、U −6、Y +9；0x404040：rm=0.2 → V +16
- 第三節配方：lenscorrection 1.8 s／2 秒；deband 0.8 s／3 秒，全畫面 Y 水平相鄰差 ≥ 2 比例 0.41–0.42% → 1.99–2.02%（×4.8–4.9，第 0／1／2 秒各一格；另一輪 0.9% → 4.4% 與 1.17% → 4.57%，倍率一致、絕對值不同）；眼白提亮 0.3 s（照片）；chromakey＋despill 3.2 s／3 秒（mix 0.5、expand 0：眼白 244/241/238 不動、臉頰 R/G 1.30 不動、臉緣 2 px 欄 R/G 1.20 → 1.29；mix 0.6＋expand 0.3：眼白 G 241 → 212；mix 0.3：臉頰 R/G → 1.37；alphaextract＋erosion×2＋alphamerge 4.1 s）；backgroundkey 2.7 s／3 秒（0.02 殘影、0.15 乾淨）；顆粒 2.1 s／2 秒；minterpolate 快速橫移 1 秒 20.6 s，邊緣拖影；放大 PSNR lanczos 33.96／spline 33.95／bicubic 33.92／bilinear 33.71；vectorscope／waveform 各 0.25 s；雜訊估計：逐格 YDIF 12.4–12.6、÷1.13 ≈ 11（真值 ≈ 13；該片 60 格裡 11 格是重複格 YDIF=0，連零一起平均才會得到 9）；濾鏡單跑 3 秒：bilateral 0.9 s、gblur 0.6 s、smartblur 1.0 s、median 2.5 s、hqdn3d 0.5 s、atadenoise 0.5 s、cas 0.8 s、deflicker 0.4 s、deband 0.6 s、unsharp 0.5 s；2 秒：nlmeans p7r15 48 s、p5r9 18 s、bm3d 15 s、dctdnoiz 22 s、minterpolate 60fps 51 s
- 第四節配方（1600×1067）：identify／strip 0.08 s；level 0.12、sigmoidal 0.08、modulate 0.12；channel 白平衡 0.09、ffmpeg 色溫 0.17、curves 0.18；dodge & burn 0.14、橢圓遮罩 1.15（blur 0x60）；頻率分離 blur 0.6＋高頻 0.3＋bilateral 0.5＋合回 0.3＋遮罩合成 0.3（IM `-selective-blur 0x25+12%` 88.6 s、`0x10+10%` 18.5 s，棄用）；unsharp 0.28、despeckle 0.56、nlmeans 單張 1.5；resize 200% 0.37、三分線 0.08、mogrify 兩張 0.22、輸出 0.09、直方圖 0.05；膚色 R/G／G/B：原圖 1.34／1.25、portrait 1.34／1.34、頻率分離 1.34／1.25、日轉夜 1.13／0.88（刻意偏藍）
- 第五節：parallax 3.2 s／3 秒；統一調色鏈 kenburns 4 秒 7.2 s、實拍 3 秒 5.0 s；拼圖 0.4 s
- 未測／選用：HEIC 轉檔（只確認 `convert -list format` 為可讀）、libplacebo 放大（無 Vulkan）、AI 放大與 AI 去背（未裝）、Display P3 → sRGB 的 `-profile` 轉換（本機無任何 .icc 檔；photo 子命令的 ICC 提示用手工做的 132 byte 空描述檔測過會觸發）
