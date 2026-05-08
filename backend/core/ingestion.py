import os
import shutil
import hashlib
import re
import zipfile
import io
import urllib.request
import urllib.error
from pathlib import Path
from typing import List, Dict, Any
from core.config import get_settings

settings = get_settings()

SUPPORTED_EXTENSIONS = {
    ".py", ".js", ".ts", ".jsx", ".tsx", ".java", ".cpp", ".c", ".h",
    ".go", ".rs", ".rb", ".php", ".cs", ".swift", ".kt", ".scala",
    ".html", ".css", ".scss", ".json", ".yaml", ".yml", ".toml",
    ".md", ".sh", ".bash", ".sql", ".graphql"
}

IGNORE_DIRS = {
    "node_modules", ".git", "__pycache__", ".pytest_cache", "dist",
    "build", ".next", "venv", "env", ".venv", "coverage", ".nyc_output",
    "target", "vendor", ".idea", ".vscode",
}


def get_repo_id(github_url: str) -> str:
    clean = github_url.rstrip("/").lower()
    return hashlib.md5(clean.encode()).hexdigest()[:12]


def parse_github_url(url: str) -> Dict[str, str]:
    patterns = [
        r"github\.com[:/]([^/]+)/([^/\.]+?)(?:\.git)?/?$",
        r"github\.com/([^/]+)/([^/]+?)/?$",
    ]
    for pat in patterns:
        m = re.search(pat, url)
        if m:
            return {"owner": m.group(1), "repo": m.group(2)}
    raise ValueError(f"Cannot parse GitHub URL: {url}")


def _download_zip(owner: str, repo: str, branch: str = "main") -> bytes:
    """Download repo ZIP from GitHub. Tries main then master branch."""
    for b in [branch, "master", "main"]:
        zip_url = f"https://github.com/{owner}/{repo}/archive/refs/heads/{b}.zip"
        try:
            req = urllib.request.Request(
                zip_url,
                headers={"User-Agent": "github-intel-tool/1.0"}
            )
            with urllib.request.urlopen(req, timeout=60) as resp:
                return resp.read()
        except urllib.error.HTTPError:
            continue
    raise ValueError(f"Could not download ZIP for {owner}/{repo}. Check the URL.")


def clone_repository(github_url: str) -> Dict[str, Any]:
    """Download repo as ZIP and extract. No git executable needed."""
    os.makedirs(settings.repos_dir, exist_ok=True)
    repo_id = get_repo_id(github_url)
    info = parse_github_url(github_url)
    owner, repo = info["owner"], info["repo"]
    extract_path = Path(settings.repos_dir) / repo_id

    status = "cached"
    if not extract_path.exists():
        zip_bytes = _download_zip(owner, repo)
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            zf.extractall(Path(settings.repos_dir) / f"{repo_id}_tmp")

        # GitHub ZIP contains a top-level folder like "repo-main/"
        tmp_root = Path(settings.repos_dir) / f"{repo_id}_tmp"
        inner_dirs = [d for d in tmp_root.iterdir() if d.is_dir()]
        if inner_dirs:
            shutil.move(str(inner_dirs[0]), str(extract_path))
        shutil.rmtree(tmp_root, ignore_errors=True)
        status = "downloaded"

    return {
        "repo_id": repo_id,
        "owner": owner,
        "repo": repo,
        "clone_path": str(extract_path),
        "status": status,
    }


def walk_files(clone_path: str) -> List[Dict[str, Any]]:
    root = Path(clone_path)
    files = []

    for path in root.rglob("*"):
        if any(ig in path.parts for ig in IGNORE_DIRS):
            continue
        if not path.is_file():
            continue
        if path.suffix not in SUPPORTED_EXTENSIONS:
            continue
        size_kb = path.stat().st_size / 1024
        if size_kb > settings.max_file_size_kb:
            continue
        try:
            content = path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue

        rel_path = str(path.relative_to(root))
        files.append({
            "path": rel_path,
            "abs_path": str(path),
            "extension": path.suffix,
            "size_kb": round(size_kb, 2),
            "content": content,
            "lines": content.splitlines(),
        })

    return files