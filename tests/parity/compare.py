from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from .schema import ParityArtifact

_MISSING = object()


def compare_artifacts(
    expected: Path,
    actual: Path,
    *,
    ignored_fields: set[str],
    set_like_fields: set[str] | None = None,
    path_fields: set[str] | None = None,
) -> list[str]:
    """Return stable, path-based differences between two JSON artifacts.

    ``ignored_fields`` and ``set_like_fields`` match the final key name at any
    nesting depth. This keeps the initial contract useful for receipts and
    manifests whose generated metadata is nested differently across versions.
    """

    expected_artifact = ParityArtifact.from_path(expected)
    actual_artifact = ParityArtifact.from_path(actual)
    differences: list[str] = []
    _compare_values(
        expected_artifact.payload,
        actual_artifact.payload,
        path=(),
        differences=differences,
        ignored_fields=ignored_fields,
        set_like_fields=set_like_fields or set(),
        path_fields=path_fields or set(),
    )
    return differences


def _compare_values(
    expected: Any,
    actual: Any,
    *,
    path: tuple[str, ...],
    differences: list[str],
    ignored_fields: set[str],
    set_like_fields: set[str],
    path_fields: set[str],
) -> None:
    if path and path[-1] in ignored_fields:
        return

    if isinstance(expected, Mapping) and isinstance(actual, Mapping):
        keys = sorted(set(expected) | set(actual), key=str)
        for key in keys:
            key_name = str(key)
            _compare_values(
                expected.get(key, _MISSING),
                actual.get(key, _MISSING),
                path=(*path, key_name),
                differences=differences,
                ignored_fields=ignored_fields,
                set_like_fields=set_like_fields,
                path_fields=path_fields,
            )
        return

    if expected is _MISSING or actual is _MISSING:
        _append_difference(path, expected, actual, differences)
        return

    if path and path[-1] in set_like_fields and _is_sequence(expected) and _is_sequence(actual):
        expected = sorted(expected, key=_stable_sort_key)
        actual = sorted(actual, key=_stable_sort_key)

    if (
        path
        and any(part in path_fields for part in path[:-1])
        and isinstance(expected, str)
        and isinstance(actual, str)
    ):
        expected = Path(expected).name
        actual = Path(actual).name

    if expected != actual:
        _append_difference(path, expected, actual, differences)


def _is_sequence(value: Any) -> bool:
    return isinstance(value, (list, tuple))


def _stable_sort_key(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _append_difference(
    path: Iterable[str], expected: Any, actual: Any, differences: list[str]
) -> None:
    path_text = ".".join(path) or "$"
    differences.append(
        f"{path_text}: expected {_format_value(expected)}, actual {_format_value(actual)}"
    )


def _format_value(value: Any) -> str:
    if value is _MISSING:
        return "<missing>"
    return repr(value)
