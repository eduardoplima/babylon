import io
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

from publisher import db, log
from publisher.settings import Settings

ROOT = Path(__file__).resolve().parents[1]


def make_video(path: Path, w: int = 270, h: int = 480, seconds: float = 1.0, faststart: bool = True) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    cmd = ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"testsrc=size={w}x{h}:rate=30:duration={seconds}",
           "-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}:sample_rate=48000",
           "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest"]
    if faststart:
        cmd += ["-movflags", "+faststart"]
    subprocess.run(cmd + [str(path)], check=True)
    return path


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """No test may reach the network: respx intercepts httpx before sockets, so any real
    connection attempt (httpx unmocked, requests, google-auth) fails loudly."""
    import socket

    real_connect, real_create = socket.socket.connect, socket.create_connection
    loopback = lambda address: isinstance(address, tuple) and address[0] in ("127.0.0.1", "localhost")

    def connect(self, address):
        if not loopback(address):  # only local OAuth callback servers are reachable
            raise RuntimeError("network access in tests is forbidden; mock it with respx")
        return real_connect(self, address)

    def create_connection(address, *args, **kwargs):
        if not loopback(address):
            raise RuntimeError("network access in tests is forbidden; mock it with respx")
        return real_create(address, *args, **kwargs)

    monkeypatch.setattr(socket.socket, "connect", connect)
    monkeypatch.setattr(socket, "create_connection", create_connection)


@pytest.fixture(scope="session")
def vertical_video(tmp_path_factory) -> Path:
    return make_video(tmp_path_factory.mktemp("v") / "vertical.mp4")


@pytest.fixture
def settings(tmp_path) -> Settings:
    (tmp_path / "config").mkdir()
    shutil.copy(ROOT / "config" / "platforms.yaml", tmp_path / "config" / "platforms.yaml")
    (tmp_path / "content").mkdir()
    return Settings(home=tmp_path, _env_file=None)


@pytest.fixture
def conn(settings):
    c = db.connect(settings.path(settings.db_path))
    yield c
    c.close()


@pytest.fixture
def logs():
    buf = io.StringIO()
    log.configure(stream=buf)
    return buf


def write_content(settings: Settings, folder: str, video: Path, **overrides) -> Path:
    d = settings.path(settings.content_dir) / folder
    d.mkdir(parents=True, exist_ok=True)
    shutil.copy(video, d / "master.mp4")
    meta = {
        "slug": folder, "channel": "roman-in-stones", "hook_type": "foreign-quote", "format": "loop-paintings-narrated",
        "schedule": "2026-10-01T18:00", "synthetic_media": True,
        "youtube": {"title": "Why does every empire get eaten?", "description": "Time eats everything.",
                    "tags": ["ancient rome", "ovid"]},
    }
    meta.update(overrides)
    (d / "meta.yaml").write_text(yaml.safe_dump(meta, sort_keys=False))
    return d
