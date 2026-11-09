# agent-faultbench

**Does your agent's defence actually stop an action that should not run?**

v0.1 measures one case: **a truncated action**. The fake model asks a tool to write
a 40-line file and its arguments stop inside line 17. A client that runs the call
anyway leaves a 16-line file behind. The evidence is that file — not a log line,
not a self-report.

```
line 01: the quick brown fox jumps over the lazy dog
...
line 16: the quick brown fox jumps over the lazy dog
line 17: the quick
```

2,120 bytes expected, **866 bytes written**. Nothing raised. The agent reported
success.

## What v0.1 covers

Three clients, default path only (the entry each project's official quickstart
demonstrates). Four ways for a reply to end: `length`, `drop`, `responses-incomplete`,
`responses-drop`. Each cell is measured three times.

| Client | Version | Entry (from its quickstart) | `chat-length` | `chat-drop` | `responses-*` |
|---|---|---|---|---|---|
| NVIDIA NeMo Agent Toolkit (`tool_calling_agent`) | 1.9.0 | `tool_calling_agent`, default settings | not executed | **executed** | **executed** |
| NVIDIA NeMo Agent Toolkit (`react_agent`, native tool calling) | 1.9.0 | `use_native_tool_calling: true` | **executed** | **executed** | **executed** |
| langchain (`create_agent`) | 1.4.9 | `langchain.agents.create_agent`, `openai:gpt-5.5` | not executed (BT: `unknown`) | not executed (BT: `unknown`) | not measurable |
| semantic-kernel (automatic function calling) | 1.36.0 | `Kernel` + `FunctionChoiceBehavior.Auto()` | not executed (BT: `unknown`) | not executed (BT: `unknown`) | not measurable |

- **executed** = the tool ran on a truncated call; the file on disk is short.
- **not executed** = no call reached the tool.
- **not measurable** = the client never requested the wire endpoint this variant
  needs, so the cell is excluded from the denominator instead of being scored.
- **BT** is how a *not executed* cell was stopped: `blocked-by-end-signal` (the
  client checked that the reply had finished), `blocked-by-parse` (a parser refused
  the payload — luck, not correctness), or `unknown` (the record cannot tell).

The NVIDIA rows are a **reproduction** of two upstream reports
([#2550](https://github.com/NVIDIA/NeMo-Agent-Toolkit/issues/2550),
[#2552](https://github.com/NVIDIA/NeMo-Agent-Toolkit/issues/2552)); both were fixed
upstream in November 2026. The langchain and semantic-kernel rows are first
measurements.

## Reproduce

```bash
git clone <this repo> && cd agent-faultbench
uv venv .envs/nat190 --python 3.12
uv pip install --python .envs/nat190/bin/python --require-hashes -r requirements.lock
python bench/run_matrix.py --python .envs/nat190/bin/python --out results-local/nat/runs.jsonl
```

Each framework has its own lock file and its own driver (`bench/lc_matrix.py`,
`bench/sk_matrix.py`). `REPRODUCE.md` has the details, including what the runner
refuses to do (it will not overwrite an existing results file).

The expected values live in `docs/preregistration/` and are read from a **git ref**,
never from the working tree, so a run cannot edit the standard it is judged by.

## How this is measured

`METHODS.md` has the rules: the default-path rule, the pre-registration flow, the
four-field judgement, and the two controls that differ in exactly one variable.
Short version:

- no API key, no hosted model: the fake server speaks the OpenAI wire formats;
- the tool is ours, so the side effect is attributable;
- the judged fields are **verdict, lines, bytes, sha256** — all four must match;
- a cell that cannot be measured is reported as such, never as a pass.

## Interests

The upstream issues and pull requests this benchmark cites were filed by this
project's author, and some of them were merged. The raw records (links, timestamps)
are in each pre-registration file so a reader can check the order of events.

## Limits

- The server models the **wire format**, not any provider's behaviour. It shows what
  a client does with such a reply; it says nothing about how often that reply occurs.
- v0.1 measures **default paths only**, and only the truncation case.
- `check` — the self-test a user will run against their own agent — is **not in
  v0.1**.
- One tool, one cut point per variant.

## Related work

`deepseek-harness` ships an [`llm-mock-server`](https://github.com/deepseek-ai/deepseek-harness);
`llmposter`, `stubllm`, `fakellm` and `llmock` cover similar ground. They **produce**
faults. This project judges whether a client handled them, with cases behind real
upstream reports.

## Roadmap

Later versions add more clients, a streaming-mode scoreboard, and the self-test
`check`. Nothing on the roadmap is promised by date.

## License and citation

Apache-2.0 (`LICENSE`, `NOTICE`). Citation metadata in `CITATION.cff`.

Author: **Simin Yuan**.

