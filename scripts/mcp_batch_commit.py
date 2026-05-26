"""Un commit en GitHub con varios archivos (API Trees). Usa GITHUB_TOKEN del entorno."""

from __future__ import annotations

import base64
import json
import os
import subprocess
import sys
from pathlib import Path

from urllib.request import Request, urlopen

OWNER = "KevinQuishpe99"
REPO = "Automitizacion_HBI_Capital"
BRANCH = "main"
MESSAGE = "feat: migrar endpoints pesados a Vercel Workflow (job runner)"


def api(method: str, url: str, token: str, body: dict | None = None) -> dict:
    data = None
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = Request(url, data=data, headers=headers, method=method)
    with urlopen(req) as resp:
        return json.loads(resp.read().decode())


def git_paths() -> list[str]:
    out = subprocess.check_output(
        ["git", "diff", "--name-only", "HEAD"],
        text=True,
        cwd=Path(__file__).resolve().parents[1],
    )
    untracked = subprocess.check_output(
        ["git", "ls-files", "--others", "--exclude-standard"],
        text=True,
        cwd=Path(__file__).resolve().parents[1],
    )
    paths = {p.strip() for p in (out + "\n" + untracked).splitlines() if p.strip()}
    return sorted(paths)


def main() -> None:
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        print("GITHUB_TOKEN requerido", file=sys.stderr)
        sys.exit(1)
    root = Path(__file__).resolve().parents[1]
    paths = git_paths()
    if not paths:
        print("Sin cambios para commitear")
        return

    ref = api("GET", f"https://api.github.com/repos/{OWNER}/{REPO}/git/ref/heads/{BRANCH}", token)
    base_sha = ref["object"]["sha"]
    base_commit = api(
        "GET", f"https://api.github.com/repos/{OWNER}/{REPO}/git/commits/{base_sha}", token
    )
    base_tree_sha = base_commit["tree"]["sha"]

    tree_entries = []
    for rel in paths:
        full = root / rel
        if not full.is_file():
            continue
        content_b64 = base64.b64encode(full.read_bytes()).decode("ascii")
        blob = api(
            "POST",
            f"https://api.github.com/repos/{OWNER}/{REPO}/git/blobs",
            token,
            {"content": content_b64, "encoding": "base64"},
        )
        tree_entries.append(
            {"path": rel.replace("\\", "/"), "mode": "100644", "type": "blob", "sha": blob["sha"]}
        )

    tree = api(
        "POST",
        f"https://api.github.com/repos/{OWNER}/{REPO}/git/trees",
        token,
        {"base_tree": base_tree_sha, "tree": tree_entries},
    )
    commit = api(
        "POST",
        f"https://api.github.com/repos/{OWNER}/{REPO}/git/commits",
        token,
        {"message": MESSAGE, "tree": tree["sha"], "parents": [base_sha]},
    )
    api(
        "PATCH",
        f"https://api.github.com/repos/{OWNER}/{REPO}/git/refs/heads/{BRANCH}",
        token,
        {"sha": commit["sha"], "force": False},
    )
    print(f"OK {len(tree_entries)} archivos → {commit['html_url']}")


if __name__ == "__main__":
    main()
