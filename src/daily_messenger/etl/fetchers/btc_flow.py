"""BTC/ETF 资金流抓取。

从 daily_messenger.etl.run_fetch 拆出的数据源组，依赖共享工具层
(daily_messenger.etl.fetchers._common) 与网络层 (daily_messenger.etl.http)。
"""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any

import requests

from daily_messenger.etl.config import (
    coerce_api_key as _coerce_api_key,
)
from daily_messenger.etl.fetchers._common import (
    BROWSER_USER_AGENT,
    _latest_date,
    _parse_number,
    _safe_float,
)
from daily_messenger.etl.fetchers.normalize import (
    _HTMLTableParser,
)
from daily_messenger.etl.http import (
    REQUEST_TIMEOUT,
    RetryPolicy,
)
from daily_messenger.etl.http import (
    request_json as _request_json,
)
from daily_messenger.etl.simulation import (
    simulate_btc_theme as _simulate_btc_theme,
)
from daily_messenger.etl.types import FetchStatus

logger = logging.getLogger(__name__)

SOSOVALUE_INFLOW_URL = "https://api.sosovalue.xyz/openapi/v2/etf/historicalInflowChart"
COINGLASS_ETF_ENDPOINTS = (
    "https://open-api-v4.coinglass.com/api/bitcoin/etf/flow-history",
    "https://open-api-v1.coinglass.com/api/bitcoin/etf/flow-history",
)


