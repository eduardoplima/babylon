"""Burn new captions onto a video with MoviePy + Pillow.

Captions come from a word-timestamp JSON produced by Whisper
([{"w": word, "s": start, "e": end}, ...]). Words are grouped into short
chunks. The default "shorts" style draws big uppercase words with a thick
outline and no background, highlighting the word being spoken. The "box"
style draws plain text on a semi-transparent dark box.

Usage:
    python scripts/add_subs.py INPUT.mp4 WORDS.json [OUTPUT.mp4]
        [--style shorts|box] [--color HEX] [--highlight HEX] [--center 0.78]
        [--transparency 0.2] [--max-words 3] [--font PATH] [--no-upper] [--preview T ...]
"""
import argparse
import json
import os

import numpy as np
from moviepy import VideoFileClip
from PIL import Image, ImageDraw, ImageFont

FONT = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"


def load_words(path):
    raw = json.load(open(path))
    words = []
    for w in raw:
        text = w["w"].strip()
        if not text:
            continue
        # Whisper splits "150,000" into "150" + ",000"; glue those back on.
        if words and text[0] in ",.%":
            words[-1]["w"] += text
            words[-1]["e"] = w["e"]
        else:
            words.append(dict(w, w=text))
    return words


def group(words, max_words, max_dur=1.6, gap=0.35):
    chunks, cur = [], []
    for w in words:
        if cur and (len(cur) >= max_words
                    or w["s"] - cur[-1]["e"] > gap
                    or w["e"] - cur[0]["s"] > max_dur
                    or cur[-1]["w"][-1] in ".?!"):
            chunks.append(cur)
            cur = []
        cur.append(w)
    if cur:
        chunks.append(cur)
    out = []
    for i, c in enumerate(chunks):
        start = c[0]["s"]
        # Hold each caption until the next one starts, capped at 0.5s of silence.
        nxt = chunks[i + 1][0]["s"] if i + 1 < len(chunks) else c[-1]["e"] + 0.5
        end = min(nxt, c[-1]["e"] + 0.5)
        out.append((start, end, " ".join(w["w"] for w in c), c))
    return out


