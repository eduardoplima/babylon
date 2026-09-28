import json
from datetime import datetime, timezone

import httpx
import pytest
import respx

from publisher import content, db, service
from publisher.platforms.youtube import YouTube
from conftest import write_content

HOST = "www.googleapis.com"
UPLOAD_PATH = "/upload/youtube/v3/videos"
SESSION = "https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&upload_id=SESSION1"
NOW = datetime(2026, 10, 2, 12, 0, tzinfo=timezone.utc)
noop = lambda s: None


def processing(state="succeeded", upload="processed", **status):
    return {"items": [{"id": "vid1", "status": {"uploadStatus": upload, **status},
                       "processingDetails": {"processingStatus": state}}]}


@pytest.fixture
def item(settings, vertical_video):
    return content.load(write_content(settings, "001-test", vertical_video), settings)


@pytest.fixture
def tokens():
    calls = []

    def token(force=False):
        calls.append(force)
        return "fresh" if force else "tok"

    token.calls = calls
    return token


@pytest.fixture
def yt(settings, tokens):
    return YouTube(settings.platform("youtube"), tokens, http=httpx.Client(), sleep=noop)


@pytest.fixture
def api():
    with respx.mock(assert_all_mocked=True, assert_all_called=False) as router:
        router.start = router.route(method="POST", host=HOST, path=UPLOAD_PATH)
        router.put_ = router.route(method="PUT", host=HOST, path=UPLOAD_PATH)
        router.videos = router.route(method="GET", host=HOST, path="/youtube/v3/videos")
        yield router


def happy(api, size_ref=None):
    api.start.mock(return_value=httpx.Response(200, headers={"Location": SESSION}))
    api.put_.mock(return_value=httpx.Response(200, json={"id": "vid1"}))
    api.videos.mock(side_effect=[httpx.Response(200, json=processing("processing", "uploaded")),
                                 httpx.Response(200, json=processing())])


def test_upload_happy_path(item, yt, conn, api, logs):
    happy(api)
    out = service.publish(item, yt, conn, live=True, log=__import__("publisher.log", fromlist=["get"]).get(), sleep=noop)

    assert out.action == "published" and out.detail == "https://www.youtube.com/shorts/vid1"
    req = api.start.calls[0].request
    assert req.url.params["uploadType"] == "resumable" and req.url.params["part"] == "snippet,status"
    body = json.loads(req.content)
    assert body["status"] == {"privacyStatus": "private", "selfDeclaredMadeForKids": False, "containsSyntheticMedia": True}
    assert body["snippet"]["title"] == "Why does every empire get eaten?"
    assert req.headers["X-Upload-Content-Length"] == str(item.video.stat().st_size)
    assert req.headers["Authorization"] == "Bearer tok"
    assert api.put_.calls[0].request.content == item.video.read_bytes()

    row = db.get(conn, "001-test", "youtube")
    assert row["state"] == db.PUBLISHED and row["remote_id"] == "vid1" and row["upload_session"] is None
    assert row["upload_started_at"] and row["published_at"]
    attempt = conn.execute("SELECT * FROM attempts").fetchone()
    assert attempt["outcome"] == "success"
    events = [json.loads(line)["event"] for line in logs.getvalue().splitlines()]
    assert "youtube.uploaded" in events and "publish.ok" in events


def test_second_run_does_not_republish(item, yt, conn, api):
    happy(api)
    service.publish(item, yt, conn, live=True, sleep=noop)
    calls = len(api.calls)
    out = service.publish(item, yt, conn, live=True, sleep=noop)
    assert out.action == "skipped" and "already published" in out.detail
    assert len(api.calls) == calls


def test_publish_due_twice_uploads_once(item, yt, conn, api, settings):
    happy(api)
    args = dict(live=True, now=NOW, tz=settings.tz, daily_caps={"youtube": 100}, sleep=noop)
    first = service.publish_due([item], {"youtube": yt}, conn, **args)
    second = service.publish_due([item], {"youtube": yt}, conn, **args)
    assert [o.action for o in first] == ["published"]
    assert [o.action for o in second] == ["skipped"]
    assert api.start.call_count == 1 and api.put_.call_count == 1


def test_not_due_is_ignored(item, yt, conn, api, settings):
    early = datetime(2026, 10, 1, 20, 59, tzinfo=timezone.utc)  # 17:59 in São Paulo, schedule is 18:00
    out = service.publish_due([item], {"youtube": yt}, conn, live=True, now=early, tz=settings.tz, daily_caps={})
    assert out == [] and not api.calls


def test_dry_run_makes_no_calls_and_no_rows(item, yt, conn, api, settings):
    out = service.publish_due([item], {"youtube": yt}, conn, live=False, now=NOW, tz=settings.tz, daily_caps={})
    assert [o.action for o in out] == ["dry-run"] and "as private" in out[0].detail
    assert not api.calls
    assert conn.execute("SELECT COUNT(*) FROM publications").fetchone()[0] == 0


