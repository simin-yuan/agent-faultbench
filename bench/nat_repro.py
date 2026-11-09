"""One NAT run against one truncation variant.

This is the step-1 reproduction harness: it starts a fake OpenAI-compatible
server, runs a pinned NVIDIA NeMo Agent Toolkit (1.9.0) workflow against it, and
records what the tool actually received and what landed on disk.

Variants (all streaming, which is how NAT talks to a model):
    chat-length            Chat Completions, finish_reason="length"          + [DONE]
    chat-drop              Chat Completions, body ends: no finish_reason, no [DONE]
    responses-incomplete   Responses, response.incomplete (max_output_tokens)
    responses-drop         Responses, body ends: no response.completed

Agent types:
    tool_calling_agent               default settings, _type: openai
    react_agent                      use_native_tool_calling: true

Markers: the content of the tool arguments starts with "BENCH-A|" on the first
request of a run and "BENCH-B|" on any later request. The marker is stripped
before the file is written, so the disk artifact is byte-identical to the old
bench (2,120 bytes complete, 866 bytes truncated). Rationale for putting the
marker inside `content` rather than as an extra argument key: an extra key
changes the tool schema, and a framework that rejects the call would turn a
real fail into a not-measurable.

Usage:
    python bench/nat_repro.py --agent tool_calling_agent --variant chat-drop \
        --run 1 --out runs.jsonl --evidence evidence/
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import sys
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

os.environ.setdefault("NO_PROXY", "127.0.0.1,localhost")
os.environ.setdefault("no_proxy", "127.0.0.1,localhost")

TARGET = "report.txt"
LINES = [f"line {i:02d}: the quick brown fox jumps over the lazy dog" for i in range(1, 41)]
FULL_CONTENT = "\n".join(LINES) + "\n"          # 2,120 bytes
CUT_MARKER = "line 17: the quick"

MARK_A = "BENCH-A"
MARK_B = "BENCH-B"
REACT_FINAL = "Thought: I now know the final answer\nFinal Answer: Done."

VARIANTS = ("chat-length", "chat-drop", "responses-incomplete", "responses-drop")
AGENTS = ("tool_calling_agent", "react_agent")


def args_for(marker: str, cut: bool) -> str:
    # v3: the marker is its own argument field (first key), not part of `content`.
    payload = json.dumps({"bench_marker": marker, "path": TARGET, "content": FULL_CONTENT})
    if not cut:
        return payload
    index = payload.index(CUT_MARKER)
    return payload[: index + len(CUT_MARKER)]


class RunState:
    def __init__(self) -> None:
        self.requests = 0
        self.raw = bytearray()
        self.lock = threading.Lock()
        self.tool_calls: list[dict] = []

    def next_request(self) -> int:
        with self.lock:
            self.requests += 1
            return self.requests


STATE = RunState()


def sse_bytes(obj: dict, event: str | None = None) -> bytes:
    prefix = f"event: {event}\n" if event else ""
    return (prefix + "data: " + json.dumps(obj) + "\n\n").encode()


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    variant: str = "chat-length"
    agent: str = "tool_calling_agent"

    def log_message(self, *args):  # quiet
        pass

    def _send(self, data: bytes) -> None:
        with STATE.lock:
            STATE.raw.extend(data)
        self.wfile.write(data)
        self.wfile.flush()

    def _sse(self, obj: dict, event: str | None = None) -> None:
        self._send(sse_bytes(obj, event))

    def do_POST(self):  # noqa: N802
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else b"{}"
        request_no = STATE.next_request()
        marker = MARK_A if request_no == 1 else MARK_B
        responses = self.variant.startswith("responses")

        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Connection", "close")
        self.end_headers()

        if b"Wrote " in body:  # the tool ran: this is the follow-up turn
            reply = REACT_FINAL if self.agent == "react_agent" else "Done."
            if responses:
                item = {
                    "id": "m2",
                    "type": "message",
                    "role": "assistant",
                    "status": "completed",
                    "content": [{"type": "output_text", "text": reply, "annotations": []}],
                }
                self._sse(
                    {"type": "response.output_item.added", "output_index": 0,
                     "item": {**item, "status": "in_progress", "content": []}},
                    "response.output_item.added",
                )
                self._sse(
                    {"type": "response.output_text.delta", "item_id": "m2", "output_index": 0,
                     "content_index": 0, "delta": reply},
                    "response.output_text.delta",
                )
                self._sse({"type": "response.output_item.done", "output_index": 0, "item": item},
                          "response.output_item.done")
                self._sse(
                    {"type": "response.completed",
                     "response": {"id": "r2", "object": "response", "status": "completed",
                                  "model": "m", "output": [item]}},
                    "response.completed",
                )
            else:
                self._sse(
                    {"id": "c2", "object": "chat.completion.chunk", "created": 0, "model": "m",
                     "choices": [{"index": 0, "delta": {"role": "assistant", "content": reply},
                                  "finish_reason": "stop"}]}
                )
                self._send(b"data: [DONE]\n\n")
            return

        # All four variants send the same cut-off arguments; only the way the
        # response ends differs. (v1 of this file sent COMPLETE arguments for
        # `chat-length`, which made the stimulus wrong; see the v2
        # pre-registration.)
        arguments = args_for(marker, cut=True)

        if responses:
            fc = {"id": "fc1", "type": "function_call", "call_id": "call_1",
                  "name": "write_file", "arguments": "", "status": "in_progress"}
            self._sse(
                {"type": "response.created",
                 "response": {"id": "r1", "object": "response", "status": "in_progress",
                              "model": "m", "output": []}},
                "response.created",
            )
            self._sse({"type": "response.output_item.added", "output_index": 0, "item": fc},
                      "response.output_item.added")
            self._sse(
                {"type": "response.function_call_arguments.delta", "item_id": "fc1",
                 "output_index": 0, "delta": arguments},
                "response.function_call_arguments.delta",
            )
            if self.variant == "responses-incomplete":
                self._sse(
                    {"type": "response.incomplete",
                     "response": {"id": "r1", "object": "response", "status": "incomplete",
                                  "model": "m",
                                  "incomplete_details": {"reason": "max_output_tokens"},
                                  "output": [dict(fc, arguments=arguments, status="incomplete")]}},
                    "response.incomplete",
                )
            # responses-drop: the body simply ends, no response.completed
            return

        def chunk(delta: dict, finish: str | None = None) -> dict:
            return {"id": "c1", "object": "chat.completion.chunk", "created": 0, "model": "m",
                    "choices": [{"index": 0, "delta": delta, "finish_reason": finish}]}

        self._sse(
            chunk({"role": "assistant",
                   "tool_calls": [{"index": 0, "id": "call_1", "type": "function",
                                   "function": {"name": "write_file", "arguments": arguments}}]})
        )
        if self.variant == "chat-length":
            self._sse(chunk({}, "length"))
            self._send(b"data: [DONE]\n\n")
        # chat-drop: nothing more; the body ends cleanly


def make_handler(agent: str, variant: str):
    return type("BoundHandler", (Handler,), {"agent": agent, "variant": variant})


# ---------------------------------------------------------------- NAT side
# These must live at module level: NAT reads the tool signature with
# `inspect.signature(..., eval_str=True)`, which evaluates annotations against
# the function's module globals. A class defined inside a function is invisible
# there (found by the first smoke run, before any measurement).
try:
    from pydantic import BaseModel

    from nat.builder.builder import Builder
    from nat.builder.function_info import FunctionInfo
    from nat.cli.register_workflow import register_function
    from nat.data_models.function import FunctionBaseConfig
except ImportError as _import_exc:  # pragma: no cover - environment dependent
    print(json.dumps({"not_installed": f"{type(_import_exc).__name__}: {_import_exc}"}))
    raise SystemExit(42)

WORKDIR: Path | None = None


class WriteArgs(BaseModel):
    bench_marker: str = ""
    path: str
    content: str


class WriteFileConfig(FunctionBaseConfig, name="faultbench_write_file"):
    pass


@register_function(config_type=WriteFileConfig)
async def faultbench_write_file(_config: WriteFileConfig, _builder: Builder):
    workdir = WORKDIR if WORKDIR is not None else Path.cwd()

    async def write_file(args: WriteArgs) -> str:
        raw = args.content
        marker = args.bench_marker or "none"
        target = workdir / Path(args.path or TARGET).name
        target.write_text(raw, encoding="utf-8")
        with (workdir / "calls.jsonl").open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({
                "marker": marker,
                "content_chars": len(raw),
                "bytes": len(raw.encode("utf-8")),
                "newline_lines": raw.count("\n"),
            }) + "\n")
        return f"Wrote {len(raw)} characters to {target.name}"

    yield FunctionInfo.from_fn(write_file, description="Write content to a file.")


def build_workflow(agent: str, base_url: str, workdir: Path):
    llm = {"_type": "openai", "base_url": base_url, "api_key": "x", "model_name": "m"}
    if "/responses-" in base_url:
        llm["api_type"] = "responses"

    workflow = {"_type": agent, "llm_name": "m", "tool_names": ["write_file"]}
    if agent == "react_agent":
        workflow["use_native_tool_calling"] = True

    config = {
        "functions": {"write_file": {"_type": "faultbench_write_file"}},
        "llms": {"m": llm},
        "workflow": workflow,
    }
    config_path = workdir / "nat-config.json"
    config_path.write_text(json.dumps(config), encoding="utf-8")
    return config_path


async def run_workflow_async(config_path: Path):
    from nat.utils import run_workflow

    return await run_workflow(
        config_file=config_path,
        prompt="Write the 40-line report to report.txt.",
    )


def make_workdir(prefix: str) -> Path:
    """Create a scratch directory, gitignored, inside the project.

    Two environment facts forced this: the interpreter created inside the project
    (`.envs/.../python.exe`) is denied writes to the system temp directory (WinError 5), while the
    base interpreter is not; and `tempfile.gettempdir()` therefore silently falls
    back to the current directory. So scratch dirs live in `<project>/.tmp`,
    which is ignored by git, and `tempfile` is not used at all.
    """
    base = Path(os.environ.get("BENCH_TMP") or Path(__file__).resolve().parent.parent / ".tmp")
    base.mkdir(parents=True, exist_ok=True)
    for _ in range(100):
        candidate = base / f"{prefix}{uuid.uuid4().hex[:8]}"
        try:
            candidate.mkdir()
            return candidate
        except FileExistsError:
            continue
    raise RuntimeError(f"could not create a work directory under {base}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--agent", required=True, choices=AGENTS)
    parser.add_argument("--variant", required=True, choices=VARIANTS)
    parser.add_argument("--run", type=int, required=True)
    parser.add_argument("--out", default="runs.jsonl")
    parser.add_argument("--evidence", default="evidence")
    parser.add_argument("--timeout", type=float, default=180.0)
    args = parser.parse_args()

    # tempfile is unusable here (see make_workdir); the base is pinned explicitly.
    workdir = make_workdir(f"nat-{args.agent}-{args.variant}-")
    global WORKDIR
    WORKDIR = workdir
    evidence_dir = Path(args.evidence)
    evidence_dir.mkdir(parents=True, exist_ok=True)

    server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(args.agent, args.variant))
    port = server.server_address[1]
    threading.Thread(target=server.serve_forever, daemon=True).start()

    base_url = f"http://127.0.0.1:{port}/{args.variant}/v1"
    started = time.perf_counter()
    error = None
    answer = None
    try:
        config_path = build_workflow(args.agent, base_url, workdir)
        answer = asyncio.run(
            asyncio.wait_for(run_workflow_async(config_path), timeout=args.timeout)
        )
    except Exception as exc:  # a client error is data, not a harness failure
        error = f"{type(exc).__name__}: {str(exc)[:400]}"
    finally:
        duration = round(time.perf_counter() - started, 3)
        server.shutdown()
        server.server_close()

    raw_path = evidence_dir / f"{args.agent}-{args.variant}-run{args.run}.sse"
    raw_path.write_bytes(bytes(STATE.raw))

    target = workdir / TARGET
    if target.exists():
        data = target.read_text(encoding="utf-8")
        disk = {
            "file_written": True,
            "lines": data.count("\n"),
            "bytes": len(data.encode("utf-8")),
            "sha256": hashlib.sha256(data.encode("utf-8")).hexdigest(),
            "last_line": data.splitlines()[-1] if data.splitlines() else "",
            "complete": data.count("\n") == 40 and data.startswith("line 01"),
        }
    else:
        disk = {"file_written": False}

    calls = []
    log = workdir / "calls.jsonl"
    if log.exists():
        calls = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines() if line.strip()]

    record = {
        "agent": args.agent,
        "variant": args.variant,
        "run": args.run,
        "requests": STATE.requests,
        "tool_calls": calls,
        "tool_called": bool(calls),
        "disk": disk,
        "answer": str(answer)[:300] if answer is not None else None,
        "error": error,
        "duration_s": duration,
        "evidence": str(raw_path),
        "evidence_sha256": hashlib.sha256(raw_path.read_bytes()).hexdigest(),
        "workdir_name": Path(workdir).name,  # never the absolute path: records get published
        "timestamp": round(time.time(), 3),
        "python": sys.version.split()[0],
    }

    with Path(args.out).open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")

    print(json.dumps({k: record[k] for k in
                      ("agent", "variant", "run", "tool_called", "disk", "error")},
                     ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
