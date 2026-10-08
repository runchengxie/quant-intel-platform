from datetime import UTC, date, datetime

import pytest

from daily_messenger.daily_report.news_snapshot import CaptureOptions, capture, main
from daily_messenger.daily_report.news_snapshot_preview import render_preview


def rss(*, build="Wed, 07 Oct 2026 21:00:08 GMT", market="Wednesday", extra=""):
    return f"""<?xml version="1.0" encoding="utf-8"?>
    <rss xmlns:a="http://www.w3.org/2005/Atom"><channel><lastBuildDate>{build}</lastBuildDate>
    <item><title>US equities finish lower</title><a:updated>2026-10-07T09:00:00-04:00</a:updated>
    <description><![CDATA[<ul><li>US equities lower in {market} trading; yields down 1-3 bp.</li>
    <li>Session found late support as rate backdrop stabilized.</li>
    <li>XYZ reportedly plans $40B financing.</li>
    <li>FOMC minutes released today.</li>{extra}</ul>]]></description></item>
    <item><title>Notable Gainers:</title><description><![CDATA[
    <ul><li>+3.2% XYZ: results beat.</li></ul>]]></description></item>
    <item><title>Notable Decliners:</title><description><![CDATA[
    <ul><li>-4.8% ABC: rating cut.</li></ul>]]></description></item>
    </channel></rss>""".encode()


CAPTURED = datetime(2026, 10, 8, 3, tzinfo=UTC)


def test_capture_preserves_original_and_six_sections(tmp_path):
    raw = b"\xef\xbb\xbf" + rss()
    result = capture(
        raw,
        expected_date=date(2026, 10, 7),
        captured_at=CAPTURED,
        output_dir=tmp_path / "capture",
    )
    assert (tmp_path / "capture" / "source.xml").read_bytes() == raw
    assert result["status"] == "needs_review"
    assert len(result["sections"]) == 6
    assert result["sections"][0]["blocks"][0]["published_at"] is None
    assert "1-3 bp" in (tmp_path / "capture" / "preview.md").read_text(encoding="utf-8")
    assert "NOT FOR PUBLICATION" in (tmp_path / "capture" / "preview.md").read_text(
        encoding="utf-8"
    )


@pytest.mark.parametrize(
    "change,reason",
    [
        ({"market": "Tuesday"}, "weekday_mismatch"),
        ({"build": "Tue, 06 Oct 2026 21:00:08 GMT"}, "session_mismatch"),
        ({"build": "Wed, 07 Oct 2026 15:00:00 GMT"}, "preclose_build"),
        ({"build": "Fri, 09 Oct 2026 21:00:08 GMT"}, "build_after_capture"),
        ({"extra": "<li>Unexpected extra summary</li>"}, "layout_changed"),
    ],
)
def test_ambiguous_inputs_are_archived_but_quarantined(tmp_path, change, reason):
    result = capture(
        rss(**change),
        expected_date=date(2026, 10, 7),
        captured_at=CAPTURED,
        output_dir=tmp_path / "capture",
    )
    assert result["status"] == "quarantined"
    assert reason in result["issues"]
    assert result["sections"] == []
    assert (tmp_path / "capture" / "source.xml").exists()


@pytest.mark.parametrize(
    "raw",
    [b"not xml", b"<!DOCTYPE x><rss/>", b"x" * 1_048_577],
    ids=["invalid", "doctype", "oversized"],
)
def test_reject_invalid_or_oversized_xml(tmp_path, raw):
    with pytest.raises(ValueError):
        capture(
            raw,
            expected_date=date(2026, 10, 7),
            captured_at=CAPTURED,
            output_dir=tmp_path / "capture",
        )


def test_no_overwrite(tmp_path):
    destination = tmp_path / "existing"
    destination.mkdir()
    with pytest.raises(FileExistsError):
        capture(
            rss(),
            expected_date=date(2026, 10, 7),
            captured_at=CAPTURED,
            output_dir=destination,
        )


def test_empty_git_directory_is_not_a_source_repository(tmp_path):
    (tmp_path / ".git").mkdir()
    result = capture(
        rss(),
        expected_date=date(2026, 10, 7),
        captured_at=CAPTURED,
        output_dir=tmp_path / "capture",
    )
    assert result["status"] == "needs_review"


def test_reject_output_inside_git_repository(tmp_path):
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
    with pytest.raises(ValueError, match="outside"):
        capture(
            rss(),
            expected_date=date(2026, 10, 7),
            captured_at=CAPTURED,
            output_dir=tmp_path / "capture",
        )


def test_replay_cli_requires_capture_timestamp(tmp_path):
    source = tmp_path / "sample.xml"
    source.write_bytes(rss())
    with pytest.raises(SystemExit):
        main(
            [
                "--date",
                "2026-10-07",
                "--input-rss",
                str(source),
                "--output-dir",
                str(tmp_path / "capture"),
            ]
        )


