"""Narrate a script with Chatterbox (local voice cloning) and save word timings.

Runs in its own environment:  .venvs/chatterbox/bin/python scripts/tts_chatterbox.py ...

Every paragraph is spoken in the channel's narrator voice, cloned from a short
reference clip. A stretch in another language uses the multilingual model with
the same reference voice, e.g. Latin read with Italian phonetics:

    {it|Tempus edax rerum.}          {it pause=0.5|Tempus edax rerum.}

`pause` inserts that much silence between the words of the stretch.
Word timings come from Whisper and are snapped back onto the script's own words,
in the add_subs.py format: [{"w": word, "s": start, "e": end}, ...]

Usage:
    .venvs/chatterbox/bin/python scripts/tts_chatterbox.py script.txt voice.wav words.json \
        --ref channels/roman-in-stones/voice/narrator-ref.wav [--exaggeration 0.5] [--cfg 0.5] [--seed 7]
    .venvs/chatterbox/bin/python scripts/tts_chatterbox.py script.txt voice.wav words.json --ref X --snap-only
"""
import argparse
import difflib
import json
import re

import numpy as np
import soundfile as sf
import torch
import whisper

SEGMENT = re.compile(r"^\{([^|{}]+)\|([^{}]+)\}$")
GAP = 0.55  # silence between paragraphs, seconds


def norm(text):
    return re.sub(r"[^a-z0-9]", "", text.lower())


def parse(path):
    """Paragraphs as (text, lang, pause)."""
    out = []
    for p in open(path).read().split("\n\n"):
        p = " ".join(p.split())
        if not p:
            continue
        m = SEGMENT.match(p)
        if m:
            head = m.group(1).split()
            opts = dict(kv.split("=", 1) for kv in head[1:])
            out.append((m.group(2).strip(), head[0], float(opts.get("pause", 0))))
        else:
            out.append((p, "en", 0.0))
    return out


def align(text, audio, sr, asr, lang):
    """Word timings for `text` spoken in `audio`: Whisper timestamps mapped onto
    the script's tokens; tokens Whisper missed are interpolated."""
    audio16 = torch.from_numpy(audio).float()
    if sr != 16000:
        import torchaudio.functional as AF
        audio16 = AF.resample(audio16, sr, 16000)
    res = asr.transcribe(audio16.numpy(), language="la" if lang != "en" else "en",
                         word_timestamps=True, fp16=False)
    heard = [w for s in res["segments"] for w in s.get("words", [])]
    tokens = text.split()
    times = [None] * len(tokens)
    sm = difflib.SequenceMatcher(None, [norm(t) for t in tokens], [norm(w["word"]) for w in heard])
    for op, a1, a2, b1, b2 in sm.get_opcodes():
        if op in ("equal", "replace") and a2 - a1 == b2 - b1:
            for k in range(a2 - a1):
                times[a1 + k] = (heard[b1 + k]["start"], heard[b1 + k]["end"])
        elif op == "replace" and b2 > b1:  # uneven: spread the span evenly
            s, e = heard[b1]["start"], heard[b2 - 1]["end"]
            step = (e - s) / (a2 - a1)
            for k in range(a2 - a1):
                times[a1 + k] = (s + k * step, s + (k + 1) * step)
    dur = len(audio) / sr
    for i, t in enumerate(times):  # interpolate anything still missing
        if t is None:
            prev = times[i - 1][1] if i and times[i - 1] else 0.0
            nxt = next((x[0] for x in times[i + 1:] if x), dur)
            times[i] = (prev, prev + max(0.15, (nxt - prev) / 2))
    return [{"w": tok, "s": s, "e": e} for tok, (s, e) in zip(tokens, times)]


