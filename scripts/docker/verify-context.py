#!/usr/bin/env python3
"""Fail fast when a Dockerfile COPY source is missing or excluded by .dockerignore.

The first CI run of the docker gate failed on `COPY frontend/dist` because
.dockerignore listed `frontend/dist` while the Dockerfile copies the built
bundle into the image. BuildKit reports that as a red build with a log nobody
can read without repo admin rights, so this check makes the cause explicit and
runs before the expensive build.

Usage: python3 scripts/docker/verify-context.py [--dockerfile backend/Dockerfile]
"""

from __future__ import annotations

import argparse
import fnmatch
import re
import sys
from pathlib import Path

COPY_RE = re.compile(r"^\s*COPY\s+(?:--\S+\s+)*(.+)$", re.IGNORECASE)


def parse_copy_sources(dockerfile: Path) -> list[tuple[int, str]]:
    sources: list[tuple[int, str]] = []
    for number, line in enumerate(dockerfile.read_text(encoding="utf-8").splitlines(), 1):
        if line.strip().startswith("#"):
            continue
        match = COPY_RE.match(line)
        if not match:
            continue
        parts = match.group(1).split()
        if len(parts) < 2:
            continue
        # JSON form: COPY ["a", "b", "dest"]
        if parts[0].startswith("["):
            continue
        # COPY --from=<stage> <src> <dest>: the source lives in another stage, not
        # in the build context, so .dockerignore rules cannot affect it.
        if "--from=" in line:
            continue
        sources.append((number, parts[0]))
    return sources


def load_ignore_patterns(path: Path) -> list[str]:
    if not path.is_file():
        return []
    patterns: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if not text or text.startswith("#"):
            continue
        patterns.append(text)
    return patterns


def matches_ignore(relative: str, patterns: list[str]) -> str | None:
    """Return the pattern that excludes ``relative`` (Docker semantics, simplified)."""
    parts = relative.split("/")
    for pattern in patterns:
        negated = pattern.startswith("!")
        body = pattern[1:] if negated else pattern
        body = body.lstrip("/").rstrip("/")
        if not body:
            continue
        candidates = [relative] + ["/".join(parts[: index + 1]) for index in range(len(parts))]
        hit = any(
            fnmatch.fnmatch(candidate, body)
            or fnmatch.fnmatch(candidate, body.rstrip("*").rstrip("/"))
            or fnmatch.fnmatch(Path(candidate).name, body)
            for candidate in candidates
        )
        if hit:
            if negated:
                return None
            return pattern
    return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dockerfile", default="backend/Dockerfile")
    parser.add_argument("--context", default=".")
    parser.add_argument("--dockerignore", default=".dockerignore")
    args = parser.parse_args()

    root = Path(args.context).resolve()
    dockerfile = Path(args.dockerfile)
    patterns = load_ignore_patterns(Path(args.dockerignore))
    sources = parse_copy_sources(dockerfile)

    print(f"dockerfile: {dockerfile}")
    print(f"context:    {root}")
    print(f"ignore rules: {len(patterns)}")
    print(f"COPY sources: {len(sources)}")

    problems: list[str] = []
    for number, source in sources:
        if "*" in source or "?" in source:
            print(f"  line {number}: {source} (glob - skipped)")
            continue
        target = (root / source).resolve()
        if not target.exists():
            problems.append(f"line {number}: COPY source does not exist: {source}")
            print(f"  line {number}: {source} MISSING")
            continue
        try:
            relative = target.relative_to(root).as_posix()
        except ValueError:
            problems.append(f"line {number}: COPY source outside the context: {source}")
            continue
        pattern = matches_ignore(relative, patterns)
        if pattern:
            problems.append(
                f"line {number}: COPY source is excluded by .dockerignore pattern {pattern!r}: {source}"
            )
            print(f"  line {number}: {source} EXCLUDED by {pattern!r}")
        else:
            print(f"  line {number}: {source} ok")

    if problems:
        print("\nBUILD CONTEXT VERIFY FAILED")
        for problem in problems:
            print(" -", problem)
        return 1

    print("\nBUILD CONTEXT VERIFY OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
