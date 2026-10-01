"""Classify optional provider failures without retaining URLs or response bodies."""

import re

import requests


def failure_reason(error: Exception) -> str:
    if isinstance(error, (TimeoutError, requests.Timeout)):
        return "timeout"
    response = getattr(error, "response", None)
    status = getattr(response, "status_code", None)
    if isinstance(status, int) and 400 <= status <= 599:
        return f"http_{status}"
    text = str(error)
    match = re.match(r"HTTP 状态错误: ([45]\d{2})(?:\s|$)", text)
    if match:
        return "http_" + match[1]
    reason = "provider_unavailable"
    if "Yahoo Finance" in text and ("尚未完成" in text or "尚未到完成时点" in text):
        reason = "bar_incomplete"
    elif "Yahoo Finance 指定交易日日线不存在或重复" in text:
        reason = "target_bar_missing_or_duplicate"
    elif isinstance(error, (ValueError, TypeError)):
        reason = "invalid_data"
    return reason
