"""Narrate a script with edge-tts and save word timings.

The text file is read as-is; blank lines become short pauses (edge-tts
honours sentence punctuation, so paragraph breaks are joined with " ... ").
Word timings are written in the add_subs.py format:
[{"w": word, "s": start, "e": end}, ...]

A stretch of text can be spoken by another voice, e.g. Latin read by an
Italian voice so it isn't anglicised:

    Ovid wrote three words. {it-IT-DiegoNeural rate=-15%|Tempus... edax... rerum.}

Each stretch is synthesized separately and the pieces are joined with a short
pause; word timings are shifted to match.

Usage:
    python scripts/tts.py script.txt voice.mp3 words.json [--voice en-GB-RyanNeural] [--rate -5%] [--pitch -2Hz]
"""
import argparse
import asyncio
import json
import os
import re
import subprocess
import tempfile

import edge_tts

SEGMENT = re.compile(r"\{([^|{}]+)\|([^{}]+)\}")

TICKS = 10_000_000  # edge-tts offsets are in 100 ns units


async def narrate(text, voice, rate, pitch, audio_path):
    comm = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch, boundary="WordBoundary")
    words = []
    with open(audio_path, "wb") as f:
        async for chunk in comm.stream():
            if chunk["type"] == "audio":
                f.write(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                s = chunk["offset"] / TICKS
                words.append({"w": chunk["text"], "s": round(s, 3), "e": round(s + chunk["duration"] / TICKS, 3)})
    return words


def norm(text):
    return re.sub(r"[^a-z0-9]", "", text.lower())


def restore_punctuation(words, text):
    """edge-tts drops punctuation; copy it back from the script so captions
    can break at sentence ends (add_subs.py splits after . ? !)."""
    tokens = text.split()
    j = 0
    for w in words:
        key = norm(w["w"])
        for k in range(j, min(j + 4, len(tokens))):
            if norm(tokens[k]).startswith(key) and key:
                tok = re.sub(r"\.\.\.$", "", tokens[k].strip('"\u201c\u201d'))
                if norm(tok) == key:
                    w["w"] = tok
                j = k + 1
                break
    return words


def segments(text, voice, rate, pitch):
    """Split text into (text, voice, rate, pitch) runs using {voice k=v|text} markup."""
    out, pos = [], 0
    for m in SEGMENT.finditer(text):
        if text[pos:m.start()].strip():
            out.append((text[pos:m.start()].strip(), voice, rate, pitch))
        head = m.group(1).split()
        opts = dict(kv.split("=", 1) for kv in head[1:])
        out.append((m.group(2).strip(), head[0], opts.get("rate", rate), opts.get("pitch", pitch)))
        pos = m.end()
    if text[pos:].strip():
        out.append((text[pos:].strip(), voice, rate, pitch))
    return out


def duration(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path],
                       capture_output=True, text=True, check=True)
    return float(r.stdout)


def narrate_all(text, voice, rate, pitch, audio_path, gap=0.4):
    runs = segments(text, voice, rate, pitch)
    if len(runs) == 1:
        return asyncio.run(narrate(text, voice, rate, pitch, audio_path))
    words, offset, parts = [], 0.0, []
    with tempfile.TemporaryDirectory() as tmp:
        silence = os.path.join(tmp, "gap.wav")
        subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono", "-t", str(gap), silence], check=True)
        for i, (chunk, v, r, p) in enumerate(runs):
            mp3, wav = os.path.join(tmp, f"{i}.mp3"), os.path.join(tmp, f"{i}.wav")
            for w in asyncio.run(narrate(chunk, v, r, p, mp3)):
                words.append(dict(w, s=round(w["s"] + offset, 3), e=round(w["e"] + offset, 3)))
            subprocess.run(["ffmpeg", "-v", "error", "-i", mp3, "-ar", "24000", "-ac", "1", wav], check=True)
            parts += [wav, silence]
            offset += duration(wav) + gap
        listing = os.path.join(tmp, "list.txt")
        open(listing, "w").write("".join(f"file '{p}'\n" for p in parts[:-1]))
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", listing,
                        "-c:a", "libmp3lame", "-b:a", "96k", audio_path], check=True)
    return words


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("script")
    ap.add_argument("audio")
    ap.add_argument("words")
    ap.add_argument("--voice", default="en-GB-RyanNeural")
    ap.add_argument("--rate", default="-5%")
    ap.add_argument("--pitch", default="+0Hz")
    args = ap.parse_args()

    paras = [" ".join(p.split()) for p in open(args.script).read().split("\n\n") if p.strip()]
    text = "\n".join(paras)
    words = restore_punctuation(narrate_all(text, args.voice, args.rate, args.pitch, args.audio), SEGMENT.sub(r"\2", text))
    json.dump(words, open(args.words, "w"), ensure_ascii=False, indent=0)
    end = words[-1]["e"] if words else 0
    print(f"{len(words)} words, {end:.1f} s of speech → {args.audio}")


if __name__ == "__main__":
    main()
