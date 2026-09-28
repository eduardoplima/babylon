"""The interface every platform adapter implements. Adapters never import each other."""
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol

from ..content import ContentItem
from ..media import Issue
from ..retry import PlatformError


class NeedsReconcile(PlatformError):
    """The outcome is unknown (e.g. an upload may or may not exist). Never retried automatically."""


class AuthRequired(Exception):
    """No usable credentials; the user must run `publisher auth <platform>`."""


@dataclass
class PublishContext:
    """What an adapter needs to publish one (content, platform) pair.
    `pub` is the publication row as a dict; `save(**fields)` persists fields immediately
    (so a crash can resume) and updates `pub` in place."""
    item: ContentItem
    pub: dict[str, Any]
    save: Callable[..., None]
    log: Any = None
    extra: dict[str, Any] = field(default_factory=dict)


class Platform(Protocol):
    name: str

    def check(self, item: ContentItem) -> list[Issue]:
        """Media and metadata problems for this platform (no network)."""

    def describe(self, item: ContentItem) -> str:
        """One line saying what publish() would do (for --dry-run)."""

    def publish(self, ctx: PublishContext) -> None:
        """Drive the publication forward from ctx.pub's state, saving progress as it goes.
        Raises TransientError, PermanentError or NeedsReconcile."""
