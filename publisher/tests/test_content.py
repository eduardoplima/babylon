from datetime import datetime

import pytest
import yaml

from publisher import content
from conftest import write_content


def test_valid_meta_loads_and_localizes_schedule(settings, vertical_video):
    d = write_content(settings, "001-test", vertical_video)
    item = content.load(d, settings)
    assert item.meta.platforms() == ["youtube"]
    assert item.meta.youtube.privacy == "private"  # private by default
    at = item.meta.schedule_at(settings.tz)
    assert at.utcoffset().total_seconds() == -3 * 3600  # America/Sao_Paulo
    assert at.replace(tzinfo=None) == datetime(2026, 10, 1, 18, 0)


def test_unknown_field_rejected(settings, vertical_video):
    d = write_content(settings, "001-test", vertical_video, colour="red")
    with pytest.raises(content.ContentError, match="colour"):
        content.load(d, settings)


def test_hook_type_must_be_in_taxonomy(settings, vertical_video):
    d = write_content(settings, "001-test", vertical_video, hook_type="clickbait")
    with pytest.raises(content.ContentError, match="hook_type 'clickbait'"):
        content.load(d, settings)


def test_slug_must_match_folder(settings, vertical_video):
    d = write_content(settings, "001-test", vertical_video, slug="other")
    with pytest.raises(content.ContentError, match="must match folder"):
        content.load(d, settings)


def test_platform_text_limits(settings, vertical_video):
    d = write_content(settings, "001-test", vertical_video,
                      youtube={"title": "x" * 101},
                      instagram={"caption": " ".join(f"#t{i}" for i in range(31))})
    with pytest.raises(content.ContentError) as exc:
        content.load(d, settings)
    assert "youtube.title is 101 chars" in str(exc.value)
    assert "more than 30 hashtags" in str(exc.value)


def test_load_all_reports_invalid_without_stopping(settings, vertical_video):
    write_content(settings, "001-good", vertical_video)
    bad = write_content(settings, "002-bad", vertical_video)
    (bad / "meta.yaml").write_text(yaml.safe_dump({"slug": "002-bad"}))
    items, errors = content.load_all(settings)
    assert [i.slug for i in items] == ["001-good"]
    assert len(errors) == 1 and "002-bad" in errors[0]
