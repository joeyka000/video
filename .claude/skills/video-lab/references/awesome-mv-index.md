# awesome 庫 MV／藝術向精選索引

從 `~/video-lab/refs/awesome-opus5-5-videos`（475 支）挑出 29 支與 MV、歌詞動畫、音訊反應、動態字型排印（kinetic typography）、生成／藝術影片、電影感 3D 相關，且 prompt 寫得完整到手法可以遷移的。每支只借「做法」；文案、角色、品牌、歌曲一律換成自己的。

- 原文：`prompts/<slug>.md`；索引：`data/videos.json`（欄位 slug／author／category／tech_tags／prompt／prompt_partial／post_url／skillry_url／added）
- 標「貼文」= `prompt_partial: true`，作者沒公開完整 prompt，只有貼文描述，借概念不借規格
- 標「anime.md 已有」= `references/anime.md` 已列，這裡只補 MV 角度
- 對應工具：`assets/mv-kit.js`（`MV.*`）、`scripts/render.py`（`--samples`、`--sheet`）、`scripts/analyze.py`（`audio.json`）、`scripts/align.py`（`lyrics.json`）
- 用法：查下表拿 slug → `cat prompts/<slug>.md` 讀原文 → 只把「做法」段落改寫進自己的 treatment

## 依需求查詢

| 需求 | 先讀 | 再讀 |
|---|---|---|
| 每拍換鏡、拍點白閃、段落強度 40／70／100% | pound75423-464968 | gandamu-ml-220530 |
| 歌詞不直譯，用典故與隱喻排分鏡 | doubleunplussed-181894 | paranoidamerica-686717 |
| 歌詞大字與字幕交替、構圖預留字位 | anabology-491441 | samaote-124569（一句需求：歌詞對人聲、動畫對拍點） |
| 逐字卡拉OK | 本庫沒有完整 prompt；用 `MV.karaoke` 配 `align.py`，排版看 anabology-491441 | — |
| kick／bass／high 各驅動一個幾何量、breakdown 收 drop 放 | acoramaa-248467 | — |
| 配樂程式合成、剪點全踩拍 | prasenx-693512 | iniyanai-856596 |
| 聲音從畫面推導（亮度→音量） | nathanwilbanks-981110 | — |
| 字型片頭、字形當結構、印刷錯位 | techhalla-498547 | gdgtify-929495 |
| 品牌片規格書（禁止清單、轉場好壞表、品質門檻） | daniel-haida-636937 | brainextends-606193、ik-builds-585923 |
| 資料驅動影片（抓資料→手繪風→合成旋律） | groundcontrol-230877 | — |
| 著色器逐畫素背景、程式樂器 | demitiyageekzen-818523 | zeezomb-726206 |
| 無限縮放（infinite zoom）、深度分層視差 | koldo2k-778767 | kgonia7-746268 |
| 畫素風、粒子池、整數格點 | majidmanzarpour-927543 | op7418-814408 |
| 單一形狀連續變形、彈簧疊加、每拍一事 | twoclipping-402193 | thegrootdev-966114、annacher-433425、verbove-268381 |
| 一鏡到底、物件驅動轉場（iris、flood、液態玻璃） | twoclipping-496100 | daniel-haida-636937 |
| 實拍素材放入程式時間軸、SFX 峰值對齊、-14 LUFS | twoclipping-000267 | twoclipping-496100 |
| 分鏡規格：機位、焦段、色溫、表演弧線、鎖定清單 | alexwtlf-981005 | — |
| 慢而穩的單一連續鏡頭 | jake11moran-414633 | daniel-haida-636937 |
| 子格動態模糊、每拍一格預覽拼圖 | verbove-268381 | brainextends-606193 |
| 卡通描線、手遊結算演出、柔光規則 | op7418-814408 | — |

## 一、MV 與歌詞動畫

