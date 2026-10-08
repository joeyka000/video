# 日系動漫剪輯元素與風格

做動漫風片頭、MV、MAD、紀錄片的日系段落時讀這份。
- 程式動畫效果：`assets/anime-fx.js`（`AFX.*`，全部是 t 的純函式）
- 示範頁：`assets/anime-demo.html`，用 `scripts/render.py` 輸出
- **Python seek(t) 引擎（實拍＋特效）**：`scripts/animefx.py`——`cel`（實拍轉賽璐璐）、`speed_lines`、`streaks`、`impact`、`flash_at`、`shake`、`sunburst`、`sparkles`、`god_rays`、`para`、`lightning`、`particles`（ember／bubble／leaf／dust／cloud／confetti／heart／spark）、`outline_sprite`／`karaoke`（動畫 OP 字幕）、`tag_sprite`（膠囊標籤）、`slam`、`cut_in`、`dialog_box`（遊戲對話框）、`ball`／`ball_wipe`／`capture_burst`／`wobble`（收服用的球、球形轉場）、`evolution`（白色剪影交替閃）、`gloom`／`sweat_sprite`（漫畫搞笑）。`python scripts/animefx.py demo 一張圖.jpg -o qa/demo.jpg` 出每個效果一格的對照表。用法範例：寶可夢峇里島動漫版（`projects/pokemon/work/engine_anime.py`，不進 git）
- 實拍素材：用下面的 ffmpeg 做法（都實測過）
- 本文保留日文術語原文（画面動、セル画調、作画MAD、10か条），其中的日文漢字 `画`／`条` 會被 OpenCC s2twp 檢查誤報成簡體；檢查本文時排除含這些詞的列：`/root/video-lab/.venv/bin/python -c "import opencc,re,sys; c=opencc.OpenCC('s2twp'); s='\n'.join(l for l in open(sys.argv[1]).read().split('\n') if not re.search('画面動|セル画|作画|か条', l)); print('OK' if c.convert(s)==s else 'HAS_SIMPLIFIED')" references/anime.md`

## 一、演出手法（術語對照）

