"""OAuth tokens stored as JSON files in the secrets folder (outside git, mode 600)."""
import json
import os
from pathlib import Path
from typing import Any


class TokenStore:
    def __init__(self, dir: Path):
        self.dir = dir

    def path(self, name: str) -> Path:
        return self.dir / f"{name}_token.json"

    def read(self, name: str) -> dict[str, Any] | None:
        p = self.path(name)
        return json.loads(p.read_text()) if p.exists() else None

    def write(self, name: str, data: dict[str, Any]) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        os.chmod(self.dir, 0o700)
        p = self.path(name)
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=1))
        os.chmod(tmp, 0o600)
        tmp.replace(p)
