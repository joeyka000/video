# Easel 技能庫（ZJU-REAL/Easel，Apache-2.0）

位置：`~/video-lab/refs/easel/`（session-start hook 稀疏 clone，只有 `skills/` 與 `docs/`；不進本 repo）
- `skills/openclaw/<名稱>/SKILL.md`：114 個內容技能的做法說明（簡體中文）
- `skills/shared/scripts/*.py`：確定性的工具腳本（標準庫＋ffmpeg／faster-whisper／librosa），在我們的 venv 直接跑：
  `python ~/video-lab/refs/easel/skills/shared/scripts/<腳本>.py <子命令> -h`

沒有裝的部分：Easel 的網頁後台、OpenClaw 代理閘道、各平臺自動發文。那些要另外的 Anthropic API 金鑰（另外計費），
而且主要服務小紅書、抖音、B 站、微信等平臺；我們的工作流程已經是 Claude Code 本身，不需要再套一層代理。

## 規則
- **花錢**：`ai_image.py`、`ai_video.py`、`ai_music.py`、`voice_clone.py` 與 `tts.py --engine closed` 都會打付費 API，照 CLAUDE.md 的花錢規則先問；
  不要設定 `VIDEO_PROVIDER`／`MUSIC_PROVIDER`／`VOICE_PROVIDER`。配音一律加 `--engine edge`（免費，避免哪天環境變數被設了自動改走付費）
- **字**：它的預設與範例是簡體中文、中國平臺用語；我們的輸出一律繁體中文（臺灣用語），字幕先過 OpenCC `s2twp`，配音用 `zh-TW-*` 音色
- **發文**：`*_publish.py`、`*-upload`、`web_publisher.py` 不用（使用者發 IG，而且自動發文有封號風險）
- 腳本是外部程式碼：用之前先 `-h` 看參數、`selftest` 子命令試跑；輸出寫到 `projects/<案名>/` 或 scratchpad，不寫進 refs
- 它的做法和我們的規範衝突時（例如全部淡入、置中大標的卡片版型），以 `CLAUDE.md` 與 `references/review.md` 為準

## 值得用的（補我們沒有或比較弱的）
| 需求 | Easel | 用法重點 |
|---|---|---|
| 免費 AI 配音、旁白 | `tts.py`（技能 `tts-voiceover`） | `speak -t "文字" -o vo.mp3 --voice zh-TW-HsiaoChenNeural --engine edge --subtitle vo.srt`；同時出逐句字幕。臺灣音色：HsiaoChen（女）、HsiaoYu（女）、YunJhe（男）；`voices` 列表 |
| 多角色對話配音 | `multivoice.py`（`multi-voice-dubbing`） | 每個角色一個 zh-TW 音色，一樣加 edge |
| 長片／直播剪成多支短影音 | `highlight_cut.py`（`video-highlights`）、`clipify/` | `energy` 依音量找高潮段 → `cut` 切片並轉 9:16；clipify 另有語意選段與字幕 |
| 橫轉直、人臉置中裁切 | `reframe.py`（`video-reframe`） | 模糊填充／焦點裁切／人臉感知三種；比 SKILL.md A 段的 ffmpeg 一行式多了人臉追蹤 |
| 綠幕去背 | `chromakey.py`（`green-screen`） | ffmpeg chromakey 封裝，含背景合成 |
| 去背（照片、商品） | `remove_bg.py`（`remove-bg`） | 需要 rembg（第一次會下載約 170 MB 模型），磁碟緊時先問 |
| 照片相簿成片 | `slideshow.py`（`slideshow-video`） | Ken Burns＋轉場＋BGM＋字幕；只當快速草稿，正式片走 seek(t) 引擎 |
| 音樂卡點 | `beatsync.py`（`beat-sync-video`） | 簡易版；正式踩點照 C 段 `analyze.py`＋`cutlist.py` |
| 字幕雙語、轉檔、燒錄 | `subtitle_ops.py`（`auto-subtitle`、`subtitle-translate`） | parse／merge／convert／burn |
| 音訊降噪、混音、ducking | `audio_ops.py`、`audio_mix.py`（`audio-denoise`、`audio-mix`） | 口播收音差時先降噪再混 |
| 開頭 3 秒鉤子 | `skill-hook-generator/SKILL.md` | 只借方法論：鉤子類型、開場句式，寫成繁中 |
| 發文前檢查 | `skill-quality-gate/`、`skill-publish-checklist/` | 借檢查項目補我們的交付清單（平臺尺寸、封面、標題長度） |
| 社群腳本、分鏡 | `video-script/`、`video-strategy/`、`skill-content-repurposing/` | 一個素材改成多平臺版本時參考 |

## 不用的
- 中國平臺專屬：小紅書／抖音／快手／B 站／視頻號／知乎／公眾號的發文、登入、數據、評論
- 需要付費 provider 的生成（圖、影片、音樂、聲音複製），除非使用者同意那一筆花費