### pound75423-464968 — @pound75423（anime.md 已有）
canvas · css｜附圖與歌曲做「迷幻故障系」動畫 MV：Canvas 畫、Playwright 逐格截、ffmpeg 合音，1280×720 30fps。
- 先分析 BPM、第一拍、小節頭、各段能量；每拍換鏡位（全身／半身／眼部特寫／雙姿並列／五連色相差），相鄰兩拍不重複；效果強度前奏 40%、主歌 70%、副歌 100%
- 每拍白閃且小節第一拍最強；拍落瞬間橫向撕裂＋RGB 三色分離、下一拍前復原；副歌每隔一小節萬花筒；小節頭中央大字閃 0.4 秒、difference 合成、彩虹描邊
- 正式輸出前先給每段落的截圖清單確認
- 注意：角色圖與歌曲屬原作者；大字內容要自選關鍵字

### doubleunplussed-181894 — @doubleunplussed
canvas｜指定一個開源程式 MV 當風格基準加一首歌，要求歌詞不必直譯，改用概念、事件、典故與圈內梗，交付成品檔。
- 歌詞→畫面的轉譯原則：不畫字面，畫隱喻（prompt 的例子是把「預測 token」畫成一隻鸚鵡）；每句歌詞先寫成一個可畫的意象再排分鏡
- 回饋輪示範怎麼給修改意見：角色嘴型別假裝在唱（只會抖），改成符合情緒的表情；手臂姿勢不自然就重做再重算
- 收尾把歌曲結束後多出的兩拍剪掉
- 注意：歌、角色與 credit 規則都是對方的；客戶案另寫

### anabology-491441 — @anabology
canvas · ai-image｜用既有歌曲重做一支 MV：先產風格表與角色表，AI 影片當底，JavaScript 動畫疊在上面把底完全蓋掉，歌詞排版有大有小。
- 流程：風格表（style sheet）→角色表→場景→逐句生成底片→JS 覆蓋層，等於先實拍再描線（rotoscope）
- 歌詞兩種檔位：開頭鉤子段大字佔畫面、角色靠右把左側留給字；其餘段落退成字幕，整支不用同一種強度
- 驗證：整支看多次、逐段截圖、對照品質門檻再回修；先做好構圖與時間的規劃再合成，不然會「拼起來很刺」
- 注意：K-pop 與迷因只是對方的選題；具體歌曲、角色不可用

### paranoidamerica-686717 — @ParanoidAmerica
canvas · ai-image｜給 lyrics.txt 對位整首歌，「太空明信片拼貼」加「原子筆素描」兩種風格，鏡頭從店外一路走進地下室。
- 空間敘事：一條鏡頭路徑（外→內→密門→地下室）串整首歌，每段歌詞對應路徑上的一站
- 兩種畫風做對比（照片拼貼 vs 線稿），影像交給生成工具、動畫與合成交給程式
- 注意：店與主題是對方的概念；lyrics.txt 歌詞不可用

## 二、音訊反應與節拍視覺

### acoramaa-248467 — @Acoramaa（貼文）
threejs · shader · svg · audio｜72 片機械板包住一顆 3D 眼球：kick 翻板、bass 推鏡片、高頻點亮核心；breakdown 閉眼，drop 全開。
- 一個頻段對一個幾何量（kick→板片開合、low→鏡片前後、high→核心亮度），不要所有東西都跟 rms；對應 `MV.hit('kick',t)`、`MV.env('low',t)`
- 先找 tempo、breakdown、drop，段落決定物件「狀態」（閉／開），拍點只給瞬間脈衝（`MV.sectionAt(t)`）；右側數值面板跟音樂動，當作看得見的 debug 層
- 注意：貼文沒給 prompt；眼球造型是對方設計

### prasenx-693512 — @prasenx
shader · canvas · audio｜15 秒 showreel，配樂全程式合成（無取樣、無音檔），每個剪點與轉場都落拍，輸出含音軌 MP4。
- 先定節拍格再做畫面：音樂與畫面讀同一份拍點表，剪點天然對齊（同庫 apoorvjain25-309680 貼文：音樂讀同一個 beat 檔，畫面事件與音效同格落下）
- 驗收寫成「每個轉場都在拍上」，不是「有音樂」
- 注意：自創曲要自己檢查有沒有撞到既有旋律

