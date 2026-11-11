"""Run and verify the imported suites from one entry point.

    python bench/run_suites.py --list
    python bench/run_suites.py --verify            # all suites
    python bench/run_suites.py --verify --suite cutoff

Verification is what the merge needs to answer: did moving the files change
anything, and does the committed evidence still reproduce the table? It does not
re-run the framework measurements; those results are the committed evidence.

Each suite is imported verbatim from its own repository. The original repository,
commit, author and license are recorded in suites/README.md and in each suite's
own README/CITATION files.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SUITES = {
    "double-exec": {
        "dir": "suites/double-exec",
        "measures": "one network fault: what does a framework do twice?",
        "verify": "regenerate results/e1/TABLE.md + cells.json from the committed evidence",
    },
    "cutoff": {
        "dir": "suites/cutoff",
        "measures": "a tool call whose arguments were cut off: does it run?",
        "verify": "rebuild the results table from results/runs.jsonl",
    },
    "runaway": {
        "dir": "suites/runaway",
        "measures": "a model loop inside one streamed reply: does the client stop?",
        "verify": "recompute the characters-read column from results/*.jsonl",
    },
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(args: list[str], cwd: Path) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True, env=env)


def _norm(data: bytes) -> str:
    return data.decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")


def verify_double_exec(suite: Path) -> tuple[bool, str]:
    targets = [suite / "results" / "e1" / "TABLE.md", suite / "results" / "e1" / "cells.json"]
    original = {p: p.read_bytes() for p in targets}
    try:
        proc = run([sys.executable, "harness/e1_summarize.py"], suite)
        if proc.returncode != 0:
            return False, f"e1_summarize.py exited {proc.returncode}: {proc.stderr.strip()[:200]}"
        changed = [str(p.relative_to(suite)) for p in targets if _norm(original[p]) != _norm(p.read_bytes())]
    finally:
        for path, data in original.items():
            path.write_bytes(data)
    if changed:
        return False, "regenerated files differ from the committed table: " + ", ".join(changed)
    return True, "TABLE.md and cells.json regenerated with identical content (line endings normalised)"


def table_lines(text: str) -> list[str]:
    return [line for line in text.splitlines() if line.startswith("|")]


def verify_cutoff(suite: Path) -> tuple[bool, str]:
    proc = run([sys.executable, "summarize.py", "results/runs.jsonl"], suite)
    if proc.returncode != 0:
        return False, f"summarize.py exited {proc.returncode}: {proc.stderr.strip()[:200]}"
    readme = (suite / "README.md").read_text(encoding="utf-8")
    lines = readme.splitlines()
    try:
        start = lines.index("## Result")
    except ValueError:
        return False, "README has no '## Result' section"
    expected: list[str] = []
    for line in lines[start:]:
        if line.startswith("|"):
            expected.append(line)
        elif expected:
            break
    actual = table_lines(proc.stdout)
    if not expected:
        return False, "README has no result table under '## Result'"
    if actual[: len(expected)] != expected:
        return False, "recomputed table does not match the README table"
    return True, f"{len(expected)} table lines match the README"


def verify_runaway(suite: Path) -> tuple[bool, str]:
    # Expected values are the "Read before stopping" column of results/README.md.
    expected = {
        "hermes": (16168, True),
        "codex-cli": (300048, False),
        "langgraph": (300048, False),
        "smolagents": (300048, False),
        "openai-agents-sdk-chat": (300048, False),
        "openai-agents-sdk-responses": (300048, False),
        "nat-tool-calling-agent-chat": (300048, False),
        "nat-tool-calling-agent-responses": (300048, False),
    }
    seen = {}
    for path in sorted((suite / "results").glob("*.jsonl")):
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        seen[path.stem] = (max(r["chars_streamed"] for r in rows), any(r["client_hung_up_early"] for r in rows))
    missing = sorted(set(expected) - set(seen))
    if missing:
        return False, "missing evidence files: " + ", ".join(missing)
    bad = [name for name, value in expected.items() if seen[name] != value]
    if bad:
        return False, "recomputed column differs for: " + ", ".join(bad)
    return True, f"{len(expected)} evidence files match the README column"


def verify(name: str) -> tuple[bool, str]:
    suite = ROOT / SUITES[name]["dir"]
    fn = {"double-exec": verify_double_exec, "cutoff": verify_cutoff, "runaway": verify_runaway}[name]
    try:
        return fn(suite)
    except Exception as exc:  # noqa: BLE001 - report, never mask
        return False, f"{type(exc).__name__}: {exc}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--verify", action="store_true")
    ap.add_argument("--suite", choices=sorted(SUITES))
    args = ap.parse_args()

    if args.list:
        for name, meta in SUITES.items():
            print(f"{name:12s} {meta['measures']}\n{'':12s} verify: {meta['verify']}")
        return 0

    names = [args.suite] if args.suite else list(SUITES)
    failed = 0
    for name in names:
        ok, detail = verify(name)
        print(f"[{'PASS' if ok else 'FAIL'}] {name}: {detail}")
        failed += 0 if ok else 1
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
