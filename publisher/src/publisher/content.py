"""The content unit: content/<slug>/master.mp4 + meta.yaml, validated with Pydantic."""
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from .settings import Settings

PLATFORMS = ("youtube", "instagram", "tiktok")


class ContentError(Exception):
    pass


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class YouTubeMeta(_Strict):
    title: str = Field(min_length=1)
    description: str = ""
    tags: list[str] = []
    category_id: str = "27"  # Education
    privacy: Literal["private", "unlisted", "public"] = "private"
    made_for_kids: bool = False
    notify_subscribers: bool = False


class InstagramMeta(_Strict):
    caption: str = ""
    share_to_feed: bool = True
    thumb_offset_ms: int | None = Field(default=None, ge=0)


class TikTokMeta(_Strict):
    caption: str = ""


class Meta(_Strict):
    slug: str = Field(pattern=r"^[a-z0-9][a-z0-9-]*$")
    channel: str
    hook_type: str
    format: str
    schedule: datetime | None = None
    synthetic_media: bool = False
    youtube: YouTubeMeta | None = None
    instagram: InstagramMeta | None = None
    tiktok: TikTokMeta | None = None

    @field_validator("schedule")
    @classmethod
    def _no_seconds_needed(cls, v: datetime | None) -> datetime | None:
        return v.replace(microsecond=0) if v else v

    def platforms(self) -> list[str]:
        return [p for p in PLATFORMS if getattr(self, p) is not None]

    def schedule_at(self, tz: ZoneInfo) -> datetime | None:
        """Schedule as an aware datetime; naive values are local time in `tz`."""
        if self.schedule is None:
            return None
        return self.schedule if self.schedule.tzinfo else self.schedule.replace(tzinfo=tz)


def check_metadata(meta: Meta, settings: Settings) -> list[str]:
    """Rules that depend on config: taxonomy values and per-platform text limits."""
    problems = []
    tax = settings.taxonomy
    if meta.hook_type not in tax["hook_type"]:
        problems.append(f"hook_type '{meta.hook_type}' not in taxonomy {tax['hook_type']}")
    if meta.format not in tax["format"]:
        problems.append(f"format '{meta.format}' not in taxonomy {tax['format']}")
    if meta.youtube:
        m = settings.platform("youtube")["metadata"]
        if len(meta.youtube.title) > m["title_max"]:
            problems.append(f"youtube.title is {len(meta.youtube.title)} chars (max {m['title_max']})")
        if len(meta.youtube.description.encode()) > m["description_max"]:
            problems.append(f"youtube.description exceeds {m['description_max']} bytes")
        # TODO(verificar): how YouTube counts the 500 characters (separators? quotes around
        # tags with spaces?) is not spelled out; this counts tag text plus one comma between tags.
        tag_chars = sum(len(t) for t in meta.youtube.tags) + max(0, len(meta.youtube.tags) - 1)
        if tag_chars > m["tags_max_chars"]:
            problems.append(f"youtube.tags use {tag_chars} chars (max {m['tags_max_chars']})")
    if meta.instagram:
        m = settings.platform("instagram")["metadata"]
        cap = meta.instagram.caption
        if len(cap) > m["caption_max"]:
            problems.append(f"instagram.caption is {len(cap)} chars (max {m['caption_max']})")
        if len(re.findall(r"#\w+", cap)) > m["hashtags_max"]:
            problems.append(f"instagram.caption has more than {m['hashtags_max']} hashtags")
        if len(re.findall(r"@\w+", cap)) > m["mentions_max"]:
            problems.append(f"instagram.caption has more than {m['mentions_max']} @mentions")
    if meta.tiktok:
        m = settings.platform("tiktok")["metadata"]
        if len(meta.tiktok.caption.encode("utf-16-le")) // 2 > m["caption_max"]:
            problems.append(f"tiktok.caption exceeds {m['caption_max']} UTF-16 units")
    return problems


@dataclass(frozen=True)
class ContentItem:
    dir: Path
    meta: Meta

    @property
    def slug(self) -> str:
        return self.meta.slug

    @property
    def video(self) -> Path:
        return self.dir / "master.mp4"


def load(dir: Path, settings: Settings) -> ContentItem:
    meta_path = dir / "meta.yaml"
    if not meta_path.exists():
        raise ContentError(f"{meta_path} not found")
    try:
        meta = Meta.model_validate(yaml.safe_load(meta_path.read_text()) or {})
    except ValidationError as exc:
        raise ContentError(f"{meta_path}: {exc}") from exc
    if meta.slug != dir.name:
        raise ContentError(f"{meta_path}: slug '{meta.slug}' must match folder name '{dir.name}'")
    problems = check_metadata(meta, settings)
    if problems:
        raise ContentError(f"{meta_path}: " + "; ".join(problems))
    item = ContentItem(dir=dir, meta=meta)
    if not item.video.exists():
        raise ContentError(f"{item.video} not found")
    return item


def load_all(settings: Settings) -> tuple[list[ContentItem], list[str]]:
    """Every valid content unit, plus error messages for the invalid ones."""
    items, errors = [], []
    root = settings.path(settings.content_dir)
    for d in sorted(p for p in root.iterdir() if p.is_dir()) if root.exists() else []:
        try:
            items.append(load(d, settings))
        except ContentError as exc:
            errors.append(str(exc))
    return items, errors