### gandamu-ml-220530 — @gandamu_ml
threejs · shader · canvas · audio｜用一首 S3M 模組音樂做 90 年代 demoscene：動手前先研究怎麼播放與解析曲子、各段落情緒，效果要配段落。
- 開工前兩件事：解析音樂（段落與態度）、調查可用效果與物理，再排「哪段配哪種效果」
- 段落「態度」不同時換效果庫，不是同一套效果調強弱
- 注意：原曲屬原作者；C/C++ 與 OpenGL 的做法改成 Canvas／WebGL 即可

### nathanwilbanks-981110 — @NathanWilbanks_（貼文）
threejs · shader · audio｜GPU 流體模擬的火焰拍 38 秒短片，聲音由每格火焰亮度推導，離線逐格渲染加預排鏡頭。
- 反向聲畫對位：畫面數值（亮度、速度）驅動音量與噪聲，適合沒有歌的藝術短片
- 自評迴圈：渲染一格→視覺模型當 VFX 監督挑毛病→修→重來，約 40 輪；不錄螢幕，預排鏡頭逐格離線渲染
- 注意：貼文沒給 prompt，流體模擬要自己寫

### iniyanai-856596 — @iniyanai（貼文）
threejs · svg · audio｜機械鍵盤解說片：配樂程式寫、真實軸體錄音當鼓點、three.js 做 3D、每個剪點踩拍。
- 主題物件的聲音當節拍素材（按鍵聲＝鼓），畫面與聲音出自同一物件
- 解說片也用 MV 規則剪：剪點＝拍點
- 注意：貼文沒給 prompt

## 三、動態字型與片頭

### techhalla-498547 — @techhalla
canvas｜20 秒方形識別片頭：三套字型分工、六句鎖定文案、120 BPM 前 16 拍每拍一事、首尾同格可接回。
- 字型分工：展示用超粗縮窄體（1–4 字）、都市粗體（次標）、等寬體（小標與時間碼），字距各自規定（展示 −40 到 −80，等寬 +20）
- 每字一組彈簧（y／透明度／模糊），stagger 用 1/16 音符（120 BPM＝125 ms）；印刷錯位只在重音格：文字層複製成兩色各偏 2–4 px、40% 透明
- 遮罩揭示：用上一句字形輪廓當下一句的遮罩；鏡頭只准 punch-in 1.0→1.08 與橫向 smash-pan；正式渲染前先出 8 格大拍靜幀
- 注意：色票、文案、品牌是對方的；禁止清單（腦、機器人、神經網路、閃粉、紫藍霓虹、玻璃擬態）可照用

### gdgtify-929495 — @Gdgtify
canvas｜20 秒「字型建築」口白短片：五句話，關鍵字各有結構角色（門楣、懸吊、支柱、開口、平臺），最後一句站在前面的字堆出的平臺上。
- 字形即結構：用真實字形路徑變形，保留字腔與可讀性；不同字之間用遮擋或對齊邊緣轉場，不做任意路徑插值
- 節奏用「片語、停頓、重音」排 cue sheet，不硬套舞曲拍；至少留一次 400 ms 完全靜止；承重用臨界阻尼，只有基線可以用彈性形變
- 結尾鏡頭鑽到平臺底部→底部變成開場門楣→被遮住時把元素歸位，做到 render(0)=render(20)
- 注意：五句講稿是對方原創，要自己寫；不可把講稿歸給真實人物

### daniel-haida-636937 — @daniel_haida（貼文，但貼文附了完整 prompt）
canvas · svg · css｜15 秒產品片規格書：ONE SHOT = ONE IDEA、物件驅動轉場、轉場好壞清單、19 條禁令、十個時間點抽格自檢。
- 轉場清單：好＝圖表線→單據邊、數字→發票金額、共用幾何、用產品形狀做遮罩揭示；壞＝交叉淡化、隨機擦除、旋轉、故障、兩秒一次甩鏡、縮放模糊
- 動態規格：cubic-bezier(0.16,1,0.3,1)、超調 < 2%、各元素到達時間錯開、場與場共享速度；按 115–120 BPM 設計，沒有安全音軌就只交畫面＋cue sheet
- 品質門檻：「每個重要格都能當平面廣告」「三個極好的瞬間勝過十個普通動畫」；在 0、1、2.5、4.5…14.8 秒抽格親眼看，不以編譯成功為完成
- 注意：品牌色票、字型、德文文案屬對方