def snap_onsets(audio, sr, words, floor_db=-38.0, hop=0.01, min_pause=0.08):
    """Whisper tends to start a word where the previous one ended, absorbing the
    pause (and the previous word's tail), so karaoke highlights light up early.
    Within each word's window: if there is a pause of at least `min_pause`, the
    word starts after the last such pause; otherwise at the first frame within
    `floor_db` of the clip's peak. Ends are pulled back to the last loud frame."""
    n = int(hop * sr)
    frames = audio[: len(audio) // n * n].reshape(-1, n)
    rms = np.sqrt((frames ** 2).mean(1)) + 1e-9
    loud = 20 * np.log10(rms / rms.max()) > floor_db
    need = int(round(min_pause / hop))
    out = []
    for w in words:
        a, b = int(w["s"] / hop), max(int(w["s"] / hop) + 1, int(w["e"] / hop))
        seg = loud[a:b]
        start, quiet = None, 0
        for i, is_loud in enumerate(seg):
            if not is_loud:
                quiet += 1
            else:
                if start is None or quiet >= need:
                    start = i
                quiet = 0
        if start is not None:
            last = len(seg) - 1 - int(np.argmax(seg[::-1]))
            s = (a + start) * hop
            e = (a + last + 1) * hop
            w = dict(w, s=round(min(s, w["e"] - 0.05), 3), e=round(max(e, s + 0.05), 3))
        out.append(w)
    return out


def spread(audio, sr, words, pause):
    """Insert `pause` seconds of silence between words (cut halfway through each gap)."""
    if pause <= 0 or len(words) < 2:
        return audio, words
    cuts = [int((a["e"] + b["s"]) / 2 * sr) for a, b in zip(words, words[1:])]
    pieces = np.split(audio, cuts)
    sil = np.zeros(int(pause * sr), dtype=audio.dtype)
    out = []
    for i, piece in enumerate(pieces):
        out += [piece, sil] if i < len(pieces) - 1 else [piece]
    shifted = [dict(w, s=w["s"] + i * pause, e=w["e"] + i * pause) for i, w in enumerate(words)]
    return np.concatenate(out), shifted


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("script")
    ap.add_argument("audio")
    ap.add_argument("words")
    ap.add_argument("--ref", required=True, help="narrator reference clip (~10 s)")
    ap.add_argument("--exaggeration", type=float, default=0.5)
    ap.add_argument("--cfg", type=float, default=0.5)
    ap.add_argument("--foreign-cfg", type=float, default=0.3, help="cfg for non-English stretches")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--device", default="mps" if torch.backends.mps.is_available() else "cpu")
    ap.add_argument("--snap-only", action="store_true", help="only re-snap word onsets in an existing words.json")
    args = ap.parse_args()

    if args.snap_only:
        audio, sr = sf.read(args.audio, dtype="float32")
        words = snap_onsets(audio, sr, json.load(open(args.words)))
        json.dump(words, open(args.words, "w"), ensure_ascii=False, indent=0)
        print(f"re-snapped {len(words)} word onsets in {args.words}")
        return

    paras = parse(args.script)
    from chatterbox.tts import ChatterboxTTS
    en = ChatterboxTTS.from_pretrained(device=args.device)
    mtl = None
    if any(lang != "en" for _, lang, _ in paras):
        from chatterbox.mtl_tts import ChatterboxMultilingualTTS
        mtl = ChatterboxMultilingualTTS.from_pretrained(device=args.device)
    asr = whisper.load_model("small", device="cpu")
    sr = en.sr

    torch.manual_seed(args.seed)
    parts, words, offset = [], [], 0.0
    for text, lang, pause in paras:
        clean = text.replace('"', "").replace("“", "").replace("”", "")
        if lang == "en":
            wav = en.generate(clean, audio_prompt_path=args.ref, exaggeration=args.exaggeration, cfg_weight=args.cfg)
        else:
            wav = mtl.generate(clean, language_id=lang, audio_prompt_path=args.ref,
                               exaggeration=args.exaggeration, cfg_weight=args.foreign_cfg)
        audio = wav.squeeze(0).cpu().numpy().astype(np.float32)
        ws = snap_onsets(audio, sr, align(text, audio, sr, asr, lang))
        audio, ws = spread(audio, sr, ws, pause)
        words += [dict(w, s=round(w["s"] + offset, 3), e=round(w["e"] + offset, 3)) for w in ws]
        parts += [audio, np.zeros(int(GAP * sr), dtype=np.float32)]
        offset += len(audio) / sr + GAP
        print(f"[{lang}] {len(audio) / sr:5.1f}s  {text[:70]}")

    full = np.concatenate(parts[:-1])
    sf.write(args.audio, full, sr)
    for w in words:  # captions: keep the script's words, minus quote marks
        w["w"] = w["w"].strip('"“”')
    json.dump(words, open(args.words, "w"), ensure_ascii=False, indent=0)
    print(f"{len(words)} words, {len(full) / sr:.1f} s → {args.audio}")


if __name__ == "__main__":
    main()
