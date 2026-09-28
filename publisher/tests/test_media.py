from publisher import media
from conftest import make_video


def test_probe_vertical(vertical_video):
    info = media.probe(vertical_video)
    assert (info.width, info.height, info.orientation) == (270, 480, "vertical")
    assert info.video_codec == "h264" and info.audio_codec == "aac"
    assert info.audio_sample_rate == 48000
    assert 0.9 < info.duration_s < 1.2 and info.fps == 30
    assert info.faststart is True


def test_youtube_limits_accept_vertical(vertical_video, settings):
    issues = media.check(media.probe(vertical_video), settings.platform("youtube")["limits"])
    assert issues == []


def test_horizontal_rejected_for_shorts(tmp_path, settings):
    info = media.probe(make_video(tmp_path / "h.mp4", w=480, h=270))
    issues = media.check(info, settings.platform("youtube")["limits"])
    assert any("horizontal video" in i.message for i in issues)


def test_too_long_uses_margin(vertical_video):
    info = media.probe(vertical_video)
    issues = media.check(info, {"max_duration_s": 1.5, "duration_margin_s": 1})
    assert [i.level for i in issues] == ["error"] and "exceeds 0.5s" in issues[0].message


def test_faststart_detection(tmp_path):
    slow = make_video(tmp_path / "slow.mp4", faststart=False)
    assert media.moov_before_mdat(slow) is False
    issues = media.check(media.probe(slow), {"require_faststart": True})
    assert [i.level for i in issues] == ["warning"]


def test_instagram_limits(vertical_video, settings):
    # 1 s is below Instagram's 3 s minimum
    issues = media.check(media.probe(vertical_video), settings.platform("instagram")["limits"])
    assert any("below 3s" in i.message for i in issues)