### brainextends-606193 — @brainextends
shader · svg｜18 秒音樂產品片：0.1 秒粒度時間表、固定圓角舞臺框、一條持續的播放器列串起所有鏡頭、位置匹配轉場。
- 以 0.6–1.5 秒為單位寫時間表，每格寫「進什麼、怎麼進、哪個元素留下」；底部播放器列貫穿中段，鏡頭再怎麼換都有錨
- 主視覺（專輯封面）在搜尋→詳情→品牌板→放大的每個狀態都是同一物件，用 match-position、遮罩、透視，不用全幅交叉淡化；出場標題消失後進場標題才能佔同一位置
- 60 fps、每格 3–5 個時間子格做動態模糊、靜止文字保持銳利（對應 `render.py --samples 4 --shutter 0.5`）
- 注意：Spotify 品牌、綠色、介面與虛構曲名屬對方；自己做播放器與曲名

### ik-builds-585923 — @ik_builds（貼文，附可填空 prompt）
canvas · svg｜15 秒產品片填空範本：紙感畫布、麥克筆註記描線、硬切明暗、每 1.5–2 秒一個新想法、每個 hit 一個音效。
- 範本變數化（產品、受眾、禁止詞、色票、字型、logo 檔），一份 prompt 服務多個案子；螢幕上不可出現動畫術語、不可捏造數字與客戶名
- 工程規則：每個元素的起始狀態在 t=0 就設好（seek-safe）、出場不被蓋住；一次轉場只有一個主要動作；混音 -14 LUFS／-2 dBTP，AAC 編碼後再量一次
- 注意：Anton、Caveat 字型要查授權，繁中換 Noto；貼文沒附其他段落

## 四、生成與藝術影片

### zeezomb-726206 — @zeezomb
threejs · shader｜80 秒方形短片：玻璃與金箔馬賽克牆，磁磚沒黏死所以能掀、翻、飛、歸位；角色是磁磚群，一條魚經過就是它的磁磚在移動。
- 一個材質規則撐整支片：磁磚是唯一基本單位，所有畫面都是磁磚排列，轉場就是磁磚重排
- WebGL2 無外部圖片、字型、音檔，一個 HTML
- 注意：prompt 只有概念；馬賽克畫什麼要自己設計

### koldo2k-778767 — @koldo2k
canvas · ai-image｜20 秒接回開頭的無限縮放：鏡頭穿過懷錶、相機鏡頭、放大鏡、手鏡飛進下一個風景，報紙剪影拼貼風。
- 每個風景用深度圖切 3 層並補洞；視差「層縮放 = camera^Z，Z 在 0.45–1.22」
- 等速感：對固定點做指數縮放，每段時長與 log(縮放量) 成正比；入口物件的玻璃裡放下一個世界，填滿畫面時無縫切；剪影素材 15 fps 一拍二；音樂 96 BPM 剛好 8 小節＝20 秒
- 注意：風景與物件由生成工具產出，世界清單屬對方；手法可直接用在 MV 段落轉場

### demitiyageekzen-818523 — @DemitiyaGeekzen（貼文）
shader · webgl · canvas · audio｜30 秒詩詞短片：整幅畫面由 WebGL2 著色器逐畫素算出（暮色、按緯度推算的日月軌跡、程式生成的魚鱗雲、9 組波浪疊加的江面倒影），古箏用 Karplus-Strong 合成，直書書法字幕配印章。
- 天空、江面、倒影全靠著色器與數學，畫面是 t 的純函式、任何解析度都銳利
- 程式樂器（弦振動模型＋按滑揉弦）配中式題材；直書字幕＋印章是中文 MV 好用的字卡形式（`AFX.tategaki`）
- 注意：貼文沒給 prompt；詩句是公共領域，但選題與畫面設計屬對方

