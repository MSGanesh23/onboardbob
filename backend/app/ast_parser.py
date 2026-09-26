"""
ast_parser.py – Dynamic Python AST extractor.

Walks all .py files under a given repo path and builds a structured
knowledge graph containing:
  - HTTP endpoints (FastAPI / Flask style decorators)
  - Pydantic models / data schemas
  - Function signatures with parameters, return types, and docstrings
  - Class inheritance and import relationships

Public API
----------
parse_repo(repo_path: str) -> dict
    Walk the repo and return a knowledge-graph dict.

generate_mermaid_graph(ast_json: dict) -> str
    Convert a knowledge-graph dict into a Mermaid.js flowchart string.
"""

from __future__ import annotations

import ast
import os
import sys
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_HTTP_METHODS = {"get", "post", "put", "delete", "patch", "options", "head"}


def _safe_id(name: str) -> str:
    """Return a Mermaid-safe node identifier (no spaces, slashes, dots)."""
    return name.replace("/", "_").replace(".", "_").replace(" ", "_").replace("-", "_")


def _annotation_to_str(node: ast.expr | None) -> str | None:
    """Convert an annotation AST node to its source string representation."""
    if node is None:
        return None
    return ast.unparse(node)


def _get_decorator_method(decorator: ast.expr) -> str | None:
    """
    Return the HTTP method name if *decorator* looks like @*.get / @*.post …
    Works for both ``@app.get(…)`` (Call wrapping Attribute) and bare
    ``@router.delete`` (Attribute).
    """
    node = decorator
    if isinstance(node, ast.Call):
        node = node.func
    if isinstance(node, ast.Attribute) and node.attr.lower() in _HTTP_METHODS:
        return node.attr.lower()
    return None


def _get_decorator_path(decorator: ast.expr) -> str | None:
    """Extract the first string argument from a decorator call (the URL path)."""
    if isinstance(decorator, ast.Call) and decorator.args:
        first = decorator.args[0]
        if isinstance(first, ast.Constant) and isinstance(first.value, str):
            return first.value
    return None


def _param_info(arg: ast.arg, default: ast.expr | None) -> dict:
    return {
        "name": arg.arg,
        "annotation": _annotation_to_str(arg.annotation),
        "default": ast.unparse(default) if default is not None else None,
    }


# ---------------------------------------------------------------------------
# Per-file extraction
# ---------------------------------------------------------------------------

def _extract_from_file(filepath: str, rel_path: str, kg: dict) -> None:
    """Parse *filepath* with the ast module and populate *kg* in-place."""
    try:
        source = Path(filepath).read_text(encoding="utf-8", errors="replace")
        tree = ast.parse(source, filename=filepath)
    except SyntaxError as exc:
        print(f"[ast_parser] SyntaxError in {rel_path}: {exc}", file=sys.stderr)
        return
    except Exception as exc:  # noqa: BLE001
        print(f"[ast_parser] Cannot parse {rel_path}: {exc}", file=sys.stderr)
        return

    # ------------------------------------------------------------------
    # Imports
    # ------------------------------------------------------------------
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                kg["imports"].append({
                    "module": alias.name,
                    "alias": alias.asname,
                    "names": [],
                    "file": rel_path,
                })
        elif isinstance(node, ast.ImportFrom):
            kg["imports"].append({
                "module": node.module or "",
                "alias": None,
                "names": [a.name for a in node.names],
                "file": rel_path,
            })

    # ------------------------------------------------------------------
    # Top-level and nested class / function definitions
    # ------------------------------------------------------------------
    for node in ast.walk(tree):
        if isinstance(node, (ast.ClassDef,)):
            bases = [_annotation_to_str(b) for b in node.bases]
            kg["classes"].append({
                "name": node.name,
                "bases": bases,
                "file": rel_path,
                "line": node.lineno,
            })

            # Pydantic model detection
            is_pydantic = any(
                b and (
                    b == "BaseModel"
                    or b.endswith("Model")
                    or b.endswith("Schema")
                    or b.endswith("Base")
                )
                for b in bases
            )
            if is_pydantic:
                fields: list[dict] = []
                for item in node.body:
                    if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                        fields.append({
                            "name": item.target.id,
                            "annotation": _annotation_to_str(item.annotation),
                            "default": ast.unparse(item.value) if item.value else None,
                        })
                kg["pydantic_models"].append({
                    "name": node.name,
                    "bases": bases,
                    "fields": fields,
                    "file": rel_path,
                    "line": node.lineno,
                })

        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            # Parameters
            fn_args = node.args
            # Build defaults list aligned with the args list (positional)
            n_args = len(fn_args.args)
            n_defaults = len(fn_args.defaults)
            # defaults are right-aligned
            padding = n_args - n_defaults
            defaults_padded: list[ast.expr | None] = [None] * padding + list(fn_args.defaults)

            params: list[dict] = []
            for arg, dflt in zip(fn_args.args, defaults_padded):
                params.append(_param_info(arg, dflt))
            # *args
            if fn_args.vararg:
                params.append(_param_info(fn_args.vararg, None))
            # **kwargs
            if fn_args.kwarg:
                params.append(_param_info(fn_args.kwarg, None))

            docstring = ast.get_docstring(node)
            return_ann = _annotation_to_str(node.returns)

            kg["functions"].append({
                "name": node.name,
                "params": params,
                "return_type": return_ann,
                "docstring": docstring,
                "is_async": isinstance(node, ast.AsyncFunctionDef),
                "file": rel_path,
                "line": node.lineno,
            })

            # HTTP endpoint detection via decorators
            for dec in node.decorator_list:
                method = _get_decorator_method(dec)
                if method:
                    path = _get_decorator_path(dec)
                    kg["endpoints"].append({
                        "method": method.upper(),
                        "path": path or "<unknown>",
                        "function": node.name,
                        "file": rel_path,
                        "line": node.lineno,
                    })