| 日文術語 | 中文 | 是什麼、何時用 | 程式動畫 | 實拍（ffmpeg） |
|---|---|---|---|---|
| 集中線 | 集中線 | 從畫面外往主體收的放射線，強調「就是這個」、驚訝、登場 | `AFX.speedLines` | 用程式動畫做透明疊層 |
| 流線 | 速度線 | 水平或斜向的線條，高速移動、衝刺 | `AFX.streaks` | 同上 |
| 画面動 | 畫面震動 | 整個畫面抖動，爆炸、落地、重擊、拍點 | `AFX.shake` | 見〈實拍 3〉 |
| インパクトフレーム | 衝擊格 | 2–4 格高反差黑白反轉，出拳、爆點、重拍 | `AFX.impactFrame` | 見〈實拍 4〉 |
| フラッシュ（白フラ） | 白閃 | 一瞬全白，轉場、拍點、回憶切入 | `AFX.flash` | 見〈實拍 6〉 |
| 透過光（T光） | 透過光 | 光點加十字星芒，刀光、眼神光、水面反光、星空 | `AFX.tokaLight` | 柔光見〈實拍 5〉 |
| キラキラ | 閃爍星點 | 四角星閃動，可愛、驚喜、回憶 | `AFX.sparkles` | 用程式動畫做透明疊層 |
| パラ | 漸層覆蓋 | 畫面疊一層漸層，營造空氣感、時段（黃昏、夜） | `AFX.para` | 見〈實拍 9〉 |
| 止め絵 | 停格繪 | 動作中突然停成一張圖，情緒高點、關鍵瞬間（出崎統的招牌） | 停住 t | 見〈實拍 2〉 |
| 3回PAN | 三連 PAN | 同一張圖切三次、每次換方向或放大，強化印象（出崎演出） | `AFX.sanKaiPan` | 用 `zoompan` 分三段，段間硬切 |
| 2コマ打ち／3コマ打ち | 一拍二／一拍三 | 24fps 下每 2 或 3 格才換一張，手繪動畫的頓挫感 | `AFX.onTwos(t)` | 見〈實拍 1〉 |
| カットイン | 切入 | 斜向色帶從側邊切進來，角色特寫、名字、年份 | `AFX.cutIn` | 實拍放進 drawInside，或疊透明層 |
| サンバースト | 放射背景 | 旋轉的放射色塊，登場、慶祝、搞笑 | `AFX.sunburst` | — |
| 擬音字（オノマトペ） | 狀聲字 | 「ドン」「ゴゴゴ」「ドキドキ」砸進畫面 | `AFX.slam` | 疊透明層 |
| 明朝體字卡 | 明朝體字卡 | 黑底極粗明朝體、大小字混排、橫向壓扁，章節標題、關鍵句（90 年代動畫風） | `AFX.minchoCard` | — |
| 縦書き | 直書標題 | 直排標題逐字出現，日系片名、回憶段 | `AFX.tategaki` | — |
| スクリーントーン | 網點 | 45° 網點，漫畫感、陰影、背景 | `AFX.screentone` | — |
| グリッチ | 撕裂色偏 | 拍點瞬間帶狀錯位加 RGB 分離，電子、MAD | `AFX.tear` | 見〈實拍 7〉 |
| セル画調 | 賽璐璐畫風 | 色階壓縮加描線，實拍轉動畫感 | — | 見〈實拍 8〉；更精緻的做法見參考二 |
| 紙の質感 | 紙紋 | 細顆粒，手作、懷舊 | `AFX.paperTexture` | `noise=alls=12:allf=t` |
| ハーモニー | 和聲處理 | 賽璐璐角色改成背景美術筆觸的停格繪（出崎統） | 用插畫素材做 | — |
| 金田パース／スメア | 金田透視／拖影 | 誇張透視、拖影格，極快動作（金田伊功） | 需要逐格手繪素材 | — |

### 節奏原則
- **緩急**：止め絵、白閃、衝擊格是「標點符號」，用在最重的拍點，不要每拍都用
- **音ハメ**（踩點）：剪點對齊 downbeat（見 SKILL.md C 段），衝擊格和白閃放在重拍
- **強度隨段落**：前奏約 40%、主歌 70%、副歌 100%（awesome 庫 `pound75423-464968` 的規則）
- **不要改原片速度硬湊拍點**，節奏不合就換素材

## 二、實拍素材的 ffmpeg 做法

以下都在 1280×720 30fps 素材上實測過，時間點請依需求調整。