def test_resume_from_saved_session(item, yt, conn, api):
    size = item.video.stat().st_size
    row = db.ensure(conn, "001-test", "youtube")
    db.update(conn, row["id"], state=db.FAILED, upload_session=SESSION, upload_started_at=db.now())

    def put(request):
        if request.headers["Content-Range"] == f"bytes */{size}":
            return httpx.Response(308, headers={"Range": "bytes=0-99"})
        assert request.headers["Content-Range"] == f"bytes 100-{size - 1}/{size}"
        assert request.content == item.video.read_bytes()[100:]
        return httpx.Response(200, json={"id": "vid1"})

    api.put_.mock(side_effect=put)
    api.videos.mock(return_value=httpx.Response(200, json=processing()))
    out = service.publish(item, yt, conn, live=True, sleep=noop)
    assert out.action == "published"
    assert api.start.call_count == 0 and api.put_.call_count == 2


def test_session_already_complete_is_not_reuploaded(item, yt, conn, api):
    row = db.ensure(conn, "001-test", "youtube")
    db.update(conn, row["id"], state=db.UPLOADING, upload_session=SESSION)
    api.put_.mock(return_value=httpx.Response(200, json={"id": "vid1"}))
    api.videos.mock(return_value=httpx.Response(200, json=processing()))
    out = service.publish(item, yt, conn, live=True, sleep=noop)
    assert out.action == "published"
    assert api.put_.call_count == 1 and api.put_.calls[0].request.headers["Content-Length"] == "0"


def test_expired_session_needs_reconcile_and_is_never_retried(item, yt, conn, api):
    row = db.ensure(conn, "001-test", "youtube")
    db.update(conn, row["id"], state=db.UPLOADING, upload_session=SESSION)
    api.put_.mock(return_value=httpx.Response(404))
    out = service.publish(item, yt, conn, live=True, sleep=noop)
    assert out.action == "reconcile"
    assert db.get(conn, "001-test", "youtube")["state"] == db.NEEDS_RECONCILE
    again = service.publish(item, yt, conn, live=True, sleep=noop)
    assert again.action == "skipped" and "needs reconcile" in again.detail
    assert api.put_.call_count == 1


def google_error(code, reason):
    return httpx.Response(code, json={"error": {"code": code, "message": reason, "errors": [{"reason": reason}]}})


def test_quota_exceeded_is_permanent(item, yt, conn, api, settings):
    api.start.mock(return_value=google_error(403, "quotaExceeded"))
    out = service.publish(item, yt, conn, live=True, sleep=noop)
    assert out.action == "failed" and "quotaExceeded" in out.detail
    row = db.get(conn, "001-test", "youtube")
    assert row["state"] == db.FAILED and row["retryable"] == 0
    attempt = conn.execute("SELECT * FROM attempts").fetchone()
    assert (attempt["outcome"], attempt["http_status"], attempt["reason"]) == ("permanent", 403, "quotaExceeded")
    due = service.publish_due([item], {"youtube": yt}, conn, live=True, now=NOW, tz=settings.tz, daily_caps={}, sleep=noop)
    assert due[0].action == "skipped" and api.start.call_count == 1


def test_server_errors_are_retried_then_recorded_as_retryable(item, yt, conn, api):
    api.start.mock(return_value=google_error(503, "backendError"))
    out = service.publish(item, yt, conn, live=True, sleep=noop)
    assert out.action == "failed" and "will retry" in out.detail
    assert api.start.call_count == 5  # with_retry default attempts
    row = db.get(conn, "001-test", "youtube")
    assert row["state"] == db.FAILED and row["retryable"] == 1


def test_401_refreshes_token_once(item, yt, conn, api, tokens):
    api.start.mock(side_effect=[httpx.Response(401), httpx.Response(200, headers={"Location": SESSION})])
    api.put_.mock(return_value=httpx.Response(200, json={"id": "vid1"}))
    api.videos.mock(return_value=httpx.Response(200, json=processing()))
    assert service.publish(item, yt, conn, live=True, sleep=noop).action == "published"
    assert api.start.calls[1].request.headers["Authorization"] == "Bearer fresh"
    assert True in tokens.calls


def test_rejected_video_is_permanent(item, yt, conn, api):
    happy(api)
    api.videos.mock(return_value=httpx.Response(200, json=processing("failed", "rejected", rejectionReason="duplicate")))
    out = service.publish(item, yt, conn, live=True, sleep=noop)
    assert out.action == "failed" and "duplicate" in out.detail
    assert db.get(conn, "001-test", "youtube")["retryable"] == 0


def test_daily_cap_blocks_new_uploads(item, yt, conn, api, settings):
    out = service.publish_due([item], {"youtube": yt}, conn, live=True, now=NOW, tz=settings.tz,
                              daily_caps={"youtube": 0}, sleep=noop)
    assert out[0].action == "skipped" and "daily cap" in out[0].detail and not api.calls


def test_invalid_media_is_not_uploaded(settings, tmp_path, yt, conn, api):
    from conftest import make_video
    wide = make_video(tmp_path / "wide.mp4", w=480, h=270)
    item = content.load(write_content(settings, "002-wide", wide), settings)
    out = service.publish(item, yt, conn, live=True, sleep=noop)
    assert out.action == "invalid" and "horizontal" in out.detail and not api.calls
