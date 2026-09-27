"""Split a long video into scenes defined by approximate start times and
anchor phrases, snapping each start to where the anchor is actually spoken.

cenas.json: [["HH:MM:SS", "anchor phrase", "title"], ...]
palavras.json: [{"w": word, "s": start, "e": end}, ...]  (from yt_captions.py)

Usage:
    python scripts/split_scenes.py VIDEO cenas.json palavras.json OUT_DIR [--dry-run]
"""
import argparse
import json
import os
import re
import subprocess
import unicodedata

WINDOW = 45  # seconds around the estimate to search for the anchor


def norm(text):
    text = unicodedata.normalize("NFKD", text.lower())
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9 ]", "", text).split()


def hms(s):
    h, m, sec = s.split(":")
    return int(h) * 3600 + int(m) * 60 + float(sec)


def fmt(s, sep=","):
    ms = int(round(s * 1000))
    return f"{ms // 3600000:02}:{ms // 60000 % 60:02}:{ms // 1000 % 60:02}{sep}{ms % 1000:03}"


def find_anchor(words, tokens, anchor, est):
    target = norm(anchor)
    best = None
    for i, w in enumerate(words):
        if abs(w["s"] - est) > WINDOW:
            continue
        if tokens[i:i + len(target)] == target:
            d = abs(w["s"] - est)
            if best is None or d < best[0]:
                best = (d, i)
    return best[1] if best else None


def largest_gap(words, est):
    cands = [(words[i + 1]["s"] - words[i]["e"], i + 1) for i in range(len(words) - 1)
             if abs(words[i + 1]["s"] - est) <= 10]
    return max(cands)[1] if cands else min(range(len(words)), key=lambda i: abs(words[i]["s"] - est))


def safe(name):
    return re.sub(r'[\\/:*?"<>|]', "", name).strip()


def main():
    p = argparse.ArgumentParser()
    p.add_argument("video")
    p.add_argument("scenes")
    p.add_argument("words")
    p.add_argument("out")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--bitrate", default="6M")
    args = p.parse_args()

    scenes = json.load(open(args.scenes))
    words = json.load(open(args.words))
    tokens = []
    token_word = []
    for i, w in enumerate(words):
        for t in norm(w["w"]):
            tokens.append(t)
            token_word.append(i)
    dur = float(subprocess.check_output(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", args.video]))

    starts, report = [], []
    for est_s, anchor, title in scenes:
        est = hms(est_s)
        if not anchor:
            starts.append(0.0)
            report.append((est_s, "início", title))
            continue
        # search on the token stream, mapped back to word timings
        tw = [{"s": words[token_word[k]]["s"]} for k in range(len(tokens))]
        k = find_anchor(tw, tokens, anchor, est)
        if k is not None:
            wi = token_word[k]
            prev_end = words[wi - 1]["e"] if wi > 0 else 0
            start = max(prev_end, words[wi]["s"] - 0.35)
            report.append((est_s, "ok", title))
        else:
            wi = largest_gap(words, est)
            start = words[wi]["s"] - 0.2
            report.append((est_s, "SEM ÂNCORA, usei pausa", title))
        starts.append(start)

    bounds = list(zip(starts, starts[1:] + [dur]))
    os.makedirs(args.out, exist_ok=True)
    index = []
    for n, ((s, e), (est_s, status, title)) in enumerate(zip(bounds, report), 1):
        base = f"{n:02d} - {safe(title)}"
        index.append({"n": n, "titulo": title, "inicio": fmt(s, "."), "fim": fmt(e, "."),
                      "duracao_s": round(e - s, 1), "arquivo": base + ".mp4", "ancora": status})
        print(f"{n:02d} {fmt(s, '.')[:8]} -> {fmt(e, '.')[:8]} ({(e - s) / 60:4.1f} min) [{status}] {title}")
        if args.dry_run:
            continue
        # Scene subtitles, re-timed to start at zero.
        with open(os.path.join(args.out, base + ".srt"), "w") as f:
            seg = [w for w in words if s <= w["s"] < e]
            for k in range(0, len(seg), 10):
                chunk = seg[k:k + 10]
                f.write(f"{k // 10 + 1}\n{fmt(chunk[0]['s'] - s)} --> {fmt(min(chunk[-1]['e'], e) - s)}\n"
                        f"{' '.join(w['w'] for w in chunk)}\n\n")
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{s:.3f}", "-i", args.video,
                        "-t", f"{e - s:.3f}", "-c:v", "h264_videotoolbox", "-b:v", args.bitrate,
                        "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart",
                        os.path.join(args.out, base + ".mp4")], check=True)

    if not args.dry_run:
        json.dump(index, open(os.path.join(args.out, "indice.json"), "w"), ensure_ascii=False, indent=1)
        with open(os.path.join(args.out, "indice.md"), "w") as f:
            f.write("| # | Início | Fim | Duração | Cena |\n|---|---|---|---|---|\n")
            for c in index:
                f.write(f"| {c['n']} | {c['inicio'][:8]} | {c['fim'][:8]} | {c['duracao_s'] / 60:.1f} min | {c['titulo']} |\n")


if __name__ == "__main__":
    main()
