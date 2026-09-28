"""Command line: publisher <command>. Publishing commands are dry-run unless --live."""
import fcntl
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Optional

import typer

from . import babylon, content, db, log as logging, media, service
from .platforms.base import AuthRequired, Platform
from .settings import Settings
from .tokens import TokenStore

app = typer.Typer(no_args_is_help=True, add_completion=False, help=__doc__)
auth_app = typer.Typer(no_args_is_help=True, help="Authorize platforms (stores tokens in the secrets folder).")
app.add_typer(auth_app, name="auth")

IMPLEMENTED = ("youtube",)


def _settings() -> Settings:
    return Settings()


def _adapters(settings: Settings, live: bool, only: list[str] | None = None) -> dict[str, Platform]:
    """Adapters for implemented platforms. In dry-run no credentials are loaded."""
    from .platforms import youtube

    store = TokenStore(settings.path(settings.secrets_dir))
    adapters: dict[str, Platform] = {}
    for name in only or IMPLEMENTED:
        if name == "youtube":
            token = youtube.token_provider(store) if live else (lambda force=False: "dry-run")
            adapters[name] = youtube.YouTube(settings.platform("youtube"), token)
    return adapters


@contextmanager
def _lock(settings: Settings):
    """One publishing run at a time (cron overlap, manual runs)."""
    path = settings.path(settings.db_path).with_suffix(".lock")
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        try:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            typer.echo("another publisher run is in progress; exiting", err=True)
            raise typer.Exit(1)
        yield


def _load(settings: Settings, slug: str) -> content.ContentItem:
    try:
        return content.load(settings.path(settings.content_dir) / slug, settings)
    except content.ContentError as exc:
        typer.echo(f"invalid: {exc}", err=True)
        raise typer.Exit(1)


@app.command()
def validate(slug: Annotated[Optional[str], typer.Argument(help="content slug; all when omitted")] = None):
    """Check meta.yaml and the video against each enabled platform's limits (no network)."""
    settings = _settings()
    if slug:
        items, errors = [_load(settings, slug)], []
    else:
        items, errors = content.load_all(settings)
    for e in errors:
        typer.echo(f"✗ {e}")
    bad = bool(errors)
    for item in items:
        info = media.probe(item.video)
        typer.echo(f"{item.slug}: {info.width}x{info.height} {info.duration_s:.1f}s {info.video_codec}/{info.audio_codec} "
                   f"{info.fps}fps {info.size_bytes / 1e6:.1f}MB faststart={info.faststart}")
        for name in item.meta.platforms():
            issues = media.check(info, settings.platform(name)["limits"])
            bad |= any(i.level == "error" for i in issues)
            mark = "✗" if any(i.level == "error" for i in issues) else "✓"
            typer.echo(f"  {mark} {name}" + "".join(f"\n      {i}" for i in issues))
    raise typer.Exit(1 if bad else 0)


@app.command()
def publish(slug: str,
            platform: Annotated[Optional[list[str]], typer.Option("--platform", "-p")] = None,
            live: Annotated[bool, typer.Option("--live", help="actually publish (default is a dry run)")] = False,
            force: Annotated[bool, typer.Option(help="retry a permanent failure")] = False):
    """Publish one content unit (dry-run unless --live)."""
    settings = _settings()
    item = _load(settings, slug)
    names = [p for p in (platform or item.meta.platforms()) if p in item.meta.platforms()]
    _run(settings, live, lambda conn, adapters, lg: [
        service.publish(item, adapters[n], conn, live=live, log=lg, force=force) if n in adapters
        else service.Outcome(slug, n, "skipped", "adapter not implemented yet") for n in names])