### majidmanzarpour-927543 — @majidmanzarpour
canvas｜單檔 HTML 畫素風法師施法：128×96 離屏畫布整數倍放大、24 色固定色盤、姿勢數值量化到格點。
- 畫素風三件事：離屏固定邏輯解析度＋整數倍放大＋`imageSmoothingEnabled=false`；座標全取整、禁漸層與陰影模糊
- 動作用連續值算再量化到格點，就有 8–12 fps 手繪感；粒子池預先配置不在迴圈內配置，顏色沿色盤索引白→魔法色→暗色；狀態機 IDLE→CHARGE→CAST→RECOVER，施法時 1–2 畫素螢幕震動
- 注意：法師造型是對方的；同一 prompt 另見 zacxbt-944604

### groundcontrol-230877 — @GroundControl
canvas · audio｜3 分鐘資料視覺化動畫：抓線上氣象資料與往年比較，手繪鉛筆風加少量色差，JS 合成器做主題旋律。
- 資料驅動影片的三段需求：資料來源與比較基準、視覺風格（鉛筆＋色差）、程式配樂；先決定「為什麼」的敘事再排資料出場順序
- 注意：題材與資料是對方的；紙紋用 `AFX.paperTexture`

## 五、電影感 3D 與鏡頭

### alexwtlf-981005 — @alexwtlf
canvas｜25 秒七個鏡頭的太空站短劇，寫成一份完整分鏡聖經：場景地圖、第一格 blocking、每鏡起訖與最後一格、焦段、機位、光源色溫、表演弧線、物理、音床、鎖定清單。
- treatment 分章：SCENE CONTEXT／LOCATION MAP／FIRST FRAME／每個 CUT／OPTICS（35、24、50 mm 等效與景深）／CAMERA（鎖定機位加幾畫素漂移，動作引起的小抖半秒內回穩）／LIGHTING（主光 5600 K、補光 2800 K、情緒光 2400 K 慢慢升）／AUDIO（一條貫穿全片的環境音床）／PERFORMANCE（逐段寫情緒弧線）
- 「只有兩個機位來回切」的限制反而給片子節奏；POSITIVE LOCKS 把所有不能變的尺寸與幾何關係列出，避免每鏡不一致
- 注意：這是 AI 影片生成用的 prompt 不是程式；劇情、角色、圖樣屬對方。寫 `templates/treatment.md` 時借它的章節骨架

### twoclipping-496100 — @twoclipping
canvas｜Apple 發表會風格一鏡到底產品片：每個場景從上一個長出來，禁止淡化、模糊、硬切；54 拍每拍一事。
- 轉場機制庫：文字從遮罩線升起、圖示從零彈簧彈出、黑色形狀淹沒全幅再收縮成下一場（flood 要超出四角、約 0.3 秒）、六葉光圈（iris）開合、字標像手風琴擠進自己的句點
- 液態玻璃：每個玻璃元素持有背後場景的複製，用 SVG feImage 距離場做三層不同尺度的 feDisplacementMap 得到色散邊；實拍素材 `ffmpeg -g 1` 全 I 格重編、blob URL 載入、每格等 seeked
- 音樂起於 downbeat、縮放落在 drop、牆面段放在 breakdown；每個事件一個 SFX 按測得峰值對齊、loudnorm -14 LUFS；渲染後掃單格爆點（格差是鄰格 3 倍）
- 注意：品牌、照片、iOS 風格介面屬對方；gotchas（backdrop-filter 讀不到位移貼圖、visibility 用 inherit、http.server 不能 range seek）是實測經驗可照用

### twoclipping-000267 — @twoclipping
svg · css｜10 小節 120 BPM 的極簡產品片：鉤子逐字落拍→一個字變成介面→drop 時按鈕開出圓形進暗場→之後每小節一個動作。
- 實拍片段轉 30 fps JPEG 序列、每格換 img 來源、seek 等解碼；numpy 分析 tempo、拍格、每小節能量與 drop，拍格校準到真實 kick
- 每個剪點在 downbeat、每個 UI 事件在拍上；每格三個子格（t−1/240、t、t+1/240）用 ffmpeg tmix 混成動態模糊；音效按峰值不按檔頭對齊；正式渲染前抽 20 格以上
- 禁止清單（衝擊波環、粒子爆、RGB 分離、鏡頭震動、光暈、網格地板、閃爍背景、彈跳緩動）適合「高階極簡」案
- 注意：同一 prompt 另見 raphaelaubryy-687877；preserve-3d 元素不能直接設 opacity／filter，淡它的外層

