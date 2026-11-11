# Suites

These three suites were imported verbatim on 2026-11-12 from their own repositories.
Every imported file is byte-identical to the source repository at the commit below
(the comparison is recorded in `VERIFICATION.md`). **Results are from the original
runs; the evidence is in each suite's `results/` directory.**

| suite | what it measures | imported from | commit | license |
|---|---|---|---|---|
| `double-exec` | one network fault: what does a framework do twice? | `simin-yuan/agent-double-exec-bench` | `463b9d6` | MIT |
| `cutoff` | a tool call whose arguments were cut off: does it run? | `simin-yuan/agent-cutoff-bench` | `6b31536` | see `cutoff/LICENSE` |
| `runaway` | a model loop inside one streamed reply: does the client stop? | `simin-yuan/agent-runaway-bench` | `1170eb4` | MIT |

## One entry point

From the repository root:

```bash
python bench/run_suites.py --list      # what is here
python bench/run_suites.py --verify    # every suite
python bench/run_suites.py --verify --suite cutoff
```

`--verify` is the merge check: it regenerates each suite's table from the committed
evidence and fails if the output differs. It does not re-run the framework
measurements.

## Provenance

Each suite keeps its own README, CITATION.cff and license. The author of all three
is Simin Yuan. The per-suite `results/` directories are the primary evidence.
