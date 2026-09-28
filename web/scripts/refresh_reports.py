"""Stage public Markdown through the installed owner CLI; never send messages."""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import subprocess
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

CHINA_TZ = timezone(timedelta(hours=8))
PRIVATE_TEXT = re.compile(
    r"/home/|/Users/|[A-Za-z]:[\\/]Users[\\/]"
    r"|\b(?:oc|ou|on)_[A-Za-z0-9_-]{8,}"
    r"|\b(?:sk-|ghp_|github_pat_|AKIA)[A-Za-z0-9_-]{8,}"
    r"|\bBearer\s+\S+"
    r"|\b(?:chat[_ -]?id|api[_ -]?key|secret|password|access[_ -]?token|credential|authorization)"
    r"\s*[:=]\s*\S+",
    re.IGNORECASE,
)
STRAY_DATASETS = ("ths_hot", "dc_concept", "dc_concept_cons", "kpl_concept_cons")


@dataclass(frozen=True)
class OwnerRun:
    cli: Path
    stage: Path
    env: dict[str, str]
    date: str
    deadline: float

    def call(self, name: str, arguments: list[str], filename: str) -> Path:
        """Keep raw owner output private, including diagnostics from unsuccessful commands."""
        output = self.stage / filename
        with output.open("wb") as stdout, (self.stage / f"{filename}.stderr.log").open("wb") as stderr:
            try:
                result = subprocess.run(
                    [str(self.cli), name, *arguments],
                    cwd=self.stage,
                    env=self.env,
                    stdout=stdout,
                    stderr=stderr,
                    check=False,
                    timeout=max(0.001, self.deadline - time.monotonic()),
                )
            except subprocess.TimeoutExpired as exc:
                raise ValueError("owner CLI batch timeout; inspect the private batch diagnostics") from exc
        if result.returncode:
            raise ValueError(f"owner CLI {name} failed; inspect the private batch diagnostics")
        return output


def read_object(path: Path, label: str) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError(f"invalid or missing {label}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object")
    return value


def validate_output_subdirectories(output_dir: Path) -> None:
    for name in (".private-batches", "public"):
        child = output_dir / name
        if child.is_symlink() or child.resolve().parent != output_dir:
            raise ValueError("output child directories must stay inside output and cannot be symlinks")


def validate_paths(owner_cli: Path, data_root: Path, snapshot_root: Path, output_dir: Path) -> None:
    if not owner_cli.is_absolute() or not owner_cli.is_file() or not os.access(owner_cli, os.X_OK):
        raise ValueError("owner CLI must be an absolute executable path")
    if not data_root.is_dir() or not snapshot_root.is_dir():
        raise ValueError("data and snapshot roots must be existing directories")
    repo = Path(__file__).resolve().parents[1]
    output = output_dir.resolve()
    # A workspace may itself be a Git repository containing both the project and its external data roots.
    foreign_checkout = any(
        (parent / ".git").exists() and not repo.is_relative_to(parent) for parent in (output, *output.parents)
    )
    if output.is_relative_to(repo) or repo.is_relative_to(output) or foreign_checkout:
        raise ValueError("output directory must be outside Git repositories")
    validate_output_subdirectories(output)


def validate_morning_inputs(data_root: Path, snapshot_root: Path, date: str) -> None:
    for dataset in STRAY_DATASETS:
        path = data_root / "assets/tushare/a_share" / dataset / "data"
        if path.exists() or path.is_symlink():
            raise ValueError("owner must resolve stray dataset directories before morning generation")
    snapshot = read_object(snapshot_root / "cross-market" / f"{date}.json", "dated cross-market snapshot")
    if snapshot.get("date") != date.replace("-", ""):
        raise ValueError("cross-market snapshot date does not match the requested date")


def positive_number(value: object) -> bool:
    return (
        isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value > 0
    )


