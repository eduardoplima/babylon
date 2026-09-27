"""Build a looping, branded short from a video folder.

The folder holds the director's inputs:
    short.json   {"channel": "roman-in-stones", "series": "PART 1 · ...", "title": "...",
                  "handle": "@...", "music": "music/<file>", "music_db": -20}
    script.txt   narration; foreign lines as their own paragraph: {it|Tempus edax rerum.}
    shots.json   written by the director after the `voice` step (needs words.json timings)

Steps:
    voice    script.txt → voice.wav + words.json   (Chatterbox, channel narrator voice)
    render   frame.png → render.mp4 → final.mp4 (captions) → check_short.py

Usage:
    python scripts/build_short.py channels/<slug>/videos/<NNN-slug> voice
    python scripts/build_short.py channels/<slug>/videos/<NNN-slug> render [--preview 1 5 9 ...]
"""
import argparse
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = os.path.join(ROOT, ".venv", "bin", "python")
PY_TTS = os.path.join(ROOT, ".venvs", "chatterbox", "bin", "python")
CAPTIONS = ["--font", "/System/Library/Fonts/Supplemental/Georgia Bold.ttf", "--no-upper",
            "--color", "#F3E9D2", "--highlight", "#E0B04A", "--font-ratio", "0.08",
            "--center", "0.715", "--max-words", "3"]


def run(cmd, **kw):
    print("→", " ".join(os.path.relpath(c, ROOT) if c.startswith(ROOT) else c for c in cmd), flush=True)
    subprocess.run(cmd, check=True, **kw)


def script(name):
    return os.path.join(ROOT, "scripts", name)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video_dir")
    ap.add_argument("step", choices=["voice", "render"])
    ap.add_argument("--preview", nargs="*", type=float, help="render step: only write preview frames")
    args = ap.parse_args()

    vd = os.path.abspath(args.video_dir)
    spec = json.load(open(os.path.join(vd, "short.json")))
    channel_dir = os.path.join(ROOT, "channels", spec["channel"])
    env = dict(os.environ, PYTORCH_ENABLE_MPS_FALLBACK="1")

    if args.step == "voice":
        ref = os.path.join(channel_dir, spec.get("voice_ref", "voice/narrator-ref.wav"))
        run([PY_TTS, script("tts_chatterbox.py"), "script.txt", "voice.wav", "words.json", "--ref", ref,
             "--seed", str(spec.get("seed", 7))], cwd=vd, env=env)
        words = json.load(open(os.path.join(vd, "words.json")))
        print("\nTimeline (write shots.json from this):")
        print(" ".join(f"{w['w']}@{w['s']:.1f}" for w in words))
        print(f"\nspeech ends at {words[-1]['e']:.1f} s → last shot should end ≈ {words[-1]['e'] + 1.2:.1f} s")
        return

    if not os.path.exists(os.path.join(vd, "shots.json")):
        sys.exit("shots.json missing: run the voice step, then write shots.json from the timeline")

    frame = ["--series", spec.get("series", ""), "--title", spec.get("title", "")]
    for key in ("handle", "follow"):
        if spec.get(key):
            frame += [f"--{key}", spec[key]]
    run([PY, script("shorts_frame.py"), "--channel", spec["channel"], "frame.png"] + frame, cwd=vd)

    render = [PY, script("render_short.py"), "shots.json", "voice.wav", "render.mp4", "--frame", "frame.png"]
    if spec.get("music"):
        render += ["--music", os.path.join(channel_dir, "content", spec["music"]),
                   "--music-db", str(spec.get("music_db", -20)), "--music-start", str(spec.get("music_start", 0))]
    if args.preview:
        run(render + ["--preview"] + [str(t) for t in args.preview], cwd=vd)
        return
    run(render, cwd=vd)
    run([PY, script("add_subs.py"), "render.mp4", "words.json", "final.mp4"] + CAPTIONS, cwd=vd)
    os.remove(os.path.join(vd, "render.mp4"))
    run([PY, script("check_short.py"), vd])


if __name__ == "__main__":
    main()
