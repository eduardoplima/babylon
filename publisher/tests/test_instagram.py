import json
from datetime import datetime, timedelta, timezone

import httpx
import pytest
import respx

from publisher import content, db, service
from publisher.platforms.base import AuthRequired
from publisher.platforms.instagram import Instagram, InstagramAuth
from publisher.tokens import TokenStore
from conftest import make_video, write_content

GRAPH = "graph.instagram.com"
NOW = datetime(2026, 10, 2, 12, 0, tzinfo=timezone.utc)
noop = lambda s: None


class FakeAuth:
    def token(self, force=False):
        return "tok"

    def user_id(self):
        return "IGID"


@pytest.fixture(scope="module")
def reel_video(tmp_path_factory):
    return make_video(tmp_path_factory.mktemp("ig") / "reel.mp4", w=360, h=640, seconds=4)


@pytest.fixture
def item(settings, reel_video):
    d = write_content(settings, "001-test", reel_video, youtube=None,
                      instagram={"caption": "Every empire gets eaten. #ancientrome", "thumb_offset_ms": 1000})
    return content.load(d, settings)


@pytest.fixture
def ig(settings):
    return Instagram(settings.platform("instagram"), FakeAuth(), http=httpx.Client(), sleep=noop)


@pytest.fixture
def api():
    with respx.mock(assert_all_mocked=True, assert_all_called=False) as r:
        r.create = r.route(method="POST", host=GRAPH, path="/v25.0/IGID/media")
        r.upload = r.route(method="POST", host="rupload.facebook.com", path__startswith="/ig-api-upload/v25.0/")
        r.status = r.route(method="GET", host=GRAPH, path__regex=r"^/v25\.0/C\d+$")
        r.publish = r.route(method="POST", host=GRAPH, path="/v25.0/IGID/media_publish")
        r.media = r.route(method="GET", host=GRAPH, path="/v25.0/M1")
        r.quota = r.route(method="GET", host=GRAPH, path="/v25.0/IGID/content_publishing_limit")
        yield r


def containers():
    n = iter(range(1, 100))
    return lambda request: httpx.Response(200, json={"id": f"C{next(n)}"})


def status(code, detail=None):
    return httpx.Response(200, json={"status_code": code, "status": detail or code, "id": "C1"})


def meta_error(code, sub=None, http=400, msg="boom"):
    return httpx.Response(http, json={"error": {"message": msg, "type": "OAuthException", "code": code,
                                                 "error_subcode": sub, "fbtrace_id": "x"}})


def happy(api):
    api.create.mock(side_effect=containers())
    api.upload.mock(return_value=httpx.Response(200, json={"success": True, "message": "Upload successful."}))
    api.status.mock(side_effect=[status("IN_PROGRESS"), status("FINISHED")])
    api.publish.mock(return_value=httpx.Response(200, json={"id": "M1"}))
    api.media.mock(return_value=httpx.Response(200, json={"permalink": "https://www.instagram.com/reel/abc/"}))


def test_happy_path(item, ig, conn, api):
    happy(api)
    out = service.publish(item, ig, conn, live=True, sleep=noop)
    assert out.action == "published" and out.detail == "https://www.instagram.com/reel/abc/"

    p = api.create.calls[0].request.url.params
    assert (p["media_type"], p["upload_type"], p["is_ai_generated"], p["share_to_feed"]) == ("REELS", "resumable", "true", "true")
    assert p["caption"] == "Every empire gets eaten. #ancientrome" and p["thumb_offset"] == "1000"
    assert p["access_token"] == "tok"
    up = api.upload.calls[0].request
    assert up.url.path == "/ig-api-upload/v25.0/C1"
    assert up.headers["Authorization"] == "OAuth tok" and up.headers["offset"] == "0"
    assert up.headers["file_size"] == str(item.video.stat().st_size) and up.content == item.video.read_bytes()
    assert api.publish.calls[0].request.url.params["creation_id"] == "C1"

    row = db.get(conn, "001-test", "instagram")
    assert (row["state"], row["remote_id"], row["upload_session"]) == (db.PUBLISHED, "M1", None)


def test_dry_run_is_public_warning_and_silent(item, ig, conn, api, settings):
    out = service.publish_due([item], {"instagram": ig}, conn, live=False, now=NOW, tz=settings.tz, daily_caps={})
    assert out[0].action == "dry-run" and "PUBLIC Reel" in out[0].detail
    assert not api.calls


