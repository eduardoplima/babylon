"""Render a vertical short from still images (Ken Burns) plus narration.

shots.json:
    [{"image": "path (relative to shots.json)", "start": 0.0, "end": 3.1,
      "zoom": [1.0, 1.12], "focus": [[0.5, 0.5], [0.55, 0.45]], "beat": "..."}]

"focus" is the point of the image (0..1 in x and y) that sits at the frame
centre at the start and end of the shot; it is clamped so the frame never
leaves the image. Neighbouring shots crossfade over --fade seconds. Frames get
a warm grade and a dark vignette. Narration is mixed with an optional music
bed and loudness-normalised to -14 LUFS.

With --frame, the paintings animate inside the frame's transparent window
(default 0,440,1080,1080, the channel's branded Shorts frame) and the frame is
drawn on top.

Usage:
    python scripts/render_short.py shots.json voice.mp3 render.mp4 [--music music.flac] [--music-db -20]
        [--frame frame.png [--window 0,440,1080,1080]]
"""
import argparse
import json
import os
import subprocess
import tempfile

import cv2
import numpy as np
from moviepy import VideoClip
from PIL import Image

W, H, FPS = 1080, 1920, 30


def ease(p):
    return p * p * (3 - 2 * p)


def lerp(a, b, p):
    return a + (b - a) * p


class Shot:
    def __init__(self, spec, base_dir):
        self.spec = spec
        self.start, self.end = spec["start"], spec["end"]
        self.z0, self.z1 = spec.get("zoom", [1.0, 1.1])
        (fx0, fy0), (fx1, fy1) = spec.get("focus", [[0.5, 0.5], [0.5, 0.5]])
        self.f0, self.f1 = (fx0, fy0), (fx1, fy1)
        img = Image.open(os.path.join(base_dir, spec["image"])).convert("RGB")
        # Pre-scale so the most zoomed-in frame samples the source at ~1:1.
        cover = max(W / img.width, H / img.height)
        k = min(1.0, cover * max(self.z0, self.z1))
        if k < 1.0:
            img = img.resize((round(img.width * k), round(img.height * k)), Image.LANCZOS)
        self.img = np.asarray(img)
        self.cover = max(W / self.img.shape[1], H / self.img.shape[0])

    def frame(self, t):
        p = ease(np.clip((t - self.start) / max(self.end - self.start, 1e-6), 0, 1))
        z = lerp(self.z0, self.z1, p)
        s = self.cover * z
        ih, iw = self.img.shape[:2]
        vw, vh = W / s, H / s  # visible source size
        cx = np.clip(lerp(self.f0[0], self.f1[0], p) * iw, vw / 2, iw - vw / 2)
        cy = np.clip(lerp(self.f0[1], self.f1[1], p) * ih, vh / 2, ih - vh / 2)
        m = np.float32([[s, 0, W / 2 - cx * s], [0, s, H / 2 - cy * s]])
        return cv2.warpAffine(self.img, m, (W, H), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)


def grade_mask():
    y, x = np.mgrid[0:H, 0:W].astype(np.float32)
    r = np.sqrt(((x - W / 2) / (W / 2)) ** 2 + ((y - H / 2) / (H / 2)) ** 2) / np.sqrt(2)
    vignette = 1 - 0.6 * np.clip(r, 0, 1) ** 2.2
    warm = np.array([1.05, 1.0, 0.9], np.float32)
    return vignette[..., None] * warm


def build(shots, fade):
    mask = grade_mask()
    half = fade / 2

    def make_frame(t):
        live = [s for s in shots if s.start - half <= t < s.end + half]
        if not live:
            live = [min(shots, key=lambda s: min(abs(t - s.start), abs(t - s.end)))]
        if len(live) == 1:
            img = live[0].frame(t).astype(np.float32)
        else:
            a, b = live[0], live[1]
            w = np.clip((t - (b.start - half)) / fade, 0, 1)
            img = a.frame(t).astype(np.float32) * (1 - w) + b.frame(t).astype(np.float32) * w
        # gentle S-curve for contrast, then warm grade + vignette
        img = img / 255.0
        img = img + 0.08 * (img - 0.5) * (1 - np.abs(2 * img - 1))
        return np.clip(img * mask * 255, 0, 255).astype(np.uint8)

    return make_frame


