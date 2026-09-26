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

def _build_entry_points(root: Path) -> list[dict]:
    """Identify key entry-point files in *root* and return a typed list."""
    entry_points: list[dict] = []
    seen: set[str] = set()

    # Root-level entrypoints (main.py, app.py, run.py, wsgi.py, asgi.py)
    for name in ("main.py", "app.py", "run.py", "wsgi.py", "asgi.py"):
        candidate = root / name
        if candidate.exists():
            rel = str(candidate.relative_to(root))
            if rel not in seen:
                entry_points.append({"name": rel, "type": "entrypoint"})
                seen.add(rel)

    # Router files under any routers/ directory
    for py_file in sorted(root.rglob("routers/*.py")):
        if py_file.name == "__init__.py":
            continue
        rel = str(py_file.relative_to(root))
        if rel not in seen:
            entry_points.append({"name": rel, "type": "router"})
            seen.add(rel)

    # Schema/model files under any models/ directory
    for py_file in sorted(root.rglob("models/*.py")):
        if py_file.name == "__init__.py":
            continue
        rel = str(py_file.relative_to(root))
        if rel not in seen:
            entry_points.append({"name": rel, "type": "model"})
            seen.add(rel)

    return entry_points


def _build_tour_steps(entry_points: list[dict]) -> list[str]:
    """Generate 5 structured reading-tour steps from *entry_points*."""
    steps: list[str] = []

    entrypoints = [ep for ep in entry_points if ep["type"] == "entrypoint"]
    routers     = [ep for ep in entry_points if ep["type"] == "router"]
    models      = [ep for ep in entry_points if ep["type"] == "model"]

    # Step 1 – application bootstrap
    if entrypoints:
        names = ", ".join(ep["name"] for ep in entrypoints[:2])
        steps.append(
            f"1. Start with {names} to understand the application bootstrap "
            "and how the framework (FastAPI/Flask) is initialised."
        )
    else:
        steps.append(
            "1. Locate the main entry point (main.py / app.py) to understand "
            "how the application is bootstrapped."
        )

    # Step 2 – routers / API surface
    if routers:
        names = ", ".join(ep["name"] for ep in routers[:3])
        steps.append(
            f"2. Explore the routers ({names}) to discover the API endpoints "
            "and understand the request/response flow."
        )
    else:
        steps.append(
            "2. Explore the routers directory to discover the API endpoints "
            "and understand the request/response flow."
        )

    # Step 3 – data models / schemas
    if models:
        names = ", ".join(ep["name"] for ep in models[:3])
        steps.append(
            f"3. Read the data models ({names}) to learn the Pydantic schemas "
            "and the shapes of data passed between layers."
        )
    else:
        steps.append(
            "3. Read the models directory to learn the data schemas and "
            "structures passed between layers."
        )

    # Step 4 – services / business logic
    steps.append(
        "4. Dive into the services (or core) layer to understand the business "
        "logic, external API calls, and any background tasks."
    )

    # Step 5 – tests
    steps.append(
        "5. Review the tests directory to understand expected behaviour, "
        "edge cases, and how to run the test suite locally."
    )

    return steps


def parse_repo(repo_path: str) -> dict:
    """Walk *repo_path* recursively and return a structured knowledge graph.

    Parameters
    ----------
    repo_path:
        Absolute or relative path to the root of the cloned repository.

    Returns
    -------
    dict with keys: ``endpoints``, ``pydantic_models``, ``functions``,
    ``classes``, ``imports``, ``entry_points``, ``tour_steps``.
    """
    kg: dict[str, Any] = {
        "endpoints": [],
        "pydantic_models": [],
        "functions": [],
        "classes": [],
        "imports": [],
        "entry_points": [],
        "tour_steps": [],
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

    # Automatically populate entry_points and tour_steps
    kg["entry_points"] = _build_entry_points(root)
    kg["tour_steps"] = _build_tour_steps(kg["entry_points"])

    return kg


# ---------------------------------------------------------------------------
# Public: generate_mermaid_graph
# ---------------------------------------------------------------------------

def generate_mermaid_graph(ast_json: dict) -> str:
    """Convert a knowledge-graph dict into a Mermaid.js ``flowchart TD``.

    The graph is organized into three named subgraphs for readability:

    Subgraphs
    ---------
    - **Endpoints** – HTTP endpoint nodes wired to their handler functions
    - **Functions** – standalone function nodes referenced by endpoints
    - **Models**    – Pydantic model nodes with inheritance edges

    Orientation: ``flowchart TD`` (top-down, compact vertical layout).
    """
    known_classes  = {c["name"] for c in ast_json.get("classes", [])}
    known_models   = {m["name"] for m in ast_json.get("pydantic_models", [])}
    known_functions = {f["name"] for f in ast_json.get("functions", [])}

    # Collect lines per subgraph so empty subgraphs are omitted cleanly
    endpoint_lines: list[str] = []
    function_lines: list[str] = []
    model_lines:    list[str] = []
    edge_lines:     list[str] = []   # cross-subgraph edges go after all subgraphs

    # --- Endpoint nodes & edges -------------------------------------------
    fn_ids_used: set[str] = set()
    for idx, ep in enumerate(ast_json.get("endpoints", [])):
        ep_id = f"ENDPOINT_{idx}"
        label = f"{ep['method']} {ep['path']}"
        endpoint_lines.append(f"        {ep_id}[\"{label}\"]")

        fn_name = ep.get("function", "")
        if fn_name and fn_name in known_functions:
            fn_id = "FN_" + _safe_id(fn_name)
            fn_ids_used.add(fn_id)
            function_lines.append(f"        {fn_id}[\"{fn_name}()\"]")
            edge_lines.append(f"    {ep_id} --> {fn_id}")

    # Remove duplicate function nodes (same function on multiple endpoints)
    seen_fn: set[str] = set()
    deduped_fn: list[str] = []
    for line in function_lines:
        node_id = line.strip().split("[")[0]
        if node_id not in seen_fn:
            seen_fn.add(node_id)
            deduped_fn.append(line)
    function_lines = deduped_fn

    # --- Pydantic model nodes & inheritance edges -------------------------
    for model in ast_json.get("pydantic_models", []):
        m_id = "MODEL_" + _safe_id(model["name"])
        model_lines.append(f"        {m_id}[\"{model['name']}\"]")
        for base in model.get("bases", []):
            if base and (base in known_models or base in known_classes):
                base_id = "MODEL_" + _safe_id(base)
                edge_lines.append(f"    {m_id} --> {base_id}")

    # --- Class nodes (non-Pydantic) inside Models subgraph ----------------
    for cls in ast_json.get("classes", []):
        if cls["name"] in known_models:
            continue
        c_id = "CLASS_" + _safe_id(cls["name"])
        model_lines.append(f"        {c_id}[\"{cls['name']}\"]")
        for base in cls.get("bases", []):
            if base and base in known_classes:
                base_id = "CLASS_" + _safe_id(base)
                edge_lines.append(f"    {c_id} --> {base_id}")

    # --- Assemble output --------------------------------------------------
    out: list[str] = ["flowchart TD"]

    if endpoint_lines:
        out.append("    subgraph Endpoints")
        out.extend(endpoint_lines)
        out.append("    end")

    if function_lines:
        out.append("    subgraph Functions")
        out.extend(function_lines)
        out.append("    end")

    if model_lines:
        out.append("    subgraph Models")
        out.extend(model_lines)
        out.append("    end")

    out.extend(edge_lines)

    return "\n".join(out) + "\n"