@app.command("publish-due")
def publish_due(live: Annotated[bool, typer.Option("--live", help="actually publish (default is a dry run)")] = False):
    """Publish everything whose schedule has passed and isn't published yet. Meant for cron/systemd."""
    settings = _settings()
    items, errors = content.load_all(settings)
    for e in errors:
        typer.echo(f"✗ {e}", err=True)
    caps = {"youtube": settings.platform("youtube")["uploads_per_day"]}
    _run(settings, live, lambda conn, adapters, lg: service.publish_due(
        items, adapters, conn, live=live, now=datetime.now(timezone.utc), tz=settings.tz, daily_caps=caps, log=lg))


def _run(settings: Settings, live: bool, body) -> None:
    logging.configure(settings.path(settings.log_path))
    lg = logging.get(run=datetime.now(timezone.utc).isoformat(timespec="seconds"), live=live)
    if not live:
        typer.echo("DRY RUN: nothing will be published (use --live)")
    with _lock(settings):
        conn = db.connect(settings.path(settings.db_path))
        try:
            outcomes = body(conn, _adapters(settings, live), lg)
        except AuthRequired as exc:
            typer.echo(f"auth: {exc}", err=True)
            raise typer.Exit(2)
    for o in outcomes:
        typer.echo(str(o))
    if not outcomes:
        typer.echo("nothing to do")
    raise typer.Exit(1 if any(o.action in ("failed", "invalid", "reconcile") for o in outcomes) else 0)


@app.command()
def status(slug: Annotated[Optional[str], typer.Argument()] = None):
    """Show publication state per (slug, platform)."""
    settings = _settings()
    conn = db.connect(settings.path(settings.db_path))
    rows = db.all_publications(conn, slug)
    if not rows:
        typer.echo("no publications yet")
    for r in rows:
        line = f"{r['slug']:<32} {r['platform']:<10} {r['state']:<16} runs={r['attempts']}"
        line += f"  {r['remote_url'] or ''}"
        if r["last_error"] and r["state"] not in db.DONE:
            line += f"\n    last error: {r['last_error'][:200]}"
        typer.echo(line)


@app.command()
def resolve(slug: str, platform: str,
            remote_id: Annotated[Optional[str], typer.Option(help="the post exists: record its id as published")] = None,
            reset: Annotated[bool, typer.Option(help="the post does not exist: allow publishing again")] = False):
    """Settle a publication stuck in needs_reconcile (or failed) after checking the platform by hand."""
    if bool(remote_id) == reset:
        typer.echo("pass exactly one of --remote-id or --reset", err=True)
        raise typer.Exit(2)
    settings = _settings()
    conn = db.connect(settings.path(settings.db_path))
    row = db.get(conn, slug, platform)
    if not row:
        typer.echo("no such publication", err=True)
        raise typer.Exit(1)
    if remote_id:
        url = f"https://www.youtube.com/shorts/{remote_id}" if platform == "youtube" else None
        db.update(conn, row["id"], state=db.PUBLISHED, remote_id=remote_id, remote_url=url, upload_session=None,
                  published_at=db.now(), last_error=None)
    else:
        db.update(conn, row["id"], state=db.PENDING, retryable=1, upload_session=None, remote_id=None,
                  remote_url=None, last_error=None)
    typer.echo(f"{slug} [{platform}] → {db.get(conn, slug, platform)['state']}")


@auth_app.command("youtube")
def auth_youtube():
    """Open the browser for Google OAuth (loopback flow) and store the refresh token."""
    from .platforms import youtube

    settings = _settings()
    try:
        youtube.authorize(settings.path(settings.youtube_client_secrets), TokenStore(settings.path(settings.secrets_dir)))
    except AuthRequired as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(2)
    typer.echo("YouTube authorized.")


@app.command("import-babylon")
def import_babylon(video_dir: Path):
    """Create content/<slug>/ (master.mp4 + draft meta.yaml) from a Babylon video folder."""
    settings = _settings()
    dest = babylon.import_video(video_dir.resolve(), settings.path(settings.content_dir), settings.taxonomy)
    typer.echo(f"created {dest}\nreview {dest / 'meta.yaml'} (hook_type, format, schedule, captions), then "
               f"`publisher validate {dest.name}`")