def framed(make_frame, frame_path, window):
    """Composite the animated window under a 1080x1920 RGBA frame."""
    frame = np.asarray(Image.open(frame_path).convert("RGBA")).astype(np.float32)
    rgb, alpha = frame[..., :3], frame[..., 3:] / 255.0
    x, y, w, h = window

    def make(t):
        canvas = np.zeros_like(rgb)
        canvas[y:y + h, x:x + w] = make_frame(t)
        return (rgb * alpha + canvas * (1 - alpha)).astype(np.uint8)

    return make


def main():
    global W, H
    ap = argparse.ArgumentParser()
    ap.add_argument("shots")
    ap.add_argument("voice")
    ap.add_argument("output")
    ap.add_argument("--music")
    ap.add_argument("--music-db", type=float, default=-20, help="music gain relative to narration")
    ap.add_argument("--music-start", type=float, default=0, help="seconds into the music track")
    ap.add_argument("--fade", type=float, default=0.4)
    ap.add_argument("--preview", nargs="*", type=float, help="write preview frames at these times and exit")
    ap.add_argument("--frame", help="1080x1920 RGBA overlay with a transparent video window")
    ap.add_argument("--window", default="0,440,1080,1080", help="x,y,w,h of the frame's video window")
    args = ap.parse_args()
    window = tuple(int(v) for v in args.window.split(","))
    if args.frame:
        W, H = window[2], window[3]

    base = os.path.dirname(os.path.abspath(args.shots))
    specs = json.load(open(args.shots))
    shots = [Shot(s, base) for s in specs]
    duration = max(s.end for s in shots)
    make_frame = build(shots, args.fade)
    if args.frame:
        make_frame = framed(make_frame, args.frame, window)

    if args.preview:
        out_dir = os.path.join(os.path.dirname(os.path.abspath(args.output)), "frames")
        os.makedirs(out_dir, exist_ok=True)
        for t in args.preview:
            path = os.path.join(out_dir, f"preview_{t:05.1f}.jpg")
            Image.fromarray(make_frame(t)).save(path, quality=85)
            print(path)
        return

    with tempfile.TemporaryDirectory() as tmp:
        silent = os.path.join(tmp, "video.mp4")
        VideoClip(make_frame, duration=duration).write_videofile(
            silent, fps=FPS, codec="libx264", audio=False, preset="medium",
            ffmpeg_params=["-crf", "17", "-pix_fmt", "yuv420p"], logger="bar")

        # Mix narration + music, then loudness-normalise in two passes so the
        # result actually lands on -14 LUFS (single-pass loudnorm undershoots).
        mixed = os.path.join(tmp, "mix.wav")
        cmd = ["ffmpeg", "-y", "-v", "error", "-i", args.voice]
        voice = "[0:a]aresample=48000,acompressor=threshold=-20dB:ratio=3:attack=5:release=120:makeup=2,apad[v]"
        if args.music:
            cmd += ["-ss", str(args.music_start), "-i", args.music]
            gain = 10 ** (args.music_db / 20)
            music = (f"[1:a]aresample=48000,volume={gain:.4f},afade=t=in:d=1.5,"
                     f"afade=t=out:st={max(duration - 2.5, 0):.2f}:d=2.5[m]")
            mix = f"{voice};{music};[v][m]amix=inputs=2:duration=first:normalize=0[a]"
        else:
            mix = f"{voice};[v]anull[a]"
        cmd += ["-filter_complex", mix, "-map", "[a]", "-t", f"{duration:.3f}", mixed]
        subprocess.run(cmd, check=True)

        target = "I=-14:TP=-1.5:LRA=11"
        probe = subprocess.run(["ffmpeg", "-v", "info", "-i", mixed, "-af", f"loudnorm={target}:print_format=json",
                                "-f", "null", "-"], capture_output=True, text=True, check=True).stderr
        m = json.loads(probe[probe.rindex("{"):probe.rindex("}") + 1])
        norm = (f"loudnorm={target}:measured_I={m['input_i']}:measured_TP={m['input_tp']}:"
                f"measured_LRA={m['input_lra']}:measured_thresh={m['input_thresh']}:"
                f"offset={m['target_offset']}:linear=true,aresample=48000")
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", silent, "-i", mixed, "-map", "0:v", "-map", "1:a",
                        "-af", norm, "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart",
                        args.output], check=True)
    print(f"wrote {args.output} ({duration:.1f} s)")


if __name__ == "__main__":
    main()
