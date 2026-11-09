"""Run the 24-cell reproduction: 2 agents x 4 variants x 3 runs, sequentially.

Expected values are copied verbatim from the two upstream issues:

  R1 = NVIDIA/NeMo-Agent-Toolkit#2550  (tool_calling_agent, 1.9.0)
  R2 = NVIDIA/NeMo-Agent-Toolkit#2552  (react_agent + use_native_tool_calling, 1.9.0)

A cell reproduces when all 3 runs match the expected outcome. Any mismatch is a
deviation and is reported as such -- the harness is not adjusted to fit.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

AGENTS = ("tool_calling_agent", "react_agent")
VARIANTS = ("chat-length", "chat-drop", "responses-incomplete", "responses-drop")

# Expected values live in a committed file and are read from a git ref, never
# from the working tree. A run must not be able to rewrite the standard it is
# compared against; that is the v1 lesson (a comparison whose baseline sat in a
# writable path reported a false 8/8).
EXPECTED_PATH = "docs/preregistration/expected-nat190.json"


def load_expected(ref: str, path: str = EXPECTED_PATH) -> dict:
    raw = subprocess.run(
        ["git", "show", f"{ref}:{path}"], capture_output=True, text=True, check=False
    )
    if raw.returncode != 0:
        raise SystemExit(
            f"cannot read expected values from {ref}:{path} ({raw.stderr.strip()[:200]})\n"
            "Expected values must come from an immutable ref, not from the working tree."
        )
    data = json.loads(raw.stdout)
    return {
        (row["agent"], row["variant"]): (
            row["verdict"],
            row["lines"],
            row["bytes"],
            row["sha256"],
        )
        for row in data["cells"]
    }

SOURCES = {
    "tool_calling_agent": "https://github.com/NVIDIA/NeMo-Agent-Toolkit/issues/2550",
    "react_agent": "https://github.com/NVIDIA/NeMo-Agent-Toolkit/issues/2552",
}


def judge(record: dict) -> tuple[str, int | None, int | None, str | None]:
    """(verdict, lines, bytes, sha256). All four must match the expected cell."""
    calls = record.get("tool_calls") or []
    disk = record.get("disk") or {}
    observed = (disk.get("lines"), disk.get("bytes"), disk.get("sha256"))
    if not calls:
        return ("not-executed", None, None, None)
    for call in calls:
        if call.get("marker") == "BENCH-B" and call.get("newline_lines") == 40:
            continue
        return ("executed", *observed)
    return ("not-executed", None, None, None)


def version_report(python: str) -> dict:
    code = (
        "import json,platform;"
        "out={'python':platform.python_version(),'platform':platform.platform()};"
        "\nfor name in ('nvidia_nat','nat','langchain_core','langchain_openai','pydantic'):\n"
        "    try:\n"
        "        m=__import__(name); out[name]=getattr(m,'__version__','?')\n"
        "    except Exception as e:\n"
        "        out[name]='missing'\n"
        "print(json.dumps(out))"
    )
    try:
        raw = subprocess.run([python, "-c", code], capture_output=True, text=True, timeout=120)
        return json.loads(raw.stdout.strip().splitlines()[-1])
    except Exception as exc:  # pragma: no cover
        return {"error": f"{type(exc).__name__}: {exc}"}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--python", required=True, help="interpreter of the NAT environment")
    parser.add_argument("--out", default="results-local/runs.jsonl", help="never an existing directory")
    parser.add_argument("--evidence", default="", help="defaults to <out dir>/evidence")
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--expected-ref", default="HEAD", help="git ref holding the expected values")
    parser.add_argument("--expected-path", default=EXPECTED_PATH)
    args = parser.parse_args()

    out = Path(args.out)
    evidence = Path(args.evidence) if args.evidence else out.parent / "evidence"
    # Never overwrite a previous result set. Overwriting the baseline and then
    # "comparing" against the overwritten copy is a silent false pass.
    if out.exists():
        raise SystemExit(
            f"refusing to overwrite existing results: {out}\n"
            "Write to a fresh, version-uncontrolled directory (e.g. results-local/)."
        )
    out.parent.mkdir(parents=True, exist_ok=True)
    evidence.mkdir(parents=True, exist_ok=True)

    expected_map = load_expected(args.expected_ref, args.expected_path)

    versions = version_report(args.python)
    meta = {"started": round(time.time(), 3), "versions": versions,
            "runs_per_cell": args.runs, "expected_sources": SOURCES,
            "expected_ref": args.expected_ref, "expected_path": args.expected_path}
    (out.parent / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(f"versions: {json.dumps(versions)}", flush=True)

    script = Path(__file__).with_name("nat_repro.py")
    deviations = []
    total = len(AGENTS) * len(VARIANTS) * args.runs
    done = 0

    for agent in AGENTS:
        for variant in VARIANTS:
            for run in range(1, args.runs + 1):
                done += 1
                started = time.time()
                proc = subprocess.run(
                    [args.python, str(script), "--agent", agent, "--variant", variant,
                     "--run", str(run), "--out", str(out), "--evidence", str(evidence)],
                    capture_output=True, text=True, timeout=600,
                )
                elapsed = round(time.time() - started, 1)
                status = "ok" if proc.returncode == 0 else f"EXIT {proc.returncode}"
                tail = (proc.stdout or proc.stderr or "").strip().splitlines()
                print(f"[{done}/{total}] {agent}/{variant} run{run}: {status} {elapsed}s "
                      f"{tail[-1] if tail else ''}", flush=True)

    records = [json.loads(line) for line in out.read_text(encoding="utf-8").splitlines() if line.strip()]

    cells: dict[tuple[str, str], list[dict]] = {}
    for record in records:
        cells.setdefault((record["agent"], record["variant"]), []).append(record)

    rows = []
    reproduced = 0
    compared = 0
    for agent in AGENTS:
        for variant in VARIANTS:
            runs = cells.get((agent, variant), [])
            observed = [judge(r) for r in runs]
            expected = expected_map[(agent, variant)]
            agree = len(observed) == args.runs and all(o == expected for o in observed)
            compared += 1
            reproduced += 1 if agree else 0
            disk = next((r["disk"] for r in runs if r.get("disk", {}).get("file_written")), {})
            rows.append({
                "agent": agent,
                "variant": variant,
                "expected": expected,
                "observed": observed,
                "reproduced": agree,
                "lines": disk.get("lines"),
                "bytes": disk.get("bytes"),
                "source": SOURCES[agent],
            })
            if not agree:
                deviations.append(rows[-1])

    summary = {
        "cells": compared,
        "reproduced": reproduced,
        "deviations": deviations,
        "records": len(records),
        "finished": round(time.time(), 3),
    }
    (out.parent / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")

    def fmt(value: tuple[str, int | None, int | None, str | None]) -> str:
        verdict, lines, byts, sha = value
        if lines is None:
            return verdict
        short = (sha or "")[:8]
        return f"{verdict} {lines}/40 {byts}B {short}"

    table = ["| Agent | Variant | Expected | Observed (x3) | Disk | Reproduced |",
             "|---|---|---|---|---|---|"]
    for row in rows:
        disk = "—" if row["bytes"] is None else f"{row['lines']} lines / {row['bytes']}B"
        table.append(
            f"| {row['agent']} | `{row['variant']}` | {fmt(row['expected'])} | "
            f"{', '.join(fmt(o) for o in row['observed'])} | {disk} | "
            f"{'yes' if row['reproduced'] else '**NO**'} |"
        )
    (out.parent / "reproduction.md").write_text("\n".join(table) + "\n", encoding="utf-8")

    print("\n".join(table))
    print(json.dumps(summary, ensure_ascii=False, indent=2)[:1200])
    return 0


if __name__ == "__main__":
    sys.exit(main())
