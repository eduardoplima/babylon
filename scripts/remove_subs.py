"""Remove burned-in captions from a video with MoviePy + OpenCV inpainting.

Captions are detected per frame inside a horizontal band as white or yellow
text with a dark outline, then filled in with cv2.inpaint.

Usage:
    python scripts/remove_subs.py INPUT.mp4 [OUTPUT.mp4] [--band 0.73 0.83] [--preview T ...]
"""
import argparse
import os

import cv2
import numpy as np
from moviepy import VideoFileClip

KERNEL_3 = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))


def caption_mask(band_rgb):
    hsv = cv2.cvtColor(band_rgb, cv2.COLOR_RGB2HSV)
    h, s, v = cv2.split(hsv)
    white = (s < 60) & (v > 200)
    yellow = (h >= 18) & (h <= 38) & (s > 110) & (v > 170)
    bright = (white | yellow).astype(np.uint8)
    dark = (v < 60).astype(np.uint8)

    # Letters are bright fill wrapped in a dark stroke. Keep only bright blobs
    # that touch that stroke, which rejects glass reflections and white objects.
    near_dark = cv2.dilate(dark, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7)))
    n, labels, stats, _ = cv2.connectedComponentsWithStats(bright, connectivity=8)
    mask = np.zeros_like(bright)
    band_h = band_rgb.shape[0]
    for i in range(1, n):
        x, y, w, hh, area = stats[i]
        if area < 15 or hh > band_h * 0.8:
            continue
        comp = labels == i
        edge_ratio = (near_dark[comp] > 0).mean()
        if edge_ratio > 0.25:
            mask[comp] = 1

    # The letters carry a thick dark stroke and drop shadow. Add every dark
    # pixel close to a detected letter, then grow to cover anti-aliasing.
    if mask.any():
        near_text = cv2.dilate(mask, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (31, 31)))
        outline = (v < 110) & (near_text > 0)
        mask = (mask.astype(bool) | outline).astype(np.uint8)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9)))
        mask = cv2.dilate(mask, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (13, 13)))
    return mask * 255


def make_processor(band):
    def process(frame):
        H = frame.shape[0]
        y0, y1 = int(H * band[0]), int(H * band[1])
        region = frame[y0:y1]
        mask = caption_mask(region)
        if not mask.any():
            return frame
        out = frame.copy()
        # Inpaint with some context above/below the band.
        pad = 40
        a, b = max(0, y0 - pad), min(H, y1 + pad)
        full_mask = np.zeros(frame.shape[:2], np.uint8)
        full_mask[y0:y1] = mask
        bgr = cv2.cvtColor(frame[a:b], cv2.COLOR_RGB2BGR)
        fixed = cv2.inpaint(bgr, full_mask[a:b], 9, cv2.INPAINT_TELEA)
        out[a:b] = cv2.cvtColor(fixed, cv2.COLOR_BGR2RGB)
        return out
    return process


def main():
    p = argparse.ArgumentParser()
    p.add_argument("input")
    p.add_argument("output", nargs="?")
    p.add_argument("--band", nargs=2, type=float, default=[0.73, 0.83],
                   help="caption band as fractions of frame height")
    p.add_argument("--preview", nargs="*", type=float,
                   help="write before/after PNGs for these timestamps instead of a video")
    args = p.parse_args()

    clip = VideoFileClip(args.input)
    process = make_processor(args.band)

    if args.preview:
        base = os.path.splitext(args.output or args.input)[0]
        for t in args.preview:
            before = clip.get_frame(t)
            after = process(before)
            H = before.shape[0]
            y0, y1 = int(H * args.band[0]), int(H * args.band[1])
            m = caption_mask(before[y0:y1])
            m3 = np.zeros_like(before); m3[y0:y1, :, 0] = m
            row = np.hstack([before, cv2.addWeighted(before, 1, m3, 0.8, 0), after])
            row = cv2.resize(row, None, fx=0.25, fy=0.25)
            cv2.imwrite(f"{base}_preview_{t:g}.png", cv2.cvtColor(row, cv2.COLOR_RGB2BGR))
        return

    out = args.output or os.path.splitext(args.input)[0] + " - no subs.mp4"
    clip.image_transform(process).write_videofile(
        out, codec="libx264", audio_codec="aac", preset="medium",
        ffmpeg_params=["-crf", "18", "-pix_fmt", "yuv420p"], logger="bar")
    print("wrote", out)


if __name__ == "__main__":
    main()