# ---------------------------------------------------------------------------
# Public: parse_repo
# ---------------------------------------------------------------------------

def parse_repo(repo_path: str) -> dict:
    """Walk *repo_path* recursively and return a structured knowledge graph.

    Parameters
    ----------
    repo_path:
        Absolute or relative path to the root of the cloned repository.

    Returns
    -------
    dict with keys: ``endpoints``, ``pydantic_models``, ``functions``,
    ``classes``, ``imports``.
    """
    kg: dict[str, list] = {
        "endpoints": [],
        "pydantic_models": [],
        "functions": [],
        "classes": [],
        "imports": [],
    }

    root = Path(repo_path).resolve()
    if not root.exists():
        raise FileNotFoundError(f"Repo path not found: {root}")

    for dirpath, _dirnames, filenames in os.walk(root):
        # Skip hidden dirs and common non-source dirs
        _dirnames[:] = [
            d for d in _dirnames
            if not d.startswith(".") and d not in {"__pycache__", "node_modules", ".venv", "venv"}
        ]
        for filename in filenames:
            if not filename.endswith(".py"):
                continue
            full = os.path.join(dirpath, filename)
            rel = os.path.relpath(full, root)
            _extract_from_file(full, rel, kg)

    return kg


# ---------------------------------------------------------------------------
# Public: generate_mermaid_graph
# ---------------------------------------------------------------------------

def generate_mermaid_graph(ast_json: dict) -> str:
    """Convert a knowledge-graph dict into a Mermaid.js ``graph TD`` flowchart.

    Nodes
    -----
    - Each HTTP endpoint:  ``ENDPOINT_<n>[METHOD /path]``
    - Each Pydantic model: ``MODEL_<name>[<name>]``
    - Each class:          ``CLASS_<name>[<name>]``

    Edges
    -----
    - Endpoint → Function node (if the function name matches a known function)
    - Pydantic model inheritance: child → parent (when parent is a known model/class)
    - Class inheritance: child → parent (when parent is a known class)
    """
    lines: list[str] = ["graph TD"]

    known_classes = {c["name"] for c in ast_json.get("classes", [])}
    known_models = {m["name"] for m in ast_json.get("pydantic_models", [])}
    known_functions = {f["name"] for f in ast_json.get("functions", [])}

    # --- Endpoint nodes & edges -------------------------------------------
    for idx, ep in enumerate(ast_json.get("endpoints", [])):
        ep_id = f"ENDPOINT_{idx}"
        label = f"{ep['method']} {ep['path']}"
        lines.append(f"    {ep_id}[\"{label}\"]")

        fn_name = ep.get("function", "")
        if fn_name and fn_name in known_functions:
            fn_id = "FN_" + _safe_id(fn_name)
            lines.append(f"    {fn_id}[\"{fn_name}()\"]")
            lines.append(f"    {ep_id} --> {fn_id}")

    # --- Pydantic model nodes & inheritance edges -------------------------
    for model in ast_json.get("pydantic_models", []):
        m_id = "MODEL_" + _safe_id(model["name"])
        lines.append(f"    {m_id}[\"{model['name']}\"]")
        for base in model.get("bases", []):
            if base and (base in known_models or base in known_classes):
                base_id = "MODEL_" + _safe_id(base)
                lines.append(f"    {m_id} --> {base_id}")

    # --- Class nodes & inheritance edges ----------------------------------
    for cls in ast_json.get("classes", []):
        # Skip if already rendered as a Pydantic model
        if cls["name"] in known_models:
            continue
        c_id = "CLASS_" + _safe_id(cls["name"])
        lines.append(f"    {c_id}[\"{cls['name']}\"]")
        for base in cls.get("bases", []):
            if base and base in known_classes:
                base_id = "CLASS_" + _safe_id(base)
                lines.append(f"    {c_id} --> {base_id}")

    return "\n".join(lines) + "\n"