def validate_evening(payload: dict, date: str) -> None:
    if payload.get("trade_date") != date:
        raise ValueError("evening trade date does not match the requested date")
    try:
        generated = datetime.fromisoformat(payload.get("generated_at", ""))
    except (TypeError, ValueError) as exc:
        raise ValueError("evening generated_at is invalid") from exc
    generated = generated.replace(tzinfo=generated.tzinfo or CHINA_TZ)
    if abs((datetime.now(CHINA_TZ) - generated).total_seconds()) > 300:
        raise ValueError("evening generated_at is not from this refresh")
    overview = payload.get("overview")
    if not isinstance(overview, dict) or not isinstance(overview.get("breadth"), dict):
        raise ValueError("evening overview lacks observed market data")
    if not positive_number(overview["breadth"].get("total")) or not positive_number(
        overview.get("turnover_total")
    ):
        raise ValueError("evening overview lacks observed market data")


def evening_markdown(run: OwnerRun) -> str:
    facts = run.call("evening", ["--date", run.date, "--json"], "evening_review.json")
    validate_evening(read_object(facts, "evening JSON"), run.date)
    return run.call("evening", ["--date", run.date], "evening_review.md").read_text(encoding="utf-8")


def validate_morning(payload: dict, date: str) -> None:
    dashed = f"{date[:4]}-{date[4:6]}-{date[6:]}"
    if payload.get("date") != date or payload.get("date_dash", dashed) != dashed:
        raise ValueError("morning date does not match the requested date")
    cross_market = payload.get("cross_market")
    if not isinstance(cross_market, dict):
        raise ValueError("morning lacks the dated cross-market snapshot")
    if cross_market.get("date") != date or cross_market.get("_source") != "data-snapshots":
        raise ValueError("morning must use the matching data-snapshots source; live fallback is refused")


def morning_markdown(run: OwnerRun) -> str:
    manifest = run.call("morning", ["--date", run.date], "morning_manifest.json")
    validate_morning(read_object(manifest, "morning manifest"), run.date)
    news = run.stage / "news.json"
    news.write_text(json.dumps({"markets": {}, "markets_requested": [], "disabled": True}), encoding="utf-8")
    rendered = run.stage / "morning_report.md"
    run.call(
        "morning-report",
        ["--manifest", str(manifest), "--news", str(news), "--out", str(rendered)],
        "morning_report.stdout.md",
    )
    return rendered.read_text(encoding="utf-8")


def public_markdown(text: str, date: str, kind: str, generation_mode: str) -> str:
    if PRIVATE_TEXT.search(text):
        raise ValueError("owner Markdown contains private paths, chat identifiers or credential-like text")
    heading = next((line for line in text.splitlines() if line.startswith("#")), "")
    dates = re.findall(r"\d{4}-\d{2}-\d{2}|\d{8}", heading)
    if not dates or any(value.replace("-", "") != date.replace("-", "") for value in dates):
        raise ValueError("owner Markdown heading date does not match the requested date")
    text = re.sub(r"(?m)^生成时间([:：])", r"原稿生成时间\1", text)
    text = re.sub(r"(?m)^# ", "## ", text)
    title = "收盘复盘" if kind == "evening" else "亚洲市场盘前 / 美股市场盘后"
    timestamp = datetime.now(CHINA_TZ).replace(tzinfo=None).isoformat(sep=" ", timespec="microseconds")
    notice = "本报告按计划生成，生成时间为本次实际运行时间。"
    if generation_mode == "backfill":
        notice = "本报告为历史数据补发，生成时间是本次重建时间，不代表当时已发布。"
    if kind == "morning":
        notice += "新闻输入已禁用，新闻栏目缺项；跨市场事实使用目标日期快照。"
    return (
        f"# {title}（{date}）\n\n生成时间: {timestamp}\n数据日期: {date}\n"
        f"报告生成方式: {generation_mode}\n\n{notice}\n\n{text.strip()}\n"
    )


