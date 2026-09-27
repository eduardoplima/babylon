"""Download public-domain books from Project Gutenberg (gutenberg.org search)
into channels/<channel>/content/texts/ and record them in the manifest.

Queries download the most-downloaded English match; use --search first to
list candidates, then --id to pick exact editions.

Usage:
    python scripts/fetch_gutenberg.py --channel roman-in-stones [--tag history] "tacitus annals" ...
    python scripts/fetch_gutenberg.py --channel roman-in-stones --search "seneca" "livy"
    python scripts/fetch_gutenberg.py --channel roman-in-stones --tag stoics --id 2680 --id 3794
"""
import argparse
import html
import os
import re
import time

import requests

import manifest

SITE = "https://www.gutenberg.org"
HEADERS = {"User-Agent": "babylon-librarian/0.1"}
BOOK = re.compile(
    r'href="/ebooks/(\d+)".*?<span class="title">(.*?)</span>(?:\s*<span class="subtitle">(.*?)</span>)?',
    re.S,
)


def get(url, **kw):
    for attempt in range(4):
        try:
            r = requests.get(url, headers=HEADERS, timeout=60, **kw)
            r.raise_for_status()
            return r
        except requests.RequestException:
            if attempt == 3:
                raise
            time.sleep(3 * (attempt + 1))


def search(query, limit=5):
    """Top English results by downloads: [{"id", "title", "author"}]."""
    page = get(f"{SITE}/ebooks/search/", params={"query": f"{query} l.en", "sort_order": "downloads"}).text
    return [
        {"id": int(i), "title": html.unescape(t), "author": html.unescape(a or "Anonymous")}
        for i, t, a in BOOK.findall(page)[:limit]
    ]


CREATOR = re.compile(r'rel="marcrel:(\w+)"[^>]*itemprop="creator">([^<]+)<')


def book_info(book_id):
    page = get(f"{SITE}/ebooks/{book_id}").text
    title = html.unescape(re.search(r'<h1 itemprop="name"[^>]*>(.*?)</h1>', page, re.S).group(1))
    people = [(role, html.unescape(name)) for role, name in CREATOR.findall(page)]
    authors = [n for r, n in people if r == "aut"] or [n for _, n in people] or ["Anonymous"]
    translators = [n for r, n in people if r == "trl"]
    title = re.sub(r"\s+by\s+[^,]+$", "", title.strip())
    return {"id": book_id, "title": title, "author": authors[0], "translator": translators[0] if translators else None}


def fetch(book_id, channel, tags):
    info = book_info(book_id)
    last = info["author"].split(",")[0]
    name = f"{manifest.slug(last, 20)}-{manifest.slug(info['title'], 50)}-{book_id}.txt"
    rel = os.path.join("texts", name)
    dest = os.path.join(manifest.content_dir(channel), rel)
    if not os.path.exists(dest):
        body = get(f"{SITE}/cache/epub/{book_id}/pg{book_id}.txt").content.decode("utf-8", "replace")
        open(dest, "w").write(body)
    return {
        "id": f"gutenberg-{book_id}",
        "kind": "text",
        "title": info["title"],
        "author": info["author"],
        "translator": info["translator"],
        "source_url": f"{SITE}/ebooks/{book_id}",
        "license": "Public domain (Project Gutenberg, US)",
        "path": rel,
        "tags": tags,
        "bytes": os.path.getsize(dest),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--channel", required=True)
    ap.add_argument("--tag", action="append", default=[])
    ap.add_argument("--search", action="store_true", help="only list candidates for each query")
    ap.add_argument("--id", type=int, action="append", default=[], help="Gutenberg ebook id to download")
    ap.add_argument("queries", nargs="*", help="download the top English result for each query")
    args = ap.parse_args()

    if args.search:
        for q in args.queries:
            print(f"# {q}")
            for b in search(q):
                print(f"  {b['id']:>6}  {b['title'][:70]}  — {b['author']}")
        return

    os.makedirs(os.path.join(manifest.content_dir(args.channel), "texts"), exist_ok=True)
    entries = manifest.load(args.channel)
    ids = list(args.id)
    for q in args.queries:
        hits = search(q, 1)
        if hits:
            ids.append(hits[0]["id"])
        else:
            print(f"NOT FOUND  {q}")
    for book_id in ids:
        entry = fetch(book_id, args.channel, args.tag)
        manifest.upsert(entries, entry)
        print(f"ok  {entry['id']:<16} {entry['bytes'] // 1024:>6} KB  {entry['author']} — {entry['title'][:70]}")
        manifest.save(args.channel, entries)


if __name__ == "__main__":
    main()
