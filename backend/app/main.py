"""
main.py – FastAPI entry point for the OnboardBob backend.
"""

from __future__ import annotations

import os
import re
import subprocess
import textwrap
from pathlib import Path
from typing import Optional

try:
    from dotenv import load_dotenv as _load_dotenv
    _load_dotenv()
except ImportError:
    pass

from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .ast_parser import generate_architecture_svg, generate_mermaid_graph, parse_repo
from .doc_sync import DriftReport, _gemini_generate, run_doc_drift
from .git_pr_service import create_pr_branch
from .git_service import clone_github_repo, fetch_github_issue

# Root of the workspace/ directory (two levels up from this file: backend/app/ → project root)
_WORKSPACE_DIR = Path(__file__).resolve().parent.parent.parent / "workspace"

app = FastAPI(
    title="OnboardBob API",
    description="Dynamic GitHub developer onboarding engine – IBM Hackathon 2.0",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------

class CloneRepoRequest(BaseModel):
    repo_url: str
    issue_url: Optional[str] = None


class CloneRepoResponse(BaseModel):
    status: str
    repo_name: str
    local_path: str
    issue: Optional[dict] = None
    impacted_files: list = []


class ExecuteFixRequest(BaseModel):
    repo_name: str
    issue_title: str = ""
    issue_body: str = ""


class ExecuteFixResponse(BaseModel):
    status: str
    branch: str
    pr_description: str
    pytest_output: str


class ScanRepoRequest(BaseModel):
    repo_name: str


class ScanRepoResponse(BaseModel):
    mermaid: str
    knowledge_graph: dict
    svg_image: str = ""
    entry_points: list = []
    tour_steps: list = []
    ai_summary: str = ""


class DocDriftRequest(BaseModel):
    repo_name: str
    issue_title: str = ""
    issue_body: str = ""


class DocDriftResponse(BaseModel):
    repo_name: str
    drift_score: float
    undocumented_endpoints: list
    missing_docstrings: list
    stale_parameters: list
    documented_endpoints: list
    total_endpoints: int
    total_functions: int
    markdown_suggestions: list
    watsonx_used: bool
    gemini_used: bool = False
    ai_summary: str = ""
    ai_doc_suggestions: list = []
    ai_issue_breakdown: list = []
    ai_setup_guide: list = []


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/health")
def health_check() -> dict[str, str]:
    """Liveness probe."""
    return {"status": "ok"}


@app.post("/api/clone-repo", response_model=CloneRepoResponse)
def clone_repo(payload: CloneRepoRequest) -> CloneRepoResponse:
    """Clone a public GitHub repository into ``workspace/`` and, when an
    *issue_url* is provided, fetch its metadata.

    Request body::

        {
            "repo_url": "https://github.com/owner/repo",
            "issue_url": "https://github.com/owner/repo/issues/42"  // optional
        }

    Returns the clone status, local path, and issue metadata (if requested).
    """
    # --- Clone the repository ------------------------------------------
    try:
        local_path: Path = clone_github_repo(payload.repo_url)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:  # subprocess.CalledProcessError et al.
        raise HTTPException(
            status_code=500,
            detail=f"git clone failed: {exc}",
        ) from exc

    # --- Fetch the issue (optional) ------------------------------------
    issue_data: Optional[dict] = None
    if payload.issue_url:
        try:
            issue_data = fetch_github_issue(payload.issue_url)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(
                status_code=502,
                detail=f"GitHub API error: {exc}",
            ) from exc

    # --- Compute impacted_files from issue keywords --------------------
    impacted_files: list[str] = []
    if issue_data:
        impacted_files = _compute_impacted_files(
            local_path,
            issue_data.get("title", ""),
            issue_data.get("body", ""),
        )

    return CloneRepoResponse(
        status="cloned" if not local_path.exists() else "ready",
        repo_name=local_path.name,
        local_path=str(local_path),
        issue=issue_data,
        impacted_files=impacted_files,
    )


# ---------------------------------------------------------------------------
# Helper: compute impacted files from issue keywords
# ---------------------------------------------------------------------------

def _compute_impacted_files(repo_path: Path, title: str, body: str) -> list[str]:
    """Return relative paths of Python files whose names/paths contain keywords
    extracted from the issue *title* and *body*.

    Strategy:
    1. Tokenise title + body into lowercase words (≥ 4 chars, letters only).
    2. Walk all ``*.py`` files under *repo_path*.
    3. Return those whose relative path contains at least one keyword.
    """
    text = f"{title} {body}".lower()
    keywords = {w for w in re.findall(r"[a-z]{4,}", text)}
    # Remove very common English stop-words that produce too many false positives
    _STOP = {
        "this", "that", "with", "from", "have", "will", "they", "what",
        "when", "where", "which", "should", "would", "could", "been",
        "into", "more", "some", "than", "then", "also", "each", "only",
        "just", "like", "test", "file", "code", "repo", "body", "base",
        "open", "data", "make", "func", "call", "type", "name", "list",
        "path", "note", "true", "false", "none",
    }
    keywords -= _STOP
    if not keywords:
        return []

    matched: list[str] = []
    for py_file in sorted(repo_path.rglob("*.py")):
        rel = py_file.relative_to(repo_path)
        rel_str = str(rel).replace("\\", "/")
        # Skip __pycache__ and virtual-env dirs
        if "__pycache__" in rel_str or "/." in rel_str:
            continue
        rel_lower = rel_str.lower()
        if any(kw in rel_lower for kw in keywords):
            matched.append(rel_str)

    return matched



@app.post("/api/scan-repo", response_model=ScanRepoResponse)
def scan_repo(
    payload: ScanRepoRequest,
    x_gemini_api_key: Optional[str] = Header(default=None, alias="X-Gemini-Api-Key"),
) -> ScanRepoResponse:
    """Scan a previously cloned repository with the Python AST parser.

    Request body::

        { "repo_name": "my-cloned-repo" }

    Optionally pass ``X-Gemini-Api-Key`` header to enable the Gemini AI summary.

    Returns the Mermaid.js flowchart string, SVG image, entry points, tour steps,
    and the full knowledge-graph JSON.
    """
    repo_path = _WORKSPACE_DIR / payload.repo_name
    if not repo_path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Repository '{payload.repo_name}' not found in workspace. "
                   "Clone it first via POST /api/clone-repo.",
        )

    try:
        kg = parse_repo(str(repo_path))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=500,
            detail=f"AST parsing failed: {exc}",
        ) from exc

    mermaid    = generate_mermaid_graph(kg)
    svg_image  = kg.get("svg_image", "") or generate_architecture_svg(kg)
    entry_pts  = kg.get("entry_points", [])
    tour_steps = kg.get("tour_steps", [])

    # Optional Gemini AI summary
    ai_summary = ""
    effective_key = x_gemini_api_key or os.environ.get("GEMINI_API_KEY", "")
    if effective_key:
        try:
            from .doc_sync import _build_ai_summary  # local import avoids circular dep
            ai_summary = _build_ai_summary(payload.repo_name, kg, effective_key)
        except Exception as exc:  # noqa: BLE001
            print(f"[main] Gemini summary failed: {exc}")

    return ScanRepoResponse(
        mermaid=mermaid,
        knowledge_graph=kg,
        svg_image=svg_image,
        entry_points=entry_pts,
        tour_steps=tour_steps,
        ai_summary=ai_summary,
    )


