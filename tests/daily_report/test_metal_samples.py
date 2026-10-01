import json
from datetime import UTC, datetime

import pytest
import requests

from daily_messenger import cli
from daily_messenger.daily_report import gold_reference, metal_samples


def test_timestamped_reference_is_not_an_exchange_close(monkeypatch):
    class Response:
        status_code = 200

        def json(self):
            return {
                "symbol": "XAU",
                "currency": "USD",
                "price": 2000,
                "updatedAt": "2026-01-01T00:00:00Z",
            }

    monkeypatch.setattr(gold_reference.requests, "get", lambda *args, **kwargs: Response())
    quote = gold_reference.fetch_reference_quote("XAU")
    assert quote.price == 2000
    assert quote.actual_quote_time == datetime(2026, 1, 1, tzinfo=UTC)
    assert quote.retrieved_at >= quote.actual_quote_time


@pytest.mark.parametrize(
    "field,value",
    [
        ("symbol", "XAG"),
        ("currency", "EUR"),
        ("price", True),
        ("price", 0),
        ("price", -1),
        ("price", float("nan")),
        ("price", float("inf")),
        ("price", "2000"),
        ("price", None),
        ("updatedAt", "2099-01-01T00:00:00Z"),
        ("updatedAt", "2026-01-01T00:00:00"),
    ],
)
def test_reference_quote_rejects_invalid_metadata(monkeypatch, field, value):
    class Response:
        status_code = 200

        def json(self):
            return {
                "symbol": "XAU",
                "currency": "USD",
                "price": 2000,
                "updatedAt": "2026-01-01T00:00:00Z",
                field: value,
            }

    monkeypatch.setattr(gold_reference.requests, "get", lambda *args, **kwargs: Response())
    with pytest.raises(RuntimeError, match="Gold API"):
        gold_reference.fetch_reference_quote("XAU")


def test_samples_are_private_immutable_pairs(monkeypatch, tmp_path):
    now = datetime.now(UTC)
    monkeypatch.setattr(
        metal_samples,
        "fetch_reference_quote",
        lambda symbol: gold_reference.MetalReferenceQuote(symbol, 2000, now, now),
    )
    first = metal_samples.sample_metals(tmp_path)
    original = first.read_bytes()
    second = metal_samples.sample_metals(tmp_path)
    assert second != first
    assert first.read_bytes() == original
    assert first.stat().st_mode & 0o777 == 0o600
    result = json.loads(original)
    assert result["publication"] == "private"
    assert result["instrument"] == result["quotation_unit"] == "unverified"
    assert [row["symbol"] for row in result["quotes"]] == ["XAU", "XAG"]


def test_repository_output_is_rejected_before_network(monkeypatch):
    def unexpected(symbol):
        pytest.fail("network must not run")

    monkeypatch.setattr(metal_samples, "fetch_reference_quote", unexpected)
    with pytest.raises(ValueError, match="outside"):
        metal_samples.sample_metals(metal_samples.PROJECT_ROOT / "samples")


def test_partial_pair_is_not_saved(monkeypatch, tmp_path):
    def fetch(symbol):
        if symbol == "XAG":
            raise RuntimeError("Gold API request failed")
        now = datetime.now(UTC)
        return gold_reference.MetalReferenceQuote(symbol, 2000, now, now)

    monkeypatch.setattr(metal_samples, "fetch_reference_quote", fetch)
    with pytest.raises(RuntimeError):
        metal_samples.sample_metals(tmp_path)
    assert not list(tmp_path.iterdir())


def test_reference_network_error_is_safe(monkeypatch):
    def fail(*args, **kwargs):
        raise requests.RequestException("secret-token-provider-body")

    monkeypatch.setattr(gold_reference.requests, "get", fail)
    with pytest.raises(RuntimeError, match="^Gold API request failed$"):
        gold_reference.fetch_reference_quote("XAU")


def test_sample_cli_never_logs_provider_errors(monkeypatch, tmp_path, capsys):
    def fail(output):
        raise RuntimeError("secret-token-provider-body")

    monkeypatch.setattr(metal_samples, "sample_metals", fail)
    assert cli.main(["metal-sample", "--out", str(tmp_path)]) == 2
    captured = capsys.readouterr()
    assert "secret-token-provider-body" not in captured.out + captured.err


def test_shared_writable_output_is_rejected(monkeypatch, tmp_path):
    tmp_path.chmod(0o777)
    monkeypatch.setattr(
        metal_samples, "fetch_reference_quote", lambda symbol: pytest.fail("network must not run")
    )
    with pytest.raises(ValueError, match="private"):
        metal_samples.sample_metals(tmp_path)


def test_other_checkout_is_rejected(monkeypatch, tmp_path):
    (tmp_path / ".git").touch()
    monkeypatch.setattr(
        metal_samples, "fetch_reference_quote", lambda symbol: pytest.fail("network must not run")
    )
    with pytest.raises(ValueError, match="outside"):
        metal_samples.sample_metals(tmp_path / "generated")


def test_forced_name_collision_preserves_previous_sample(monkeypatch, tmp_path):
    now = datetime.now(UTC)
    monkeypatch.setattr(
        metal_samples,
        "fetch_reference_quote",
        lambda symbol: gold_reference.MetalReferenceQuote(symbol, 2000, now, now),
    )
    monkeypatch.setattr(metal_samples, "uuid4", lambda: type("Id", (), {"hex": "fixed"})())
    first = metal_samples.sample_metals(tmp_path)
    original = first.read_bytes()
    with pytest.raises(FileExistsError):
        metal_samples.sample_metals(tmp_path)
    assert first.read_bytes() == original
    assert not list(tmp_path.glob("*.tmp"))


def test_temporary_collision_preserves_unowned_file(monkeypatch, tmp_path):
    now = datetime.now(UTC)
    monkeypatch.setattr(
        metal_samples,
        "fetch_reference_quote",
        lambda symbol: gold_reference.MetalReferenceQuote(symbol, 2000, now, now),
    )
    monkeypatch.setattr(metal_samples, "uuid4", lambda: type("Id", (), {"hex": "fixed"})())
    existing = tmp_path / ".metal-reference-fixed.json.tmp"
    existing.write_text("another invocation")
    with pytest.raises(FileExistsError):
        metal_samples.sample_metals(tmp_path)
    assert existing.read_text() == "another invocation"
