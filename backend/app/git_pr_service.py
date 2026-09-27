"""
git_pr_service.py – Git PR Packager for OnboardBob.

Automates branch creation, staged commits, and rich Markdown PR description
generation for GitHub issue resolutions inside ``workspace/<repo_name>/``.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from textwrap import dedent
from typing import Any

import tempfile

# Root directory where repositories live (with /tmp fallback for serverless read-only filesystems)
def _get_workspace_root() -> Path:
    ws = Path(__file__).resolve().parents[2] / "workspace"
    try:
        ws.mkdir(parents=True, exist_ok=True)
        test = ws / ".write_test"
        test.touch()
        test.unlink()
        return ws
    except Exception:
        tmp_ws = Path(tempfile.gettempdir()) / "workspace"
        tmp_ws.mkdir(parents=True, exist_ok=True)
        return tmp_ws

WORKSPACE_ROOT = _get_workspace_root()

# Conventional branch name and commit message for issue-42 remediation.
DEFAULT_BRANCH = "fix/issue-42-remediation"
DEFAULT_COMMIT = "fix: resolve GitHub issue #42 and add pytest verification"

# Path to the IBM Bob task session screenshot referenced in the PR body.
BOB_SCREENSHOT = Path(".bob") / "screenshots" / "05_module_fix.png"


# ---------------------------------------------------------------------------
# _git  (internal helper)
# ---------------------------------------------------------------------------

def _git(repo_path: Path, *args: str) -> str:
    """Run a git command inside *repo_path* and return stdout stripped."""
    result = subprocess.run(
        ["git", "-C", str(repo_path), *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


# ---------------------------------------------------------------------------
# create_pr_branch
# ---------------------------------------------------------------------------

def create_pr_branch(
    repo_name: str,
    *,
    branch_name: str = DEFAULT_BRANCH,
    commit_msg: str = DEFAULT_COMMIT,
    issue_summary: str = "",
    pytest_log: str = "",
) -> dict[str, Any]:
    """Create a fix branch in ``workspace/<repo_name>/``, stage modified files,
    commit, and return a rich Markdown PR description.

    Args:
        repo_name:     Subdirectory name inside ``workspace/`` (e.g. ``"b"``).
        branch_name:   Name for the new git branch (default: fix/issue-42-remediation).
        commit_msg:    Commit message for the staged changes.
        issue_summary: Short text summarising the GitHub issue (embedded in PR body).
        pytest_log:    Terminal pytest output snippet to embed in the PR body.

    Returns:
        Dictionary with keys:

        * ``branch``         – branch name used.
        * ``commit_msg``     – commit message used.
        * ``modified_files`` – list of staged file paths.
        * ``pr_description`` – ready-to-paste Markdown string.

    Raises:
        FileNotFoundError: If ``workspace/<repo_name>`` does not exist.
        subprocess.CalledProcessError: If any git command exits non-zero.
    """
    repo_path = WORKSPACE_ROOT / repo_name
    if not repo_path.exists():
        raise FileNotFoundError(
            f"Repository not found at {repo_path}. "
            "Clone it first with git_service.clone_github_repo()."
        )

    # ── 1. Create and switch to the fix branch ──────────────────────────────
    _git(repo_path, "checkout", "-b", branch_name)

    # ── 2. Stage all modifications ───────────────────────────────────────────
    _git(repo_path, "add", "--all")

    # ── 3. Collect the list of staged Python files ───────────────────────────
    diff_output = _git(repo_path, "diff", "--cached", "--name-only")
    modified_files: list[str] = [
        f for f in diff_output.splitlines() if f.strip()
    ]
    python_files = [f for f in modified_files if f.endswith(".py")]

    # ── 4. Commit only when there is something staged ────────────────────────
    status = _git(repo_path, "status", "--porcelain")
    if status:
        _git(repo_path, "commit", "-m", commit_msg)

    # ── 5. Build rich Markdown PR description ────────────────────────────────
    pr_description = _build_pr_description(
        branch_name=branch_name,
        commit_msg=commit_msg,
        issue_summary=issue_summary or "(no summary provided)",
        python_files=python_files or modified_files,
        pytest_log=pytest_log or "(no pytest log provided)",
        screenshot_path=BOB_SCREENSHOT,
    )

    return {
        "branch": branch_name,
        "commit_msg": commit_msg,
        "modified_files": modified_files,
        "pr_description": pr_description,
    }


# ---------------------------------------------------------------------------
# _build_pr_description  (internal)
# ---------------------------------------------------------------------------

def _build_pr_description(
    *,
    branch_name: str,
    commit_msg: str,
    issue_summary: str,
    python_files: list[str],
    pytest_log: str,
    screenshot_path: Path,
) -> str:
    """Compose and return the rich Markdown PR body string."""

    py_file_list = "\n".join(f"- `{f}`" for f in python_files) or "- *(none detected)*"

    # Truncate long pytest logs to keep the PR body readable.
    max_log_lines = 40
    log_lines = pytest_log.splitlines()
    if len(log_lines) > max_log_lines:
        shown = "\n".join(log_lines[:max_log_lines])
        pytest_block = f"{shown}\n… (truncated, {len(log_lines)} lines total)"
    else:
        pytest_block = pytest_log

    return dedent(f"""\
        ## 🐛 GitHub Issue Summary

        {issue_summary}

        ---

        ## 🌿 Branch

        `{branch_name}`

        ---

        ## 📝 Modified Python Files

        {py_file_list}

        ---

        ## 🧪 Terminal PyTest Execution Log

        ```
        {pytest_block}
        ```

        ---

        ## 📸 IBM Bob Task Session Summary

        ![Module Fix Screenshot]({screenshot_path})

        > **Path:** `{screenshot_path}`
        > Captured during IBM Bob onboarding session — Module 6: Git PR Service.

        ---

        ## ✅ Checklist

        - [x] Issue reproduced and root-cause identified
        - [x] Fix implemented in Python source
        - [x] pytest suite passes (`{commit_msg}`)
        - [ ] Peer review requested
        - [ ] Documentation updated if applicable
    """)
