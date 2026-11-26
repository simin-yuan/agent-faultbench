# Raw-admission evaluation, October 22, 2026

These runs come from `simin-yuan/agent-cutoff-bench#1`. The optional check
uses the existing `createReactAgent`, `write_file`, real temporary files and
the same [`server.py`](../../server.py) fixture as upstream commit
`1f4488f0069092a7a4924c9feaf7929851bfb6d6`.

## Actual results

Both clean Windows installations produced the following results. Each row
was run with all three clients on the same installed SDK versions.

| Existing fixture | Native | Small raw-native check | PSJ core 0.6.3 |
| --- | --- | --- | --- |
| Complete | One 2,120-byte write, 40 complete lines | Same | Same |
| Length cutoff | One truncated 866-byte write | 0 bytes, no write | 0 bytes, no write |
| Clean EOF/drop | One truncated 866-byte write | 0 bytes, no write | 0 bytes, no write |
| TCP reset | No write; raised transport error | Same | Same |

Healthy calls preserve `call_bench_1`, one successful ToolMessage and two
model requests. Guarded length/drop calls still enter the callback once,
but stop before `writeFileSync`, send an error ToolMessage with that original
ID and continue to a second model request. This fake server answers `Done.`
even after an error result: that answer is not proof that a file was written.

There were no false refusals in the single healthy fixture. The small native
check and PSJ produced equal observed application outcomes in all four modes;
no unique protection or lower maintenance cost is established here. A future
native strict-final-JSON fix may remove the reason to retain either check.
These authored fixtures do not establish incident frequency or PSJ adoption.

## Reproduce the retained benchmark pins

Run from the repository root with Node 22+, Python 3, and the locked packages
in your local npm cache.

```sh
cd suites/cutoff/harness/js
npm ci --offline --ignore-scripts --strict-peer-deps --no-audit --no-fund &&
npm run test:raw-policy
```

This leaves the original four dependency pins intact: LangChain core 1.2.18,
OpenAI 1.6.2, LangGraph 1.5.1 and Zod 4.6.7. Only published
`prefix-safe-json@0.6.3` is added as a development dependency. The existing
default benchmark matrix and tool remain available without the optional fifth
CLI argument. The command writes raw client/server records and original SSE
captures to a newly created directory and prints its location.

The optional observation fetch drains each finite response before SDK parsing
in all three clients; its limit is 1 MiB. That changes streaming timing, so
this is not a latency benchmark or a drop-in streaming integration. Admission
is per original call, not whole-batch. These four one-call fixtures do not
certify multiple calls, arbitrary providers or other protocols.

## Executed environment and evidence

Windows 11 build 26200 x64, Node 22.23.2, npm 10.9.8, Python 3.12.10.
Both installs used fresh source directories and registry packages with peer
checks enabled, no existing `node_modules`, links or overlays.

- Retained pins: clean `npm ci` exit 0; **12/12**, exit 0. Runtime/test source
  `7d88b2fb82ffe8c5ce6fea605e991523e7dd2914`.
- Separate second operator validation: current registry core **1.3.0**, OpenAI
  **1.7.0**, LangGraph **1.5.2**, same Zod and PSJ. Clean `npm ci` with
  `--engine-strict` exit 0; one invocation, **12/12**, exit 0. Isolated
  validation head `0d30e3562c843663e8ecc9e4746045c4bb49e516`; only three SDK
  pins differ from the same runtime/test source. These versions are not
  substituted into the benchmark's committed manifest.
- The [retained-pin records](retained-records.jsonl) and
  [second-pin records](current-records.jsonl) are the original runs. Their
  summaries, environment details and command receipts are in this directory.

To reproduce the second SDK version set, run from the repository root with
the second set of locked packages in your local npm cache. This uses a
temporary copy so the retained pins stay in place.

```sh
trial=$(mktemp -d)
evidence=suites/cutoff/results/js-raw-policy-windows-20261022
mkdir -p "$trial/harness/js"
cp suites/cutoff/server.py "$trial/"
cp suites/cutoff/harness/js/*.mjs "$trial/harness/js/"
cp "$evidence/current-package.json" "$trial/harness/js/package.json"
cp "$evidence/current-package-lock.json" "$trial/harness/js/package-lock.json"
(
  cd "$trial/harness/js" &&
  npm ci --offline --ignore-scripts --strict-peer-deps --engine-strict --no-audit --no-fund &&
  npm run test:raw-policy
)
```

The first retained-pin test invocation failed at `reset-native-check`:
`actual request count: 1 !== 0`. Fetch failed before headers, outside the
observer's catch, so one real request was not recorded. The original eleven
rows remain in `first-instrumentation-run.jsonl`; that run is not counted as
passing. Commit `7d88b2f` records pre-header failures, including actual zero
bytes, and removes the unsupported assumption that a TCP reset always
delivers a nonempty prefix. Zero-write requirements were not relaxed.

Complete/length/drop argument hashes, original IDs and lifecycle fingerprints
match across clients; only volatile `created` timestamps are omitted from the
comparison fingerprint, never from bytes supplied to the SDK or PSJ. TCP reset
delivery can differ: the current-pin PSJ run observed 4,754 bytes, while its
native runs observed none. Reset therefore supplies three real transport
controls, not byte-identical paired inputs. In every reset run no response body
was released to the SDK by the shared buffering fetch, and no file was written.

The recorded SDK `sdk_tool_calls` projection was empty in these graph outputs.
Identity evidence comes from the actual callback configuration, ToolMessages
and outgoing tool-result IDs.