def test_quota_used_up_skips_without_uploading(item, ig, conn, api, settings):
    api.quota.mock(return_value=httpx.Response(200, json={"data": [
        {"quota_usage": 50, "config": {"quota_total": 50, "quota_duration": 86400}}]}))
    out = service.publish_due([item], {"instagram": ig}, conn, live=True, now=NOW, tz=settings.tz, daily_caps={}, sleep=noop)
    assert out[0].action == "skipped" and "quota" in out[0].detail
    assert api.quota.call_count == 1 and not api.create.called
    assert api.quota.calls[0].request.url.params["fields"] == "quota_usage,config"


def test_publish_due_twice_publishes_once(item, ig, conn, api, settings):
    happy(api)
    api.quota.mock(return_value=httpx.Response(200, json={"data": [{"quota_usage": 0, "config": {"quota_total": 100}}]}))
    args = dict(live=True, now=NOW, tz=settings.tz, daily_caps={}, sleep=noop)
    assert service.publish_due([item], {"instagram": ig}, conn, **args)[0].action == "published"
    assert service.publish_due([item], {"instagram": ig}, conn, **args)[0].action == "skipped"
    assert api.publish.call_count == 1


def test_processing_container_is_resumed_not_reuploaded(item, ig, conn, api):
    row = db.ensure(conn, "001-test", "instagram")
    db.update(conn, row["id"], state=db.PROCESSING, upload_session="C7")
    api.status.mock(return_value=status("FINISHED"))
    api.publish.mock(return_value=httpx.Response(200, json={"id": "M1"}))
    api.media.mock(return_value=httpx.Response(200, json={"permalink": "https://www.instagram.com/reel/abc/"}))
    assert service.publish(item, ig, conn, live=True, sleep=noop).action == "published"
    assert not api.create.called and not api.upload.called
    assert api.publish.calls[0].request.url.params["creation_id"] == "C7"


def test_already_published_container_needs_reconcile(item, ig, conn, api):
    row = db.ensure(conn, "001-test", "instagram")
    db.update(conn, row["id"], state=db.PROCESSING, upload_session="C7")
    api.status.mock(return_value=status("PUBLISHED"))
    out = service.publish(item, ig, conn, live=True, sleep=noop)
    assert out.action == "reconcile" and not api.publish.called
    assert service.publish(item, ig, conn, live=True, sleep=noop).action == "skipped"


def test_failed_upload_starts_a_new_container(item, ig, conn, api):
    happy(api)
    api.upload.mock(side_effect=[
        httpx.Response(500, json={"debug_info": {"retriable": True, "type": "ProcessingFailedError", "message": "x"}}),
        httpx.Response(200, json={"success": True})])
    api.status.mock(return_value=status("FINISHED"))
    assert service.publish(item, ig, conn, live=True, sleep=noop).action == "published"
    assert api.create.call_count == 2
    assert [c.request.url.path for c in api.upload.calls] == ["/ig-api-upload/v25.0/C1", "/ig-api-upload/v25.0/C2"]
    assert api.publish.calls[0].request.url.params["creation_id"] == "C2"


def test_non_retriable_upload_failure_is_permanent(item, ig, conn, api):
    api.create.mock(side_effect=containers())
    api.upload.mock(return_value=httpx.Response(400, json={"debug_info": {
        "retriable": False, "type": "ProcessingFailedError", "message": "unauthorized user request"}}))
    out = service.publish(item, ig, conn, live=True, sleep=noop)
    assert out.action == "failed" and "unauthorized user request" in out.detail
    assert db.get(conn, "001-test", "instagram")["retryable"] == 0


def test_expired_container_is_recreated(item, ig, conn, api):
    happy(api)
    api.status.mock(side_effect=[status("EXPIRED"), status("FINISHED")])
    assert service.publish(item, ig, conn, live=True, sleep=noop).action == "published"
    assert api.create.call_count == 2


def test_container_error_is_permanent(item, ig, conn, api):
    happy(api)
    api.status.mock(return_value=status("ERROR", "2207026"))
    out = service.publish(item, ig, conn, live=True, sleep=noop)
    assert out.action == "failed" and "2207026" in out.detail and not api.publish.called


def test_media_not_ready_is_retried(item, ig, conn, api):
    happy(api)
    api.status.mock(return_value=status("FINISHED"))
    api.publish.mock(side_effect=[meta_error(9007, 2207027, msg="The media is not ready for publishing, please wait"),
                                  httpx.Response(200, json={"id": "M1"})])
    assert service.publish(item, ig, conn, live=True, sleep=noop).action == "published"
    assert api.create.call_count == 1 and api.publish.call_count == 2


