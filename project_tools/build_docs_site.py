"""Build the Platform documentation and a compatibility redirect to Pages."""

from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAGES_URL = "https://runchengxie.github.io/quant-intel-pages/"


def _redirect_html() -> str:
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Market reports moved</title>
</head>
<body>
  <p>Market reports moved to <a href="{PAGES_URL}">Quant Market Intel Pages</a>.</p>
  <script>
    const destination = new URL("{PAGES_URL}");
    destination.search = window.location.search;
    destination.hash = window.location.hash;
    window.location.replace(destination.href);
  </script>
</body>
</html>
"""


def build_docs_site(output: Path) -> None:
    """Atomically build /docs and the root redirect into output."""
    output = output.expanduser().absolute()
    if output.is_symlink():
        raise ValueError("site output must not be a symlink")
    output = output.resolve()
    if output == ROOT or output.is_relative_to(ROOT) or ROOT.is_relative_to(output):
        raise ValueError("site output must be outside the source repository")
    if output.exists() and not output.is_dir():
        raise ValueError("site output must be a directory")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".platform-docs-", dir=output.parent) as temp:
        stage = Path(temp) / "site"
        docs = stage / "docs"
        subprocess.run(
            [sys.executable, "-m", "mkdocs", "build", "--strict", "--site-dir", str(docs)],
            cwd=ROOT,
            check=True,
        )
        (stage / "index.html").write_text(_redirect_html(), encoding="utf-8")
        backup = Path(temp) / "previous-site"
        if output.exists():
            output.replace(backup)
        try:
            stage.replace(output)
        except Exception:
            if backup.exists() and not output.exists():
                backup.replace(output)
            raise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    build_docs_site(parser.parse_args().output)


if __name__ == "__main__":
    main()
