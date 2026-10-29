"""Bounded, pinned reader for retrospective owner evidence; no research computations."""

from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import UTC, date, datetime
from pathlib import Path
from typing import cast
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from jsonschema import Draft202012Validator, FormatChecker

# Verbatim provider schema; keep docs/contracts snapshot synchronized.
_SCHEMA = json.loads(r"""{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "overseas_theme_evidence.v1.schema.json",
  "type": "object",
  "required": [
    "schema_version",
    "study_id",
    "generated_at_utc",
    "source_revision",
    "decision_time_local",
    "decision_timezone",
    "evidence_status",
    "historical_pit_certified",
    "sample_start",
    "sample_end",
    "source_sha256",
    "sources",
    "comparisons",
    "limitations"
  ],
  "properties": {
    "schema_version": {
      "const": "overseas_theme_evidence.v1"
    },
    "decision_time_local": {
      "const": "08:45"
    },
    "decision_timezone": {
      "const": "Asia/Shanghai"
    },
    "evidence_status": {
      "const": "retrospective_exploratory"
    },
    "historical_pit_certified": {
      "const": false
    },
    "study_id": {
      "type": "string",
      "minLength": 1
    },
    "generated_at_utc": {
      "type": "string",
      "format": "date-time",
      "pattern": "(Z|\\+00:00)$"
    },
    "source_revision": {
      "type": "string",
      "pattern": "^[0-9a-f]{40}$"
    },
    "sample_start": {
      "type": "string",
      "format": "date"
    },
    "sample_end": {
      "type": "string",
      "format": "date"
    },
    "source_sha256": {
      "type": "object",
      "minProperties": 1,
      "additionalProperties": {
        "type": "string",
        "pattern": "^[0-9a-f]{64}$"
      }
    },
    "sources": {
      "type": "object",
      "minProperties": 1,
      "additionalProperties": {
        "type": "object",
        "required": [
          "url",
          "sha256"
        ],
        "properties": {
          "url": {
            "type": "string",
            "pattern": "^https?://"
          },
          "sha256": {
            "type": "string",
            "pattern": "^[0-9a-f]{64}$"
          }
        },
        "additionalProperties": false
      }
    },
    "comparisons": {
      "type": "array",
      "minItems": 1,
      "items": {
        "type": "object",
        "required": [
          "evidence_id",
          "source_ids",
          "target",
          "outcome",
          "lag_sessions",
          "n",
          "baseline",
          "augmented",
          "mse_gain",
          "mse_gain_ci95"
        ],
        "properties": {
          "evidence_id": {
            "type": "string",
            "minLength": 1
          },
          "target": {
            "type": "string",
            "minLength": 1
          },
          "outcome": {
            "type": "string",
            "minLength": 1
          },
          "baseline": {
            "type": "string",
            "minLength": 1
          },
          "augmented": {
            "type": "string",
            "minLength": 1
          },
          "source_ids": {
            "type": "array",
            "minItems": 1,
            "uniqueItems": true,
            "items": {
              "type": "string",
              "minLength": 1
            }
          },
          "lag_sessions": {
            "type": "integer",
            "minimum": 0
          },
          "n": {
            "type": "integer",
            "minimum": 1
          },
          "mse_gain": {
            "type": "number"
          },
          "mse_gain_ci95": {
            "type": "array",
            "minItems": 2,
            "maxItems": 2,
            "items": {
              "type": "number"
            }
          },
          "first": {
            "type": "string",
            "format": "date"
          },
          "last": {
            "type": "string",
            "format": "date"
          },
          "baseline_rmse_bp": {
            "type": "number"
          },
          "augmented_rmse_bp": {
            "type": "number"
          },
          "baseline_hit": {
            "type": "number"
          },
          "augmented_hit": {
            "type": "number"
          }
        },
        "additionalProperties": false
      }
    },
    "limitations": {
      "type": "array",
      "minItems": 1,
      "items": {
        "type": "string",
        "minLength": 1
      }
    }
  },
  "additionalProperties": false
}
""")
_VALIDATOR = Draft202012Validator(_SCHEMA, format_checker=FormatChecker())

MAX_EVIDENCE_BYTES = 2 * 1024 * 1024
REJECTION_CODES = frozenset(
    {
        "invalid_pin",
        "invalid_observed_at",
        "unreadable",
        "too_large",
        "hash_mismatch",
        "invalid_json",
        "schema_invalid",
        "invalid_timestamp",
        "future_generated",
        "sample_dates",
        "source_identity",
        "comparison_invalid",
    }
)


class EvidenceError(ValueError):
    """Stable rejection code, deliberately excluding file paths and raw data."""


def _require(condition: bool, code: str = "schema_invalid") -> None:
    if not condition:
        raise EvidenceError(code)