def publish_batch(output_dir: Path, stage: Path, texts: dict[str, str], date: str) -> Path:
    validate_output_subdirectories(output_dir)
    public_stage = stage / "public"
    public_stage.mkdir()
    relative = Path("public") / stage.name
    entries = []
    for kind, text in texts.items():
        name = f"{date}-{kind}.md"
        (public_stage / name).write_text(text, encoding="utf-8")
        entries.append({"path": (relative / name).as_posix(), "date": date, "kind": kind})
    manifest = {"schema_version": "market_intel_pages.import.v1", "publication": "public", "reports": entries}
    staged_manifest = stage / "public_manifest.json"
    staged_manifest.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    destination = output_dir / relative
    destination.parent.mkdir(exist_ok=True)
    public_stage.rename(destination)
    # Each batch has distinct Markdown paths. A failed replace leaves the previous manifest and files intact.
    manifest_path = output_dir / "manifest.json"
    staged_manifest.replace(manifest_path)
    return manifest_path


def refresh_reports(
    owner_cli: Path,
    data_root: Path,
    snapshot_root: Path,
    output_dir: Path,
    date: str,
    kind: str = "evening",
    *,
    generation_mode: str = "backfill",
    timeout_seconds: float = 180,
) -> Path:
    """Generate a complete private batch, then publish an explicitly public import manifest."""
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date):
        raise ValueError("date must be YYYY-MM-DD")
    datetime.strptime(date, "%Y-%m-%d")
    if kind not in ("evening", "morning", "both"):
        raise ValueError("kind must be evening, morning or both")
    if generation_mode not in ("backfill", "scheduled") or not positive_number(timeout_seconds):
        raise ValueError("generation mode must be backfill or scheduled and timeout must be positive")
    validate_paths(owner_cli, data_root, snapshot_root, output_dir)
    data_root, snapshot_root, output_dir = data_root.resolve(), snapshot_root.resolve(), output_dir.resolve()
    kinds = ("evening", "morning") if kind == "both" else (kind,)
    if "morning" in kinds:
        validate_morning_inputs(data_root, snapshot_root, date)
    private_root = output_dir / ".private-batches"
    private_root.mkdir(parents=True, exist_ok=True, mode=0o700)
    stage = Path(tempfile.mkdtemp(prefix=f"{date}-", dir=private_root))
    env = {
        **os.environ,
        "DATA_PLATFORM_ROOT": str(data_root),
        "A_SHARE_OUTPUT_DIR": str(stage),
        "CROSS_MARKET_SNAPSHOT_ROOT": str(snapshot_root),
        "MARKET_INTEL_REPORT_AUDIT_ONLY": "1",
    }
    run = OwnerRun(owner_cli.resolve(), stage, env, date.replace("-", ""), time.monotonic() + timeout_seconds)
    renderers = {"evening": evening_markdown, "morning": morning_markdown}
    texts = {name: public_markdown(renderers[name](run), date, name, generation_mode) for name in kinds}
    return publish_batch(output_dir, stage, texts, date)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--owner-cli", type=Path, required=True)
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--snapshot-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--date", required=True, help="Explicit target data date YYYY-MM-DD")
    parser.add_argument("--kind", choices=("evening", "morning", "both"), default="evening")
    parser.add_argument("--generation-mode", choices=("scheduled", "backfill"), default="backfill")
    parser.add_argument("--timeout-seconds", type=float, default=180, help="Total owner CLI batch budget")
    args = parser.parse_args()
    try:
        manifest = refresh_reports(
            args.owner_cli,
            args.data_root,
            args.snapshot_root,
            args.output_dir,
            args.date,
            args.kind,
            generation_mode=args.generation_mode,
            timeout_seconds=args.timeout_seconds,
        )
    except (OSError, ValueError) as exc:
        print(json.dumps({"manifest": None, "errors": [str(exc)]}, ensure_ascii=False))
        raise SystemExit(1) from exc
    print(json.dumps({"manifest": str(manifest), "errors": []}, ensure_ascii=False))


if __name__ == "__main__":
    main()
