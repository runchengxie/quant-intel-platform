from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from matplotlib import image as mpimg

from a_share_daily import d11_h5_shadow_delivery as delivery
from a_share_daily.d11_h5_shadow_render import _position_row_copy


def _artifact() -> dict[str, object]:
    positions = [
        {
            "symbol": f"{index:06d}.SZ",
            "name": f"股票{index}",
            "industry": "测试行业",
            "score_percentile": 1 - index / 1000,
            "model_rank": index,
            "sleeve_weight": 0.25,
            "aggregate_target_weight": 0.05,
            "is_new": index <= 2,
        }
        for index in range(1, 5)
    ]
    aggregate = [
        {
            "symbol": f"{index:06d}.SZ",
            "name": f"股票{index}",
            "industry": "测试行业",
            "sleeve_occurrences": 1,
            "target_weight": 0.05,
        }
        for index in range(1, 21)
    ]
    return {
        "schema_version": delivery.SELECTION_SCHEMA,
        "product_id": delivery.PRODUCT_ID,
        "status": "passed",
        "research_only": True,
        "eligible_for_live": False,
        "source_date": "20260731",
        "signal_date": "20260803",
        "content_sha256": "a" * 64,
        "strategy": {
            "active_sleeves": 5,
            "positions_per_sleeve": 4,
            "aggregate_slot_count": 20,
            "cross_sleeve_overlap_allowed": False,
            "max_new_positions_per_refresh": 4,
        },
        "signal": {
            "cohort_number": 5,
            "selected_count": 4,
            "retained_count": 2,
            "new_position_count": 2,
            "exited_count": 2,
            "positions": positions,
            "added": positions[:2],
            "removed": [
                {"symbol": "000021.SZ", "name": "股票21"},
                {"symbol": "000022.SZ", "name": "股票22"},
            ],
        },
        "aggregate_target": {
            "sleeve_count": 5,
            "unique_position_count": 20,
            "cash_weight": 0.0,
            "positions": aggregate,
        },
    }


def test_load_and_render_research_only_selection(tmp_path: Path) -> None:
    selection_path = tmp_path / "selection.json"
    selection_path.write_text(json.dumps(_artifact(), ensure_ascii=False), encoding="utf-8")

    artifact = delivery.load_selection(
        selection_path,
        expected_source_date="20260731",
        expected_signal_date="20260803",
    )
    markdown = delivery.render_markdown(artifact)

    assert "中期排序五日错峰" in markdown
    assert "2026-07-31 收盘 → 2026-08-03 开盘目标" in markdown
    assert "每日关注清单" in markdown
    assert "研究影子" not in markdown
    assert "eligible_for_live=false" not in markdown
    assert "D11-D20 标签与 2026 区间参与过研究筛选" not in markdown
    assert "不构成投资建议或收益承诺" not in markdown
    assert delivery.DEFAULT_STRATEGY_DOC_URL in markdown
    assert "中期排序五日错峰方法说明" in markdown
    assert artifact["eligible_for_live"] is False
    assert "AI精选（新）" not in markdown
    assert "1. 股票1（000001）" in markdown
    assert "本次更新子组合（4 只，每只约占总组合 5%）" in markdown
    assert "当前完整组合" in markdown


def test_load_selection_accepts_legacy_v1_during_migration(tmp_path: Path) -> None:
    artifact = _artifact()
    legacy_positions = [
        {
            "symbol": f"{index:06d}.SZ",
            "name": f"股票{index}",
            "model_rank": index,
            "aggregate_target_weight": 0.01,
            "is_new": False,
        }
        for index in range(1, 21)
    ]
    artifact["schema_version"] = delivery.LEGACY_SELECTION_SCHEMA
    artifact["product_id"] = delivery.LEGACY_PRODUCT_ID
    artifact["signal"] = {
        "cohort_number": 5,
        "selected_count": 20,
        "retained_count": 20,
        "new_position_count": 0,
        "exited_count": 0,
        "positions": legacy_positions,
        "added": [],
        "removed": [],
    }
    selection_path = tmp_path / "legacy-selection.json"
    selection_path.write_text(json.dumps(artifact), encoding="utf-8")

    loaded = delivery.load_selection(
        selection_path,
        expected_source_date="20260731",
        expected_signal_date="20260803",
    )

    assert loaded["schema_version"] == delivery.LEGACY_SELECTION_SCHEMA


