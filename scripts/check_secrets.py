"""Scan tracked files and Git revisions without printing secret material."""

import argparse
import re
import subprocess
from pathlib import Path

PATTERNS = [
    re.compile(
        rb"(?i)(?:api_key|access_token|refresh_token|client_secret|password)[ \t]*[=:][ \t]*[\"\x27]?[A-Za-z0-9_\-/+.]{20,}"
    ),
    re.compile(rb"dapi[a-f0-9]{32}"),
    re.compile(rb"gh[pousr]_[A-Za-z0-9]{20,}"),
    re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
]
FORBIDDEN = {".env", ".databrickscfg", "token-cache.json", "profiles.yml"}


def forbidden(relative):
    path = Path(relative)
    return (
        path.name in FORBIDDEN
        or (path.name.startswith(".env.") and path.name != ".env.example")
        or any(
            part in {"private-learning", "secrets", ".databricks", "data"} for part in path.parts
        )
    )


def scan(root, history=False):
    paths = subprocess.check_output(["git", "ls-files", "-z"], cwd=root).split(b"\0")
    issues = []
    for entry in paths:
        if not entry:
            continue
        relative = entry.decode("utf-8")
        path = Path(root) / relative
        if forbidden(relative):
            issues.append((relative, "forbidden_file"))
        content = path.read_bytes()
        if any(p.search(content) for p in PATTERNS):
            issues.append((relative, "credential_pattern"))
        staged = subprocess.check_output(["git", "show", ":" + relative], cwd=root)
        if staged != content and any(p.search(staged) for p in PATTERNS):
            issues.append((relative, "staged_credential_pattern"))
    if history:
        revisions = (
            subprocess.check_output(["git", "rev-list", "--all"], cwd=root).decode().splitlines()
        )
        for revision in revisions:
            names = (
                subprocess.check_output(["git", "ls-tree", "-r", "--name-only", revision], cwd=root)
                .decode()
                .splitlines()
            )
            if any(forbidden(name) for name in names):
                issues.append((revision[:12], "history_forbidden_file"))
            content = subprocess.check_output(
                ["git", "show", "--format=", "--no-ext-diff", revision], cwd=root
            )
            if any(p.search(content) for p in PATTERNS):
                issues.append((revision[:12], "history_credential_pattern"))
    return issues


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--history", action="store_true")
    args = parser.parse_args()
    failures = scan(Path(__file__).resolve().parents[1], args.history)
    for path, reason in failures:
        print(f"{path}: {reason}")
    print(f"Secret scan: {len(failures)} findings")
    raise SystemExit(bool(failures))
