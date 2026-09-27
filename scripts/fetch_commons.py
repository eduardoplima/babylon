"""Download public-domain / CC0 images from Wikimedia Commons into
channels/<channel>/content/art/ and record them in the manifest.

Arguments are exact file titles ("File:Cole Thomas The Course of Empire
Desolation 1836.jpg") or search terms (the top --per-search results that pass
the license and size filters are kept).

Usage:
    python scripts/fetch_commons.py --channel roman-in-stones --tag ruins "File:..." "thomas cole course of empire"
    python scripts/fetch_commons.py --search "hubert robert ruins"    # list candidates only
"""
import argparse
import html
import os
import re
import time

import requests

import manifest

API = "https://commons.wikimedia.org/w/api.php"
HEADERS = {"User-Agent": "babylon-librarian/0.1 (https://github.com/; research use)"}
FREE = re.compile(r"public domain|^pd\b|^pd-|cc0", re.I)


def get(url, **kw):
    for attempt in range(5):
        try:
            r = requests.get(url, headers=HEADERS, timeout=90, **kw)
            if r.status_code == 429:
                raise requests.RequestException("rate limited")
            r.raise_for_status()
            return r
        except requests.RequestException:
            if attempt == 4:
                raise
            time.sleep(5 * (attempt + 1))


def strip(text):
    return html.unescape(re.sub(r"<[^>]+>", "", str(text or ""))).strip()


def clean_title(desc, file_title):
    """Commons ObjectName often carries Wikidata junk ("title QS:...", "label
    QS:...", "French: ...") or is non-Latin; fall back to the file name."""
    t = re.split(r"\s*(?:title|label) QS:", desc or "")[0]
    t = re.sub(r"^[A-Z][a-z]+:\s+", "", t).strip(" .")
    if not re.search(r"[A-Za-z]{3}", t):
        t = re.sub(r"\.\w+$", "", file_title.removeprefix("File:"))
    return t


def info(titles, width):
    params = {
        "action": "query", "format": "json", "titles": "|".join(titles),
        "prop": "imageinfo", "iiprop": "url|size|extmetadata|mime", "iiurlwidth": width,
    }
    pages = get(API, params=params).json()["query"]["pages"].values()
    out = []
    for p in pages:
        if "imageinfo" not in p:
            continue
        ii = p["imageinfo"][0]
        meta = {k: strip(v.get("value")) for k, v in ii.get("extmetadata", {}).items()}
        out.append({
            "title": p["title"], "mime": ii["mime"], "w": ii["width"], "h": ii["height"],
            "url": (ii.get("thumburl") if ii["mime"].startswith("image/") else None) or ii["url"], "page": ii["descriptionurl"],
            "license": meta.get("LicenseShortName", ""), "artist": meta.get("Artist", ""),
            "desc": clean_title(meta.get("ObjectName") or meta.get("ImageDescription", ""), p["title"]),
            "date": meta.get("DateTimeOriginal", ""),
        })
    return out


def search(query, limit, filetype="bitmap"):
    params = {"action": "query", "format": "json", "list": "search", "srsearch": f"{query} filetype:{filetype}",
              "srnamespace": 6, "srlimit": limit}
    return [r["title"] for r in get(API, params=params).json()["query"]["search"]]


def ok(img, min_side):
    if not FREE.search(img["license"]):
        return False
    if img["mime"].startswith("audio/") or img["mime"] == "application/ogg":
        return True
    return max(img["w"], img["h"]) >= min_side and img["mime"] in ("image/jpeg", "image/png", "image/tiff")


def save(img, channel, tags):
    base = manifest.slug(re.sub(r"\.\w+$", "", img["title"].removeprefix("File:")), 80)
    audio = not img["mime"].startswith("image/")
    rel = os.path.join("music", base + os.path.splitext(img["url"].split("?")[0])[1].lower()) if audio else os.path.join("art", base + ".jpg")
    dest = os.path.join(manifest.content_dir(channel), rel)
    if not os.path.exists(dest):
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        data = get(img["url"]).content
        if not audio and not img["url"].lower().endswith((".jpg", ".jpeg")):
            from io import BytesIO
            from PIL import Image
            Image.open(BytesIO(data)).convert("RGB").save(dest, quality=92)
        else:
            open(dest, "wb").write(data)
        time.sleep(1)
    return {
        "id": "commons-" + base,
        "kind": "audio" if audio else "image",
        "title": img["desc"][:200] or img["title"],
        "author": img["artist"][:120],
        "date": img["date"][:40],
        "source_url": img["page"],
        "license": img["license"],
        "path": rel,
        "tags": tags,
        "size": [img["w"], img["h"]],
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--channel")
    ap.add_argument("--tag", action="append", default=[])
    ap.add_argument("--search", action="store_true", help="only list candidates")
    ap.add_argument("--per-search", type=int, default=3)
    ap.add_argument("--min-side", type=int, default=1600)
    ap.add_argument("--width", type=int, default=2400, help="download width (thumbnail) in px")
    ap.add_argument("--audio", action="store_true", help="search audio files instead of images")
    ap.add_argument("items", nargs="+")
    args = ap.parse_args()

    entries = manifest.load(args.channel) if args.channel else []
    if args.channel:
        os.makedirs(os.path.join(manifest.content_dir(args.channel), "art"), exist_ok=True)
    for item in args.items:
        titles = [item] if item.startswith("File:") else search(item, 12, "audio" if args.audio else "bitmap")
        imgs = info(titles, args.width) if titles else []
        imgs.sort(key=lambda i: titles.index(i["title"]) if i["title"] in titles else 99)
        if args.search:
            print(f"# {item}")
            for i in imgs:
                flag = "OK " if ok(i, args.min_side) else "-- "
                print(f"  {flag}{i['w']}x{i['h']}  {i['license'][:18]:<18} {i['title']}  | {i['artist'][:40]}")
            continue
        kept = [i for i in imgs if ok(i, args.min_side)][: 1 if item.startswith("File:") else args.per_search]
        if not kept:
            print(f"NOT FOUND / not free  {item}")
        for img in kept:
            entry = save(img, args.channel, args.tag)
            manifest.upsert(entries, entry)
            print(f"ok  {entry['path']}  ({entry['license']})")
        if args.channel:
            manifest.save(args.channel, entries)


if __name__ == "__main__":
    main()
