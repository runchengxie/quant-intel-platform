import json
from pathlib import Path

from parity.compare import compare_artifacts
from parity.schema import ParityArtifact


def _write(path: Path, payload: object) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_compare_ignores_generated_at_and_message_id(tmp_path):
    expected = _write(
        tmp_path / "expected.json",
        {"trade_date": "20260908", "generated_at": "a", "message_id": "x"},
    )
    actual = _write(
        tmp_path / "actual.json",
        {"trade_date": "20260908", "generated_at": "b", "message_id": "y"},
    )

    assert compare_artifacts(expected, actual, ignored_fields={"generated_at", "message_id"}) == []


def test_compare_reports_trade_date_difference(tmp_path):
    expected = _write(tmp_path / "expected.json", {"trade_date": "20260908"})
    actual = _write(tmp_path / "actual.json", {"trade_date": "20260909"})

    differences = compare_artifacts(expected, actual, ignored_fields=set())

    assert differences
    assert "trade_date" in differences[0]


def test_compare_reports_nested_missing_and_changed_values(tmp_path):
    expected = _write(
        tmp_path / "expected.json",
        {"receipt": {"status": "published", "rows": 20}},
    )
    actual = _write(
        tmp_path / "actual.json",
        {"receipt": {"status": "failed", "symbols": 19}},
    )

    differences = compare_artifacts(expected, actual, ignored_fields=set())

    assert differences == [
        "receipt.rows: expected 20, actual <missing>",
        "receipt.status: expected 'published', actual 'failed'",
        "receipt.symbols: expected <missing>, actual 19",
    ]


def test_compare_sorts_declared_set_like_lists(tmp_path):
    expected = _write(tmp_path / "expected.json", {"symbols": ["600000", "000001"]})
    actual = _write(tmp_path / "actual.json", {"symbols": ["000001", "600000"]})

    assert (
        compare_artifacts(expected, actual, ignored_fields=set(), set_like_fields={"symbols"}) == []
    )


def test_parity_artifact_loads_json_mapping(tmp_path):
    artifact_path = _write(tmp_path / "artifact.json", {"schema_version": 1, "status": "ok"})

    artifact = ParityArtifact.from_path(artifact_path)

    assert artifact.path == artifact_path
    assert artifact.payload == {"schema_version": 1, "status": "ok"}


def test_parity_artifact_rejects_non_mapping_json(tmp_path):
    artifact_path = _write(tmp_path / "artifact.json", ["not", "an", "artifact"])

    try:
        ParityArtifact.from_path(artifact_path)
    except ValueError as exc:
        assert "JSON object" in str(exc)
    else:
        raise AssertionError("expected a non-mapping artifact to be rejected")
