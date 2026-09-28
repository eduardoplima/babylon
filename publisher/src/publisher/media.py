"""Inspect a video with ffprobe and check it against a platform's limits."""
import json
import struct
import subprocess
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class MediaInfo:
    path: Path
    width: int
    height: int
    duration_s: float
    fps: float
    video_codec: str
    audio_codec: str | None
    audio_sample_rate: int | None
    size_bytes: int
    format_name: str
    faststart: bool | None  # None when the container isn't MP4/MOV

    @property
    def orientation(self) -> str:
        if self.width == self.height:
            return "square"
        return "vertical" if self.height > self.width else "horizontal"


@dataclass(frozen=True)
class Issue:
    level: str  # "error" | "warning"
    message: str

    def __str__(self) -> str:
        return f"{self.level}: {self.message}"


def probe(path: Path) -> MediaInfo:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)],
        capture_output=True, text=True, check=True).stdout
    data = json.loads(out)
    v = next(s for s in data["streams"] if s["codec_type"] == "video")
    a = next((s for s in data["streams"] if s["codec_type"] == "audio"), None)
    width, height = int(v["width"]), int(v["height"])
    if _rotation(v) in (90, 270):
        width, height = height, width
    rate = v.get("avg_frame_rate") or v.get("r_frame_rate") or "0/1"
    fps = float(Fraction(rate)) if rate != "0/0" else 0.0
    return MediaInfo(
        path=path, width=width, height=height,
        duration_s=float(data["format"].get("duration") or v.get("duration") or 0),
        fps=round(fps, 3), video_codec=v["codec_name"],
        audio_codec=a["codec_name"] if a else None,
        audio_sample_rate=int(a["sample_rate"]) if a and a.get("sample_rate") else None,
        size_bytes=int(data["format"].get("size") or path.stat().st_size),
        format_name=data["format"]["format_name"],
        faststart=moov_before_mdat(path) if "mp4" in data["format"]["format_name"] else None,
    )


def _rotation(stream: dict[str, Any]) -> int:
    for sd in stream.get("side_data_list", []):
        if "rotation" in sd:
            return abs(int(sd["rotation"])) % 360
    return abs(int(stream.get("tags", {}).get("rotate", 0))) % 360


def moov_before_mdat(path: Path) -> bool:
    """True if the top-level 'moov' box comes before 'mdat' (MP4 'faststart')."""
    with open(path, "rb") as f:
        while header := f.read(8):
            if len(header) < 8:
                break
            size, kind = struct.unpack(">I4s", header)
            if kind == b"moov":
                return True
            if kind == b"mdat":
                return False
            if size == 1:  # 64-bit size follows
                size = struct.unpack(">Q", f.read(8))[0]
                f.seek(size - 16, 1)
            elif size == 0:  # box runs to end of file
                break
            else:
                f.seek(size - 8, 1)
    return False


def check(info: MediaInfo, limits: dict[str, Any]) -> list[Issue]:
    """Compare media against a platform's `limits` block from platforms.yaml.
    Only the limits present in the block are checked."""
    issues: list[Issue] = []
    err = lambda msg: issues.append(Issue("error", msg))

    if "orientations" in limits and info.orientation not in limits["orientations"]:
        err(f"{info.orientation} video ({info.width}x{info.height}); allowed: {', '.join(limits['orientations'])}")
    if "max_duration_s" in limits:
        cap = limits["max_duration_s"] - limits.get("duration_margin_s", 0)
        if info.duration_s > cap:
            err(f"duration {info.duration_s:.1f}s exceeds {cap}s")
    if "min_duration_s" in limits and info.duration_s < limits["min_duration_s"]:
        err(f"duration {info.duration_s:.1f}s is below {limits['min_duration_s']}s")
    if "video_codecs" in limits and info.video_codec not in limits["video_codecs"]:
        err(f"video codec {info.video_codec} not in {limits['video_codecs']}")
    if "audio_codecs" in limits:
        if info.audio_codec is None:
            err("no audio stream")
        elif info.audio_codec not in limits["audio_codecs"]:
            err(f"audio codec {info.audio_codec} not in {limits['audio_codecs']}")
    if "audio_max_sample_rate" in limits and (info.audio_sample_rate or 0) > limits["audio_max_sample_rate"]:
        err(f"audio sample rate {info.audio_sample_rate} Hz above {limits['audio_max_sample_rate']} Hz")
    if "min_fps" in limits and info.fps < limits["min_fps"]:
        err(f"{info.fps} fps below {limits['min_fps']}")
    if "max_fps" in limits and info.fps > limits["max_fps"]:
        err(f"{info.fps} fps above {limits['max_fps']}")
    if "max_width" in limits and info.width > limits["max_width"]:
        err(f"width {info.width}px above {limits['max_width']}px")
    if "min_side" in limits and min(info.width, info.height) < limits["min_side"]:
        err(f"{info.width}x{info.height} below {limits['min_side']}px")
    if "max_side" in limits and max(info.width, info.height) > limits["max_side"]:
        err(f"{info.width}x{info.height} above {limits['max_side']}px")
    if "max_size_bytes" in limits and info.size_bytes > limits["max_size_bytes"]:
        err(f"file is {info.size_bytes / 1e6:.0f} MB, above {limits['max_size_bytes'] / 1e6:.0f} MB")
    if limits.get("require_faststart") and info.faststart is False:
        issues.append(Issue("warning", "moov atom is not at the front (re-mux with ffmpeg -movflags +faststart)"))
    return issues