def _fetch_sosovalue_latest_flow(api_key: str) -> tuple[float | None, FetchStatus]:
    headers = {
        "User-Agent": BROWSER_USER_AGENT,
        "Accept": "application/json",
        "Content-Type": "application/json",
        "x-soso-api-key": api_key,
    }
    body = {"type": "us-btc-spot"}
    try:
        payload = _request_json(
            SOSOVALUE_INFLOW_URL,
            method="POST",
            json_body=body,
            headers=headers,
            policy=RetryPolicy(retries=2, backoff_start=0.8, hard_deadline=15.0),
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("_fetch_sosovalue_latest_flow" + " 捕获到异常", exc_info=True)
        return None, FetchStatus(
            name="btc_etf_flow_sosovalue",
            ok=False,
            message=f"SoSoValue 请求失败: {exc}",
        )

    code = payload.get("code")
    if code not in (0, "0", 200, "200", None):
        message = payload.get("msg") or payload.get("message") or f"code={code}"
        return None, FetchStatus(
            name="btc_etf_flow_sosovalue",
            ok=False,
            message=f"SoSoValue 返回错误: {message}",
        )

    data = payload.get("data")
    records: list[dict[str, Any]] = []
    if isinstance(data, list):
        records = [item for item in data if isinstance(item, dict)]
    elif isinstance(data, dict):
        for key in ("result", "list", "items", "data", "rows"):
            candidate = data.get(key)
            if isinstance(candidate, list):
                records = [item for item in candidate if isinstance(item, dict)]
                break
        if not records and data:
            records = [data]

    latest_amount: float | None = None
    latest_day = ""
    latest_ts: datetime | None = None
    for item in records:
        day_value = item.get("date") or item.get("day")
        amount_value = (
            item.get("totalNetInflow")
            or item.get("netInflow")
            or item.get("netflow")
            or item.get("netFlow")
        )
        amount = _safe_float(amount_value)
        if not day_value or amount is None:
            continue
        day_text = str(day_value)[:10]
        try:
            parsed_day = datetime.strptime(day_text, "%Y-%m-%d")
        except ValueError:
            continue
        if latest_ts is None or parsed_day > latest_ts:
            latest_ts = parsed_day
            latest_day = parsed_day.strftime("%Y-%m-%d")
            latest_amount = amount

    if latest_amount is None or not latest_day:
        return None, FetchStatus(
            name="btc_etf_flow_sosovalue",
            ok=False,
            message="SoSoValue 响应缺少有效数据",
        )

    net_musd = latest_amount / 1_000_000.0
    return net_musd, FetchStatus(
        name="btc_etf_flow_sosovalue",
        ok=True,
        message=f"SoSoValue ETF 净流入已获取（{latest_day}）",
    )


def _coinglass_extract_records(data: Any) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    if isinstance(data, list):
        records = [item for item in data if isinstance(item, dict)]
    elif isinstance(data, dict):
        for key in ("list", "rows", "result", "items", "data"):
            candidate = data.get(key)
            if isinstance(candidate, list):
                records = [item for item in candidate if isinstance(item, dict)]
                break
        if not records and data:
            records = [data]
    return records


def _coinglass_pick_latest(
    records: list[dict[str, Any]],
) -> tuple[float | None, str]:
    latest_amount: float | None = None
    latest_day = ""
    latest_ts: datetime | None = None
    for item in records:
        day_value = item.get("date") or item.get("day")
        amount_value = (
            item.get("netFlow")
            or item.get("netflow")
            or item.get("net_inflow")
            or item.get("netInflow")
            or item.get("totalNetInflow")
            or item.get("totalNetFlow")
        )
        amount = _safe_float(amount_value)
        if not day_value or amount is None:
            continue
        day_text = str(day_value)[:10]
        try:
            parsed_day = datetime.strptime(day_text, "%Y-%m-%d")
        except ValueError:
            continue
        if latest_ts is None or parsed_day > latest_ts:
            latest_ts = parsed_day
            latest_day = parsed_day.strftime("%Y-%m-%d")
            latest_amount = amount
    return latest_amount, latest_day


def _fetch_coinglass_latest_flow(api_key: str) -> tuple[float | None, FetchStatus]:
    headers = {
        "User-Agent": BROWSER_USER_AGENT,
        "Accept": "application/json",
        "coinglassSecret": api_key,
    }
    params = {"page": 1, "size": 10}
    errors: list[str] = []
    policy = RetryPolicy(retries=2, backoff_start=0.7, hard_deadline=12.0)
    for url in COINGLASS_ETF_ENDPOINTS:
        try:
            payload = _request_json(url, params=params, headers=headers, policy=policy)
        except Exception as exc:  # noqa: BLE001
            logger.warning("_fetch_coinglass_latest_flow" + " 捕获到异常", exc_info=True)
            errors.append(f"{url}: {exc}")
            continue

        code = payload.get("code")
        if code not in (0, "0", 200, "200", None):
            message = payload.get("msg") or payload.get("message") or f"code={code}"
            errors.append(f"{url}: {message}")
            continue

        data = payload.get("data")
        records = _coinglass_extract_records(data)
        latest_amount, latest_day = _coinglass_pick_latest(records)
        if latest_amount is None or not latest_day:
            errors.append(f"{url}: 缺少有效数据")
            continue

        net_amount = latest_amount / 1_000_000.0 if abs(latest_amount) > 100000 else latest_amount
        return net_amount, FetchStatus(
            name="btc_etf_flow_coinglass",
            ok=True,
            message=f"CoinGlass ETF 净流入已获取（{latest_day}）",
        )

    detail = "; ".join(errors) if errors else "未知原因"
    return None, FetchStatus(
        name="btc_etf_flow_coinglass", ok=False, message=f"CoinGlass 请求失败: {detail}"
    )


FARSIDE_PAGE_URL = "https://farside.co.uk/bitcoin-etf-flow-all-data/"


def _fetch_farside_flow_from_html(session: requests.Session) -> float:
    response = session.get(FARSIDE_PAGE_URL, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    parser = _HTMLTableParser()
    parser.feed(response.text)
    latest = _latest_date(parser.rows)
    if not latest:
        raise RuntimeError("未能解析 ETF 流入数据")
    total = latest[-1] if latest else None
    amount = _parse_number(total or "")
    if amount is None:
        raise RuntimeError("ETF 流入字段为空")
    return amount


def _fetch_farside_flow_from_api(session: requests.Session) -> float:
    response = session.get(
        "https://farside.co.uk/wp-json/wp/v2/pages",
        params={"slug": "bitcoin-etf-flow-all-data"},
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    payload = response.json()
    if not payload:
        raise RuntimeError("Farside 未返回内容")
    content = payload[0].get("content", {}).get("rendered", "")
    parser = _HTMLTableParser()
    parser.feed(content)
    latest = _latest_date(parser.rows)
    if not latest:
        raise RuntimeError("未能解析 ETF 流入数据")
    amount = _parse_number((latest[-1] if latest else "") or "")
    if amount is None:
        raise RuntimeError("ETF 流入字段为空")
    return amount


def _fetch_farside_latest_flow() -> tuple[float | None, FetchStatus]:
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": BROWSER_USER_AGENT,
            "Referer": "https://farside.co.uk/",
            "Accept": "text/html,application/json;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9,zh;q=0.8",
        }
    )
    cookie = os.getenv("FARSIDE_COOKIES")
    if cookie:
        session.headers.update({"Cookie": cookie})
    errors: list[str] = []
    for fetcher, label in (
        (
            _fetch_farside_flow_from_html,
            "html",
        ),
        (_fetch_farside_flow_from_api, "api"),
    ):
        try:
            amount = fetcher(session)
            return amount, FetchStatus(
                name="btc_etf_flow", ok=True, message=f"ETF 净流入读取成功（{label}）"
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("_fetch_farside_latest_flow" + " 捕获到异常", exc_info=True)
            errors.append(f"{label}: {exc}")
    detail = "; ".join(errors) if errors else "未知原因"
    return None, FetchStatus(name="btc_etf_flow", ok=False, message=f"Farside 请求失败: {detail}")


def _fetch_btc_etf_flow(
    api_keys: dict[str, Any],
) -> tuple[float | None, FetchStatus]:
    attempts: list[str] = []

    sosovalue_key = _coerce_api_key(api_keys.get("sosovalue"))
    if sosovalue_key:
        amount, status = _fetch_sosovalue_latest_flow(sosovalue_key)
        if status.ok and amount is not None:
            message = status.message
            if attempts:
                message += f"；此前失败: {', '.join(attempts)}"
            return amount, FetchStatus(name="btc_etf_flow", ok=True, message=message)
        attempts.append(status.message or "SoSoValue 获取失败")

    coinglass_key = _coerce_api_key(api_keys.get("coinglass"))
    if coinglass_key:
        amount, status = _fetch_coinglass_latest_flow(coinglass_key)
        if status.ok and amount is not None:
            message = status.message
            if attempts:
                message += f"；此前失败: {', '.join(attempts)}"
            return amount, FetchStatus(name="btc_etf_flow", ok=True, message=message)
        attempts.append(status.message or "CoinGlass 获取失败")

    amount, status = _fetch_farside_latest_flow()
    if status.ok and amount is not None:
        message = status.message
        if attempts:
            message += f"；已跳过 {', '.join(attempts)}"
        return amount, FetchStatus(name="btc_etf_flow", ok=True, message=message)

    if status.message:
        attempts.append(status.message)
    detail = "；".join(filter(None, attempts))
    message = detail or "ETF 净流入获取失败"
    return None, FetchStatus(name="btc_etf_flow", ok=False, message=message)


def _fetch_coinbase_spot() -> tuple[float | None, FetchStatus]:
    url = "https://api.coinbase.com/v2/prices/BTC-USD/spot"
    try:
        payload = _request_json(url)
    except Exception as exc:  # noqa: BLE001
        logger.warning("_fetch_coinbase_spot" + " 捕获到异常", exc_info=True)
        return None, FetchStatus(
            name="coinbase_spot", ok=False, message=f"Coinbase 请求失败: {exc}"
        )

    try:
        amount = float(payload["data"]["amount"])
    except (KeyError, TypeError, ValueError) as exc:
        return None, FetchStatus(
            name="coinbase_spot", ok=False, message=f"Coinbase 响应解析失败: {exc}"
        )

    return amount, FetchStatus(name="coinbase_spot", ok=True, message="Coinbase 现货价格已获取")


def _fetch_okx_funding() -> tuple[float | None, FetchStatus]:
    url = "https://www.okx.com/api/v5/public/funding-rate"
    try:
        payload = _request_json(url, params={"instId": "BTC-USD-SWAP"})
    except Exception as exc:  # noqa: BLE001
        logger.warning("_fetch_okx_funding" + " 捕获到异常", exc_info=True)
        return None, FetchStatus(name="okx_funding", ok=False, message=f"OKX 请求失败: {exc}")

    if payload.get("code") != "0":
        return None, FetchStatus(
            name="okx_funding", ok=False, message=f"OKX 返回错误: {payload.get('msg')}"
        )

    data = payload.get("data") or []
    if not data:
        return None, FetchStatus(name="okx_funding", ok=False, message="OKX 未返回资金费率")

    try:
        rate = float(data[0]["fundingRate"])
    except (KeyError, TypeError, ValueError) as exc:
        return None, FetchStatus(name="okx_funding", ok=False, message=f"资金费率解析失败: {exc}")

    return rate, FetchStatus(name="okx_funding", ok=True, message="OKX 资金费率已获取")


def _fetch_okx_basis(spot_price: float) -> tuple[float | None, FetchStatus]:
    url = "https://www.okx.com/api/v5/market/ticker"
    try:
        payload = _request_json(url, params={"instId": "BTC-USD-SWAP"})
    except Exception as exc:  # noqa: BLE001
        logger.warning("_fetch_okx_basis" + " 捕获到异常", exc_info=True)
        return None, FetchStatus(name="okx_basis", ok=False, message=f"OKX ticker 请求失败: {exc}")

    if payload.get("code") != "0":
        return None, FetchStatus(
            name="okx_basis", ok=False, message=f"OKX 返回错误: {payload.get('msg')}"
        )

    data = payload.get("data") or []
    if not data:
        return None, FetchStatus(name="okx_basis", ok=False, message="OKX 未返回永续价格")

    try:
        last_price = float(data[0]["last"])
    except (KeyError, TypeError, ValueError) as exc:
        return None, FetchStatus(name="okx_basis", ok=False, message=f"永续价格解析失败: {exc}")

    if spot_price <= 0:
        return None, FetchStatus(name="okx_basis", ok=False, message="现货价格无效，无法计算基差")

    basis = (last_price - spot_price) / spot_price
    return basis, FetchStatus(name="okx_basis", ok=True, message="已计算 OKX 永续基差")


def _fetch_btc_payload(
    api_keys: dict[str, Any],
    trading_day: str,
    previous_btc: dict[str, Any],
    statuses: list[Any],
) -> tuple[dict[str, Any], bool]:
    spot_price, spot_status = _fetch_coinbase_spot()
    statuses.append(spot_status)
    funding_rate, funding_status = _fetch_okx_funding()
    statuses.append(funding_status)

    basis = None
    if spot_price is not None:
        basis, basis_status = _fetch_okx_basis(spot_price)
        statuses.append(basis_status)
    else:
        statuses.append(
            FetchStatus(name="okx_basis", ok=False, message="缺少现货价格，无法计算基差")
        )

    etf_flow, flow_status = _fetch_btc_etf_flow(api_keys)
    statuses.append(flow_status)
    flow_ok = flow_status.ok
    if not flow_status.ok:
        previous_flow = _safe_float(previous_btc.get("etf_net_inflow_musd"))
        if previous_flow is not None:
            etf_flow = previous_flow
            statuses.append(
                FetchStatus(name="btc_etf_flow_fallback", ok=True, message="使用上一期 ETF 净流入")
            )

    if (
        spot_price is not None
        and funding_rate is not None
        and basis is not None
        and etf_flow is not None
    ):
        statuses.append(FetchStatus(name="btc", ok=True, message="BTC 主题数据已获取"))
        return (
            {
                "date": trading_day,
                "spot_price_usd": round(spot_price, 2),
                "perpetual_price_usd": round(spot_price * (1 + basis), 2),
                "etf_net_inflow_musd": round(etf_flow, 2),
                "funding_rate": round(funding_rate, 6),
                "futures_basis": round(basis, 6),
            },
            bool(spot_status.ok and funding_status.ok and flow_ok),
        )

    btc_data, sim_status = _simulate_btc_theme(trading_day)
    statuses.append(sim_status)
    return btc_data, False
