# Reproduce the NAT 1.9.0 measurement

This reproduces the 24-cell matrix described in
[`docs/preregistration/nat-1.9.0-repro.md`](docs/preregistration/nat-1.9.0-repro.md):
2 NVIDIA NeMo Agent Toolkit agent types × 4 truncation variants × 3 runs.

No API key, no network access to a model. The fake server runs on `127.0.0.1`.

## Prerequisites

- Python 3.12
- [uv](https://docs.astral.sh/uv/) (any recent version; `uv --version` must work)
- ~1 GB of disk for the isolated environment

## One command to build the environment

```bash
uv venv .envs/nat190 --python 3.12
uv pip install --python .envs/nat190/bin/python --require-hashes -r requirements.lock
```

On Windows the interpreter path is `.envs\nat190\Scripts\python.exe`.

`requirements.lock` pins the **entire** dependency tree (`uv pip compile`
output, committed). Install from the lock, not from `requirements.in` — that is
the only way a run next week gets the same tree as the run recorded here.

First run downloads ~100 packages; expect **5–15 minutes** depending on the
network. Later runs reuse the environment.

## One command to run the matrix

```bash
python bench/run_matrix.py \
  --python .envs/nat190/bin/python \
  --out results-local/runs.jsonl
```

Windows:

```powershell
.\.envs\nat190\Scripts\python.exe bench\run_matrix.py --python .\.envs\nat190\Scripts\python.exe
```

**Write results to `results-local/` (or any fresh directory), never to a
directory that already exists in the repository.** The runner refuses to
overwrite an existing results file on purpose: overwriting a baseline and then
comparing against the overwritten copy is a silent false pass.

Expected values are read from a git ref (`--expected-ref`, default `HEAD`), not
from the working tree, so a run cannot rewrite the standard it is judged by.

The 24 runs take about **5–10 minutes** (each run starts a fresh server, a fresh
temporary working directory, and a fresh NAT process).

## Troubleshooting: `502` on the first run

If the client fails with `502 Bad Gateway` (or a connection error) even though the fake
server is running, a **system HTTP proxy is probably intercepting the loopback call**.
The failure looks like a server bug and is not one. The harness sets
`NO_PROXY=127.0.0.1,localhost` itself; if you run the runners by hand, export the same
two variables (`NO_PROXY` and `no_proxy`) before you start.

## What it writes

| Path | Content |
|---|---|
| `results/nat-1.9.0/runs.jsonl` | one line per run: agent, variant, whether the tool ran, the arguments it received, the file on disk (lines/bytes/sha256), the exception if any, duration |
| `results/nat-1.9.0/evidence/*.sse` | the exact bytes the fake server sent, per run |
| `results/nat-1.9.0/meta.json` | resolved component versions |
| `results/nat-1.9.0/summary.json` | cells reproduced vs deviations |
| `results/nat-1.9.0/reproduction.md` | expected vs observed table |

## How to read the result

`pass` means the tool was not executed (or only with complete, marker-B
arguments). `fail` means a call with truncated arguments was executed. A
**reproduced** cell means all three runs agree with the value copied from the
upstream issues (#2550 for `tool_calling_agent`, #2552 for `react_agent`).

If a cell does not reproduce, that is a finding about the harness, not about
NAT: do **not** adjust the harness to make the table match.