### kgonia7-746268 — @kgonia7（貼文）
threejs · shader · canvas · particles｜從葡萄牙海岬一路拉遠到可觀測宇宙的電影感短片，three.js、無外部素材。
- 尺度連續的一鏡拉遠（地表→大氣→行星→恆星→星系→宇宙），每個尺度換一套程式生成內容但鏡頭速度連續
- 注意：貼文沒給 prompt，只有成本參考（約 3 小時、66 萬輸出 token）

### op7418-814408 — @op7418（anime.md 已有）
threejs · shader · canvas · gsap｜手遊「高光時刻」結算演出單檔網頁：真 3D 主體、卡通分階著色、後製邊緣檢測描線、五階段演出、交付前逐圖自檢。
- 描線用法線圖＋深度圖做後製邊緣檢測（外輪廓粗、交界細、粗細一致），不用「放大黑色背面」；深度閾值放寬，接縫靠法線
- 柔光規則：conic-gradient 疊 2–3 層不同轉速、閃白用 screen 且強度 ≤ 0.8、粒子帶低透明外暈、衝擊波三層描邊；彩帶只在最高潮用一次
- 自檢清單：主角有沒有被光暈擋住、有沒有過曝、背景有沒有穿幫描線、小字能不能讀、結算後有沒有東西還在抖
- 注意：同一 prompt 另見 op7418-818226；美術要原創。anime.md 已有的 allforbigfire-029657（動畫風 3D 變形合體）、anduraio-570761（柔和卡通著色）、ishuagra02-922825（動畫風對戰預告）都是貼文或一句需求，不另立條目

## 六、轉場與特效片段

### twoclipping-402193 — @twoclipping
svg｜「一個形狀、永不剪接」的 UI 變形片：按鈕→載入→勾→播放器→滑桿→開關→分頁→圖表→命令列→提示→回到按鈕，7 小節每拍一事。
- 彈簧用閉式階躍響應，目標多次改變時把每次的響應相加，動畫仍是 t 的純函式（`MV.spring` 的用法）；分頁指示器與開關把兩個邊緣放在不同彈簧上，前緣先伸後緣再跟
- 拖曳是直接操作，放手時從當下位置彈回；numpy 抓拍格、從 downbeat 起算，UI 音效按峰值放；Playwright 每格 4 子格 tmix；正式渲染前「每拍一格」先看
- 注意：同一 prompt 另見 morse-369333、demonugc-525162、dzhohola-249003、hicallmechai-878304、nezbuilds-294391、sanjeevn72-457691；gotchas：別對會被鏡頭縮放的元素設 will-change（文字會糊）、容器內換字要各自進出場、最後一格等於第一格含指標位置與速度

### thegrootdev-966114 — @TheGrootDev
svg｜同一範本換成「一顆球體連續變形成 28 個介面狀態」，7 小節 28 拍，每拍編號寫清楚做什麼。
- 拍點表寫成「拍 1：指標靠近；拍 2：點選；拍 3：按鈕變載入；拍 4：解析成勾並拉長」的逐拍清單（`templates/cuts.csv` 的寫法）
- 持續的外形元素貫穿全片，內容可換、輪廓不能斷；曲子 BPM 不是 120 就改時間表配真實節奏；素材與字型內嵌 HTML 不依賴網路
- 注意：Pokémon 角色、名稱、配色屬任天堂，主題整個換

### annacher-433425 — @AnnaCher___
svg｜同一範本套到自家產品：先分析網站再用真實介面做狀態清單；不放音樂，UI 音效用 numpy 合成並按峰值對拍。
- 「無音樂也要有拍格」：120 BPM 格只拿來排事件與音效；狀態清單先給人看再寫程式
- 一個強調色配黑白元件，介面不上漸層
- 注意：產品介面與色票屬對方