def render_caption(text, width, font_size, transparency):
    font = ImageFont.truetype(FONT, font_size)
    pad_x, pad_y = int(font_size * 0.6), int(font_size * 0.45)
    probe = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    l, t, r, b = probe.textbbox((0, 0), text, font=font)
    tw, th = r - l, b - t
    box_w, box_h = min(width - 40, tw + 2 * pad_x), th + 2 * pad_y
    img = Image.new("RGBA", (box_w, box_h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    alpha = int(round(255 * (1 - transparency)))
    d.rounded_rectangle([0, 0, box_w - 1, box_h - 1], radius=int(font_size * 0.35), fill=(0, 0, 0, alpha))
    d.text(((box_w - tw) / 2 - l, pad_y - t), text, font=font, fill=(255, 255, 255, 255))
    arr = np.asarray(img).astype(np.float32)
    return arr[..., :3], arr[..., 3:] / 255.0


SHORTS_FONT = "/System/Library/Fonts/Supplemental/Arial Black.ttf"


def hex_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def render_karaoke(words, active, width, font_size, color, highlight, font_path=None, upper=True):
    """Big words with a thick black outline and no background.

    The word at index `active` is drawn in the highlight color and slightly
    larger. Lines wrap when the chunk is wider than the frame.
    """
    probe = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    max_w = width * 0.9
    # Shrink the font if any single word (e.g. a URL) is wider than the frame.
    while True:
        font = ImageFont.truetype(font_path or SHORTS_FONT, font_size)
        big = ImageFont.truetype(font_path or SHORTS_FONT, int(font_size * 1.12))
        stroke = max(4, int(font_size * 0.11))
        shadow = max(3, int(font_size * 0.06))
        space = probe.textlength(" ", font=font)
        items = []
        for i, w in enumerate(words):
            f = big if i == active else font
            text = w.upper() if upper else w
            l, t, r, b = probe.textbbox((0, 0), text, font=f, stroke_width=stroke)
            items.append((text, f, r - l, l))
        widest = max(it[2] for it in items)
        if widest <= max_w or font_size <= 20:
            break
        font_size = int(font_size * max_w / widest) - 1

    # Greedy wrap into lines that fit inside the frame margins.
    lines, cur, cur_w = [], [], 0
    for i, it in enumerate(items):
        add = it[2] + (space if cur else 0)
        if cur and cur_w + add > max_w:
            lines.append(cur)
            cur, cur_w = [], 0
            add = it[2]
        cur.append(i)
        cur_w += add
    lines.append(cur)

    asc, desc = big.getmetrics()
    line_h = asc + desc + 2 * stroke
    img_w = int(width)
    img_h = line_h * len(lines) + shadow
    img = Image.new("RGBA", (img_w, img_h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    for li, line in enumerate(lines):
        lw = sum(items[i][2] for i in line) + space * (len(line) - 1)
        x = (img_w - lw) / 2
        base_y = li * line_h + stroke + asc  # shared baseline for the line
        for i in line:
            text, f, w, l = items[i]
            fill = highlight if i == active else color
            pos = (x - l, base_y)
            d.text((pos[0] + shadow, pos[1] + shadow), text, font=f, fill=(0, 0, 0, 160),
                   stroke_width=stroke, stroke_fill=(0, 0, 0, 160), anchor="ls")
            d.text(pos, text, font=f, fill=fill + (255,), stroke_width=stroke,
                   stroke_fill=(0, 0, 0, 255), anchor="ls")
            x += w + space
    arr = np.asarray(img).astype(np.float32)
    return arr[..., :3], arr[..., 3:] / 255.0


def active_word(words, t):
    """Index of the word being spoken at t; holds the last spoken word in gaps."""
    idx = 0
    for i, w in enumerate(words):
        if t >= w["s"]:
            idx = i
    return idx


def make_processor(chunks, center, transparency, font_ratio, style="shorts",
                   color="#FFFFFF", highlight="#FFE600", font_path=None, upper=True):
    starts = np.array([c[0] for c in chunks])
    cache = {}

    def process(get_frame, t):
        frame = get_frame(t)
        i = int(np.searchsorted(starts, t, side="right")) - 1
        if i < 0 or t >= chunks[i][1]:
            return frame
        H, W = frame.shape[:2]
        if style == "shorts":
            words = chunks[i][3]
            key = (i, active_word(words, t))
            if key not in cache:
                cache.clear()
                cache[key] = render_karaoke([w["w"] for w in words], key[1], W,
                                            int(W * font_ratio), hex_rgb(color), hex_rgb(highlight),
                                            font_path, upper)
        else:
            key = i
            if key not in cache:
                cache.clear()
                cache[key] = render_caption(chunks[i][2], W, int(W * font_ratio), transparency)
        rgb, a = cache[key]
        h, w = a.shape[:2]
        y0 = int(H * center - h / 2)
        x0 = (W - w) // 2
        out = frame.copy()
        region = out[y0:y0 + h, x0:x0 + w].astype(np.float32)
        out[y0:y0 + h, x0:x0 + w] = (rgb * a + region * (1 - a)).astype(np.uint8)
        return out

    return process


def main():
    p = argparse.ArgumentParser()
    p.add_argument("input")
    p.add_argument("words")
    p.add_argument("output", nargs="?")
    p.add_argument("--center", type=float, default=0.78, help="caption center, fraction of height")
    p.add_argument("--transparency", type=float, default=0.2, help="box transparency, 0=opaque 1=invisible")
    p.add_argument("--max-words", type=int, default=3)
    p.add_argument("--style", choices=["shorts", "box"], default="shorts",
                   help="shorts: big outlined words with the spoken word highlighted; box: text on a translucent box")
    p.add_argument("--font-ratio", type=float, help="font size as fraction of width (default 0.095 shorts, 0.062 box)")
    p.add_argument("--color", default="#FFFFFF", help="caption text color (shorts style)")
    p.add_argument("--highlight", default="#FFE600", help="color of the word being spoken (shorts style)")
    p.add_argument("--font", help="TTF/TTC font for the shorts style (default Arial Black)")
    p.add_argument("--no-upper", action="store_true", help="keep original casing (shorts style)")
    p.add_argument("--preview", nargs="*", type=float)
    args = p.parse_args()

    chunks = group(load_words(args.words), args.max_words)
    out = args.output or os.path.splitext(args.input)[0] + " - new subs.mp4"

    srt = os.path.splitext(out)[0] + ".srt"
    fmt = lambda s: f"{int(s // 3600):02}:{int(s % 3600 // 60):02}:{int(s % 60):02},{int(s * 1000 % 1000):03}"
    with open(srt, "w") as f:
        for n, (s, e, text, _) in enumerate(chunks, 1):
            f.write(f"{n}\n{fmt(s)} --> {fmt(e)}\n{text}\n\n")

    clip = VideoFileClip(args.input)
    font_ratio = args.font_ratio or (0.095 if args.style == "shorts" else 0.062)
    process = make_processor(chunks, args.center, args.transparency, font_ratio,
                             args.style, args.color, args.highlight, args.font, not args.no_upper)

    if args.preview:
        import cv2
        base = os.path.splitext(out)[0]
        frames = [process(clip.get_frame, t) for t in args.preview]
        row = cv2.resize(np.hstack(frames), None, fx=0.25, fy=0.25)
        cv2.imwrite(f"{base}_preview.png", cv2.cvtColor(row, cv2.COLOR_RGB2BGR))
        print("preview", f"{base}_preview.png")
        return

    clip.transform(process).write_videofile(
        out, codec="libx264", audio_codec="aac", preset="medium",
        ffmpeg_params=["-crf", "18", "-pix_fmt", "yuv420p"], logger="bar")
    print("wrote", out, "and", srt)


if __name__ == "__main__":
    main()