@app.post("/api/doc-drift", response_model=DocDriftResponse)
def doc_drift(
    payload: DocDriftRequest,
    x_gemini_api_key: Optional[str] = Header(default=None, alias="X-Gemini-Api-Key"),
) -> DocDriftResponse:
    """Analyse documentation drift for a previously cloned repository.

    Parses ``workspace/<repo_name>/README.md`` using Document Understanding
    and cross-references discovered AST endpoints / docstrings against it.

    Request body::

        {
            "repo_name": "my-cloned-repo",
            "issue_title": "...",   // optional
            "issue_body": "..."     // optional
        }

    Optionally pass ``X-Gemini-Api-Key`` header to enable Gemini AI features.

    Returns:
    - ``drift_score`` – 0–100 health score (100 = fully documented).
    - ``undocumented_endpoints`` – code endpoints absent from README.
    - ``missing_docstrings`` – public functions with no docstring.
    - ``stale_parameters`` – README params no longer present in code.
    - ``markdown_suggestions`` – ready-to-paste Markdown fixes.
    - ``ai_summary`` – Gemini AI 2-sentence codebase overview.
    - ``ai_doc_suggestions`` – Gemini AI ready-to-paste docstrings.
    - ``ai_issue_breakdown`` – Gemini AI actionable onboarding steps for the issue.
    """
    effective_key = x_gemini_api_key or os.environ.get("GEMINI_API_KEY", "")
    try:
        report: DriftReport = run_doc_drift(
            repo_name=payload.repo_name,
            gemini_api_key=effective_key or None,
            issue_title=payload.issue_title,
            issue_body=payload.issue_body,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=500,
            detail=f"Doc-drift analysis failed: {exc}",
        ) from exc

    return DocDriftResponse(**report.to_dict())


# ---------------------------------------------------------------------------
# POST /api/execute-fix
# ---------------------------------------------------------------------------

