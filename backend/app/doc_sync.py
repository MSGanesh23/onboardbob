"""
doc_sync.py – Documentation Sync & Drift Detection engine for OnboardBob.

DocuSync-Subagent
=================
This module implements the core "Document Understanding" pipeline:

1. **README Parsing** – Extracts documented API endpoints from the repo's
   README.md using regex heuristics (Markdown code-fence blocks, backtick
   references, and ATX-heading sections).

2. **AST Extraction** – Re-uses the existing ``ast_parser`` to walk all Python
   files in the workspace repo and pull out:
   - Every HTTP endpoint (method + path) detected via decorator analysis.
   - Every function / method with its docstring (or lack thereof).

3. **Drift Detection** – Compares the two sets and classifies findings into:
   a) **Undocumented endpoints** – exist in code, absent from README.
   b) **Missing docstrings** – router/service functions with no docstring.
   c) **Stale parameters** – parameters mentioned in the README that are not
      present in the matching code function's signature.

4. **Drift Score** – A single 0–100 float that quantifies how complete the
   documentation is (100 = perfectly documented, 0 = fully undocumented).

5. **Markdown Suggestions** – Generates ready-to-paste Markdown snippets to
   fill documentation gaps, with optional IBM Granite / watsonx.ai enrichment
   when ``WATSONX_API_KEY`` + ``WATSONX_PROJECT_ID`` env-vars are set.

Public API
----------
run_doc_drift(repo_name: str) -> DriftReport
    Entry-point called by the REST layer.
"""

from __future__ import annotations

import ast
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .ast_parser import parse_repo

# ---------------------------------------------------------------------------
# Workspace root (mirrors main.py)
# ---------------------------------------------------------------------------

_WORKSPACE_DIR = Path(__file__).resolve().parent.parent.parent / "workspace"

# ---------------------------------------------------------------------------
# Data-classes
# ---------------------------------------------------------------------------

@dataclass
class EndpointInfo:
    """A single HTTP endpoint discovered in code."""
    method: str
    path: str
    function: str
    file: str
    line: int


@dataclass
class FunctionInfo:
    """A function / method extracted from the AST."""
    name: str
    params: list[str]
    docstring: str | None
    file: str
    line: int


@dataclass
class DriftReport:
    """Full result returned by :func:`run_doc_drift`."""
    repo_name: str
    drift_score: float                        # 0.0 – 100.0
    undocumented_endpoints: list[dict]        # code endpoints not in README
    missing_docstrings: list[dict]            # functions with no docstring
    stale_parameters: list[dict]             # README params not in code sig
    documented_endpoints: list[str]          # endpoint paths found in README
    total_endpoints: int
    total_functions: int
    markdown_suggestions: list[str]          # ready-to-paste Markdown blocks
    watsonx_used: bool = False

    def to_dict(self) -> dict:
        return {
            "repo_name": self.repo_name,
            "drift_score": round(self.drift_score, 2),
            "undocumented_endpoints": self.undocumented_endpoints,
            "missing_docstrings": self.missing_docstrings,
            "stale_parameters": self.stale_parameters,
            "documented_endpoints": self.documented_endpoints,
            "total_endpoints": self.total_endpoints,
            "total_functions": self.total_functions,
            "markdown_suggestions": self.markdown_suggestions,
            "watsonx_used": self.watsonx_used,
        }


# ---------------------------------------------------------------------------
# README Document Understanding
# ---------------------------------------------------------------------------

# Patterns used to recognise an endpoint mention in Markdown text.
# We look for strings that look like:  GET /api/foo   /api/foo   `GET /api/foo`
_ENDPOINT_PATTERN = re.compile(
    r"`?(?:GET|POST|PUT|DELETE|PATCH|OPTIONS|HEAD)\s+(/[^\s`\"']+)`?"
    r"|`(/[a-zA-Z0-9_/{}*-]+)`"    # bare path in backticks
    r"|(?:^|\s)(/api/[a-zA-Z0-9_/{}*-]+)",  # /api/ prefix without method
    re.IGNORECASE | re.MULTILINE,
)

# Matches a Markdown table row that looks like:  | param_name | description |
_PARAM_TABLE_ROW = re.compile(r"\|\s*`?(\w+)`?\s*\|")

# Matches a Markdown code-fence block with HTTP method + path
_CODE_FENCE_ENDPOINT = re.compile(
    r"```[^\n]*\n.*?(?:GET|POST|PUT|DELETE|PATCH)\s+(/[^\s\"']+).*?```",
    re.IGNORECASE | re.DOTALL,
)