```bash
# 1 2コマ打ち（12fps 手繪感）
ffmpeg -i in.mp4 -vf "fps=12,fps=30" out.mp4

# 2 止め絵：播到 1 秒時停格 1.5 秒
ffmpeg -i in.mp4 -vf "trim=0:1,setpts=PTS-STARTPTS,tpad=stop_mode=clone:stop_duration=1.5" out.mp4

# 3 畫面動：1.0–1.5 秒抖動（先放大 6% 避免露黑邊）
ffmpeg -i in.mp4 -vf "scale=iw*1.06:-2,crop=1280:720:x='(iw-1280)/2+if(between(t,1,1.5),30*(random(1)-0.5),0)':y='(ih-720)/2+if(between(t,1,1.5),30*(random(2)-0.5),0)'" out.mp4

# 4 衝擊格：2.0–2.1 秒黑白反轉高反差
ffmpeg -i in.mp4 -vf "split[a][b];[b]hue=s=0,negate,eq=contrast=4[i];[a][i]overlay=enable='between(t,2,2.1)'" out.mp4

# 5 柔光（透過光感、夢幻、回憶）
ffmpeg -i in.mp4 -vf "split[a][b];[b]gblur=sigma=25,eq=brightness=0.05[g];[a][g]blend=all_mode=screen:all_opacity=0.6" out.mp4

# 6 白閃：每 0.5 秒一次、持續 2 格（實際使用時換成拍點時間）
ffmpeg -i in.mp4 -vf "drawbox=color=white@0.8:t=fill:enable='lt(mod(t,0.5),0.067)'" out.mp4

# 7 RGB 色偏
ffmpeg -i in.mp4 -vf "rgbashift=rh=-10:bh=10" out.mp4

# 8 賽璐璐風：降噪 → 色階壓縮 → 疊描線
ffmpeg -i in.mp4 -vf "split[a][b];[a]hqdn3d=6:6:6:6,lutrgb=r='floor(val/48)*48+24':g='floor(val/48)*48+24':b='floor(val/48)*48+24'[p];[b]edgedetect=low=0.1:high=0.3,negate[e];[p][e]blend=all_mode=multiply" out.mp4

# 9 パラ：上方紫色漸層（尺寸要和素材一致）
ffmpeg -i in.mp4 -f lavfi -i "color=0x3C1E6E:s=1280x720,format=rgba,geq=r='r(X,Y)':g='g(X,Y)':b='b(X,Y)':a='255*0.6*(1-Y/H)'" -filter_complex "[0][1]overlay=shortest=1" out.mp4

# 疊程式動畫透明層（集中線、砸字、カットイン等）
python scripts/render.py fx.html -o out/fx.webm --dur 3 --alpha
ffmpeg -i in.mp4 -c:v libvpx-vp9 -i out/fx.webm -filter_complex "[0][1]overlay" out.mp4
```

## 三、風格方向

| 風格 | 關鍵元素 | 配色與字型 | 參考 |
|---|---|---|---|
| 90 年代賽璐璐（EVA 系） | 明朝體字卡、警告面板、網點、紙紋、一拍二 | 黑、米白、橘、警示紅；Noto Serif TC Black 壓扁 | anime-op `studio/fx.js` 的 `evaCard`、`warnPanel`；`studio/gl.js` 的 Riso-cel 濾鏡 |
| 熱血少年漫 | 集中線、衝擊格、畫面動、擬音字、放射背景 | 高飽和紅黃、黑粗描邊；Noto Sans TC Black | `AFX.speedLines`、`AFX.slam`、`AFX.impactFrame` |
| 新海誠系（光與天空） | 透過光、柔光、パラ、鏡頭光暈、雲與天空、黃昏 | 高明度藍、橘粉黃昏 | 〈實拍 5〉〈實拍 9〉＋`AFX.tokaLight` |
| 日常系（柔和） | 柔光、閃爍星點、手寫感字、粉彩 | 低對比粉彩 | `AFX.sparkles`、〈實拍 5〉 |
| 出崎統式抒情 | 止め絵、3回PAN、透過光、畫面分割 | 厚重陰影、夕陽色 | `AFX.sanKaiPan`、〈實拍 2〉 |
| 迷幻 MAD | 每拍換鏡、白閃、撕裂色偏、萬花筒、hue-rotate、每小節大字 | 彩虹漸層、difference 疊加 | awesome 庫 `pound75423-464968`（規格寫得最完整） |
| 手遊結算演出 | 蓄力、爆發、衝擊波、卡片飛出、數字滾動 | 依稀有度換色（綠→藍→紫→金） | awesome 庫 `op7418-814408` |
| 漫畫分鏡 | 網點、分格、對話方塊、擬音字 | 黑白加單一點綴色 | `AFX.screentone`、`AFX.slam` |

## 四、參考素材位置