def _text(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _hex(value: object, length: int) -> bool:
    return isinstance(value, str) and re.fullmatch(f"[0-9a-f]{{{length}}}", value) is not None


def _unique_object(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise EvidenceError("invalid_json")
        result[key] = value
    return result


def _validate_metadata(data: dict, observed_at: datetime) -> None:
    constants = {
        "schema_version": "overseas_theme_evidence.v1",
        "decision_time_local": "08:45",
        "decision_timezone": "Asia/Shanghai",
        "evidence_status": "retrospective_exploratory",
    }
    _require(all(data.get(key) == value for key, value in constants.items()))
    _require(data.get("historical_pit_certified") is False)
    _require(_text(data.get("study_id")) and _hex(data.get("source_revision"), 40))
    try:
        generated = datetime.fromisoformat(data["generated_at_utc"].replace("Z", "+00:00"))
        _require(
            generated.tzinfo is not None and generated.utcoffset() == UTC.utcoffset(generated),
            "invalid_timestamp",
        )
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        raise EvidenceError("invalid_timestamp") from exc
    _require(generated <= observed_at, "future_generated")
    try:
        start = date.fromisoformat(data["sample_start"])
        end = date.fromisoformat(data["sample_end"])
    except (KeyError, TypeError, ValueError) as exc:
        raise EvidenceError("sample_dates") from exc
    local_generated = generated.astimezone(ZoneInfo("Asia/Shanghai")).date()
    _require(
        start <= end <= local_generated <= observed_at.astimezone(ZoneInfo("Asia/Shanghai")).date(),
        "sample_dates",
    )
    limits = data.get("limitations")
    _require(isinstance(limits, list) and bool(limits) and all(_text(x) for x in limits))


def _validate_sources(data: dict) -> None:
    hashes, sources = data.get("source_sha256"), data.get("sources")
    _require(isinstance(hashes, dict) and bool(hashes) and isinstance(sources, dict))
    hashes, sources = cast(dict, hashes), cast(dict, sources)
    _require(hashes.keys() == sources.keys(), "source_identity")
    for key, digest in hashes.items():
        source = sources[key]
        _require(_text(key) and _hex(digest, 64) and isinstance(source, dict), "source_identity")
        _require(source.get("sha256") == digest, "source_identity")
        url = source.get("url")
        _require(isinstance(url, str), "source_identity")
        try:
            parsed = urlsplit(url)
            _require(
                parsed.scheme in {"http", "https"}
                and bool(parsed.hostname)
                and not parsed.username
                and not parsed.password,
                "source_identity",
            )
        except ValueError as exc:
            raise EvidenceError("source_identity") from exc


def _finite(value: object) -> bool:
    try:
        return (
            isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)
        )
    except OverflowError:
        return False


def _validate_comparisons(data: dict) -> None:
    rows = data.get("comparisons")
    _require(isinstance(rows, list) and bool(rows))
    rows = cast(list, rows)
    seen = set()
    for row in rows:
        _require(isinstance(row, dict))
        _require(all(_text(row.get(k)) for k in ("evidence_id", "target", "baseline", "augmented")))
        _require(row["evidence_id"] not in seen, "comparison_invalid")
        seen.add(row["evidence_id"])
        _require(row.get("outcome") in {"gap", "post_open", "next_tradable_open"})
        _require(type(row.get("lag_sessions")) is int and row["lag_sessions"] in {0, 1})
        _require(type(row.get("n")) is int and row["n"] > 0)
        ids = row.get("source_ids")
        _require(isinstance(ids, list) and bool(ids) and all(_text(x) for x in ids))
        _require(
            len(ids) == len(set(ids)) and set(ids) <= data["sources"].keys(), "source_identity"
        )
        for name in ("baseline_rmse_bp", "augmented_rmse_bp", "baseline_hit", "augmented_hit"):
            _require(name not in row or _finite(row[name]), "comparison_invalid")
        ci = row.get("mse_gain_ci95")
        _require(
            _finite(row.get("mse_gain"))
            and isinstance(ci, list)
            and len(ci) == 2
            and all(_finite(x) for x in ci)
            and ci[0] <= ci[1],
            "comparison_invalid",
        )


def load_evidence(path: Path, expected_sha256: str, observed_at: datetime) -> dict:
    """Read at most 2 MiB and validate bytes, provenance and retrospective semantics."""
    _require(_hex(expected_sha256, 64), "invalid_pin")
    _require(
        isinstance(observed_at, datetime) and observed_at.utcoffset() is not None,
        "invalid_observed_at",
    )
    try:
        with path.open("rb") as handle:
            payload = handle.read(MAX_EVIDENCE_BYTES + 1)
    except OSError as exc:
        raise EvidenceError("unreadable") from exc
    _require(len(payload) <= MAX_EVIDENCE_BYTES, "too_large")
    _require(hashlib.sha256(payload).hexdigest() == expected_sha256, "hash_mismatch")
    try:
        data = json.loads(payload, object_pairs_hook=_unique_object)
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise EvidenceError("invalid_json") from exc
    _require(isinstance(data, dict))
    _validate_metadata(data, observed_at.astimezone(UTC))
    _require(not any(_VALIDATOR.iter_errors(data)))
    _validate_sources(data)
    _validate_comparisons(data)
    return data
