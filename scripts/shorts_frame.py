"""Build a channel's branded 9:16 Shorts frame (PNG with a transparent video window).

Starts from the brand kit's blank frame and draws the series line, the title,
the handle and the follow line in the kit's fonts and colours (sizes and
positions measured from the kit's example frame).

Usage:
    python scripts/shorts_frame.py --channel roman-in-stones OUT.png \
        --series "PART 1 · TIME AND RUIN" --title "TEMPUS EDAX RERUM" \
        [--handle @romansinstone] [--follow "FOLLOW FOR MORE OF ANCIENT ROME"]
"""
import argparse
import os

from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Layout measured from assets/kit/shorts-9x16-example.png (1080x1920).
WINDOW = (0, 440, 1080, 1080)  # x, y, w, h of the transparent video window
SERIES = dict(font="Barlow-SemiBold.ttf", cap=21, top=186, color="#E3C47E", track=0.215)
TITLE = dict(font="Cinzel.ttf", weight="Bold", cap=53, top=244, pitch=83, color="#EFE6D3", track=0.0, max_w=960)
HANDLE = dict(font="Barlow-Medium.ttf", cap=29, top=1611, color="#A99F8C", track=0.0)
FOLLOW = dict(font="Barlow-SemiBold.ttf", cap=18, top=1669, color="#C9A45C", track=0.17)


def load_font(path, cap, weight=None):
    """Font sized so capital letters are `cap` pixels tall."""
    size = cap
    for _ in range(3):
        f = ImageFont.truetype(path, size)
        if weight:
            f.set_variation_by_name(weight)
        l, t, r, b = f.getbbox("H")
        size = max(4, round(size * cap / (b - t)))
    f = ImageFont.truetype(path, size)
    if weight:
        f.set_variation_by_name(weight)
    return f


def text_width(font, text, track):
    extra = track * font.size * (len(text) - 1)
    return font.getlength(text) + extra


def draw_line(draw, font, text, cap_top, color, track, width=1080):
    x = (width - text_width(font, text, track)) / 2
    top = font.getbbox("H")[1]  # distance from draw origin to cap top
    y = cap_top - top
    for ch in text:
        draw.text((x, y), ch, font=font, fill=color)
        x += font.getlength(ch) + track * font.size


def wrap(font, text, max_w, track):
    """One line if it fits, else the two-line split with the most even widths."""
    if text_width(font, text, track) <= max_w:
        return [text]
    words = text.split()
    splits = [[" ".join(words[:i]), " ".join(words[i:])] for i in range(1, len(words))]
    best = min(splits, key=lambda ls: max(text_width(font, l, track) for l in ls), default=[text])
    return best


def build(kit, fonts, series, title, handle, follow):
    frame = Image.open(os.path.join(kit, "shorts-9x16-blank.png")).convert("RGBA")
    d = ImageDraw.Draw(frame)
    f = lambda spec: load_font(os.path.join(fonts, spec["font"]), spec["cap"], spec.get("weight"))

    if series:
        draw_line(d, f(SERIES), series.upper().replace(" · ", "  ·  "), SERIES["top"], SERIES["color"], SERIES["track"])
    if title:
        cap = TITLE["cap"]
        font = f(TITLE)
        lines = wrap(font, title.upper(), TITLE["max_w"], 0)
        while len(lines) > 2 or max(text_width(font, l, 0) for l in lines) > TITLE["max_w"]:
            cap -= 2  # shrink until it fits in two lines
            font = load_font(os.path.join(fonts, TITLE["font"]), cap, TITLE["weight"])
            lines = wrap(font, title.upper(), TITLE["max_w"], 0)
        # two lines sit where the kit puts them; a single line is centred in that block
        block_top, block_bottom = TITLE["top"], TITLE["top"] + TITLE["pitch"] + TITLE["cap"]
        pitch = TITLE["pitch"] * cap / TITLE["cap"]
        height = cap + pitch * (len(lines) - 1)
        top = (block_top + block_bottom - height) / 2
        for i, line in enumerate(lines):
            draw_line(d, font, line, top + i * pitch, TITLE["color"], 0)
    if handle:
        draw_line(d, f(HANDLE), handle, HANDLE["top"], HANDLE["color"], HANDLE["track"])
    if follow:
        draw_line(d, f(FOLLOW), follow.upper(), FOLLOW["top"], FOLLOW["color"], FOLLOW["track"])
    return frame


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--channel", required=True)
    ap.add_argument("output")
    ap.add_argument("--series", default="")
    ap.add_argument("--title", default="")
    ap.add_argument("--handle", default="@romansinstone")
    ap.add_argument("--follow", default="FOLLOW FOR MORE OF ANCIENT ROME")
    args = ap.parse_args()
    assets = os.path.join(ROOT, "channels", args.channel, "assets")
    frame = build(os.path.join(assets, "kit"), os.path.join(assets, "fonts"),
                  args.series, args.title, args.handle, args.follow)
    frame.save(args.output)
    print(f"wrote {args.output}  (video window x={WINDOW[0]} y={WINDOW[1]} {WINDOW[2]}x{WINDOW[3]})")


if __name__ == "__main__":
    main()
