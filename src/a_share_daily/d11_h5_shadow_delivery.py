"""Render and deliver the research-only D11-H5 staggered target."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from .d11_h5_shadow_receipt import (
    successful_message as _successful_message,
)
from .d11_h5_shadow_receipt import (
    successful_receipt_for_dates,
)
from .delivery.targets import resolve_delivery_targets

LEGACY_SELECTION_SCHEMA = "strategy_pipeline.d11_h5_shadow.v1"
LEGACY_PRODUCT_ID = "d11_h5_shadow.cn.v1"
SELECTION_SCHEMA = "strategy_pipeline.d11_h5_shadow.v2"
DELIVERY_SCHEMA = "d11_h5_shadow_delivery.v1"
PRODUCT_ID = "d11_h5_shadow.cn.v2"
PRESENTATION_VERSION = "internal-research.v2"
REQUIRED_GROUP_AUDIENCES = ("client", "internal")
DEFAULT_STRATEGY_DOC_URL = "https://example.com/strategy-document"


class D11H5DeliveryError(ValueError):
    """Raised when the D11-H5 research artifact is not safe to deliver."""


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        temporary.write_text(text, encoding="utf-8")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def _atomic_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    _atomic_write_text(
        path,
        json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
    )


def _read_json_object(path: Path, *, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise D11H5DeliveryError(f"cannot read {label}: {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise D11H5DeliveryError(f"{label} is not valid JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise D11H5DeliveryError(f"{label} must contain a JSON object")
    return cast(dict[str, Any], payload)


def _mapping(value: Any, *, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise D11H5DeliveryError(f"{label} must be an object")
    return value


def _rows(value: Any, *, label: str) -> list[Mapping[str, Any]]:
    if not isinstance(value, list) or not all(isinstance(row, Mapping) for row in value):
        raise D11H5DeliveryError(f"{label} must be a list of objects")
    return cast(list[Mapping[str, Any]], value)


def _validate_v2_selection(
    artifact: Mapping[str, Any],
    aggregate: Mapping[str, Any],
    aggregate_positions: Sequence[Mapping[str, Any]],
) -> None:
    strategy = _mapping(artifact.get("strategy"), label="selection.strategy")
    expected = {
        "active_sleeves": 5,
        "positions_per_sleeve": 4,
        "aggregate_slot_count": 20,
        "cross_sleeve_overlap_allowed": False,
        "max_new_positions_per_refresh": 4,
    }
    mismatches = [
        (field, strategy.get(field), value)
        for field, value in expected.items()
        if strategy.get(field) != value
    ]
    if mismatches:
        field, actual, expected_value = mismatches[0]
        raise D11H5DeliveryError(
            f"D11-H5 v2 strategy {field}={actual!r}, expected {expected_value!r}"
        )
    aggregate_symbols = [str(row.get("symbol", "")) for row in aggregate_positions]
    if (
        len(aggregate_positions) != 20
        or int(aggregate.get("unique_position_count", -1)) != 20
        or any(not symbol for symbol in aggregate_symbols)
        or len(set(aggregate_symbols)) != 20
    ):
        raise D11H5DeliveryError("D11-H5 v2 aggregate target must contain 20 distinct positions")
    if abs(float(aggregate.get("cash_weight", 0.0))) > 1e-8 or any(
        abs(float(row.get("target_weight", 0.0)) - 0.05) > 1e-8 for row in aggregate_positions
    ):
        raise D11H5DeliveryError(
            "D11-H5 v2 aggregate target must be fully invested at 5% per stock"
        )


def load_selection(
    path: Path, *, expected_source_date: str, expected_signal_date: str
) -> dict[str, Any]:
    artifact = _read_json_object(path, label="D11-H5 selection")
    schema_product = (artifact.get("schema_version"), artifact.get("product_id"))
    expected_sleeve_size = {
        (LEGACY_SELECTION_SCHEMA, LEGACY_PRODUCT_ID): 20,
        (SELECTION_SCHEMA, PRODUCT_ID): 4,
    }.get(schema_product)
    if expected_sleeve_size is None:
        raise D11H5DeliveryError(f"unsupported D11-H5 selection schema/product: {schema_product!r}")
    expected: dict[str, Any] = {
        "status": "passed",
        "research_only": True,
        "eligible_for_live": False,
        "source_date": expected_source_date,
        "signal_date": expected_signal_date,
    }
    for field, value in expected.items():
        if artifact.get(field) != value:
            raise D11H5DeliveryError(
                f"D11-H5 selection {field}={artifact.get(field)!r}, expected {value!r}"
            )
    content_sha = artifact.get("content_sha256")
    if not isinstance(content_sha, str) or len(content_sha) != 64:
        raise D11H5DeliveryError("D11-H5 selection has no valid content hash")
    signal = _mapping(artifact.get("signal"), label="selection.signal")
    positions = _rows(signal.get("positions"), label="selection.signal.positions")
    if (
        len(positions) != expected_sleeve_size
        or int(signal.get("selected_count", -1)) != expected_sleeve_size
    ):
        raise D11H5DeliveryError(
            f"D11-H5 rotating sleeve must contain exactly {expected_sleeve_size} positions"
        )
    symbols = [str(row.get("symbol", "")) for row in positions]
    if any(not symbol for symbol in symbols) or len(set(symbols)) != expected_sleeve_size:
        raise D11H5DeliveryError("D11-H5 rotating sleeve contains invalid or duplicate symbols")
    aggregate = _mapping(artifact.get("aggregate_target"), label="selection.aggregate_target")
    aggregate_positions = _rows(
        aggregate.get("positions"), label="selection.aggregate_target.positions"
    )
    total_weight = sum(float(row.get("target_weight", 0.0)) for row in aggregate_positions)
    total_weight += float(aggregate.get("cash_weight", 0.0))
    if abs(total_weight - 1.0) > 1e-8:
        raise D11H5DeliveryError(
            f"D11-H5 aggregate target weights sum to {total_weight:.8f}, expected 1"
        )
    if int(aggregate.get("sleeve_count", -1)) != 5:
        raise D11H5DeliveryError("D11-H5 aggregate target must contain five active sleeves")
    if schema_product == (SELECTION_SCHEMA, PRODUCT_ID):
        _validate_v2_selection(artifact, aggregate, aggregate_positions)
    return artifact


def _date_dash(value: Any) -> str:
    text = str(value or "")
    return f"{text[:4]}-{text[4:6]}-{text[6:]}" if len(text) == 8 else text


def _short_code(symbol: Any) -> str:
    return str(symbol or "").split(".", maxsplit=1)[0]


def _name_symbol(row: Mapping[str, Any]) -> str:
    return f"{row.get('name', row.get('symbol', ''))}（{_short_code(row.get('symbol'))}）"


def _is_v2(artifact: Mapping[str, Any]) -> bool:
    return (
        artifact.get("schema_version") == SELECTION_SCHEMA
        and artifact.get("product_id") == PRODUCT_ID
    )


def _png_positions(artifact: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    signal = _mapping(artifact["signal"], label="selection.signal")
    signal_positions = _rows(signal["positions"], label="selection.signal.positions")
    if not _is_v2(artifact):
        return signal_positions
    aggregate = _mapping(artifact["aggregate_target"], label="selection.aggregate_target")
    aggregate_positions = _rows(
        aggregate["positions"], label="selection.aggregate_target.positions"
    )
    refreshed = {str(row.get("symbol")): row for row in signal_positions}
    return [
        {
            **dict(row),
            "is_refreshed": str(row.get("symbol")) in refreshed,
            "is_new": bool(refreshed.get(str(row.get("symbol")), {}).get("is_new")),
            "model_rank": refreshed.get(str(row.get("symbol")), {}).get("model_rank"),
        }
        for row in aggregate_positions
    ]


def _resolve_strategy_doc_url(explicit: str | None = None) -> str | None:
    value = explicit or os.environ.get("D11_H5_STRATEGY_DOC_URL", DEFAULT_STRATEGY_DOC_URL)
    return value.strip() or None


def render_markdown(artifact: Mapping[str, Any], *, strategy_doc_url: str | None = None) -> str:
    signal = _mapping(artifact["signal"], label="selection.signal")
    aggregate = _mapping(artifact["aggregate_target"], label="selection.aggregate_target")
    positions = _rows(signal["positions"], label="selection.signal.positions")
    added = _rows(signal.get("added", []), label="selection.signal.added")
    removed = _rows(signal.get("removed", []), label="selection.signal.removed")
    aggregate_positions = _rows(
        aggregate["positions"], label="selection.aggregate_target.positions"
    )
    is_v2 = _is_v2(artifact)
    sleeve_size = 4 if is_v2 else 20
    aggregate_weight = 0.05 if is_v2 else 0.01
    lines = [
        "📊 中期排序五日错峰｜每日关注清单",
        "",
        (
            f"信号：{_date_dash(artifact['source_date'])} 收盘 → "
            f"{_date_dash(artifact['signal_date'])} 开盘目标"
        ),
        (
            f"本次轮换：第 {signal['cohort_number']}/5 个子组合 · "
            f"保留 {signal['retained_count']} · 新增 {signal['new_position_count']} · "
            f"移除 {signal['exited_count']}"
        ),
        (
            f"五个子组合合并：{aggregate['unique_position_count']} 只 · "
            f"现金目标 {float(aggregate['cash_weight']):.1%}"
        ),
        "",
        (f"本次更新子组合（{sleeve_size} 只，每只约占总组合 {aggregate_weight:.0%}）"),
        "",
    ]
    for index, row in enumerate(positions, start=1):
        state = "新增" if bool(row.get("is_new")) else "保留"
        lines.append(f"{index}. {_name_symbol(row)} · 模型排名 #{int(row['model_rank'])} · {state}")
    added_text = "、".join(_name_symbol(row) for row in added) or "无"
    removed_text = "、".join(_name_symbol(row) for row in removed) or "无"
    lines.extend(
        [
            "",
            "本次变化",
            "",
            f"- 新增：{added_text}",
            f"- 移除：{removed_text}",
            "",
            "当前完整组合" if is_v2 else "合并目标中重复入选的股票",
            "",
        ]
    )
    if is_v2:
        for row in aggregate_positions:
            lines.append(f"- {_name_symbol(row)}：{float(row['target_weight']):.0%}")
    else:
        concentrated = [
            row for row in aggregate_positions if float(row.get("target_weight", 0.0)) >= 0.03
        ][:15]
        for row in concentrated:
            lines.append(
                f"- {_name_symbol(row)}：{float(row['target_weight']):.0%} "
                f"（{int(row['sleeve_occurrences'])}/5 个子组合）"
            )
    resolved_doc_url = _resolve_strategy_doc_url(strategy_doc_url)
    if resolved_doc_url:
        lines.extend(
            [
                "",
                (f"📖 查看完整方法：[中期排序五日错峰方法说明]({resolved_doc_url})"),
            ]
        )
    return "\n".join(lines) + "\n"


def render_png(artifact: Mapping[str, Any], output_path: Path) -> Path:
    from .d11_h5_shadow_render import render_png as render_png_impl

    return render_png_impl(artifact, output_path)


def render_selection(
    artifact: Mapping[str, Any],
    output_dir: Path,
    *,
    strategy_doc_url: str | None = None,
) -> tuple[Path, Path]:
    markdown_path = output_dir / "d11_h5_shadow.md"
    image_path = output_dir / "d11_h5_shadow.png"
    _atomic_write_text(
        markdown_path,
        render_markdown(artifact, strategy_doc_url=strategy_doc_url),
    )
    render_png(artifact, image_path)
    return markdown_path, image_path


def _extract_json(text: str) -> dict[str, Any]:
    stripped = text.strip()
    candidates = [stripped]
    start = stripped.find("{")
    end = stripped.rfind("}")
    if 0 <= start < end:
        candidates.append(stripped[start : end + 1])
    for candidate in candidates:
        try:
            value = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return cast(dict[str, Any], value)
    for line in reversed([line.strip() for line in text.splitlines() if line.strip()]):
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return cast(dict[str, Any], value)
    return {}


def _message_id(payload: Mapping[str, Any]) -> str | None:
    data = payload.get("data")
    candidates = [payload.get("message_id"), payload.get("messageId")]
    if isinstance(data, Mapping):
        candidates.extend((data.get("message_id"), data.get("messageId")))
    for value in candidates:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _lark_cli(explicit: str | None) -> str:
    candidate = explicit or os.environ.get("LARK_CLI") or str(Path.home() / ".local/bin/lark-cli")
    resolved = candidate if Path(candidate).is_file() else shutil.which(candidate)
    if not resolved:
        raise D11H5DeliveryError(f"lark-cli is unavailable: {candidate}")
    return str(resolved)


def _send_lark(
    *,
    lark_cli: str,
    chat_id: str,
    medium: str,
    markdown: str,
    image_path: Path,
    signal_date: str,
    content_sha256: str,
) -> dict[str, Any]:
    key_material = f"{PRODUCT_ID}\0{medium}\0{chat_id}\0{signal_date}\0{content_sha256}"
    key = "d11-h5-" + hashlib.sha256(key_material.encode()).hexdigest()[:24]
    command = [lark_cli, "im", "+messages-send", "--chat-id", chat_id]
    cwd: Path | None = None
    if medium == "markdown":
        command.extend(("--markdown", markdown))
    elif medium == "image":
        command.extend(("--msg-type", "image", "--image", image_path.name))
        cwd = image_path.parent
    else:
        raise D11H5DeliveryError(f"unsupported Lark medium: {medium}")
    command.extend(("--idempotency-key", key, "--as", "bot", "--format", "json"))
    result = subprocess.run(
        command,
        cwd=cwd,
        text=True,
        capture_output=True,
        timeout=90,
        check=False,
    )
    payload = _extract_json(result.stdout)
    message_id = _message_id(payload)
    ok = result.returncode == 0 and payload.get("ok") is not False and bool(message_id)
    return {
        "status": "sent" if ok else "failed",
        "idempotency_key": key,
        "content_sha256": content_sha256,
        "message_id": message_id,
        "returncode": result.returncode,
        "error": None if ok else (result.stderr or result.stdout)[-500:],
    }


def _send_or_reuse(
    *,
    previous_message: Any,
    expected_hash: str,
    lark_cli: str,
    chat_id: str,
    medium: str,
    markdown: str,
    image_path: Path,
    signal_date: str,
) -> dict[str, Any]:
    if _successful_message(previous_message, expected_hash):
        reused = dict(cast(Mapping[str, Any], previous_message))
        reused["status"] = "already_sent"
        return reused
    return _send_lark(
        lark_cli=lark_cli,
        chat_id=chat_id,
        medium=medium,
        markdown=markdown,
        image_path=image_path,
        signal_date=signal_date,
        content_sha256=expected_hash,
    )


def _target_fingerprint(chat_id: str) -> str:
    return hashlib.sha256(f"lark-chat\0{chat_id}".encode()).hexdigest()


def _filtered_targets(
    *,
    explicit_chat_ids: Sequence[str],
    explicit_audience: str,
    delivery_audience: str,
) -> dict[str, tuple[str, ...]]:
    if explicit_chat_ids:
        deduplicated = tuple(
            dict.fromkeys(item.strip() for item in explicit_chat_ids if item.strip())
        )
        return {explicit_audience: deduplicated}
    targets = resolve_delivery_targets()
    if delivery_audience == "all":
        return targets
    return {delivery_audience: targets[delivery_audience]}


def _previous_messages(
    receipt_path: Path,
    *,
    artifact: Mapping[str, Any],
    hashes: Mapping[str, str],
) -> tuple[
    dict[tuple[str, str], Mapping[str, Any]],
    dict[tuple[str, str], dict[str, Any]],
]:
    if not receipt_path.is_file():
        return {}, {}
    try:
        previous = _read_json_object(receipt_path, label="previous D11-H5 receipt")
    except D11H5DeliveryError:
        return {}, {}
    expected = {
        "schema_version": DELIVERY_SCHEMA,
        "product_id": PRODUCT_ID,
        "source_date": artifact["source_date"],
        "signal_date": artifact["signal_date"],
        "selection_sha256": hashes["selection"],
        "markdown_sha256": hashes["markdown"],
        "image_sha256": hashes["image"],
    }
    if any(previous.get(field) != value for field, value in expected.items()):
        return {}, {}
    messages_by_target: dict[tuple[str, str], Mapping[str, Any]] = {}
    rows_by_target: dict[tuple[str, str], dict[str, Any]] = {}
    try:
        targets = _rows(previous.get("targets"), label="previous delivery.targets")
    except D11H5DeliveryError:
        return {}, {}
    for target in targets:
        messages = target.get("messages")
        if not isinstance(messages, Mapping):
            continue
        key = (str(target.get("audience")), str(target.get("target_fingerprint")))
        messages_by_target[key] = messages
        rows_by_target[key] = dict(target)
    return messages_by_target, rows_by_target


def validate_delivery_receipt(
    receipt_path: Path,
    *,
    expected_source_date: str,
    expected_signal_date: str,
    required_audiences: Sequence[str],
) -> None:
    receipt = _read_json_object(receipt_path, label="D11-H5 delivery receipt")
    expected = {
        "schema_version": DELIVERY_SCHEMA,
        "source_date": expected_source_date,
        "signal_date": expected_signal_date,
        "success": True,
    }
    for field, value in expected.items():
        if receipt.get(field) != value:
            raise D11H5DeliveryError(
                f"D11-H5 delivery receipt {field}={receipt.get(field)!r}, expected {value!r}"
            )
    if receipt.get("product_id") not in {PRODUCT_ID, LEGACY_PRODUCT_ID}:
        raise D11H5DeliveryError(
            "D11-H5 delivery receipt product_id="
            f"{receipt.get('product_id')!r}, expected a supported migration product"
        )
    targets = _rows(receipt.get("targets"), label="delivery.targets")
    completed: set[str] = set()
    for target in targets:
        messages = target.get("messages")
        if not isinstance(messages, Mapping):
            continue
        if _successful_message(
            messages.get("markdown"), str(receipt["markdown_sha256"])
        ) and _successful_message(messages.get("image"), str(receipt["image_sha256"])):
            completed.add(str(target.get("audience")))
    missing = sorted(set(required_audiences) - completed)
    if missing:
        raise D11H5DeliveryError("D11-H5 delivery misses audiences: " + ",".join(missing))


def _run_producer(
    *,
    strategy_root: Path,
    data_root: Path,
    strategy_output_root: Path,
    bootstrap_root: Path | None,
    source_date: str,
    signal_date: str,
) -> Path:
    published_root = data_root / "published/strategies/d11_h5_shadow/runs"
    published_matches: list[Path] = []
    for candidate in published_root.glob("*/selection.json"):
        try:
            payload = json.loads(candidate.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if str(payload.get("source_date", "")).replace("-", "") == source_date.replace(
            "-", ""
        ) and str(payload.get("signal_date", "")).replace("-", "") == signal_date.replace("-", ""):
            published_matches.append(candidate)
    if published_matches:
        selected = max(published_matches, key=lambda path: path.stat().st_mtime)
        print(f"[d11-h5-shadow] consuming published selection artifact: {selected}")
        return selected

    command = [
        "uv",
        "run",
        "--offline",
        "--project",
        str(strategy_root),
        "strategy",
        "d11-h5-shadow",
        "--source-date",
        source_date,
        "--signal-date",
        signal_date,
        "--data-root",
        str(data_root),
        "--output-root",
        str(strategy_output_root),
    ]
    if bootstrap_root is not None:
        command.extend(["--bootstrap-root", str(bootstrap_root)])
    result = subprocess.run(
        command,
        cwd=Path.cwd(),
        text=True,
        capture_output=True,
        timeout=1200,
        check=False,
    )
    if result.returncode != 0:
        raise D11H5DeliveryError(
            "D11-H5 producer failed: " + (result.stderr or result.stdout)[-1200:]
        )
    payload = _extract_json(result.stdout)
    selection_path = payload.get("selection_path")
    if not isinstance(selection_path, str) or not selection_path:
        raise D11H5DeliveryError("D11-H5 producer did not return selection_path")
    return Path(selection_path).expanduser().resolve()


def _deliver_target_rows(
    *,
    targets: Mapping[str, Sequence[str]],
    previous_messages: Mapping[tuple[str, str], Mapping[str, Any]],
    previous_rows: Mapping[tuple[str, str], dict[str, Any]],
    hashes: Mapping[str, str],
    cli: str,
    markdown: str,
    image_path: Path,
    signal_date: str,
    receipt: dict[str, Any],
    receipt_path: Path,
) -> list[dict[str, Any]]:
    current_keys = {
        (audience, _target_fingerprint(chat_id))
        for audience, chat_ids in targets.items()
        for chat_id in chat_ids
    }
    target_rows = [row for key, row in previous_rows.items() if key not in current_keys]
    for audience, chat_ids in targets.items():
        for chat_id in chat_ids:
            fingerprint = _target_fingerprint(chat_id)
            previous = previous_messages.get((audience, fingerprint), {})
            messages = {
                "markdown": _send_or_reuse(
                    previous_message=previous.get("markdown"),
                    expected_hash=hashes["markdown"],
                    lark_cli=cli,
                    chat_id=chat_id,
                    medium="markdown",
                    markdown=markdown,
                    image_path=image_path,
                    signal_date=signal_date,
                ),
                "image": _send_or_reuse(
                    previous_message=previous.get("image"),
                    expected_hash=hashes["image"],
                    lark_cli=cli,
                    chat_id=chat_id,
                    medium="image",
                    markdown=markdown,
                    image_path=image_path,
                    signal_date=signal_date,
                ),
            }
            target_rows.append(
                {
                    "audience": audience,
                    "target_fingerprint": fingerprint,
                    "messages": messages,
                }
            )
            receipt["targets"] = target_rows
            _atomic_write_json(receipt_path, receipt)
    return target_rows


def deliver(
    *,
    artifact: Mapping[str, Any],
    selection_path: Path,
    markdown_path: Path,
    image_path: Path,
    receipt_path: Path,
    targets: Mapping[str, Sequence[str]],
    lark_cli: str | None,
    no_send: bool,
) -> dict[str, Any]:
    markdown = markdown_path.read_text(encoding="utf-8")
    hashes = {
        "selection": _sha256_file(selection_path),
        "markdown": _sha256_file(markdown_path),
        "image": _sha256_file(image_path),
    }
    preserved_receipt = (
        successful_receipt_for_dates(receipt_path, artifact=artifact) if no_send else None
    )
    previous_messages, previous_rows = _previous_messages(
        receipt_path,
        artifact=artifact,
        hashes=hashes,
    )
    receipt: dict[str, Any] = {
        "schema_version": DELIVERY_SCHEMA,
        "product_id": PRODUCT_ID,
        "presentation_version": PRESENTATION_VERSION,
        "source_date": artifact["source_date"],
        "signal_date": artifact["signal_date"],
        "selection_sha256": hashes["selection"],
        "markdown_sha256": hashes["markdown"],
        "image_sha256": hashes["image"],
        "updated_at": datetime.now(UTC).isoformat(),
        "no_send": no_send,
        "success": False,
        "targets": [],
    }
    if no_send:
        if preserved_receipt is not None:
            return preserved_receipt
        _atomic_write_json(receipt_path, receipt)
        return receipt
    cli = _lark_cli(lark_cli)
    if not targets or any(not chat_ids for chat_ids in targets.values()):
        raise D11H5DeliveryError("D11-H5 delivery target is not configured for every audience")
    # A targeted retry must keep successful rows for omitted audiences.
    target_rows = _deliver_target_rows(
        targets=targets,
        previous_messages=previous_messages,
        previous_rows=previous_rows,
        hashes=hashes,
        cli=cli,
        markdown=markdown,
        image_path=image_path,
        signal_date=str(artifact["signal_date"]),
        receipt=receipt,
        receipt_path=receipt_path,
    )
    receipt["success"] = all(
        _successful_message(row["messages"]["markdown"], hashes["markdown"])
        and _successful_message(row["messages"]["image"], hashes["image"])
        for row in target_rows
    )
    receipt["updated_at"] = datetime.now(UTC).isoformat()
    _atomic_write_json(receipt_path, receipt)
    if not receipt["success"]:
        raise D11H5DeliveryError("one or more D11-H5 Lark messages failed")
    return receipt


def run(argv: Sequence[str] | None = None) -> int:
    """Run the D11-H5 CLI while keeping the legacy module entry point."""
    from .d11_h5_shadow_cli import run as run_cli

    return run_cli(argv)


def main() -> None:
    from .d11_h5_shadow_cli import main as main_cli

    main_cli()


if __name__ == "__main__":
    main()

__all__ = [
    "D11H5DeliveryError",
    "deliver",
    "load_selection",
    "render_markdown",
    "render_png",
    "render_selection",
    "run",
    "validate_delivery_receipt",
]