def test_max_posts_waits_for_later(item, ig, conn, api, settings):
    happy(api)
    api.status.mock(return_value=status("FINISHED"))
    api.publish.mock(return_value=meta_error(9, 2207042, msg="You reached maximum number of posts"))
    out = service.publish(item, ig, conn, live=True, sleep=noop, now=NOW)
    row = db.get(conn, "001-test", "instagram")
    assert out.action == "failed" and row["retryable"] == 1 and row["retry_after"] == "2026-10-02T13:00:00+00:00"
    assert api.publish.call_count == 1


def test_spam_restriction_is_permanent_not_rate_limit(item, ig, conn, api):
    api.create.mock(return_value=meta_error(4, 2207051))
    out = service.publish(item, ig, conn, live=True, sleep=noop)
    assert out.action == "failed" and api.create.call_count == 1
    assert db.get(conn, "001-test", "instagram")["retryable"] == 0


def test_rate_limit_is_retried(item, ig, conn, api):
    happy(api)
    api.create.mock(side_effect=[meta_error(4, None, msg="Application request limit reached"), httpx.Response(200, json={"id": "C1"})])
    api.status.mock(return_value=status("FINISHED"))
    assert service.publish(item, ig, conn, live=True, sleep=noop).action == "published"


# -- tokens ---------------------------------------------------------------

@pytest.fixture
def store(tmp_path):
    return TokenStore(tmp_path / ".secrets")


def clock(t):
    return lambda: t


@pytest.mark.parametrize("body", [{"data": [{"user_id": "178", "username": "romansinstone"}]},
                                  {"user_id": "178", "username": "romansinstone"}])
def test_save_token_reads_ig_user_id(store, settings, body):
    with respx.mock(assert_all_mocked=True) as r:
        me = r.get("https://graph.instagram.com/v25.0/me").mock(return_value=httpx.Response(200, json=body))
        info = InstagramAuth(store, settings.platform("instagram"), http=httpx.Client(), now=clock(NOW)).save_token("T0")
    assert me.calls[0].request.url.params["fields"] == "user_id,username"
    assert info["user_id"] == "178" and store.read("instagram")["expires_at"].startswith("2026-12-01")
    assert oct(store.path("instagram").stat().st_mode)[-3:] == "600"


def seeded(store, obtained, expires, token="T0"):
    store.write("instagram", {"access_token": token, "user_id": "178", "username": "x",
                              "obtained_at": obtained.isoformat(), "expires_at": expires.isoformat()})


def test_token_not_refreshed_when_young(store, settings):
    seeded(store, NOW - timedelta(hours=2), NOW + timedelta(days=20))
    with respx.mock(assert_all_mocked=True):
        assert InstagramAuth(store, settings.platform("instagram"), http=httpx.Client(), now=clock(NOW)).token() == "T0"


def test_token_refreshed_when_due(store, settings):
    seeded(store, NOW - timedelta(days=15), NOW + timedelta(days=45))
    with respx.mock(assert_all_mocked=True) as r:
        ref = r.get("https://graph.instagram.com/refresh_access_token").mock(
            return_value=httpx.Response(200, json={"access_token": "T1", "token_type": "bearer", "expires_in": 5183944}))
        assert InstagramAuth(store, settings.platform("instagram"), http=httpx.Client(), now=clock(NOW)).token() == "T1"
    assert ref.calls[0].request.url.params["grant_type"] == "ig_refresh_token"
    assert store.read("instagram")["access_token"] == "T1"


def test_refresh_failure_keeps_token_while_time_remains(store, settings):
    seeded(store, NOW - timedelta(days=15), NOW + timedelta(days=45))
    with respx.mock(assert_all_mocked=True) as r:
        r.get("https://graph.instagram.com/refresh_access_token").mock(return_value=meta_error(2, http=503))
        assert InstagramAuth(store, settings.platform("instagram"), http=httpx.Client(), now=clock(NOW)).token() == "T0"


def test_expired_token_requires_auth(store, settings):
    seeded(store, NOW - timedelta(days=61), NOW - timedelta(days=1))
    with pytest.raises(AuthRequired, match="expired"):
        InstagramAuth(store, settings.platform("instagram"), now=clock(NOW)).token()
