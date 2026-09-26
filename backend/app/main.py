"""
main.py – FastAPI entry point for the OnboardBob backend.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, HttpUrl

from .ast_parser import generate_mermaid_graph, parse_repo
from .doc_sync import DriftReport, run_doc_drift
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


class ScanRepoRequest(BaseModel):
    repo_name: str


class ScanRepoResponse(BaseModel):
    mermaid: str
    knowledge_graph: dict


class DocDriftRequest(BaseModel):
    repo_name: str


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

    return CloneRepoResponse(
        status="cloned" if not local_path.exists() else "ready",
        repo_name=local_path.name,
        local_path=str(local_path),
        issue=issue_data,
    )


@app.post("/api/doc-drift", response_model=DocDriftResponse)
def doc_drift(payload: DocDriftRequest) -> DocDriftResponse:
    """Analyse documentation drift for a previously cloned repository.

    Parses ``workspace/<repo_name>/README.md`` using Document Understanding
    and cross-references discovered AST endpoints / docstrings against it.

    Request body::

        { "repo_name": "my-cloned-repo" }

    Returns:
    - ``drift_score`` – 0–100 health score (100 = fully documented).
    - ``undocumented_endpoints`` – code endpoints absent from README.
    - ``missing_docstrings`` – public functions with no docstring.
    - ``stale_parameters`` – README params no longer present in code.
    - ``markdown_suggestions`` – ready-to-paste Markdown fixes.
    """
    try:
        report: DriftReport = run_doc_drift(payload.repo_name)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=500,
            detail=f"Doc-drift analysis failed: {exc}",
        ) from exc

    return DocDriftResponse(**report.to_dict())


@app.post("/api/scan-repo", response_model=ScanRepoResponse)
def scan_repo(payload: ScanRepoRequest) -> ScanRepoResponse:
    """Scan a previously cloned repository with the Python AST parser.

    Request body::

        { "repo_name": "my-cloned-repo" }

    Returns the Mermaid.js flowchart string and the full knowledge-graph JSON.
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

    mermaid = generate_mermaid_graph(kg)
    return ScanRepoResponse(mermaid=mermaid, knowledge_graph=kg)
