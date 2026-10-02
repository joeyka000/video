#!/usr/bin/env python3
"""把歌詞對齊到人聲的字級時間碼 → data/lyrics.json。

  python align.py song.mp3 lyrics.txt -o data/lyrics.json                       # 用 faster-whisper（large-v3、zh）辨識
  python align.py song.mp3 lyrics.txt -o data/lyrics.json --from-json words.json  # 吃現成的字級時間碼，不載模型
  python align.py song.mp3 lyrics.txt -o data/lyrics.json --model medium --no-opencc

lyrics.txt：一行一句（空行略過）。中文一個字一個 word，英文一個單字一個 word；標點不算 word 但保留在 text。
words.json（--from-json）：faster-whisper 的字級時間碼，接受兩種格式：
  [{"w"|"word": "字串", "start": 秒, "end": 秒}, ...]
  {"segments": [{"words": [{"word": ..., "start": ..., "end": ...}, ...]}, ...]}

做法：
  1. 辨識結果（簡體先用 OpenCC s2twp 轉繁；--no-opencc 可關）拆成「字元序列」：中日韓一字一個、英文一個單字一個
  2. 與 lyrics.txt 全部行的字元序列用 difflib.SequenceMatcher 對齊；對到的字取辨識時間；
     辨識錯字（replace 區塊，例如同音字）按位置取對應辨識字的時間
  3. 其餘沒對到的字（漏字）在相鄰已知時間之間線性插值；開頭／結尾沒有已知時間就用中位字長外推
  4. 每行 start／end 取首尾字；全部時間強制單調遞增

沒有 --from-json 時需要 faster_whisper 與可下載的模型；下載不了（例如這個環境擋 huggingface.co）會印出提示：
改在本機跑 faster-whisper 輸出 words.json，再用 --from-json。

輸出：{ "lines": [ {"text": "整行", "start": 秒, "end": 秒, "words": [{"w": "字", "start": 秒, "end": 秒}, ...]} ] }
"""
import argparse
import difflib
import json
import os
import re
import statistics
import sys

# 中日韓一字一個 token；拉丁字母／數字連成一個單字（允許 don't 這種撇號）
TOKEN = re.compile(r"[㐀-䶿一-鿿豈-﫿々〇぀-ヿ가-힯]"
                   r"|[A-Za-z0-9]+(?:['’][A-Za-z]+)?")


def tokens(text):
    return [m.group(0) for m in TOKEN.finditer(text)]


def key(tok):
    return tok.lower() if tok.isascii() else tok


def load_words_json(path):
    with open(path, encoding="utf-8") as f:
        doc = json.load(f)
    items = []
    if isinstance(doc, dict) and "segments" in doc:
        for seg in doc["segments"]:
            items.extend(seg.get("words", []))
    elif isinstance(doc, list):
        items = doc
    else:
        sys.exit(f"{path} 格式不對：要是 [{{w,start,end}},...] 或 {{segments:[{{words:[...]}}]}}")
    words = []
    for it in items:
        w = it.get("w", it.get("word"))
        if w is None or it.get("start") is None or it.get("end") is None:
            sys.exit(f"{path} 有缺欄位的項目：{it}")
        words.append({"w": str(w), "start": float(it["start"]), "end": float(it["end"])})
    if not words:
        sys.exit(f"{path} 裡沒有任何字")
    return words


def transcribe(song, model_name):
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        sys.exit("找不到 faster_whisper 套件。請在本機裝好後再跑，或先在別處辨識好，用 --from-json 匯入字級時間碼。")
    try:
        model = WhisperModel(model_name, device="cpu", compute_type="int8")
    except Exception as e:  # 模型下載失敗（網路被擋）或名稱錯
        sys.exit(f"無法載入 Whisper 模型 {model_name!r}：{e}\n"
                 "這個環境可能連不上 huggingface.co 下載模型。請在本機跑 faster-whisper（word_timestamps=True）"
                 "把字級時間碼存成 words.json，再用 --from-json words.json 跑本腳本。")
    try:
        segments, _ = model.transcribe(song, language="zh", word_timestamps=True, beam_size=5)
        words = [{"w": w.word, "start": float(w.start), "end": float(w.end)}
                 for seg in segments for w in (seg.words or [])]
    except Exception as e:
        sys.exit(f"辨識失敗：{e}")
    if not words:
        sys.exit("Whisper 沒有辨識出任何字（人聲太小或語言不對？）")
    return words


def split_recognized(words, convert):
    """辨識出的 word 拆成 token，時間在 word 內平均分配。"""
    out = []
    for w in words:
        text = convert(w["w"]) if convert else w["w"]
        toks = tokens(text)
        if not toks:
            continue
        n = len(toks)
        for i, tok in enumerate(toks):
            s = w["start"] + (w["end"] - w["start"]) * i / n
            e = w["start"] + (w["end"] - w["start"]) * (i + 1) / n
            out.append({"w": tok, "start": s, "end": e})
    return out


