"""Shared helpers for a channel's content/manifest.json and INDEX.md."""
import json
import os
import re
import unicodedata

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def content_dir(channel):
    return os.path.join(ROOT, "channels", channel, "content")


def slug(text, n=60):
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:n].strip("-")


def load(channel):
    path = os.path.join(content_dir(channel), "manifest.json")
    return json.load(open(path)) if os.path.exists(path) else []


def save(channel, entries):
    entries.sort(key=lambda e: (e["kind"], e["path"]))
    path = os.path.join(content_dir(channel), "manifest.json")
    json.dump(entries, open(path, "w"), indent=1, ensure_ascii=False)
    write_index(channel, entries)


def upsert(entries, entry):
    for i, e in enumerate(entries):
        if e["id"] == entry["id"]:
            entries[i] = entry
            return
    entries.append(entry)


def write_index(channel, entries):
    lines = [f"# Content library — {channel}", "", "Generated from manifest.json.", ""]
    for kind in sorted({e["kind"] for e in entries}):
        items = [e for e in entries if e["kind"] == kind]
        lines += [f"## {kind} ({len(items)})", "", "| Title | Author | License | Tags | File |", "|---|---|---|---|---|"]
        for e in sorted(items, key=lambda e: (e.get("author") or "", e["title"])):
            title = e["title"].replace("|", "/").replace("\n", " ")[:90]
            author = (e.get("author") or "").replace("|", "/")
            lines.append(f"| [{title}]({e['source_url']}) | {author} | {e['license']} | {', '.join(e.get('tags', []))} | `{e['path']}` |")
        lines.append("")
    open(os.path.join(content_dir(channel), "INDEX.md"), "w").write("\n".join(lines))
