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

generate_architecture_svg(ast_json: dict) -> str
    Generate a standalone SVG vector image of the repository architecture.
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
    ``classes``, ``imports``, ``entry_points``, ``tour_steps``, ``svg_image``.
    """
    kg: dict[str, Any] = {
        "endpoints": [],
        "pydantic_models": [],
        "functions": [],
        "classes": [],
        "imports": [],
        "entry_points": [],
        "tour_steps": [],
        "svg_image": "",
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

    # Automatically populate entry_points, tour_steps, and svg_image
    kg["entry_points"] = _build_entry_points(root)
    kg["tour_steps"] = _build_tour_steps(kg["entry_points"])
    kg["svg_image"] = generate_architecture_svg(kg)

    return kg


# ---------------------------------------------------------------------------
# Public: generate_architecture_svg
# ---------------------------------------------------------------------------

# SVG layout constants
_SVG_WIDTH         = 900
_SVG_MIN_HEIGHT    = 400
_CARD_W            = 200
_CARD_H            = 56
_CARD_RX           = 8
_COL_GAP           = 60   # horizontal gap between columns
_ROW_GAP           = 28   # vertical gap between cards in a column
_TOP_PAD           = 60   # padding above first row
_BOTTOM_PAD        = 60

# Category colours
_COLOR_ROUTER  = "#7c3aed"  # Violet
_COLOR_SERVICE = "#4f46e5"  # Indigo
_COLOR_MODEL   = "#d97706"  # Amber

_COLOR_ROUTER_BG  = "#ede9fe"
_COLOR_SERVICE_BG = "#e0e7ff"
_COLOR_MODEL_BG   = "#fef3c7"

_COLOR_ROUTER_TXT  = "#5b21b6"
_COLOR_SERVICE_TXT = "#3730a3"
_COLOR_MODEL_TXT   = "#92400e"

# Arrow / line colour
_ARROW_COLOR = "#94a3b8"


def _svg_escape(text: str) -> str:
    """Escape special XML characters for safe inclusion in SVG text."""
    return (
        text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
    )


def _truncate(text: str, max_chars: int = 22) -> str:
    """Truncate *text* to *max_chars*, appending '…' if needed."""
    return text if len(text) <= max_chars else text[: max_chars - 1] + "…"


def generate_architecture_svg(ast_json: dict) -> str:
    """Generate a standalone, fully styled, high-res SVG vector image string
    representing the repository architecture.

    Three column groups are rendered left-to-right:
    - **Routers / Endpoints** (Violet ``#7c3aed``)
    - **Core Services**       (Indigo ``#4f46e5``)
    - **Models / Schemas**    (Amber  ``#d97706``)

    Connecting arrows are drawn from each Router card to every Service card,
    and from each Service card to every Model card, keeping a minimum SVG
    canvas of 800 × 400 px.

    Parameters
    ----------
    ast_json:
        Knowledge-graph dict as returned by :func:`parse_repo`.

    Returns
    -------
    A self-contained ``<svg>`` string (no external dependencies).
    """
    known_model_names = {m["name"] for m in ast_json.get("pydantic_models", [])}

    # --- Collect up to 8 items per column --------------------------------
    # Routers: unique router files (files with endpoints)
    router_files: dict[str, str] = {}
    for ep in ast_json.get("endpoints", []):
        f = ep.get("file", "")
        if f not in router_files:
            router_files[f] = Path(f).stem
    router_labels = list(router_files.values())[:8]

    # Services: non-Pydantic public classes
    service_labels: list[str] = []
    for cls in ast_json.get("classes", []):
        name = cls["name"]
        if name in known_model_names or name.startswith("_"):
            continue
        if name.lower() in _BORING_NAMES:
            continue
        service_labels.append(name)
        if len(service_labels) >= 8:
            break

    # Models: Pydantic models
    model_labels = [
        m["name"]
        for m in ast_json.get("pydantic_models", [])
        if not m["name"].startswith("_")
    ][:8]

    # Fallback labels so there's always something to render
    if not router_labels:
        router_labels = ["Routers"]
    if not service_labels:
        service_labels = ["Services"]
    if not model_labels:
        model_labels = ["Models"]

    # --- Layout: 3 columns, cards stacked vertically ---------------------
    max_rows = max(len(router_labels), len(service_labels), len(model_labels))
    col_count = 3

    # Total width: left_pad + 3*(card_w) + 2*(col_gap) + right_pad
    left_pad  = (_SVG_WIDTH - col_count * _CARD_W - (col_count - 1) * _COL_GAP) // 2
    right_pad = left_pad

    total_height = max(
        _SVG_MIN_HEIGHT,
        _TOP_PAD + max_rows * _CARD_H + (max_rows - 1) * _ROW_GAP + _BOTTOM_PAD,
    )

    # Column x-centres
    col_x = [
        left_pad + i * (_CARD_W + _COL_GAP)
        for i in range(col_count)
    ]

    def card_cy(row: int) -> int:
        """Vertical centre of card at *row* (0-based)."""
        return _TOP_PAD + row * (_CARD_H + _ROW_GAP) + _CARD_H // 2

    # --- Build SVG -------------------------------------------------------
    lines: list[str] = []

    def _card(x: int, cy: int, label: str, stroke: str, bg: str, txt: str) -> None:
        rx_val   = _CARD_RX
        card_x   = x
        card_y   = cy - _CARD_H // 2
        label_s  = _svg_escape(_truncate(label))
        lines.append(
            f'  <rect x="{card_x}" y="{card_y}" width="{_CARD_W}" height="{_CARD_H}" '
            f'rx="{rx_val}" ry="{rx_val}" '
            f'fill="{bg}" stroke="{stroke}" stroke-width="2"/>'
        )
        lines.append(
            f'  <text x="{card_x + _CARD_W // 2}" y="{cy + 5}" '
            f'text-anchor="middle" dominant-baseline="middle" '
            f'font-family="\'Segoe UI\', system-ui, sans-serif" font-size="12" '
            f'font-weight="600" fill="{txt}">{label_s}</text>'
        )

    def _arrow(x1: int, y1: int, x2: int, y2: int) -> None:
        """Draw a straight horizontal arrow from (x1,y1) to (x2,y2)."""
        lines.append(
            f'  <line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" '
            f'stroke="{_ARROW_COLOR}" stroke-width="1.5" '
            f'marker-end="url(#arrowhead)"/>'
        )

    # SVG header
    lines.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'width="{_SVG_WIDTH}" height="{total_height}" '
        f'viewBox="0 0 {_SVG_WIDTH} {total_height}" '
        f'style="background:#0f172a;font-family:\'Segoe UI\',system-ui,sans-serif">'
    )

    # Arrowhead marker definition
    lines.append(
        '  <defs>'
        '<marker id="arrowhead" markerWidth="8" markerHeight="6" '
        'refX="8" refY="3" orient="auto">'
        f'<polygon points="0 0, 8 3, 0 6" fill="{_ARROW_COLOR}"/>'
        '</marker>'
        '</defs>'
    )

    # Column header labels
    col_headers = [
        ("Routers / Endpoints", _COLOR_ROUTER),
        ("Core Services",       _COLOR_SERVICE),
        ("Models / Schemas",    _COLOR_MODEL),
    ]
    for i, (header, color) in enumerate(col_headers):
        hx = col_x[i] + _CARD_W // 2
        lines.append(
            f'  <text x="{hx}" y="34" text-anchor="middle" '
            f'font-size="13" font-weight="700" fill="{color}" '
            f'font-family="\'Segoe UI\', system-ui, sans-serif">'
            f'{_svg_escape(header)}</text>'
        )

    # Draw cards per column
    def _draw_column(
        labels: list[str],
        col_idx: int,
        stroke: str, bg: str, txt: str,
    ) -> list[tuple[int, int]]:
        """Draw all cards for a column; return list of (right_x, cy) connector points."""
        centres: list[tuple[int, int]] = []
        for row, label in enumerate(labels):
            cx  = col_x[col_idx]
            cy  = card_cy(row)
            _card(cx, cy, label, stroke, bg, txt)
            centres.append((cx, cy))
        return centres

    router_pts  = _draw_column(router_labels,  0, _COLOR_ROUTER,  _COLOR_ROUTER_BG,  _COLOR_ROUTER_TXT)
    service_pts = _draw_column(service_labels, 1, _COLOR_SERVICE, _COLOR_SERVICE_BG, _COLOR_SERVICE_TXT)
    model_pts   = _draw_column(model_labels,   2, _COLOR_MODEL,   _COLOR_MODEL_BG,   _COLOR_MODEL_TXT)

    # Draw connecting arrows (first router → first service, first service → first model)
    for rx, ry in router_pts[:1]:
        for sx, sy in service_pts[:1]:
            _arrow(rx + _CARD_W, ry, sx, sy)

    for sx, sy in service_pts[:1]:
        for mx, my in model_pts[:1]:
            _arrow(sx + _CARD_W, sy, mx, my)

    lines.append("</svg>")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Public: generate_mermaid_graph
# ---------------------------------------------------------------------------

# Node budget for the Mermaid diagram.  Large repos can have hundreds of
# endpoints / classes; cap each category so the graph stays readable.
_MAX_ROUTERS   = 10   # unique router files shown in the Routers subgraph
_MAX_SERVICES  = 8    # non-model classes shown in the Services subgraph
_MAX_MODELS    = 8    # Pydantic models shown in the Models subgraph

# Utility helpers that are never interesting at an architectural level
_BORING_NAMES = frozenset({
    "main", "app", "run", "init", "setup", "teardown", "startup", "shutdown",
    "lifespan", "create_app", "get_app", "make_app", "configure",
    "settings", "config", "logger", "get_logger", "get_db", "get_session",
    "dependency", "depends",
})


def _is_public(name: str) -> bool:
    """Return True when *name* is not a private/dunder helper."""
    return not name.startswith("_")


def _file_to_subgraph_label(file_path: str) -> str:
    """Map a relative file path to a human-readable subgraph label.

    Rules (first match wins):
    - contains ``router`` / ``routers`` → "Routers"
    - contains ``service`` / ``services`` → "Services"
    - contains ``model`` / ``models`` / ``schema`` / ``schemas`` → "Models"
    - contains ``util`` / ``utils`` / ``helper`` / ``helpers`` → "Utilities"
    - otherwise → the top-level package name (first path segment)
    """
    lower = file_path.replace("\\", "/").lower()
    parts = lower.split("/")

    for part in parts:
        if part in ("router", "routers"):
            return "Routers"
        if part in ("service", "services"):
            return "Services"
        if part in ("model", "models", "schema", "schemas"):
            return "Models"
        if part in ("util", "utils", "helper", "helpers"):
            return "Utilities"

    # Fall back to the top-level package directory (ignore root .py files)
    if len(parts) > 1:
        return parts[0].capitalize()
    return "Core"


def generate_mermaid_graph(ast_json: dict) -> str:
    """Convert a knowledge-graph dict into a compact Mermaid.js ``flowchart TD``.

    Large-repo handling
    -------------------
    - Private / internal helpers (names starting with ``_``) are excluded.
    - Common utility helpers (``get_db``, ``logger``, etc.) are excluded.
    - Endpoints are de-duplicated by *router file*; at most ``_MAX_ROUTERS``
      router files are shown in the **Routers** subgraph.
    - Service classes (non-Pydantic) are capped at ``_MAX_SERVICES`` nodes.
    - Pydantic models are capped at ``_MAX_MODELS`` nodes.
    - All nodes are clustered into directory-aware subgraphs:
      ``Routers``, ``Services``, ``Models``, plus any extra package buckets.

    Orientation: ``flowchart TD`` (top-down, compact vertical layout).
    """
    known_models    = {m["name"] for m in ast_json.get("pydantic_models", [])}
    known_classes   = {c["name"] for c in ast_json.get("classes", [])}
    known_functions = {f["name"] for f in ast_json.get("functions", [])}

    # subgraph_label → list of node definition lines
    subgraph_nodes: dict[str, list[str]] = {}
    edge_lines:     list[str] = []
    rendered_nodes: set[str]  = set()   # track IDs to avoid duplication

    def _add_node(sg_label: str, node_id: str, label: str) -> None:
        if node_id in rendered_nodes:
            return
        rendered_nodes.add(node_id)
        subgraph_nodes.setdefault(sg_label, []).append(
            f'        {node_id}["{label}"]'
        )

    # ------------------------------------------------------------------
    # 1. Routers subgraph – one node per unique router *file* with its
    #    HTTP method counts, capped at _MAX_ROUTERS files.
    # ------------------------------------------------------------------
    router_files: dict[str, list[dict]] = {}
    for ep in ast_json.get("endpoints", []):
        f = ep.get("file", "")
        router_files.setdefault(f, []).append(ep)

    for file_path in list(router_files.keys())[:_MAX_ROUTERS]:
        eps = router_files[file_path]
        # Use the filename stem as the label (e.g. scan.py → scan)
        stem = Path(file_path).stem
        if not _is_public(stem):
            continue
        # Summarise: "scan (GET×3 POST×1)"
        method_counts: dict[str, int] = {}
        for ep in eps:
            m = ep.get("method", "GET")
            method_counts[m] = method_counts.get(m, 0) + 1
        summary = " ".join(f"{m}×{n}" for m, n in sorted(method_counts.items()))
        label = f"{stem}\\n{summary}" if summary else stem
        node_id = "ROUTER_" + _safe_id(file_path)
        sg = _file_to_subgraph_label(file_path)
        _add_node(sg, node_id, label)

    # ------------------------------------------------------------------
    # 2. Services subgraph – non-Pydantic public classes, capped.
    # ------------------------------------------------------------------
    service_count = 0
    for cls in ast_json.get("classes", []):
        if service_count >= _MAX_SERVICES:
            break
        name = cls["name"]
        if name in known_models:
            continue
        if not _is_public(name):
            continue
        if name.lower() in _BORING_NAMES:
            continue
        c_id = "CLASS_" + _safe_id(name)
        sg = _file_to_subgraph_label(cls.get("file", ""))
        _add_node(sg, c_id, name)
        # Inheritance edges (only to other known classes in the graph)
        for base in cls.get("bases", []):
            if base and base in known_classes and _is_public(base):
                base_id = "CLASS_" + _safe_id(base)
                edge_lines.append(f"    {c_id} --> {base_id}")
        service_count += 1

    # ------------------------------------------------------------------
    # 3. Models subgraph – Pydantic models, capped.
    # ------------------------------------------------------------------
    model_count = 0
    for model in ast_json.get("pydantic_models", []):
        if model_count >= _MAX_MODELS:
            break
        name = model["name"]
        if not _is_public(name):
            continue
        m_id = "MODEL_" + _safe_id(name)
        sg = _file_to_subgraph_label(model.get("file", ""))
        _add_node(sg, m_id, name)
        for base in model.get("bases", []):
            if base and base in known_models and _is_public(base):
                base_id = "MODEL_" + _safe_id(base)
                edge_lines.append(f"    {m_id} --> {base_id}")
        model_count += 1

    # ------------------------------------------------------------------
    # 4. Assemble output
    # ------------------------------------------------------------------
    # Preferred display order for subgraph labels
    _ORDER = ["Routers", "Services", "Models", "Utilities", "Core"]
    ordered_labels = [l for l in _ORDER if l in subgraph_nodes]
    ordered_labels += [l for l in subgraph_nodes if l not in _ORDER]

    out: list[str] = ["flowchart TD"]
    for label in ordered_labels:
        lines = subgraph_nodes[label]
        if not lines:
            continue
        safe_label = _safe_id(label)
        out.append(f'    subgraph {safe_label}["{label}"]')
        out.extend(lines)
        out.append("    end")

    # Only emit edges whose both endpoints were actually rendered
    for edge in edge_lines:
        # edge format: "    ID1 --> ID2"
        parts = edge.strip().split(" --> ")
        if len(parts) == 2 and parts[0] in rendered_nodes and parts[1] in rendered_nodes:
            out.append(edge)

    return "\n".join(out) + "\n"