- `~/video-lab/refs/anime-op`（[2606156052/Pdoom-video-anime-version](https://github.com/2606156052/Pdoom-video-anime-version)，程式碼 ISC）
  - `studio/gl.js`：實拍轉賽璐璐的 WebGL 濾鏡（Kuwahara 平滑 → XDoG 描線 → 限定色盤 → 45° 網點 → 12fps 線條抖動與套色偏移）。比〈實拍 8〉精緻很多，要做高品質動畫化時參照
  - `studio/fx.js`：集中線、網點、筆刷轉場、明朝體字卡、警告面板、印章
  - `studio/type.js`：卡拉OK 逐字、直書、砸字
  - `STORYBOARD.md`：動畫 OP 的逐鏡分鏡範例（依 BPM 排）
  - `song.mp3`、`studio/frames/`、`studio/img/` 屬原作者或 AI 生成素材，不可使用
- awesome 庫相關 prompt：`pound75423-464968`（迷幻 MAD MV）、`op7418-814408`／`op7418-818226`（手遊演出）、`allforbigfire-029657`（機器人變形合體動畫風 3D）、`ishuagra02-922825`（動畫風對戰預告）、`anduraio-570761`（柔和卡通著色）

## 四之一、實拍動漫版的做法（`animefx.py`，寶可夢峇里島動漫版實測）

- **整支片先轉賽璐璐**（`cel`），不是只在幾個鏡頭加濾鏡；畫風統一了，特效疊上去才像同一個世界。`cel` v1（平滑 4 次、墨線 0.7）在商品特寫上像水彩、包裝圖被抹掉；v2（平滑 2 次、墨線 0.95、原片高頻加回 0.35）包裝字與圖案認得出來。1080×1920 一格 0.6–0.8 秒
- **特效跟著歌詞與段落走**，每個都要說得出為什麼在這一拍：「火の中 水の中…」每個詞一個屬性徽章（砸進來後排成一列）＋該屬性的粒子；戰利品＝收服（球落下、搖三下踩拍、喀、星星、對話框「收服成功」）；戰利品變多＝進化（白色剪影交替閃，白光落在重拍）；段落之間用球形轉場（10 格）
- **強度隨段落**（前奏 40%／主歌 70%／副歌 100%）；衝擊格只放倒帶第一下（2 格），白閃只在重拍
- **實拍要看得到**（峇里島 v1 被退的教訓）：衝擊格用那一格實拍本身反轉；集中線尖端停在主體外圈；放射光中心挖空；對話框、色帶只佔一條
- **自製的元素不碰官方素材**：球、徽章、對話框、星星全部程式畫；不用官方 logo、角色圖、遊戲截圖與遊戲音效。音效也是合成的（`engine_anime.py` 的 `sfx`：whoosh、click、pop、chime、hit、zap、rattle、evo），歌曲音量 0.86＋音效 0.7 再軟限幅
- 字幕：動畫 OP 式卡拉 OK（白字深藍描邊、唱到的變黃）＋日文原句小字在上；這種片的字幕本來就是描邊字，跟 v2 那種實拍質感片的字幕規格（`finish.md`〈六〉）是兩回事

## 五、授權與分寸

- 字型只用 OFL：Noto Sans TC、Noto Serif TC（已裝，明朝體用 Serif）
- **風格可以參考，角色、Logo、作品名、招牌臺詞不可照搬**（例如不要用 NERV 標誌、EVA 片名字樣）
- 動畫原片剪成 MAD 屬二次創作，版權在原權利人；客戶案只用原創或已授權素材
- 擬音字、日文標題用在繁中影片時，確認觀眾看得懂；必要時加中文副標

## 出處

- 出崎統的止め絵、3回PAN、ハーモニー、透過光：[練馬アニメーションサイト](https://animation-nerima.jp/enjoy/kyojin/vol07/)、[このマンガがすごい！WEB](https://konomanga.jp/special/138044-2)、[アニメ！アニメ！氷川竜介](https://animeanime.jp/article/2014/10/21/20560.html)
- 撮影處理（パラ、透過光、画面動、PAN）：[WEBアニメスタイル 撮影講座](https://animestyle.jp/2016/03/07/9837/)、[うさペンの館](https://usapen3.hatenablog.com/entry/2016/12/18/234110)
- 金田系演出與衝擊格：[Animétudes: The Kanada style now](https://animetudes.com/2021/07/09/the-kanada-style-now/)
- MAD 剪輯原則：[あの月を飼う日まで 作画MAD 10か条](https://reme-aniro9.hatenablog.com/entry/2021/04/24/210509)
