"""Report Python LOC, AST size, local imports, and statically resolved direct calls.

This is an inventory, not a dynamic call tracer: injected callables, attribute
dispatch, and runtime imports are deliberately not inferred.
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
from pathlib import Path


def _imports(tree: ast.Module, module_names: set[str]) -> tuple[dict[str, str], set[str], set[str]]:
    aliases: dict[str, str] = {}
    local: set[str] = set()
    external: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom):
            continue
        module = (node.module or "").split(".")[-1]
        if module in module_names:
            local.add(module)
            aliases.update({name.asname or name.name: f"{module}.{name.name}" for name in node.names})
        elif node.module:
            external.add(node.module.split(".")[0])
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            external.update(name.name.split(".")[0] for name in node.names)
    return aliases, local, external


def audit(directory: Path) -> dict:
    paths = sorted(directory.glob("*.py"))
    names = {path.stem for path in paths}
    modules = {}
    import_edges: set[tuple[str, str]] = set()
    call_edges: set[tuple[str, str]] = set()
    external_imports: set[str] = set()
    for path in paths:
        text = path.read_text(encoding="utf-8")
        tree = ast.parse(text, filename=str(path))
        aliases, local, external = _imports(tree, names)
        functions = [node for node in tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))]
        aliases.update({node.name: f"{path.stem}.{node.name}" for node in functions})
        import_edges.update((path.stem, target) for target in local)
        external_imports.update(external)
        modules[path.stem] = {
            "loc": len(text.splitlines()),
            "ast_nodes": sum(1 for _ in ast.walk(tree)),
            "top_level_functions": len(functions),
        }
        for function in functions:
            for node in ast.walk(function):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in aliases:
                    call_edges.add((f"{path.stem}.{function.name}", aliases[node.func.id]))
    return {
        "scope": str(directory),
        "call_graph_scope": "direct calls by name; excludes dynamic dispatch and injected generators",
        "modules": modules,
        "totals": {
            key: sum(module[key] for module in modules.values())
            for key in ("loc", "ast_nodes", "top_level_functions")
        },
        "local_import_edges": sorted(import_edges),
        "direct_call_edges": sorted(call_edges),
        "external_imports": sorted(external_imports),
        "non_stdlib_imports": sorted(external_imports - sys.stdlib_module_names),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=Path("scripts"))
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = audit(args.source)
    raw = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(raw, encoding="utf-8")
    print(raw)


if __name__ == "__main__":
    main()
