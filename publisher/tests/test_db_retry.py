import pytest

from publisher import db
from publisher.retry import PermanentError, TransientError, with_retry


def test_unique_per_slug_platform_and_idempotent_ensure(conn):
    a = db.ensure(conn, "001", "youtube")
    b = db.ensure(conn, "001", "youtube")
    assert a["id"] == b["id"]
    assert conn.execute("SELECT COUNT(*) FROM publications").fetchone()[0] == 1


def test_claim_is_exclusive(conn):
    row = db.ensure(conn, "001", "youtube")
    assert db.claim(conn, row["id"], (db.PENDING,), db.UPLOADING) is True
    assert db.claim(conn, row["id"], (db.PENDING,), db.UPLOADING) is False
    db.update(conn, row["id"], state=db.PUBLISHED)
    assert db.claim(conn, row["id"], (db.PENDING, db.FAILED, db.UPLOADING), db.UPLOADING) is False


def test_migrations_rerun_safely(settings):
    c1 = db.connect(settings.path(settings.db_path))
    c1.close()
    c2 = db.connect(settings.path(settings.db_path))
    assert c2.execute("PRAGMA user_version").fetchone()[0] == len(db.MIGRATIONS)


def test_retry_transient_then_success():
    calls, sleeps = [], []

    def fn():
        calls.append(1)
        if len(calls) < 3:
            raise TransientError("503")
        return "ok"

    assert with_retry(fn, sleep=sleeps.append) == "ok"
    assert len(calls) == 3 and len(sleeps) == 2


def test_retry_permanent_not_retried():
    calls = []

    def fn():
        calls.append(1)
        raise PermanentError("quotaExceeded")

    with pytest.raises(PermanentError):
        with_retry(fn, sleep=lambda s: None)
    assert len(calls) == 1


def test_retry_gives_up():
    with pytest.raises(TransientError):
        with_retry(lambda: (_ for _ in ()).throw(TransientError("x")), attempts=3, sleep=lambda s: None)


def test_network_is_blocked():
    import httpx
    with pytest.raises(RuntimeError, match="forbidden"):
        httpx.get("https://example.com")
