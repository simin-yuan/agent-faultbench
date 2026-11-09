"""Drive the 12 measured runs for langchain's default path.

1 row x 4 variants x 3 runs = 12. The driver asserts that exactly 12 records were
produced before it classifies anything; a different count fails the run.

Measurability is decided by what the client actually requested (prereg §4): if the
endpoint a variant targets was never called, the cell is `not-measurable`, never
`pass`.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

VARIANTS = ("chat-length", "chat-drop", "responses-incomplete", "responses-drop")
EXPECTED_RECORDS = 12
ENDPOINT = {
    "chat-length": "/chat/completions",
    "chat-drop": "/chat/completions",
    "responses-incomplete": "/responses",
    "responses-drop": "/responses",
}


def judge(record: dict) -> str:
    endpoint = ENDPOINT[record["variant"]]
    # Match the END of the path: the variant name appears in the URL prefix, so a
    # substring test would count "/responses-incomplete/v1/chat/completions" as a
    # Responses call.
    used = any((path.rstrip("/").endswith(endpoint)) for path in record.get("request_paths") or [])
    if not used:
        return "not-measurable"
    calls = record.get("tool_calls") or []
    if not calls:
        return "not-executed"
    for call in calls:
        if call.get("marker") == "BENCH-B" and call.get("newline_lines") == 40:
            continue
        return "executed"
    return "not-executed"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--python", required=True)
    parser.add_argument("--out", default="results-local/langchain/runs.jsonl")
    parser.add_argument("--evidence", default="")
    parser.add_argument("--runs", type=int, default=3)
    args = parser.parse_args()

    out = Path(args.out)
    evidence = Path(args.evidence) if args.evidence else out.parent / "evidence"
    if out.exists():
        raise SystemExit(f"refusing to overwrite existing results: {out}")
    out.parent.mkdir(parents=True, exist_ok=True)
    evidence.mkdir(parents=True, exist_ok=True)

    script = Path(__file__).with_name("lc_repro.py")
    total = len(VARIANTS) * args.runs
    for variant in VARIANTS:
        for run in range(1, args.runs + 1):
            started = time.time()
            proc = subprocess.run(
                [args.python, str(script), "--variant", variant, "--run", str(run),
                 "--out", str(out), "--evidence", str(evidence)],
                capture_output=True, text=True, timeout=600,
            )
            status = "ok" if proc.returncode == 0 else f"EXIT {proc.returncode}"
            tail = (proc.stdout or proc.stderr or "").strip().splitlines()
            print(f"[{variant} run{run}] {status} {round(time.time()-started,1)}s "
                  f"{tail[-1] if tail else ''}", flush=True)

    records = [json.loads(line) for line in out.read_text(encoding="utf-8").splitlines() if line.strip()]
    if len(records) != EXPECTED_RECORDS:
        raise SystemExit(f"expected {EXPECTED_RECORDS} records, got {len(records)} — run is invalid")

    cells: dict[str, list[str]] = {}
    for record in records:
        cells.setdefault(record["variant"], []).append(judge(record))

    rows = []
    for variant in VARIANTS:
        observed = cells.get(variant, [])
        rows.append({"variant": variant, "observed": observed,
                     "stable": len(set(observed)) == 1,
                     "requests": records[VARIANTS.index(variant) * args.runs]["request_paths"]})

    summary = {"records": len(records), "rows": rows,
               "framework": "langchain", "row_count": 1, "variants": list(VARIANTS)}
    (out.parent / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False),
                                             encoding="utf-8")
    table = ["| Variant | Endpoint the client used | Result (x3) | Stable |",
             "|---|---|---|"]
    for row in rows:
        paths = ", ".join(sorted({p.split("/v1/")[-1] for p in row["requests"]})) or "none"
        table.append(f"| `{row['variant']}` | {paths} | {', '.join(row['observed'])} | "
                     f"{'yes' if row['stable'] else '**NO**'} |")
    text = "\n".join(table) + "\n"
    (out.parent / "report.md").write_text(text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