def align(rec, lines_tokens):
    """回傳 (flat, times, kind)：flat 是 (行序, 字)，times 是 (start, end) 或 None，
    kind 是 'match'（字相同）、'replace'（辨識錯字，按位置取時間）或 None（要插值）。"""
    flat = [(li, tok) for li, toks in enumerate(lines_tokens) for tok in toks]
    rec_keys = [key(r["w"]) for r in rec]
    lyr_keys = [key(tok) for _, tok in flat]
    sm = difflib.SequenceMatcher(None, rec_keys, lyr_keys, autojunk=False)
    times = [None] * len(flat)
    kind = [None] * len(flat)
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            for k in range(i2 - i1):
                times[j1 + k] = (rec[i1 + k]["start"], rec[i1 + k]["end"])
                kind[j1 + k] = "match"
        elif tag == "replace":
            # 錯字：歌詞第 j 個字按比例對到辨識的第 i 個字
            nr, nl = i2 - i1, j2 - j1
            for k in range(nl):
                i = i1 + min(nr - 1, int(k * nr / nl))
                times[j1 + k] = (rec[i]["start"], rec[i]["end"])
                kind[j1 + k] = "replace"
    return flat, times, kind


def fill(times):
    """沒對到的字：在相鄰已知時間之間線性插值；兩端用中位字長外推；最後強制單調。"""
    n = len(times)
    known = [i for i, t in enumerate(times) if t is not None]
    if not known:
        return None
    durs = [times[i][1] - times[i][0] for i in known if times[i][1] > times[i][0]]
    d = statistics.median(durs) if durs else 0.25
    out = list(times)
    # 開頭
    first = known[0]
    for j in range(first - 1, -1, -1):
        s = max(0.0, out[j + 1][0] - d)
        out[j] = (s, out[j + 1][0])
    # 中間
    for a, b in zip(known, known[1:]):
        gap = b - a - 1
        if gap <= 0:
            continue
        t0, t1 = out[a][1], out[b][0]
        if t1 < t0:
            t1 = t0
        for k in range(1, gap + 1):
            out[a + k] = (t0 + (t1 - t0) * (k - 1) / gap, t0 + (t1 - t0) * k / gap)
    # 結尾
    last = known[-1]
    for j in range(last + 1, n):
        s = out[j - 1][1]
        out[j] = (s, s + d)
    # 單調
    prev = 0.0
    for j in range(n):
        s, e = out[j]
        s = max(s, prev)
        e = max(e, s)
        out[j] = (s, e)
        prev = s
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("song")
    ap.add_argument("lyrics", help="歌詞文字檔，一行一句")
    ap.add_argument("-o", "--out", required=True, help="輸出 lyrics.json")
    ap.add_argument("--model", default="large-v3", help="faster-whisper 模型名（預設 large-v3）")
    ap.add_argument("--from-json", dest="from_json", help="現成的字級時間碼 JSON，給了就不載模型")
    ap.add_argument("--no-opencc", dest="no_opencc", action="store_true", help="不做簡轉繁")
    a = ap.parse_args()

    if not os.path.exists(a.lyrics):
        sys.exit(f"找不到歌詞檔：{a.lyrics}")
    with open(a.lyrics, encoding="utf-8") as f:
        lines = [ln.strip() for ln in f if ln.strip()]
    if not lines:
        sys.exit("歌詞檔是空的")

    convert = None
    if not a.no_opencc:
        try:
            import opencc
            cc = opencc.OpenCC("s2twp")
            convert = cc.convert
        except ImportError:
            print("沒有 opencc 套件，略過簡轉繁", file=sys.stderr)

    if a.from_json:
        if not os.path.exists(a.from_json):
            sys.exit(f"找不到 {a.from_json}")
        words = load_words_json(a.from_json)
        src = a.from_json
    else:
        if not os.path.exists(a.song):
            sys.exit(f"找不到歌曲檔：{a.song}")
        words = transcribe(a.song, a.model)
        src = f"faster-whisper {a.model}"
    rec = split_recognized(words, convert)
    if not rec:
        sys.exit("辨識結果拆不出任何字")

    lines_tokens = [tokens(ln) for ln in lines]
    for ln, toks in zip(lines, lines_tokens):
        if not toks:
            sys.exit(f"這行沒有可對齊的字：{ln!r}")
    flat, times, kind = align(rec, lines_tokens)
    matched = kind.count("match")
    replaced = kind.count("replace")
    filled = fill(times)
    if filled is None:
        sys.exit("歌詞與辨識結果沒有任何一個字對得上，請檢查歌詞檔或辨識語言")

    out_lines = []
    idx = 0
    for li, (ln, toks) in enumerate(zip(lines, lines_tokens)):
        ws = []
        n_match = 0
        for tok in toks:
            s, e = filled[idx]
            n_match += times[idx] is not None
            ws.append({"w": tok, "start": round(s, 3), "end": round(e, 3)})
            idx += 1
        out_lines.append({"text": ln, "start": ws[0]["start"], "end": ws[-1]["end"], "words": ws})
        print(f"{li + 1:02d} [{n_match:2d}/{len(toks):2d}] {ws[0]['start']:7.2f}–{ws[-1]['end']:7.2f}  {ln}")
    os.makedirs(os.path.dirname(os.path.abspath(a.out)) or ".", exist_ok=True)
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump({"lines": out_lines}, f, ensure_ascii=False, indent=1)
    print(f"來源 {src}：辨識 {len(rec)} 字，歌詞 {len(flat)} 字，對到 {matched} 字（{matched / len(flat) * 100:.0f}%），"
          f"錯字取時間 {replaced} 字，插值 {len(flat) - matched - replaced} 字。寫入 {a.out}")


if __name__ == "__main__":
    main()