def _parse_readme(readme_path: Path) -> tuple[set[str], dict[str, list[str]]]:
    """Parse *readme_path* and return:

    - ``documented_paths``: set of URL path strings found in the README.
    - ``documented_params``: mapping of path → list of param names mentioned
      near that path's section.
    """
    if not readme_path.exists():
        return set(), {}

    text = readme_path.read_text(encoding="utf-8", errors="replace")

    documented_paths: set[str] = set()
    documented_params: dict[str, list[str]] = {}

    # --- 1. Find endpoint paths in code fences ----------------------------
    for m in _CODE_FENCE_ENDPOINT.finditer(text):
        documented_paths.add(m.group(1).strip())

    # --- 2. Find inline endpoint references (method + path) ---------------
    for m in _ENDPOINT_PATTERN.finditer(text):
        path = m.group(1) or m.group(2) or m.group(3)
        if path:
            documented_paths.add(path.strip())

    # --- 3. Extract parameters near each documented path ------------------
    # Split text into heading-delimited sections and look for param tables
    sections = re.split(r"\n#{1,4} ", text)
    for section in sections:
        # Find paths referenced in this section
        paths_in_section: list[str] = []
        for m in _ENDPOINT_PATTERN.finditer(section):
            path = m.group(1) or m.group(2) or m.group(3)
            if path:
                paths_in_section.append(path.strip())

        if not paths_in_section:
            continue

        # Find parameter names (table rows)
        params = _PARAM_TABLE_ROW.findall(section)
        # Filter out common non-param words
        _SKIP = {"parameter", "param", "field", "name", "type", "description",
                  "required", "optional", "default", "example", "value"}
        params = [p for p in params if p.lower() not in _SKIP]

        for path in paths_in_section:
            documented_params.setdefault(path, []).extend(params)

    return documented_paths, documented_params


# ---------------------------------------------------------------------------
# AST helpers – endpoint & function extraction
# ---------------------------------------------------------------------------

def _collect_endpoints(kg: dict) -> list[EndpointInfo]:
    return [
        EndpointInfo(
            method=ep["method"],
            path=ep["path"],
            function=ep["function"],
            file=ep["file"],
            line=ep["line"],
        )
        for ep in kg.get("endpoints", [])
    ]


def _collect_functions(kg: dict) -> list[FunctionInfo]:
    return [
        FunctionInfo(
            name=fn["name"],
            params=[p["name"] for p in fn.get("params", [])],
            docstring=fn.get("docstring"),
            file=fn["file"],
            line=fn["line"],
        )
        for fn in kg.get("functions", [])
    ]


# ---------------------------------------------------------------------------
# Drift detection helpers
# ---------------------------------------------------------------------------

def _normalise_path(path: str) -> str:
    """Normalise a URL path for comparison (strip trailing slash, lowercase)."""
    return path.rstrip("/").lower()


def _find_undocumented_endpoints(
    code_endpoints: list[EndpointInfo],
    documented_paths: set[str],
) -> list[dict]:
    """Return endpoints that appear in code but not in the README."""
    doc_normalised = {_normalise_path(p) for p in documented_paths}
    undoc: list[dict] = []
    for ep in code_endpoints:
        if _normalise_path(ep.path) not in doc_normalised:
            undoc.append({
                "method": ep.method,
                "path": ep.path,
                "function": ep.function,
                "file": ep.file,
                "line": ep.line,
            })
    return undoc


def _find_missing_docstrings(functions: list[FunctionInfo]) -> list[dict]:
    """Return functions/methods that have no docstring."""
    missing: list[dict] = []
    for fn in functions:
        # Skip private helpers (leading underscore) and __dunder__ methods
        if fn.name.startswith("_"):
            continue
        if not fn.docstring:
            missing.append({
                "function": fn.name,
                "file": fn.file,
                "line": fn.line,
                "params": fn.params,
            })
    return missing


def _find_stale_parameters(
    code_endpoints: list[EndpointInfo],
    code_functions: list[FunctionInfo],
    documented_params: dict[str, list[str]],
) -> list[dict]:
    """Return parameters that are mentioned in README but absent from the
    corresponding function's signature in code."""
    # Build a map from function name to its param list
    fn_params: dict[str, list[str]] = {fn.name: fn.params for fn in code_functions}

    stale: list[dict] = []
    for ep in code_endpoints:
        path_norm = _normalise_path(ep.path)
        # Try to find the matching documented params by normalised path
        readme_params: list[str] = []
        for doc_path, params in documented_params.items():
            if _normalise_path(doc_path) == path_norm:
                readme_params.extend(params)

        if not readme_params:
            continue

        code_params = fn_params.get(ep.function, [])
        stale_params = [p for p in readme_params if p not in code_params]
        if stale_params:
            stale.append({
                "endpoint_path": ep.path,
                "function": ep.function,
                "stale_params": stale_params,
                "actual_params": code_params,
            })

    return stale


