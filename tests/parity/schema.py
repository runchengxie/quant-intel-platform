from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ParityArtifact:
    """A JSON object captured from one side of a parity comparison."""

    path: Path
    payload: dict[str, Any]

    @classmethod
    def from_path(cls, path: Path) -> ParityArtifact:
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path} is not valid JSON: {exc}") from exc

        if not isinstance(raw, dict):
            raise ValueError(f"{path} must contain a JSON object artifact")
        return cls(path=path, payload=raw)
