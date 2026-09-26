"""
test_ast_parser.py – Standalone verification script for ast_parser.

Run from the project root:
    python backend/test_ast_parser.py

Or from inside backend/:
    python test_ast_parser.py
"""

from __future__ import annotations

import os
import sys

# Ensure the package is importable regardless of where the script is run from.
_HERE = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, _HERE)       # backend/  → allows `from app.ast_parser import …`
sys.path.insert(0, _PROJECT_ROOT)  # project root

from app.ast_parser import generate_mermaid_graph, parse_repo  # noqa: E402

SAMPLE_REPO = os.path.join(_PROJECT_ROOT, "workspace", "sample_repo")


def main() -> None:
    print("=" * 60)
    print(f"Scanning: {SAMPLE_REPO}")
    print("=" * 60)

    # ------------------------------------------------------------------
    # 1. Parse the sample repo
    # ------------------------------------------------------------------
    kg = parse_repo(SAMPLE_REPO)

    endpoints = kg["endpoints"]
    models    = kg["pydantic_models"]
    functions = kg["functions"]
    classes   = kg["classes"]
    imports   = kg["imports"]

    print(f"\nEndpoints  : {len(endpoints)}")
    for ep in endpoints:
        print(f"  [{ep['method']:6s}] {ep['path']:<25}  → {ep['function']}()  ({ep['file']}:{ep['line']})")

    print(f"\nPydantic models : {len(models)}")
    for m in models:
        bases = ", ".join(m["bases"]) or "—"
        fields = ", ".join(f["name"] for f in m["fields"])
        print(f"  {m['name']}  (bases: {bases})  fields: [{fields}]")

    print(f"\nFunctions  : {len(functions)}")
    for fn in functions:
        params = ", ".join(p["name"] for p in fn["params"])
        ret = fn["return_type"] or "?"
        print(f"  {'async ' if fn['is_async'] else ''}def {fn['name']}({params}) -> {ret}")

    print(f"\nClasses    : {len(classes)}")
    for cls in classes:
        bases = ", ".join(cls["bases"]) or "—"
        print(f"  {cls['name']}  (bases: {bases})")

    print(f"\nImports    : {len(imports)}")

    # ------------------------------------------------------------------
    # 2. Generate Mermaid graph
    # ------------------------------------------------------------------
    mermaid = generate_mermaid_graph(kg)

    print("\n" + "=" * 60)
    print("Mermaid graph:")
    print("=" * 60)
    print(mermaid)

    # ------------------------------------------------------------------
    # 3. Assertions
    # ------------------------------------------------------------------
    assert mermaid.startswith("graph TD"), "Mermaid output must start with 'graph TD'"
    assert len(endpoints) > 0, "Expected at least one endpoint"
    assert len(models) > 0, "Expected at least one Pydantic model"
    assert len(functions) > 0, "Expected at least one function"

    # Verify all expected HTTP methods appear
    methods_found = {ep["method"] for ep in endpoints}
    assert "GET" in methods_found, "Expected a GET endpoint"
    assert "POST" in methods_found, "Expected a POST endpoint"
    assert "DELETE" in methods_found, "Expected a DELETE endpoint"

    print("=" * 60)
    print("All assertions passed ✓")
    print("=" * 60)


if __name__ == "__main__":
    main()