def test_v2_rejects_duplicate_aggregate_holdings(tmp_path: Path) -> None:
    artifact = _artifact()
    aggregate = artifact["aggregate_target"]
    assert isinstance(aggregate, dict)
    positions = aggregate["positions"]
    assert isinstance(positions, list)
    positions[1] = dict(positions[0])
    selection_path = tmp_path / "duplicate-selection.json"
    selection_path.write_text(json.dumps(artifact), encoding="utf-8")

    with pytest.raises(delivery.D11H5DeliveryError, match="20 distinct positions"):
        delivery.load_selection(
            selection_path,
            expected_source_date="20260731",
            expected_signal_date="20260803",
        )


def test_render_png_writes_mobile_card(tmp_path: Path) -> None:
    output = delivery.render_png(_artifact(), tmp_path / "card.png")

    assert output.is_file()
    assert output.stat().st_size > 10_000
    image = mpimg.imread(output)
    assert image.shape[:2] == (1620, 1620)
    assert float(image[..., :3].mean()) > 0.65


def test_position_row_copy_uses_one_status_vocabulary() -> None:
    assert _position_row_copy({"is_new": True, "model_rank": 8}) == ("新增", " · #8")
    assert _position_row_copy({"is_new": False, "model_rank": 12}) == ("保留", " · #12")
    assert _position_row_copy({"is_new": False, "is_refreshed": False}) == ("保留", "")


def test_render_markdown_accepts_strategy_doc_override() -> None:
    markdown = delivery.render_markdown(
        _artifact(), strategy_doc_url="https://example.feishu.cn/docx/d11"
    )

    assert "https://example.feishu.cn/docx/d11" in markdown
    assert delivery.DEFAULT_STRATEGY_DOC_URL not in markdown


def test_delivery_receipt_requires_both_media_and_audience(tmp_path: Path) -> None:
    markdown_hash = hashlib.sha256(b"markdown").hexdigest()
    image_hash = hashlib.sha256(b"image").hexdigest()
    receipt = {
        "schema_version": delivery.DELIVERY_SCHEMA,
        "product_id": delivery.PRODUCT_ID,
        "source_date": "20260731",
        "signal_date": "20260803",
        "success": True,
        "markdown_sha256": markdown_hash,
        "image_sha256": image_hash,
        "targets": [
            {
                "audience": "personal",
                "messages": {
                    "markdown": {
                        "status": "sent",
                        "content_sha256": markdown_hash,
                        "message_id": "om_text",
                    },
                    "image": {
                        "status": "sent",
                        "content_sha256": image_hash,
                        "message_id": "om_image",
                    },
                },
            }
        ],
    }
    path = tmp_path / "receipt.json"
    path.write_text(json.dumps(receipt), encoding="utf-8")

    delivery.validate_delivery_receipt(
        path,
        expected_source_date="20260731",
        expected_signal_date="20260803",
        required_audiences=("personal",),
    )

    receipt["product_id"] = delivery.LEGACY_PRODUCT_ID
    path.write_text(json.dumps(receipt), encoding="utf-8")
    delivery.validate_delivery_receipt(
        path,
        expected_source_date="20260731",
        expected_signal_date="20260803",
        required_audiences=("personal",),
    )


def test_explicit_personal_target_does_not_expand_to_groups() -> None:
    targets = delivery._filtered_targets(
        explicit_chat_ids=("oc_personal", "oc_personal"),
        explicit_audience="personal",
        delivery_audience="all",
    )

    assert targets == {"personal": ("oc_personal",)}


def test_extract_json_accepts_pretty_multiline_cli_output() -> None:
    payload = delivery._extract_json(
        """
        {
          "ok": true,
          "data": {
            "message_id": "om_pretty"
          }
        }
        """
    )

    assert delivery._message_id(payload) == "om_pretty"