### verbove-268381 — @verbove
canvas｜同一套變形規則的濃縮版：一個 HTML、一個 canvas、一個 draw(t)，輸出 1:1／16:9／9:16 三種比例並行。
- 規則濃縮成可貼進任何 prompt 的十幾行；「不要從黑直接淡到強調色，改用一個強調色元素在狀態間移動」
- 每格平均 6 個子格做動態模糊；先出每拍一格的拼圖再渲染全片（對應 `render.py --samples 6`、`--sheet`）
- 注意：狀態清單是對方產品的

### jake11moran-414633 — @jake11moran
canvas · svg · gsap · ai-image｜27 秒產品預告：同一個 Mac 桌面上一個連續鏡頭、無硬切，推拉搖 1.5–3 秒緩入緩出、速度是預設的一半，快動作加動態模糊、輕微膠片顆粒。
- 慢鏡頭的量化規格：每個鏡頭移動 1.5–3 秒、gentle ease-in-out、比直覺慢一倍
- 視窗「從鏡頭後方飛進來堆疊」再「推進穿過視窗回到文字」的空間連續感；清單快轉不求可讀、最後慢慢停在關鍵字，0.2 秒後補一個標點
- 注意：產品、介面與文案屬對方；colorama 文字擦除是對方框架的元件，自己用 `MV.layout` 加漸層遮罩做

## 只有一句需求、仍值得一看

samaote-124569（附歌曲做歌詞動態影片，逐字對人聲、動畫對拍點；人聲對位用 `align.py`，拍點用 `audio.json`）、abhinayguptha-259981（虛構影集 20 秒片頭）、lexnlin-241739（可自由探索的電影感 3D 世界）、x4b47x-034026（9:16 紙雕皮影戲、程式配樂）、michaelzsguo-782312（2 分鐘沙畫）、kamstudiolabs-440893（每個音符來自可見碰撞的機器）、jrayon-054015（紙板手作感碎形視覺化加電影感後製）、johnsavage-ai-427263（復古未來風、膠片顆粒加 CRT）

## 查 videos.json（以下都在本機跑過）

```bash
cd ~/video-lab/refs/awesome-opus5-5-videos   # python = ~/video-lab/.venv/bin/python
# 依標籤：列出有 audio 標籤的（36 支）
python -c "import json;d=json.load(open('data/videos.json'));[print(v['slug'],'@'+v['author'],','.join(v['tech_tags'])) for v in d if 'audio' in v['tech_tags']]"
# 依關鍵字：prompt 含 lyric（5 支）
python -c "import json;d=json.load(open('data/videos.json'));[print(v['slug'],'@'+v['author'],v['category']) for v in d if 'lyric' in v['prompt'].lower()]"
# 只看完整 prompt、依長度排序（長的通常規格最完整）
python -c "import json;d=json.load(open('data/videos.json'));[print(len(v['prompt']),v['slug']) for v in sorted(d,key=lambda v:-len(v['prompt'])) if not v['prompt_partial']]" | head -30
# 找有 seek(t) 做法的 prompt（15 支）
grep -l -i 'seek(t)' prompts/*.md
# 讀單支原文
cat prompts/pound75423-464968.md
```

- category：motion 288／interactive 70／explainer 62／3d 55；tech_tags：canvas 336、svg 193、threejs 141、shader 100、gsap 81、css 61、audio 36、particles 26、playable 22、pixel 16、ai-image 10、webgl 9、physics 9
- 同一 prompt 被多人轉貼時 videos.json 會有多筆（例如 twoclipping-402193 有 6 個複本），查完去重

## 授權提醒

- 每支 prompt 與影片屬原作者（`post_url` 可查）；本索引只摘手法，客戶案一律改寫：文案、角色、品牌、色票、曲名、歌詞全部換掉
- 貼文類（`prompt_partial: true`）連 prompt 都沒公開，只能借概念，不要宣稱「照某某的 prompt 做」
- prompt 裡的字型（Geist、Inter、Archivo、Anton、Caveat、Plus Jakarta Sans）各自查授權；本技能只用 Noto Sans TC／Noto Serif TC
- 音樂：prompt 裡的 Mixkit、Suno、ElevenLabs 各有條款；客戶案用自有或已授權音樂，沒有安全音軌就交畫面＋cue sheet
- Spotify、Pokémon、Apple 發表會風、iOS 液態玻璃只能當風格參考，不可出現其標誌、介面與名稱
