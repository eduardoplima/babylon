import json
import os

from typer.testing import CliRunner

from publisher import babylon, content
from publisher.cli import app
from conftest import make_video


def fake_babylon_video(root, faststart=True):
    d = root / "channels" / "roman-in-stones" / "videos" / "001-tempus-edax-rerum"
    make_video(d / "final.mp4", faststart=faststart)
    (d / "short.json").write_text(json.dumps({"title": "EVERY EMPIRE GETS EATEN"}))
    (d / "script.md").write_text("**YouTube title:** Why does every empire get eaten?\n"
                                 "**Description, first line:** Because time eats everything.\n")
    return d


def test_import_creates_valid_content(tmp_path, settings):
    d = fake_babylon_video(tmp_path)
    dest = babylon.import_video(d, settings.path(settings.content_dir), settings.taxonomy)
    assert os.path.samefile(dest / "master.mp4", d / "final.mp4")  # hardlink when already faststart
    item = content.load(dest, settings)
    assert item.meta.channel == "roman-in-stones" and item.meta.schedule is None
    assert item.meta.youtube.title == "Why does every empire get eaten?"
    assert item.meta.youtube.description == "Because time eats everything."


def test_import_remuxes_when_moov_at_end(tmp_path, settings):
    from publisher import media
    d = fake_babylon_video(tmp_path, faststart=False)
    dest = babylon.import_video(d, settings.path(settings.content_dir), settings.taxonomy)
    assert media.moov_before_mdat(dest / "master.mp4")


def test_import_never_overwrites_meta(tmp_path, settings):
    d = fake_babylon_video(tmp_path)
    dest = babylon.import_video(d, settings.path(settings.content_dir), settings.taxonomy)
    (dest / "meta.yaml").write_text((dest / "meta.yaml").read_text().replace("unclassified", "foreign-quote", 1))
    babylon.import_video(d, settings.path(settings.content_dir), settings.taxonomy)
    assert "foreign-quote" in (dest / "meta.yaml").read_text()


def test_cli_validate_and_dry_run(tmp_path, settings, monkeypatch):
    d = fake_babylon_video(tmp_path)
    babylon.import_video(d, settings.path(settings.content_dir), settings.taxonomy)
    monkeypatch.setenv("PUBLISHER_HOME", str(settings.home))
    runner = CliRunner()
    res = runner.invoke(app, ["validate", "001-tempus-edax-rerum"])
    # the 1 s 270x480 test clip is fine for YouTube but below Instagram's 3 s and TikTok's 360 px
    assert res.exit_code == 1, res.output
    assert "✓ youtube" in res.output and "✗ instagram" in res.output and "✗ tiktok" in res.output
    res = runner.invoke(app, ["publish", "001-tempus-edax-rerum", "-p", "youtube"])
    assert "DRY RUN" in res.output and "dry-run: upload master.mp4" in res.output
