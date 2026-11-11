# agent-faultbench

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.24143646.svg)](https://doi.org/10.5281/zenodo.24143646)

**An agent's self-report says it did A. The write on disk says it did B. This benchmark measures that gap — and whether the defence stopped an action that should never have run.**

Most agent checks look at what the agent says it did. These four failures happened in real work, and in every one of them the self-check was green.

## Four failures we hit ourselves

### 1. A byte-order mark made an `@` directive silently do nothing

- **What happened:** a UTF-8 BOM at the top of a source file made an `@`-prefixed directive stop applying. The tool ran without it and reported success.
- **Why the checks were green:** they compared the output after the directive was supposed to run, and the output looked the same either way. Nothing asserted that the directive had been parsed at all.
- **How to detect it:** assert presence in the parsed structure, not just a successful parse; keep a BOM-free fixture and diff the raw first bytes.

### 2. Comparing one file produced the wrong root cause

- **What happened:** a failure was diagnosed by diffing only the file where the symptom appeared. The real change was in a sibling file, so the patch fixed the symptom and left the cause in place.
- **Why the checks were green:** the red/green test exercised only the single-file path; it passed as soon as that file changed.
- **How to detect it:** require the root-cause claim to name the full diff. If more than one file changed, the claim must explain every file; re-run the test on the old tree and show it fails.

### 3. A rehearsal wrote into the real database

- **What happened:** a "dry run" wrote to the production database. The rehearsal path had defaulted to the live connection string, and the write succeeded.
- **Why the checks were green:** the rehearsal read back the rows it had just written, and they were correct. Nothing compared the target identity.
- **How to detect it:** assert the connection target against a test-only allowlist before the first write; make dry-run the default and require an explicit flag to write.

### 4. The scanner published the list it was protecting

- **What happened:** a leak scanner hard-coded the private names it was supposed to block, so the guard's own source became the leak.
- **Why the checks were green:** the scanner skipped itself and only scanned data files. Its self-check reported clean.
- **How to detect it:** self-scan the guard — grep its source for the literals it blocks — and load the list from an ignored local file.

## Quick start

The measurement is one command. It builds an isolated environment from a pinned lock file, then runs the 24-cell matrix against a local fake server. No API key, no hosted model.

macOS / Linux:

```bash
git clone https://github.com/simin-yuan/agent-faultbench.git && cd agent-faultbench \
  && uv venv .envs/nat190 --python 3.12 \
  && uv pip install --python .envs/nat190/bin/python --require-hashes -r requirements.lock \
  && .envs/nat190/bin/python bench/run_matrix.py --python .envs/nat190/bin/python --out results-local/nat/runs.jsonl
```

Windows (PowerShell):

```powershell
git clone https://github.com/simin-yuan/agent-faultbench.git; cd agent-faultbench
uv venv .envs\nat190 --python 3.12
uv pip install --python .envs\nat190\Scripts\python.exe --require-hashes -r requirements.lock
.\.envs\nat190\Scripts\python.exe bench\run_matrix.py --python .envs\nat190\Scripts\python.exe --out results-local\nat\runs.jsonl
```

The first run downloads about 100 packages. The runner refuses to overwrite an existing results file, and it reads the expected values from a **git ref**, never from the working tree — a run cannot edit the standard it is judged by.

## What v0.1 covers

Three clients, default path only (the entry each project's official quickstart demonstrates). Four ways for a reply to end: `length`, `drop`, `responses-incomplete`, `responses-drop`. Each cell is measured three times.

| Client | Version | Entry (from its quickstart) | `chat-length` | `chat-drop` | `responses-*` |
|---|---|---|---|---|---|
| NVIDIA NeMo Agent Toolkit (`tool_calling_agent`) | 1.9.0 | `tool_calling_agent`, default settings | not executed | **executed** | **executed** |
| NVIDIA NeMo Agent Toolkit (`react_agent`, native tool calling) | 1.9.0 | `use_native_tool_calling: true` | **executed** | **executed** | **executed** |
| langchain (`create_agent`) | 1.4.9 | `langchain.agents.create_agent`, `openai:gpt-5.5` | not executed (BT: `unknown`) | not executed (BT: `unknown`) | not measurable |
| semantic-kernel (automatic function calling) | 1.36.0 | `Kernel` + `FunctionChoiceBehavior.Auto()` | not executed (BT: `unknown`) | not executed (BT: `unknown`) | not measurable |

- **executed** = the tool ran on a truncated call; the file on disk is short.
- **not executed** = no call reached the tool.
- **not measurable** = the client never requested the wire endpoint this variant needs, so the cell is excluded from the denominator instead of being scored.
- **BT** is how a *not executed* cell was stopped: `blocked-by-end-signal` (the client checked that the reply had finished), `blocked-by-parse` (a parser refused the payload — luck, not correctness), or `unknown` (the record cannot tell).

In the truncated-call case, the fake model asks a tool to write a 40-line file and its arguments stop inside line 17. A client that runs the call anyway leaves a 16-line file behind: 2,120 bytes expected, **866 bytes written**, nothing raised.

The NVIDIA rows reproduce two upstream reports ([#2550](https://github.com/NVIDIA/NeMo-Agent-Toolkit/issues/2550), [#2552](https://github.com/NVIDIA/NeMo-Agent-Toolkit/issues/2552)). The langchain and semantic-kernel rows are first measurements.

## Suites

agent-faultbench also carries three imported suites, each preserving its own evidence and results:

| suite | question |
|---|---|
| `suites/double-exec` | one network fault: what does a framework do twice? |
| `suites/cutoff` | a tool call whose arguments were cut off: does it run? |
| `suites/runaway` | a model loop inside one streamed reply: does the client stop? |

`python bench/run_suites.py --verify` regenerates each suite's table from its committed evidence. Results are from the original runs; the evidence is in each suite's `results/` directory.
## How this is measured

- no API key, no hosted model: the fake server speaks the OpenAI wire formats;
- the tool is ours, so the side effect is attributable;
- the judged fields are **verdict, lines, bytes, sha256** — all four must match;
- a cell that cannot be measured is reported as such, never as a pass;
- expected values are read from a git ref, and the runner refuses to overwrite results.

`METHODS.md` has the rules: the default-path rule, the pre-registration flow, the four-field judgement, and the controls.

## Limits

- The server models the **wire format**, not any provider's behaviour. It shows what a client does with such a reply; it says nothing about how often that reply occurs.
- v0.1 measures **default paths only**, and only the truncation case.
- `check` — the self-test a user will run against their own agent — is **not in v0.1**.
- One tool, one cut point per variant.

## Related work

Several mock-server projects ship similar fault injectors. They **produce** faults. This project judges whether a client handled them, with cases behind real upstream reports.

## License and citation

Apache-2.0 (`LICENSE`, `NOTICE`). Citation metadata in `CITATION.cff`.

Author: **Simin Yuan**.
