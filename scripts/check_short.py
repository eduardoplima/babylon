"""Automated checks for a finished short (the revisor's mechanical checklist).

Checks format, length, loudness, black frames, the hook, the loop (the last
shot returns to the first image) and that every image is PD/CC0 in the manifest.
Prints a PASS/FAIL table and exits non-zero on any FAIL. Captions accuracy,
facts and quotes and visual review still need the revisor.

Usage:
    python scripts/check_short.py channels/<slug>/videos/<NNN-slug>
"""
import json
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FREE = re.compile(r"public domain|^pd\b|cc0", re.I)


def ff(args):
    return subprocess.run(args, capture_output=True, text=True).stderr


def main():
    vd = os.path.abspath(sys.argv[1])
    final = os.path.join(vd, "final.mp4")
    results = []
    add = lambda name, ok, detail: results.append((name, ok, detail))

    probe = json.loads(subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,codec_name,width,height,r_frame_rate:format=duration",
         "-of", "json", final], capture_output=True, text=True, check=True).stdout)
    v = next(s for s in probe["streams"] if s["codec_type"] == "video")
    a = [s for s in probe["streams"] if s["codec_type"] == "audio"]
    dur = float(probe["format"]["duration"])
    add("format", (v["width"], v["height"], v["r_frame_rate"], v["codec_name"]) == (1080, 1920, "30/1", "h264") and bool(a),
        f"{v['codec_name']} {v['width']}x{v['height']} {v['r_frame_rate']} audio={a[0]['codec_name'] if a else 'none'}")
    add("duration 30–60 s", 30 <= dur <= 60, f"{dur:.1f} s")

    out = ff(["ffmpeg", "-i", final, "-af", "loudnorm=print_format=json", "-f", "null", "-"])
    m = json.loads(out[out.rindex("{"):out.rindex("}") + 1])
    lufs, tp = float(m["input_i"]), float(m["input_tp"])
    add("loudness", -16 <= lufs <= -12 and tp <= -1, f"{lufs:.1f} LUFS, TP {tp:.1f} dBTP")

    black = re.findall(r"black_start:([\d.]+)", ff(["ffmpeg", "-i", final, "-vf", "blackdetect=d=0.2:pix_th=0.08",
                                                   "-an", "-f", "null", "-"]))
    add("no black frames", not black, "none" if not black else f"at {', '.join(black)} s")

    words = json.load(open(os.path.join(vd, "words.json")))
    first = next((w for w in words if w["s"] >= 0), None)
    add("hook starts < 1 s", first and first["s"] < 1.0, f"first word '{first['w']}' at {first['s']:.2f} s" if first else "no words")
    mono = all(b["s"] >= a["s"] for a, b in zip(words, words[1:]))
    add("word timings monotonic", mono, f"{len(words)} words, speech ends {words[-1]['e']:.1f} s")

    shots = json.load(open(os.path.join(vd, "shots.json")))
    gaps = [f"{a['end']}→{b['start']}" for a, b in zip(shots, shots[1:]) if abs(a["end"] - b["start"]) > 0.01]
    add("shots contiguous", not gaps and shots[0]["start"] == 0, "ok" if not gaps else "gaps " + ", ".join(gaps))
    add("shots cover video", abs(shots[-1]["end"] - dur) < 0.1, f"shots end {shots[-1]['end']} s, video {dur:.1f} s")
    add("loop: ends on opening image", shots[0]["image"] == shots[-1]["image"],
        os.path.basename(shots[0]["image"]) if shots[0]["image"] == shots[-1]["image"]
        else f"first {os.path.basename(shots[0]['image'])} ≠ last {os.path.basename(shots[-1]['image'])}")
    add("speech ends before video", words[-1]["e"] <= dur - 0.5, f"{dur - words[-1]['e']:.1f} s tail")

    spec = json.load(open(os.path.join(vd, "short.json")))
    manifest = {e["path"]: e for e in json.load(open(os.path.join(ROOT, "channels", spec["channel"], "content", "manifest.json")))}
    bad = []
    for s in shots:
        rel = os.path.relpath(os.path.normpath(os.path.join(vd, s["image"])),
                              os.path.join(ROOT, "channels", spec["channel"], "content"))
        e = manifest.get(rel)
        if not e or not FREE.search(e["license"]):
            bad.append(f"{rel} ({e['license'] if e else 'not in manifest'})")
    add("images PD/CC0 in manifest", not bad, "ok" if not bad else "; ".join(bad))
    add("sources.md present", os.path.exists(os.path.join(vd, "sources.md")), "")

    width = max(len(r[0]) for r in results)
    for name, ok, detail in results:
        print(f"{'PASS' if ok else 'FAIL'}  {name:<{width}}  {detail}")
    sys.exit(0 if all(r[1] for r in results) else 1)


if __name__ == "__main__":
    main()