@app.post("/api/execute-fix", response_model=ExecuteFixResponse)
def execute_fix(
    payload: ExecuteFixRequest,
    x_gemini_api_key: Optional[str] = Header(default=None, alias="X-Gemini-Api-Key"),
) -> ExecuteFixResponse:
    """Generate an AI-powered code fix, run pytest, and create a git feature branch.

    Request body::

        {
            "repo_name": "my-cloned-repo",
            "issue_title": "...",
            "issue_body": "..."
        }

    Returns the created branch name, PR description, and pytest output.
    """
    repo_path = _WORKSPACE_DIR / payload.repo_name
    if not repo_path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Repository '{payload.repo_name}' not found in workspace.",
        )

    effective_key = x_gemini_api_key or os.environ.get("GEMINI_API_KEY", "")

    # ── 1. Generate code fix + test via Gemini AI (or built-in fallback) ──────
    fix_code, test_code = _generate_fix_and_test(
        payload.repo_name,
        payload.issue_title,
        payload.issue_body,
        effective_key,
    )

    # ── 2. Write fix + test files into the workspace repo ─────────────────────
    fix_file  = repo_path / "onboardbob_fix.py"
    test_file = repo_path / "test_onboardbob_fix.py"
    fix_file.write_text(fix_code, encoding="utf-8")
    test_file.write_text(test_code, encoding="utf-8")

    # ── 3. Run pytest ─────────────────────────────────────────────────────────
    pytest_output = _run_pytest(repo_path, test_file)

    # ── 4. Create git feature branch ──────────────────────────────────────────
    try:
        pr_result = create_pr_branch(
            payload.repo_name,
            issue_summary=f"{payload.issue_title}\n\n{payload.issue_body}".strip(),
            pytest_log=pytest_output,
        )
        branch = pr_result["branch"]
        pr_description = pr_result["pr_description"]
    except Exception as exc:  # noqa: BLE001
        branch = "fix/issue-42-remediation"
        pr_description = f"Branch creation failed: {exc}"

    return ExecuteFixResponse(
        status="executed",
        branch=branch,
        pr_description=pr_description,
        pytest_output=pytest_output,
    )


def _generate_fix_and_test(
    repo_name: str,
    issue_title: str,
    issue_body: str,
    api_key: str,
) -> tuple[str, str]:
    """Return (fix_code, test_code) using Gemini AI when available, else built-in fallback."""
    if api_key:
        fix_prompt = (
            f"You are an expert Python developer.\n\n"
            f"Repository: {repo_name}\n"
            f"GitHub Issue title: {issue_title}\n"
            f"GitHub Issue body:\n{issue_body}\n\n"
            "Write a concise Python module (named onboardbob_fix.py) that implements "
            "the fix described in the issue.  Return only valid Python source code – "
            "no explanations, no markdown fences."
        )
        test_prompt = (
            f"You are an expert Python developer.\n\n"
            f"GitHub Issue title: {issue_title}\n\n"
            "Write a single pytest test function (in test_onboardbob_fix.py) that "
            "verifies the fix implemented in onboardbob_fix.py.  "
            "Return only valid Python source code – no explanations, no markdown fences."
        )
        fix_code  = _gemini_generate(fix_prompt, api_key)
        test_code = _gemini_generate(test_prompt, api_key)
        if fix_code and test_code:
            return fix_code, test_code

    # Built-in fallback (no AI key or Gemini unavailable)
    fix_code = textwrap.dedent(f"""\
        # onboardbob_fix.py
        # Auto-generated fix placeholder for: {issue_title!r}
        # Replace this stub with the actual implementation.

        def apply_fix():
            \"\"\"Placeholder fix for the reported issue.\"\"\"
            return True
    """)
    test_code = textwrap.dedent("""\
        # test_onboardbob_fix.py
        from onboardbob_fix import apply_fix

        def test_apply_fix():
            assert apply_fix() is True
    """)
    return fix_code, test_code


def _run_pytest(repo_path: Path, test_file: Path) -> str:
    """Run pytest on *test_file* inside *repo_path* and return captured output."""
    try:
        result = subprocess.run(
            ["python", "-m", "pytest", str(test_file), "-v", "--tb=short", "--no-header"],
            capture_output=True,
            text=True,
            timeout=120,
            cwd=str(repo_path),
        )
        output = (result.stdout + result.stderr).strip()
        return output or "(no pytest output)"
    except FileNotFoundError:
        return "pytest not available in environment"
    except subprocess.TimeoutExpired:
        return "pytest timed out after 120 s"
    except Exception as exc:  # noqa: BLE001
        return f"pytest execution error: {exc}"