# ---------------------------------------------------------------------------
# Drift score calculation
# ---------------------------------------------------------------------------

def _calculate_drift_score(
    total_endpoints: int,
    undocumented_endpoints: int,
    total_functions: int,
    missing_docstrings: int,
    stale_params_count: int,
) -> float:
    """Calculate a documentation health score from 0.0 (worst) to 100.0 (best).

    Formula (weighted average):
    - Endpoint coverage  40 %
    - Docstring coverage 40 %
    - Parameter freshness 20 %
    """
    if total_endpoints == 0 and total_functions == 0:
        return 100.0

    # Endpoint coverage component
    if total_endpoints > 0:
        ep_coverage = 1.0 - (undocumented_endpoints / total_endpoints)
    else:
        ep_coverage = 1.0

    # Docstring coverage component
    if total_functions > 0:
        ds_coverage = 1.0 - (missing_docstrings / total_functions)
    else:
        ds_coverage = 1.0

    # Parameter freshness component
    # Penalise each stale param group; cap at 1.0 penalty
    if total_endpoints > 0:
        stale_penalty = min(1.0, stale_params_count / max(total_endpoints, 1))
        param_freshness = 1.0 - stale_penalty
    else:
        param_freshness = 1.0

    score = (ep_coverage * 0.40 + ds_coverage * 0.40 + param_freshness * 0.20) * 100.0
    return round(score, 2)


# ---------------------------------------------------------------------------
# Markdown suggestion generator
# ---------------------------------------------------------------------------

def _build_markdown_suggestions(
    undocumented: list[dict],
    missing_ds: list[dict],
    stale: list[dict],
) -> list[str]:
    """Return a list of ready-to-paste Markdown blocks addressing each gap."""
    suggestions: list[str] = []

    # --- Undocumented endpoints -------------------------------------------
    for ep in undocumented:
        params_hint = ""
        md = (
            f"### `{ep['method']} {ep['path']}`\n\n"
            f"> **⚠ Undocumented endpoint** – add to README.\n\n"
            f"**Function:** `{ep['function']}` ({ep['file']}:{ep['line']})\n\n"
            f"**Description:** _TODO – describe what this endpoint does._\n\n"
            f"**Request body:**\n\n```json\n{{{params_hint}}}\n```\n\n"
            f"**Response:**\n\n```json\n{{}}\n```\n"
        )
        suggestions.append(md)

    # --- Missing docstrings -----------------------------------------------
    for fn in missing_ds:
        param_lines = "\n".join(
            f"    {p}:\n        _TODO_" for p in fn["params"] if p != "self"
        )
        ds = (
            f"# Missing docstring – add to `{fn['function']}` "
            f"in {fn['file']}:{fn['line']}\n\n"
            f'"""\n'
            f"TODO: Describe the purpose of ``{fn['function']}``.\n\n"
        )
        if param_lines:
            ds += f"Parameters\n----------\n{param_lines}\n"
        ds += '"""\n'
        suggestions.append(ds)

    # --- Stale parameters -------------------------------------------------
    for item in stale:
        md = (
            f"### Stale parameters for `{item['endpoint_path']}`\n\n"
            f"The following parameters appear in the README but **no longer exist** "
            f"in `{item['function']}`:\n\n"
            + "\n".join(f"- `{p}`" for p in item["stale_params"])
            + "\n\n"
            f"**Current function parameters:** "
            + ", ".join(f"`{p}`" for p in item["actual_params"] if p != "self")
            + "\n\n> Remove or update the README documentation for these parameters.\n"
        )
        suggestions.append(md)

    return suggestions


# ---------------------------------------------------------------------------
# Optional: IBM watsonx.ai / Granite enrichment
# ---------------------------------------------------------------------------