def test_editorial_is_bound_to_source_and_section_references(tmp_path):
    snapshot = capture(
        rss(),
        expected_date=date(2026, 10, 7),
        captured_at=CAPTURED,
        output_dir=tmp_path / "capture",
    )
    editorial = {
        "source_sha256": snapshot["source_sha256"],
        "sections": [
            {
                "key": section["key"],
                "block_ids": [section["blocks"][0]["id"]],
                "text": section["blocks"][0]["text"],
            }
            for section in snapshot["sections"]
        ],
    }
    assert "一、市场表现" in render_preview(snapshot, locale="zh-CN", editorial=editorial)
    editorial["sections"][0]["text"] = "短端收益率下降13个基点"
    with pytest.raises(ValueError, match="numeric"):
        render_preview(snapshot, editorial=editorial)
    editorial["sections"][0]["block_ids"] = ["gainers-1"]
    with pytest.raises(ValueError, match="foreign"):
        render_preview(snapshot, editorial=editorial)
    editorial["source_sha256"] = "incorrect"
    with pytest.raises(ValueError, match="hash"):
        render_preview(snapshot, editorial=editorial)


def test_market_headline_is_preserved_with_its_own_locator(tmp_path):
    raw = rss().replace(
        b"US equities finish lower</title>", b"US equities finish lower: Dow (0.66%)</title>"
    )
    snapshot = capture(
        raw,
        expected_date=date(2026, 10, 7),
        captured_at=CAPTURED,
        output_dir=tmp_path / "capture",
    )
    assert snapshot["sections"][0]["blocks"][0]["id"] == "market-title"
    assert "0.66%" in snapshot["sections"][0]["blocks"][0]["text"]


@pytest.mark.parametrize("sections", [None, [], [1, 2]])
def test_invalid_editorial_structure(tmp_path, sections):
    snapshot = capture(
        rss(),
        expected_date=date(2026, 10, 7),
        captured_at=CAPTURED,
        output_dir=tmp_path / "capture",
    )
    with pytest.raises(ValueError, match="six"):
        render_preview(
            snapshot, editorial={"source_sha256": snapshot["source_sha256"], "sections": sections}
        )


def test_markdown_in_source_is_escaped(tmp_path):
    raw = rss().replace(b"results beat.", b"[click](https://untrusted.example) &lt;iframe&gt;")
    capture(
        raw,
        expected_date=date(2026, 10, 7),
        captured_at=CAPTURED,
        output_dir=tmp_path / "capture",
    )
    preview = (tmp_path / "capture" / "preview.md").read_text(encoding="utf-8")
    assert "\\[click\\]" in preview


def test_capture_rejects_naive_timestamp(tmp_path):
    with pytest.raises(ValueError, match="timezone"):
        capture(
            rss(),
            expected_date=date(2026, 10, 7),
            captured_at=CAPTURED.replace(tzinfo=None),
            output_dir=tmp_path / "capture",
        )


def test_malformed_layout_quarantines_instead_of_guessing(tmp_path):
    raw = rss().replace(b"XYZ reportedly", b"Unexpected unrelated summary")
    snapshot = capture(
        raw,
        expected_date=date(2026, 10, 7),
        captured_at=CAPTURED,
        output_dir=tmp_path / "capture",
    )
    assert "layout_changed" in snapshot["issues"]


def test_early_close_uses_xnys_calendar(tmp_path):
    raw = rss(build="Fri, 27 Nov 2026 19:00:00 GMT", market="Friday")
    snapshot = capture(
        raw,
        expected_date=date(2026, 11, 27),
        captured_at=datetime(2026, 11, 28, 3, tzinfo=UTC),
        output_dir=tmp_path / "capture",
    )
    assert snapshot["issues"] == []


def test_holiday_is_quarantined(tmp_path):
    snapshot = capture(
        rss(build="Fri, 25 Dec 2026 22:00:00 GMT", market="Friday"),
        expected_date=date(2026, 12, 25),
        captured_at=datetime(2026, 12, 26, 3, tzinfo=UTC),
        output_dir=tmp_path / "capture",
    )
    assert "non_trading_day" in snapshot["issues"]


def test_editorial_cannot_hide_changed_amount_in_currency_letters(tmp_path):
    snapshot = capture(
        rss(),
        expected_date=date(2026, 10, 7),
        captured_at=CAPTURED,
        output_dir=tmp_path / "capture",
    )
    editorial = {
        "source_sha256": snapshot["source_sha256"],
        "sections": [
            {"key": s["key"], "block_ids": [s["blocks"][0]["id"]], "text": s["blocks"][0]["text"]}
            for s in snapshot["sections"]
        ],
    }
    editorial["sections"][2]["text"] = "Company to raise USD140B"
    with pytest.raises(ValueError, match="numeric"):
        render_preview(snapshot, editorial=editorial)


def test_quarantine_cannot_accept_unchecked_editorial(tmp_path):
    with pytest.raises(ValueError, match="quarantined"):
        capture(
            rss(market="Tuesday"),
            expected_date=date(2026, 10, 7),
            captured_at=CAPTURED,
            output_dir=tmp_path / "capture",
            options=CaptureOptions(editorial={"source_sha256": "wrong", "sections": []}),
        )
