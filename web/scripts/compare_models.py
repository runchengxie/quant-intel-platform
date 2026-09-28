"""Produce comparable model samples from the same cutoff; no automatic quality score."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

try:
    from .generate_insights import DEFAULT_MODELS, run, write_json
except ImportError:
    from generate_insights import DEFAULT_MODELS, run, write_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reports", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parent.parent
    if args.output_dir.resolve().is_relative_to(root):
        raise ValueError("comparison outputs must remain outside the public repository")
    results = []
    for provider in (name for name in DEFAULT_MODELS if name != "codex"):
        prefix = provider.upper()
        output = run(
            args.reports,
            args.output_dir / f"{provider}.json",
            provider=provider,
            api_key=os.environ.get(f"{prefix}_API_KEY"),
            model=os.environ.get(f"{prefix}_MODEL"),
            archive_dir=args.output_dir / "revisions",
        )
        results.append(output["generation"])
    write_json(
        args.output_dir / "comparison.json",
        {
            "runs": results,
            "review_questions": [
                "每条判断的证据是否支持其含义？",
                "是否区分变化与因果？",
                "是否保留缺项和反例？",
                "观察条件是否有用、可核对？",
                "中文是否自然、简洁且没有夸大？",
            ],
            "note": "格式校验通过不代表事实含义正确；没有真实模型输出时不能判定模型优劣。",
        },
    )
    print(json.dumps(results, ensure_ascii=False))


if __name__ == "__main__":
    main()