def _enrich_with_watsonx(suggestions: list[str], context: str) -> list[str]:
    """
    Optionally call IBM watsonx.ai (ibm-watsonx-ai SDK) to rewrite the
    raw Markdown suggestions into polished documentation.

    Requires environment variables:
    - ``WATSONX_API_KEY``   – IBM Cloud API key
    - ``WATSONX_PROJECT_ID`` – watsonx.ai project GUID
    - ``WATSONX_URL``        – regional endpoint (default: us-south)

    Falls back silently to the plain suggestions when the SDK is absent or
    credentials are missing.
    """
    api_key = os.environ.get("WATSONX_API_KEY", "")
    project_id = os.environ.get("WATSONX_PROJECT_ID", "")
    if not api_key or not project_id:
        return suggestions

    try:
        from ibm_watsonx_ai import Credentials  # type: ignore
        from ibm_watsonx_ai.foundation_models import ModelInference  # type: ignore
        from ibm_watsonx_ai.metanames import GenTextParamsMetaNames as Params  # type: ignore
    except ImportError:
        print("[doc_sync] ibm-watsonx-ai not installed – skipping enrichment.", file=sys.stderr)
        return suggestions

    url = os.environ.get("WATSONX_URL", "https://us-south.ml.cloud.ibm.com")
    creds = Credentials(url=url, api_key=api_key)

    model = ModelInference(
        model_id="ibm/granite-13b-instruct-v2",
        credentials=creds,
        project_id=project_id,
        params={
            Params.MAX_NEW_TOKENS: 512,
            Params.TEMPERATURE: 0.3,
        },
    )

    enriched: list[str] = []
    for raw in suggestions:
        prompt = (
            "You are a technical writer. Rewrite the following raw documentation "
            "stub into a clear, concise Markdown section suitable for a project "
            "README. Preserve the structure but improve clarity.\n\n"
            f"Context about the project:\n{context}\n\n"
            f"Raw stub:\n{raw}\n\n"
            "Rewritten Markdown:"
        )
        try:
            response = model.generate_text(prompt=prompt)
            enriched.append(response.strip())
        except Exception as exc:  # noqa: BLE001
            print(f"[doc_sync] watsonx call failed: {exc}", file=sys.stderr)
            enriched.append(raw)

    return enriched


# ---------------------------------------------------------------------------
# Public entry-point
# ---------------------------------------------------------------------------

def run_doc_drift(repo_name: str) -> DriftReport:
    """Run the full Documentation Sync & Drift Detection pipeline.

    Parameters
    ----------
    repo_name:
        Name of the repository folder inside ``workspace/``.

    Returns
    -------
    :class:`DriftReport` with the complete drift analysis.

    Raises
    ------
    FileNotFoundError
        When ``workspace/<repo_name>`` does not exist.
    """
    repo_path = _WORKSPACE_DIR / repo_name
    if not repo_path.exists():
        raise FileNotFoundError(
            f"Repository '{repo_name}' not found in workspace at {repo_path}"
        )

    # ------------------------------------------------------------------
    # Step 1: Parse README (Document Understanding)
    # ------------------------------------------------------------------
    readme_path = repo_path / "README.md"
    documented_paths, documented_params = _parse_readme(readme_path)

    # ------------------------------------------------------------------
    # Step 2: AST extraction
    # ------------------------------------------------------------------
    kg = parse_repo(str(repo_path))
    code_endpoints = _collect_endpoints(kg)
    code_functions = _collect_functions(kg)

    # ------------------------------------------------------------------
    # Step 3: Drift detection
    # ------------------------------------------------------------------
    undocumented = _find_undocumented_endpoints(code_endpoints, documented_paths)
    missing_ds = _find_missing_docstrings(code_functions)
    stale = _find_stale_parameters(code_endpoints, code_functions, documented_params)

    # ------------------------------------------------------------------
    # Step 4: Drift score
    # ------------------------------------------------------------------
    drift_score = _calculate_drift_score(
        total_endpoints=len(code_endpoints),
        undocumented_endpoints=len(undocumented),
        total_functions=len(code_functions),
        missing_docstrings=len(missing_ds),
        stale_params_count=len(stale),
    )

    # ------------------------------------------------------------------
    # Step 5: Markdown suggestions (+ optional watsonx enrichment)
    # ------------------------------------------------------------------
    raw_suggestions = _build_markdown_suggestions(undocumented, missing_ds, stale)

    watsonx_used = False
    context = (
        f"Repository: {repo_name}. "
        f"Total endpoints: {len(code_endpoints)}. "
        f"Total functions: {len(code_functions)}."
    )
    enriched = _enrich_with_watsonx(raw_suggestions, context)
    if enriched is not raw_suggestions:
        watsonx_used = True

    return DriftReport(
        repo_name=repo_name,
        drift_score=drift_score,
        undocumented_endpoints=undocumented,
        missing_docstrings=missing_ds,
        stale_parameters=stale,
        documented_endpoints=sorted(documented_paths),
        total_endpoints=len(code_endpoints),
        total_functions=len(code_functions),
        markdown_suggestions=enriched,
        watsonx_used=watsonx_used,
    )
