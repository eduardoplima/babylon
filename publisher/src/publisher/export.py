"""CSV export: latest metrics per publication, joined with meta.yaml's hook_type and format."""
import csv
import sqlite3
from datetime import datetime
from typing import IO

from . import db
from .content import ContentItem

# Comparable columns across platforms. A metric missing on a platform stays empty rather than
# being approximated (e.g. TikTok has no watch time; Instagram's watch-time unit is undocumented).
CANONICAL = {
    "views":            {"youtube": "views", "instagram": "views", "tiktok": "view_count"},
    "likes":            {"youtube": "likes", "instagram": "likes", "tiktok": "like_count"},
    "comments":         {"youtube": "comments", "instagram": "comments", "tiktok": "comment_count"},
    "shares":           {"youtube": "shares", "instagram": "shares", "tiktok": "share_count"},
    "engaged_views":    {"youtube": "engagedViews"},
    "avg_view_seconds": {"youtube": "averageViewDuration"},
    "avg_view_percent": {"youtube": "averageViewPercentage"},
    "saves":            {"instagram": "saved"},
    "reach":            {"instagram": "reach"},
    "skip_rate":        {"instagram": "reels_skip_rate"},
}
# YouTube Analytics lags 48–72 h; until it has data, fall back to the Data API counters.
FALLBACK = {"youtube": {"views": "viewCount", "likes": "likeCount", "comments": "commentCount"}}

BASE = ["slug", "channel", "hook_type", "format", "platform", "state", "remote_id", "remote_url",
        "published_at", "collected_at", "hours_since_publish"]


def rows(conn: sqlite3.Connection, items: dict[str, ContentItem]) -> tuple[list[str], list[dict]]:
    latest = db.latest_metrics(conn)
    raw_names: set[str] = set()
    out = []
    for pub in db.all_publications(conn):
        collected_at, values = latest.get(pub["id"], (None, {}))
        meta = items[pub["slug"]].meta if pub["slug"] in items else None
        row = {
            "slug": pub["slug"], "channel": meta.channel if meta else "", "hook_type": meta.hook_type if meta else "",
            "format": meta.format if meta else "", "platform": pub["platform"], "state": pub["state"],
            "remote_id": pub["remote_id"] or "", "remote_url": pub["remote_url"] or "",
            "published_at": pub["published_at"] or "", "collected_at": collected_at or "",
            "hours_since_publish": _hours(pub["published_at"], collected_at),
        }
        for col, per_platform in CANONICAL.items():
            key = per_platform.get(pub["platform"])
            value = values.get(key) if key else None
            if value is None:
                value = values.get(FALLBACK.get(pub["platform"], {}).get(col, ""))
            row[col] = _fmt(value)
        for k, v in values.items():
            raw_names.add(f"{pub['platform']}.{k}")
            row[f"{pub['platform']}.{k}"] = _fmt(v)
        out.append(row)
    return BASE + list(CANONICAL) + sorted(raw_names), out


def write(conn: sqlite3.Connection, items: dict[str, ContentItem], fh: IO[str]) -> int:
    header, data = rows(conn, items)
    w = csv.DictWriter(fh, fieldnames=header, restval="")
    w.writeheader()
    w.writerows(data)
    return len(data)


def _fmt(v: float | None) -> str:
    if v is None:
        return ""
    return str(int(v)) if float(v).is_integer() else f"{v:.4f}".rstrip("0")


def _hours(published_at: str | None, collected_at: str | None) -> str:
    if not published_at or not collected_at:
        return ""
    delta = datetime.fromisoformat(collected_at) - datetime.fromisoformat(published_at)
    return f"{delta.total_seconds() / 3600:.1f}"
