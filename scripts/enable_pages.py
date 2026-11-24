"""Enable GitHub Pages for this repository and trigger the deployment.

The ``deploy-pages`` workflow can only publish once Pages exists. Creating the
Pages site needs a token with admin rights, which the workflow's GITHUB_TOKEN
does not have on a personal repository, so this helper does it explicitly.

Usage:
    # 1. create a fine-grained PAT with "Administration" (read/write) on the repo
    #    (or a classic token with the "repo" scope)
    # 2. run:
    set GITHUB_TOKEN=ghp_xxx            # PowerShell: $env:GITHUB_TOKEN="ghp_xxx"
    python scripts/enable_pages.py

After the site exists, every push to ``main`` that touches ``frontend/**``
redeploys automatically; no token is needed again.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request

API = "https://api.github.com"
WORKFLOW_FILE = "deploy-pages.yml"


def request(method: str, url: str, token: str, payload: dict | None = None) -> tuple[int, dict]:
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    req.add_header("User-Agent", "PocketScore-EnablePages/1.0")
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            body = response.read().decode() or "{}"
            return response.status, json.loads(body) if body.strip() else {}
    except urllib.error.HTTPError as exc:
        body = exc.read().decode() or "{}"
        try:
            return exc.code, json.loads(body)
        except ValueError:
            return exc.code, {"raw": body[:400]}


def main() -> int:
    parser = argparse.ArgumentParser(description="Enable GitHub Pages and deploy")
    parser.add_argument("--repo", default="engernages-lab/03", help="owner/repo")
    parser.add_argument("--branch", default="main", help="branch that Pages builds from")
    parser.add_argument("--token", default=os.environ.get("GITHUB_TOKEN", ""), help="PAT (default: $GITHUB_TOKEN)")
    parser.add_argument("--wait", action="store_true", help="poll the deployment run until it finishes")
    args = parser.parse_args()

    if not args.token:
        print("GITHUB_TOKEN is required (fine-grained PAT with Administration: write, or classic 'repo' scope).")
        return 2

    base = f"{API}/repos/{args.repo}"

    status, pages = request("GET", f"{base}/pages", args.token)
    if status == 200:
        print(f"Pages already enabled -> {pages.get('html_url')}")
    else:
        print("Enabling Pages (build_type=workflow) ...")
        status, body = request(
            "POST",
            f"{base}/pages",
            args.token,
            {"build_type": "workflow", "source": {"branch": args.branch, "path": "/"}},
        )
        if status not in (201, 409):
            print(f"  failed: HTTP {status} {json.dumps(body, ensure_ascii=False)[:400]}")
            if status == 403:
                print("  -> the token needs Administration: write on this repository.")
            return 1
        status, pages = request("GET", f"{base}/pages", args.token)
        print(f"  enabled -> {pages.get('html_url')}")

    print("Triggering the deploy workflow ...")
    status, run = request(
        "POST",
        f"{base}/actions/workflows/{WORKFLOW_FILE}/dispatches",
        args.token,
        {"ref": args.branch},
    )
    if status not in (204, 200):
        print(f"  dispatch failed: HTTP {status} {json.dumps(run, ensure_ascii=False)[:300]}")
        return 1

    url = pages.get("html_url") or f"https://{args.repo.split('/')[0]}.github.io/{args.repo.split('/')[1]}/"
    print(f"  dispatched. Site will appear at: {url}")

    if not args.wait:
        return 0

    print("Waiting for the run to finish (up to 5 minutes) ...")
    deadline = time.time() + 300
    while time.time() < deadline:
        time.sleep(10)
        status, runs = request(
            "GET", f"{base}/actions/workflows/{WORKFLOW_FILE}/runs?per_page=1", args.token
        )
        if status != 200 or not runs.get("workflow_runs"):
            continue
        latest = runs["workflow_runs"][0]
        print(f"  {latest['status']} / {latest.get('conclusion')}")
        if latest["status"] == "completed":
            ok = latest.get("conclusion") == "success"
            print("RESULT:", "PASS" if ok else "FAIL")
            return 0 if ok else 1
    print("RESULT: TIMEOUT")
    return 1


if __name__ == "__main__":
    sys.exit(main())
