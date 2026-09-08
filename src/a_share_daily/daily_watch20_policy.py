"""Strict consumer validation for the DailyWatch20 selection.v2 policy carrier.

The section semantics mirror the producer contract locally; this facade owns
canonicalization, policy identity, and receipt carrier checks.  No producer
repository is imported at runtime.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping
from typing import Any, cast

from .daily_watch20_policy_sections import (
    StrategyPolicyValidationError,
    validate_strategy_policy,
)

STRATEGY_POLICY_SCHEMA = "daily_watch20.strategy_policy.v1"
STRATEGY_POLICY_ID_PREFIX = f"{STRATEGY_POLICY_SCHEMA}:sha256:"
_REQUIRED_SECTIONS = frozenset(
    {"model", "features", "label", "candidate_pool", "news_heat", "construction", "safety"}
)


def _canonical_value(value: Any, *, path: str) -> Any:
    if value is None or isinstance(value, str | bool | int):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise StrategyPolicyValidationError(f"{path} must not contain NaN or infinity")
        return 0.0 if value == 0.0 else value
    if isinstance(value, Mapping):
        normalized: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise StrategyPolicyValidationError(f"{path} contains a non-string key")
            normalized[key] = _canonical_value(item, path=f"{path}.{key}")
        return normalized
    if isinstance(value, (list, tuple)):
        return [_canonical_value(item, path=f"{path}[{index}]") for index, item in enumerate(value)]
    raise StrategyPolicyValidationError(
        f"{path} contains unsupported value type {type(value).__name__}"
    )


def _canonical_policy(value: object) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise StrategyPolicyValidationError("receipt.strategy_policy must be a mapping for v2")
    normalized = _canonical_value(value, path="receipt.strategy_policy")
    if not isinstance(normalized, dict):  # pragma: no cover - Mapping guarantees this
        raise StrategyPolicyValidationError("receipt.strategy_policy must be a mapping for v2")
    if normalized.get("schema_version") != STRATEGY_POLICY_SCHEMA:
        raise StrategyPolicyValidationError(
            f"receipt.strategy_policy.schema_version must be {STRATEGY_POLICY_SCHEMA!r}"
        )
    missing = sorted(_REQUIRED_SECTIONS - normalized.keys())
    if missing:
        raise StrategyPolicyValidationError(
            f"receipt.strategy_policy is missing required sections: {missing}"
        )
    invalid = sorted(
        section for section in _REQUIRED_SECTIONS if not isinstance(normalized[section], dict)
    )
    if invalid:
        raise StrategyPolicyValidationError(
            f"receipt.strategy_policy sections must be mappings: {invalid}"
        )
    validate_strategy_policy(normalized)
    return normalized


def _validate_policy_id(receipt: Mapping[str, Any], policy: Mapping[str, Any]) -> None:
    canonical = json.dumps(
        policy,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    expected = STRATEGY_POLICY_ID_PREFIX + hashlib.sha256(canonical).hexdigest()
    if receipt.get("strategy_policy_id") != expected:
        raise StrategyPolicyValidationError(
            "receipt.strategy_policy_id does not match strategy_policy"
        )


def _validate_receipt_carriers(receipt: Mapping[str, Any], policy: Mapping[str, Any]) -> None:
    if receipt.get("publication_tier") not in {"production", "research"}:
        raise StrategyPolicyValidationError(
            "receipt.publication_tier must be production or research for v2"
        )
    if receipt.get("eligible_for_live") is not False:
        raise StrategyPolicyValidationError("receipt.eligible_for_live must be false for v2")
    safety = cast(Mapping[str, Any], policy["safety"])
    if safety.get("publication_tier") != receipt.get("publication_tier"):
        raise StrategyPolicyValidationError(
            "strategy_policy safety publication_tier does not match receipt"
        )
    if safety.get("eligible_for_live") is not receipt.get("eligible_for_live"):
        raise StrategyPolicyValidationError(
            "strategy_policy safety eligible_for_live does not match receipt"
        )
    policy_scope = str(safety.get("market_scope") or "").strip().lower().replace("_", "-")
    receipt_scope = str(receipt.get("market_scope") or "").strip().lower().replace("_", "-")
    if policy_scope != receipt_scope:
        raise StrategyPolicyValidationError(
            "strategy_policy safety market_scope does not match receipt"
        )
    features = cast(Mapping[str, Any], policy["features"])
    if features.get("feature_set_id") != receipt.get("feature_set_id"):
        raise StrategyPolicyValidationError("strategy_policy feature_set_id does not match receipt")
    policy_pool = cast(Mapping[str, Any], policy["candidate_pool"])
    receipt_pool = receipt.get("candidate_pool")
    if not isinstance(receipt_pool, Mapping):
        raise StrategyPolicyValidationError("receipt.candidate_pool must be a mapping for v2")
    for field in ("mode", "policy_id"):
        if policy_pool.get(field) != receipt_pool.get(field):
            raise StrategyPolicyValidationError(
                f"strategy_policy candidate_pool {field} does not match receipt"
            )


def validate_strategy_policy_v2(receipt: Mapping[str, Any]) -> None:
    """Validate canonical policy semantics, identity, and production carriers."""

    policy = _canonical_policy(receipt.get("strategy_policy"))
    _validate_policy_id(receipt, policy)
    _validate_receipt_carriers(receipt, policy)


__all__ = ["StrategyPolicyValidationError", "validate_strategy_policy_v2"]