def test_repeated_delivery_reuses_successful_messages(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    selection_path = tmp_path / "selection.json"
    markdown_path = tmp_path / "selection.md"
    image_path = tmp_path / "selection.png"
    receipt_path = tmp_path / "receipt.json"
    selection_path.write_text(json.dumps(_artifact()), encoding="utf-8")
    markdown_path.write_text("same markdown", encoding="utf-8")
    image_path.write_bytes(b"same image")
    calls: list[str] = []

    monkeypatch.setattr(delivery, "_lark_cli", lambda _explicit: "/bin/lark-cli")

    def fake_send(**kwargs: object) -> dict[str, object]:
        medium = str(kwargs["medium"])
        calls.append(medium)
        return {
            "status": "sent",
            "content_sha256": kwargs["content_sha256"],
            "message_id": f"om_{medium}",
        }

    monkeypatch.setattr(delivery, "_send_lark", fake_send)
    call_args = {
        "artifact": _artifact(),
        "selection_path": selection_path,
        "markdown_path": markdown_path,
        "image_path": image_path,
        "receipt_path": receipt_path,
        "targets": {"personal": ("oc_personal",)},
        "lark_cli": None,
        "no_send": False,
    }

    delivery.deliver(**call_args)
    delivery.deliver(**call_args)

    assert calls == ["markdown", "image"]
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert receipt["success"] is True
    assert receipt["targets"][0]["messages"]["markdown"]["status"] == "already_sent"
    assert receipt["targets"][0]["messages"]["image"]["status"] == "already_sent"


def test_targeted_retries_preserve_receipt_rows_for_other_audiences(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    selection_path = tmp_path / "selection.json"
    markdown_path = tmp_path / "selection.md"
    image_path = tmp_path / "selection.png"
    receipt_path = tmp_path / "receipt.json"
    selection_path.write_text(json.dumps(_artifact()), encoding="utf-8")
    markdown_path.write_text("same markdown", encoding="utf-8")
    image_path.write_bytes(b"same image")

    monkeypatch.setattr(delivery, "_lark_cli", lambda _explicit: "/bin/lark-cli")

    def fake_send(**kwargs: object) -> dict[str, object]:
        medium = str(kwargs["medium"])
        chat_id = str(kwargs["chat_id"])
        return {
            "status": "sent",
            "content_sha256": kwargs["content_sha256"],
            "message_id": f"om_{chat_id}_{medium}",
        }

    monkeypatch.setattr(delivery, "_send_lark", fake_send)
    call_args = {
        "artifact": _artifact(),
        "selection_path": selection_path,
        "markdown_path": markdown_path,
        "image_path": image_path,
        "receipt_path": receipt_path,
        "lark_cli": None,
        "no_send": False,
    }

    delivery.deliver(**call_args, targets={"internal": ("oc_internal",)})
    delivery.deliver(**call_args, targets={"client": ("oc_client",)})

    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert receipt["success"] is True
    assert {
        (row["audience"], row["messages"]["markdown"]["status"]) for row in receipt["targets"]
    } == {
        ("internal", "sent"),
        ("client", "sent"),
    }


def test_no_send_preserves_successful_legacy_receipt_for_same_dates(tmp_path: Path) -> None:
    selection_path = tmp_path / "selection.json"
    markdown_path = tmp_path / "selection.md"
    image_path = tmp_path / "selection.png"
    receipt_path = tmp_path / "receipt.json"
    selection_path.write_text(json.dumps(_artifact()), encoding="utf-8")
    markdown_path.write_text("new markdown", encoding="utf-8")
    image_path.write_bytes(b"new image")
    markdown_hash = hashlib.sha256(b"old markdown").hexdigest()
    image_hash = hashlib.sha256(b"old image").hexdigest()
    previous = {
        "schema_version": delivery.DELIVERY_SCHEMA,
        "product_id": delivery.LEGACY_PRODUCT_ID,
        "source_date": "20260731",
        "signal_date": "20260803",
        "success": True,
        "markdown_sha256": markdown_hash,
        "image_sha256": image_hash,
        "targets": [
            {
                "audience": "client",
                "messages": {
                    "markdown": {
                        "status": "sent",
                        "content_sha256": markdown_hash,
                        "message_id": "om_old_markdown",
                    },
                    "image": {
                        "status": "sent",
                        "content_sha256": image_hash,
                        "message_id": "om_old_image",
                    },
                },
            }
        ],
    }
    receipt_path.write_text(json.dumps(previous, sort_keys=True), encoding="utf-8")
    before = receipt_path.read_bytes()

    receipt = delivery.deliver(
        artifact=_artifact(),
        selection_path=selection_path,
        markdown_path=markdown_path,
        image_path=image_path,
        receipt_path=receipt_path,
        targets={},
        lark_cli=None,
        no_send=True,
    )

    assert receipt == previous
    assert receipt_path.read_bytes() == before
