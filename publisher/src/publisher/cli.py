"""Command line: publisher <command>. Publishing commands are dry-run unless --live."""
import fcntl
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Optional

import typer

from . import babylon, content, db, export as exporter, log as logging, media, service
from .platforms.base import AuthRequired, Platform
from .settings import Settings
from .tokens import TokenStore

app = typer.Typer(no_args_is_help=True, add_completion=False, help=__doc__)
auth_app = typer.Typer(no_args_is_help=True, help="Authorize platforms (stores tokens in the secrets folder).")
app.add_typer(auth_app, name="auth")

IMPLEMENTED = ("youtube", "instagram", "tiktok")


def _settings() -> Settings:
    return Settings()


class _DryAuth:
    """Stands in for credentials during a dry run (nothing is sent)."""

    def token(self, force: bool = False) -> str:
        return "dry-run"

    def user_id(self) -> str:
        return "dry-run"


def _adapters(settings: Settings, live: bool, only: list[str] | None = None) -> dict[str, Platform]:
    """Adapters for implemented platforms. In dry-run no credentials are loaded."""
    from .platforms import instagram, tiktok, youtube

    store = TokenStore(settings.path(settings.secrets_dir))
    adapters: dict[str, Platform] = {}
    for name in only or IMPLEMENTED:
        if name == "youtube":
            token = youtube.token_provider(store) if live else _DryAuth().token
            adapters[name] = youtube.YouTube(settings.platform("youtube"), token)
        elif name == "instagram":
            cfg = settings.platform("instagram")
            auth = instagram.InstagramAuth(store, cfg) if live else _DryAuth()
            adapters[name] = instagram.Instagram(cfg, auth)
        elif name == "tiktok":
            adapters[name] = tiktok.TikTok(settings.platform("tiktok"), _tiktok_auth(settings) if live else _DryAuth())
    return adapters


def _tiktok_auth(settings: Settings):
    from .platforms import tiktok

    return tiktok.TikTokAuth(TokenStore(settings.path(settings.secrets_dir)), settings.platform("tiktok"),
                             settings.tiktok_client_key, settings.tiktok_client_secret.get_secret_value())


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
    caps = {"youtube": settings.platform("youtube")["uploads_per_day"],
            "tiktok": settings.platform("tiktok")["pending_shares_per_day"]}
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


@app.command("collect-metrics")
def collect_metrics(platform: Annotated[Optional[list[str]], typer.Option("--platform", "-p")] = None):
    """Fetch metrics for published posts (read-only API calls) and store them with a timestamp."""
    settings = _settings()
    logging.configure(settings.path(settings.log_path))
    lg = logging.get(run=datetime.now(timezone.utc).isoformat(timespec="seconds"), command="collect-metrics")
    conn = db.connect(settings.path(settings.db_path))
    store = TokenStore(settings.path(settings.secrets_dir))
    wanted = [p for p in (platform or IMPLEMENTED) if store.read(p)]
    for p in set(platform or IMPLEMENTED) - set(wanted):
        typer.echo(f"{p}: not authorized, skipped (`publisher auth {p}`)")
    try:
        outcomes = service.collect_metrics(_adapters(settings, True, wanted), conn, now=datetime.now(timezone.utc), log=lg)
    except AuthRequired as exc:
        typer.echo(f"auth: {exc}", err=True)
        raise typer.Exit(2)
    for o in outcomes:
        typer.echo(str(o))
    if not outcomes:
        typer.echo("nothing published yet")
    raise typer.Exit(1 if any(o.action == "failed" for o in outcomes) else 0)


@app.command("export")
def export_csv(path: Annotated[Path, typer.Argument(help="CSV file to write ('-' for stdout)")] = Path("data/metrics.csv")):
    """Latest metrics per publication, with hook_type and format from meta.yaml."""
    import sys

    settings = _settings()
    conn = db.connect(settings.path(settings.db_path))
    items, _ = content.load_all(settings)
    by_slug = {i.slug: i for i in items}
    if str(path) == "-":
        n = exporter.write(conn, by_slug, sys.stdout)
    else:
        target = settings.path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        with open(target, "w", newline="") as fh:
            n = exporter.write(conn, by_slug, fh)
        typer.echo(f"wrote {n} rows to {target}")


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
        # Instagram permalinks aren't derivable from the media id; `status` shows the id instead.
        url = f"https://www.youtube.com/shorts/{remote_id}" if platform == "youtube" else None
        db.update(conn, row["id"], state=db.PUBLISHED, remote_id=remote_id, remote_url=url, upload_session=None,
                  published_at=db.now(), last_error=None)
    else:
        db.update(conn, row["id"], state=db.PENDING, retryable=1, upload_session=None, remote_id=None,
                  remote_url=None, last_error=None, retry_after=None, attempts=0, upload_started_at=None)
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


