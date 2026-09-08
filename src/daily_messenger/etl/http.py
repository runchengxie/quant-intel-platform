"""HTTP helpers shared by ETL fetchers."""

from __future__ import annotations

import random
import time
from collections.abc import Iterable
from typing import Any

import requests

REQUEST_TIMEOUT = 15
USER_AGENT = "Mozilla/5.0 (compatible; daily-messenger/0.1)"


def respect_retry_after(resp: requests.Response) -> float | None:
    retry_after = resp.headers.get("Retry-After")
    if not retry_after:
        return None
    try:
        return float(retry_after)
    except ValueError:
        return None


def sleep_exact(seconds: float) -> None:
    if seconds and seconds > 0:
        time.sleep(seconds)


class RetryPolicy:
    retries: int
    backoff_start: float
    backoff_factor: float
    jitter: float
    status_forcelist: set[int]
    max_sleep: float
    per_request_timeout: float
    hard_deadline: float | None

    def __init__(
        self,
        retries: int = 3,
        backoff_start: float = 0.6,
        backoff_factor: float = 2.0,
        jitter: float = 0.3,
        status_forcelist: Iterable[int] = (408, 409, 425, 429, 500, 502, 503, 504),
        max_sleep: float = 8.0,
        per_request_timeout: float = REQUEST_TIMEOUT,
        hard_deadline: float | None = 20.0,
    ) -> None:
        self.retries = retries
        self.backoff_start = backoff_start
        self.backoff_factor = backoff_factor
        self.jitter = jitter
        self.status_forcelist = set(status_forcelist)
        self.max_sleep = max_sleep
        self.per_request_timeout = per_request_timeout
        self.hard_deadline = hard_deadline


RETRY_DEFAULT = RetryPolicy()
RETRY_EDGAR = RetryPolicy(retries=3, backoff_start=0.6, backoff_factor=2.0, jitter=0.25)


def _compute_backoff(policy: RetryPolicy, delay: float) -> float:
    """Compute a jittered backoff duration capped at ``policy.max_sleep``."""
    return min(delay * (1.0 + random.random() * policy.jitter), policy.max_sleep)


def _exceeds_deadline(policy: RetryPolicy, start: float, sleep_seconds: float) -> bool:
    """Return True if sleeping now would breach the hard deadline."""
    return bool(
        policy.hard_deadline and (time.monotonic() - start + sleep_seconds) > policy.hard_deadline
    )


def _process_response(
    resp: requests.Response,
    policy: RetryPolicy,
    attempt: int,
    delay: float,
    start: float,
    after_each_sleep: float,
) -> tuple[bool, Any, float]:
    """Process a successful HTTP response.

    Returns ``(retry, payload, next_delay)``. ``retry=True`` means the caller
    should loop again (the request should be retried); ``retry=False`` means
    ``payload`` holds the parsed body and the caller should return it.
    """
    if resp.status_code in policy.status_forcelist:
        retry_after = respect_retry_after(resp) if resp.status_code == 429 else None
        if attempt > policy.retries:
            resp.raise_for_status()
        sleep_seconds = retry_after if retry_after is not None else _compute_backoff(policy, delay)
        if _exceeds_deadline(policy, start, sleep_seconds):
            resp.raise_for_status()
        sleep_exact(sleep_seconds)
        return True, None, delay * policy.backoff_factor

    try:
        resp.raise_for_status()
    except Exception as exc:  # noqa: BLE001
        snippet = resp.text[:200] if getattr(resp, "text", None) else str(exc)
        raise RuntimeError(f"HTTP 状态错误: {resp.status_code} {snippet}") from exc

    try:
        payload = resp.json()
    except ValueError as exc:
        if attempt <= policy.retries:
            sleep_exact(min(0.5 * (1 + random.random()), 1.0))
            return True, None, delay
        raise RuntimeError("响应解析失败（JSON）") from exc

    if after_each_sleep > 0:
        sleep_exact(after_each_sleep)
    return False, payload, delay


def _attempt_request(
    own_session: requests.Session,
    method: str,
    url: str,
    params: dict[str, Any] | None,
    json_body: Any,
    hdrs: dict[str, str],
    policy: RetryPolicy,
    attempt: int,
    delay: float,
    start: float,
    after_each_sleep: float,
) -> tuple[bool, Any, float]:
    """Execute a single request attempt and decide whether to retry.

    Returns ``(retry, payload, next_delay)``. Transport errors that should be
    retried are handled here (with backoff sleep); fatal errors raise.
    """
    try:
        resp = own_session.request(
            method,
            url,
            params=params,
            json=json_body,
            headers=hdrs,
            timeout=policy.per_request_timeout,
        )
    except requests.RequestException as exc:
        if attempt > policy.retries:
            raise RuntimeError(f"HTTP 请求失败（已重试 {attempt - 1} 次）: {exc}") from exc
        _backoff_and_sleep(policy, delay, start)
        return True, None, delay * policy.backoff_factor
    return _process_response(resp, policy, attempt, delay, start, after_each_sleep)


def request_json(
    url: str,
    *,
    method: str = "GET",
    session: requests.Session | None = None,
    params: dict[str, Any] | None = None,
    json_body: Any = None,
    headers: dict[str, str] | None = None,
    policy: RetryPolicy = RETRY_DEFAULT,
    after_each_sleep: float = 0.0,
    trust_env: bool | None = None,
) -> Any:
    method = method.upper()
    own_session = session or requests.Session()
    close_session = session is None
    if trust_env is not None:
        own_session.trust_env = trust_env
    hdrs = {"User-Agent": USER_AGENT}
    if headers:
        hdrs.update(headers)
    attempt = 0
    delay = policy.backoff_start
    start = time.monotonic()
    try:
        while True:
            attempt += 1
            retry, payload, delay = _attempt_request(
                own_session,
                method,
                url,
                params,
                json_body,
                hdrs,
                policy,
                attempt,
                delay,
                start,
                after_each_sleep,
            )
            if not retry:
                return payload
    finally:
        if close_session:
            own_session.close()


def _backoff_and_sleep(policy: RetryPolicy, delay: float, start: float) -> None:
    """Compute jittered backoff and sleep, raising if the deadline would be breached."""
    sleep_seconds = _compute_backoff(policy, delay)
    if _exceeds_deadline(policy, start, sleep_seconds):
        raise RuntimeError("HTTP 请求失败：超过重试预算")
    sleep_exact(sleep_seconds)
