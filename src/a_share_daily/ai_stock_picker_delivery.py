"""Retired legacy AI stock-picker delivery entrypoint.

The scheduled product was retired on 2026-08-03. Strategy experiments and model
selection now belong to research-workspace (strategy-app / strategy-pipeline).
This module remains only so stale deployment configuration fails explicitly
instead of resurrecting an abandoned cross-repository product by accident.
"""

from __future__ import annotations

import sys

RETIRED_EXIT = 20


def main(argv: list[str] | None = None) -> int:
    del argv
    print(
        "AI精选（旧）已于 2026-08-03 退休；market-intel 不再生产或投递该产品。"
        "研究与实验入口归 research-workspace。",
        file=sys.stderr,
    )
    return RETIRED_EXIT


if __name__ == "__main__":
    raise SystemExit(main())
