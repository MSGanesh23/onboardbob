"""
git_service.py – GitHub repository and issue utilities for OnboardBob.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from textwrap import dedent
from typing import Any

import requests

# Root directory where repositories are cloned.
WORKSPACE_ROOT = Path(__file__).resolve().parents[2] / "workspace"


# ---------------------------------------------------------------------------
# clone_github_repo
# ---------------------------------------------------------------------------

def clone_github_repo(repo_url: str) -> Path:
    """Clone a public GitHub repository into ``workspace/<repo_name>/``.

    If the target directory already exists the clone is skipped and the
    existing path is returned (idempotent).

    Args:
        repo_url: HTTPS or SSH URL of the repository, e.g.
            ``https://github.com/owner/repo.git``

    Returns:
        Absolute :class:`~pathlib.Path` to the cloned repository root.

    Raises:
        ValueError: If *repo_url* does not look like a GitHub URL.
        subprocess.CalledProcessError: If ``git clone`` exits non-zero.
    """
    if not re.search(r"(?:^|[@/])github\.com[:/].+/.+", repo_url):
        raise ValueError(f"Not a recognisable GitHub URL: {repo_url!r}")

    # Derive a clean directory name from the URL.
    repo_name = re.split(r"[/:]", repo_url.rstrip("/").rstrip(".git"))[-1]
    repo_name = repo_name.removesuffix(".git")
    target_dir = WORKSPACE_ROOT / repo_name

    if target_dir.exists():
        return target_dir

    WORKSPACE_ROOT.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["git", "clone", "--depth", "1", repo_url, str(target_dir)],
        check=True,
        capture_output=True,
        text=True,
    )
    return target_dir


# ---------------------------------------------------------------------------
# fetch_github_issue
# ---------------------------------------------------------------------------

def fetch_github_issue(issue_url: str) -> dict[str, Any]:
    """Fetch a GitHub issue's title and body via the REST API.

    Args:
        issue_url: Full HTML URL of the issue, e.g.
            ``https://github.com/owner/repo/issues/42``

    Returns:
        Dictionary with keys ``number``, ``title``, ``body``, ``url``,
        ``state``, ``labels``.

    Raises:
        ValueError: If *issue_url* cannot be parsed into owner/repo/number.
        requests.HTTPError: If the GitHub API returns a non-2xx status.
    """
    match = re.search(
        r"github\.com/(?P<owner>[^/]+)/(?P<repo>[^/]+)/issues/(?P<number>\d+)",
        issue_url,
    )
    if not match:
        raise ValueError(f"Cannot parse GitHub issue URL: {issue_url!r}")

    owner, repo, number = match["owner"], match["repo"], match["number"]
    api_url = f"https://api.github.com/repos/{owner}/{repo}/issues/{number}"

    response = requests.get(
        api_url,
        headers={"Accept": "application/vnd.github+json"},
        timeout=15,
    )
    response.raise_for_status()
    data: dict[str, Any] = response.json()

    return {
        "number": data.get("number"),
        "title": data.get("title", ""),
        "body": data.get("body", ""),
        "url": data.get("html_url", issue_url),
        "state": data.get("state", ""),
        "labels": [lbl["name"] for lbl in data.get("labels", [])],
    }


# ---------------------------------------------------------------------------
# create_github_pr_branch
# ---------------------------------------------------------------------------

def create_github_pr_branch(
    repo_path: str | Path,
    branch_name: str,
    commit_msg: str,
) -> dict[str, str]:
    """Create a branch in *repo_path*, stage all changes, commit, and return
    a formatted markdown PR description.

    Args:
        repo_path: Filesystem path to the cloned repository root.
        branch_name: Name for the new git branch.
        commit_msg: Commit message used for the staged changes.

    Returns:
        Dictionary with keys ``branch``, ``commit_msg``, and
        ``pr_description`` (a ready-to-paste markdown string).

    Raises:
        subprocess.CalledProcessError: If any git command exits non-zero.
    """
    repo_path = Path(repo_path)

    def _git(*args: str) -> str:
        result = subprocess.run(
            ["git", "-C", str(repo_path), *args],
            check=True,
            capture_output=True,
            text=True,
        )
        return result.stdout.strip()

    # Create and switch to the new branch.
    _git("checkout", "-b", branch_name)

    # Stage every modification in the working tree.
    _git("add", "--all")

    # Only commit when there is something staged.
    status = _git("status", "--porcelain")
    if status:
        _git("commit", "-m", commit_msg)

    pr_description = dedent(f"""\
        ## Summary

        {commit_msg}

        ## Branch

        `{branch_name}`

        ## Changes

        ```
        {status or "No file changes detected."}
        ```

        ## Checklist

        - [ ] Tests pass
        - [ ] Documentation updated
        - [ ] Reviewed by a peer
    """)

    return {
        "branch": branch_name,
        "commit_msg": commit_msg,
        "pr_description": pr_description,
    }
