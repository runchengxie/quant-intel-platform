"""Fail closed across automatic route fallback when provider outcome is unknown."""

from __future__ import annotations

from collections.abc import Callable
from functools import wraps
from typing import Any

from a_share_daily.delivery import state


class UnknownDeliveryError(OSError):
    def __init__(self, intent_key: str, detail: str = "") -> None:
        self.intent_key = intent_key
        super().__init__(f"unknown delivery intent {intent_key}; {detail}")


def unknown_delivery_receipt(*, exit_code: bool = False) -> Callable[..., Any]:
    def decorate(function: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(function)
        def guarded(**kwargs: Any) -> Any:
            try:
                return function(**kwargs)
            except UnknownDeliveryError as error:
                context = kwargs["context"]
                state._write_delivery_status(
                    kind=kwargs.get("kind", "morning"),
                    trade_date=kwargs["trade_date"],
                    signal_date=kwargs.get("signal_date"),
                    mode=context.mode,
                    success=False,
                    routes={"unknown_intent": error.intent_key},
                    artifacts=kwargs["artifacts"],
                    lark_targets=context.lark_targets,
                    hermes_targets=context.hermes_targets,
                    delivery_outcome="unknown",
                )
                return 1 if exit_code else False

        return guarded

    return decorate
