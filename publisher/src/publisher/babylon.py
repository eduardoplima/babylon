"""Turn a Babylon video folder (channels/<channel>/videos/<slug>/) into a content unit."""
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import yaml

from . import media


def _field(script_md: str, label: str) -> str:
    m = re.search(rf"^\*\*{re.escape(label)}:\*\*\s*(.+)$", script_md, re.M)
    return m.group(1).strip() if m else ""


def draft_meta(video_dir: Path, taxonomy: dict[str, list[str]]) -> dict:
    """A starting meta.yaml. The user reviews it; nothing is scheduled by default."""
    slug = video_dir.name
    channel = video_dir.parent.parent.name
    short = json.loads((video_dir / "short.json").read_text()) if (video_dir / "short.json").exists() else {}
    script_md = (video_dir / "script.md").read_text() if (video_dir / "script.md").exists() else ""
    title = _field(script_md, "YouTube title") or short.get("title", slug).title()
    hook = _field(script_md, "Description, first line")
    fmt = "loop-paintings-narrated" if "loop-paintings-narrated" in taxonomy["format"] else "unclassified"
    hook_type = short.get("hook_type", "unclassified")
    return {
        "slug": slug,
        "channel": channel,
        "hook_type": hook_type if hook_type in taxonomy["hook_type"] else "unclassified",
        "format": fmt,
        "schedule": None,
        "synthetic_media": True,  # Babylon narration is a synthetic voice; review per platform policy
        "youtube": {"title": title[:100], "description": hook, "tags": [], "privacy": "private"},
        "instagram": {"caption": f"{title}\n\n{hook}".strip()},
        "tiktok": {"caption": title},
    }


def import_video(video_dir: Path, content_root: Path, taxonomy: dict[str, list[str]]) -> Path:
    """Create content/<slug>/ with master.mp4 and a draft meta.yaml (never overwrites meta.yaml).
    master.mp4 is a hardlink to final.mp4, or a lossless faststart re-mux if the moov atom is at the end."""
    final = video_dir / "final.mp4"
    if not final.exists():
        raise FileNotFoundError(final)
    dest = content_root / video_dir.name
    dest.mkdir(parents=True, exist_ok=True)
    master = dest / "master.mp4"
    if master.exists():
        master.unlink()
    if media.moov_before_mdat(final):
        try:
            os.link(final, master)
        except OSError:
            shutil.copy2(final, master)
    else:
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(final), "-c", "copy", "-map", "0",
                        "-movflags", "+faststart", str(master)], check=True)
    meta_path = dest / "meta.yaml"
    if not meta_path.exists():
        meta_path.write_text(yaml.safe_dump(draft_meta(video_dir, taxonomy), sort_keys=False, allow_unicode=True))
    return dest
