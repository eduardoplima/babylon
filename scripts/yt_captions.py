"""Convert YouTube json3 auto-captions into word timings, an SRT file and a
minute-by-minute transcript for reading.

Usage:
    python scripts/yt_captions.py legendas.pt-orig.json3 OUT_DIR
"""
import json
import os
import sys


def load_words(path):
    events = json.load(open(path))["events"]
    words = []
    for ev in events:
        if "segs" not in ev:
            continue
        t0 = ev["tStartMs"]
        for seg in ev["segs"]:
            text = seg.get("utf8", "").strip()
            if not text:
                continue
            words.append({"w": text, "s": (t0 + seg.get("tOffsetMs", 0)) / 1000})
    words.sort(key=lambda w: w["s"])
    for a, b in zip(words, words[1:]):
        a["e"] = min(b["s"], a["s"] + 1.5)
    if words:
        words[-1]["e"] = words[-1]["s"] + 1.0
    return words


def ts(s, sep=","):
    return f"{int(s // 3600):02}:{int(s % 3600 // 60):02}:{int(s % 60):02}{sep}{int(s * 1000 % 1000):03}"


def main():
    src, out = sys.argv[1], sys.argv[2]
    words = load_words(src)
    json.dump(words, open(os.path.join(out, "palavras.json"), "w"), ensure_ascii=False)

    # SRT with ~10-word lines.
    with open(os.path.join(out, "legendas.srt"), "w") as f:
        n = 0
        for i in range(0, len(words), 10):
            chunk = words[i:i + 10]
            n += 1
            f.write(f"{n}\n{ts(chunk[0]['s'])} --> {ts(chunk[-1]['e'])}\n{' '.join(w['w'] for w in chunk)}\n\n")

    # Reading transcript: one line per 30 seconds.
    with open(os.path.join(out, "transcricao.txt"), "w") as f:
        bucket, cur = [], 0
        for w in words:
            b = int(w["s"] // 30)
            if b != cur and bucket:
                f.write(f"[{ts(cur * 30, '.')[:8]}] {' '.join(bucket)}\n")
                bucket = []
            cur = b
            bucket.append(w["w"])
        if bucket:
            f.write(f"[{ts(cur * 30, '.')[:8]}] {' '.join(bucket)}\n")
    print(len(words), "palavras; fim em", ts(words[-1]["e"]))


if __name__ == "__main__":
    main()