@auth_app.command("instagram")
def auth_instagram():
    """Store a long-lived Instagram token (App Dashboard → Instagram → API setup with Instagram
    business login → Generate token). Typed without echo so it stays out of shell history."""
    from .platforms import instagram

    settings = _settings()
    token = typer.prompt("Instagram access token", hide_input=True).strip()
    auth = instagram.InstagramAuth(TokenStore(settings.path(settings.secrets_dir)), settings.platform("instagram"))
    try:
        info = auth.save_token(token)
    except Exception as exc:  # classify() errors carry the API message
        typer.echo(f"token rejected: {exc}", err=True)
        raise typer.Exit(2)
    typer.echo(f"Instagram authorized as @{info['username']} (IG user {info['user_id']}); "
               f"expires {info['expires_at'][:10]}, refreshed automatically after 24 h.")


@auth_app.command("tiktok")
def auth_tiktok():
    """Open the browser for TikTok Login Kit (desktop, PKCE) and store the tokens.
    Needs PUBLISHER_TIKTOK_CLIENT_KEY/SECRET in .env and redirect http://127.0.0.1:*/callback/ registered."""
    import webbrowser

    from .platforms import tiktok

    settings = _settings()
    try:
        info = tiktok.run_login(_tiktok_auth(settings), settings.platform("tiktok"), webbrowser.open)
    except AuthRequired as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(2)
    typer.echo(f"TikTok authorized (scopes: {info['scope']}); access renews daily, re-login needed by "
               f"{info['refresh_expires_at'][:10]}.")


@app.command()
def link(slug: str, platform: str,
         video_id: Annotated[Optional[str], typer.Argument(help="the public video id; looked up when omitted")] = None):
    """Record the public post for a draft you finished in the app (TikTok inbox uploads)."""
    if platform != "tiktok":
        typer.echo("only tiktok drafts need linking", err=True)
        raise typer.Exit(2)
    from .platforms import tiktok

    settings = _settings()
    conn = db.connect(settings.path(settings.db_path))
    row = db.get(conn, slug, platform)
    if not row or row["state"] not in (db.SENT_TO_INBOX, db.PUBLISHED):
        typer.echo(f"{slug} [tiktok] is not in the inbox yet (state: {row['state'] if row else 'none'})", err=True)
        raise typer.Exit(1)
    if not video_id:
        try:
            video_id = tiktok.TikTok(settings.platform("tiktok"), _tiktok_auth(settings)).public_post_id(row["upload_session"])
        except AuthRequired as exc:
            typer.echo(str(exc), err=True)
            raise typer.Exit(2)
        if not video_id:
            typer.echo("not public yet: post the draft from the TikTok inbox (or pass the video id)")
            raise typer.Exit(1)
    db.update(conn, row["id"], state=db.PUBLISHED, remote_id=video_id, last_error=None)
    typer.echo(f"{slug} [tiktok] linked to video {video_id}")


@auth_app.command("refresh")
def auth_refresh():
    """Refresh tokens that are due (safe to run daily from cron) and show how long each lasts."""
    from .platforms import instagram, youtube

    settings = _settings()
    store = TokenStore(settings.path(settings.secrets_dir))
    failed = False
    if store.read("youtube"):
        try:
            youtube.token_provider(store)(True)
            typer.echo("youtube: refreshed")
        except AuthRequired as exc:
            failed = True
            typer.echo(f"youtube: {exc}", err=True)
    if store.read("tiktok"):
        try:
            _tiktok_auth(settings).token(True)
            typer.echo(f"tiktok: refreshed (re-login by {store.read('tiktok')['refresh_expires_at'][:10]})")
        except AuthRequired as exc:
            failed = True
            typer.echo(f"tiktok: {exc}", err=True)
    if store.read("instagram"):
        auth = instagram.InstagramAuth(store, settings.platform("instagram"))
        try:
            auth.token()
            typer.echo(f"instagram: {auth.days_left():.0f} days left")
        except Exception as exc:
            failed = True
            typer.echo(f"instagram: {exc}", err=True)
    raise typer.Exit(1 if failed else 0)


@app.command("import-babylon")
def import_babylon(video_dir: Path):
    """Create content/<slug>/ (master.mp4 + draft meta.yaml) from a Babylon video folder."""
    settings = _settings()
    dest = babylon.import_video(video_dir.resolve(), settings.path(settings.content_dir), settings.taxonomy)
    typer.echo(f"created {dest}\nreview {dest / 'meta.yaml'} (hook_type, format, schedule, captions), then "
               f"`publisher validate {dest.name}`")
