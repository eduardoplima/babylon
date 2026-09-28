"""Temporary public hosting for media, for platforms that pull a video from a URL.

None of the current adapters need it: YouTube and TikTok take the bytes directly, and
Instagram Reels accept a local file through resumable upload. The interface exists so a
URL-based path (Instagram `video_url`, TikTok `PULL_FROM_URL`) can be added later with an
S3-compatible backend chosen by the user.
"""
from pathlib import Path
from typing import Protocol


class MediaHost(Protocol):
    def put(self, path: Path, key: str, ttl_seconds: int) -> str:
        """Upload `path` and return a URL that is publicly readable for at least `ttl_seconds`."""

    def delete(self, key: str) -> None:
        """Remove the object once the platform has finished fetching it."""
