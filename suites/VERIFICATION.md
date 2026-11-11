# Import verification — 2026-11-12

Three checks were run before the suites were merged into `main`. All passed.

## a. Every imported file is byte-identical to the source repository

Comparison: SHA-256 of each file in `suites/<name>/` against the same path in the
source repository at its HEAD commit. Files excluded from the import on purpose:
`.github/`, and the three guard scripts (`scripts/leak-scan.sh`, `scripts/pre-push`,
`scripts/install-hooks.sh`).

| suite | source commit | files compared | identical | missing | different |
|---|---|---|---|---|---|
| double-exec | `463b9d6` | 835 | 835 | 0 | 0 |
| cutoff | `6b31536` | 197 | 197 | 0 | 0 |
| runaway | `1170eb4` | 29 | 29 | 0 | 0 |

## b. The committed evidence reproduces each table

- **double-exec**: `harness/e1_summarize.py` regenerated `results/e1/TABLE.md` and
  `results/e1/cells.json` with identical content (line endings normalised; the origin
  files are CRLF, the regenerated ones LF).
- **cutoff**: `summarize.py results/runs.jsonl` reproduced all 21 table lines under
  `## Result` in the README.
- **runaway**: all 8 evidence files reproduce the "Read before stopping" column
  (16,168 chars for the control, 300,048 for the rest), including the hang-up flag.

## c. The key-free parts run through the unified entry point

`python bench/run_suites.py --verify` exits 0 for all three suites. The command runs
exactly the checks above; it needs only Python 3.12 and no API key.

## What this does not verify

It does not re-run the framework measurements. Those results are the committed
evidence in each suite; re-running the frameworks would test the frameworks, not
the import. Suite READMEs state that results come from the original runs.
