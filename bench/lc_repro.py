"""One measured run of langchain `create_agent` against the fake model.

Entry and model string are the ones the official quickstart uses
(https://docs.langchain.com/oss/python/langchain/quickstart, read 2026-11-09):
`from langchain.agents import create_agent`, `create_agent(model="openai:gpt-5.5", ...)`.

The only differences from that quickstart are listed in
docs/preregistration/langchain-core-repro-v1.md §2: base_url points here, the tool
writes the case file instead of fetching weather, the prompt asks for the file,
and a marker field rides along in the tool arguments.

The fake server records the request path of every call, so "the client never used
the Responses API" is an observation, not an assumption.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

os.environ.setdefault("NO_PROXY", "127.0.0.1,localhost")  # a system proxy turns loopback calls into 502s
os.environ.setdefault("no_proxy", "127.0.0.1,localhost")

TARGET = "report.txt"
LINES = [f"line {i:02d}: the quick brown fox jumps over the lazy dog" for i in range(1, 41)]
FULL_CONTENT = "\n".join(LINES) + "\n"
CUT_MARKER = "line 17: the quick"
MARK_A = "BENCH-A"
MARK_B = "BENCH-B"
VARIANTS = ("chat-length", "chat-drop", "responses-incomplete", "responses-drop")


def make_workdir(prefix: str) -> Path:
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


def args_for(marker: str, cut: bool = True) -> str:
    payload = json.dumps({"bench_marker": marker, "path": TARGET, "content": FULL_CONTENT})
    if not cut:
        return payload
    index = payload.index(CUT_MARKER)
    return payload[: index + len(CUT_MARKER)]


class State:
    def __init__(self) -> None:
        self.requests = 0
        self.raw = bytearray()
        self.paths: list[str] = []
        self.lock = threading.Lock()


STATE = State()


def _sse(obj: dict, event: str | None = None) -> bytes:
    prefix = f"event: {event}\n" if event else ""
    return (prefix + "data: " + json.dumps(obj) + "\n\n").encode()


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    variant = "chat-length"

    def log_message(self, *args):
        pass

    def _send(self, data: bytes) -> None:
        with STATE.lock:
            STATE.raw.extend(data)
        self.wfile.write(data)
        self.wfile.flush()

    def _sse(self, obj: dict, event: str | None = None) -> None:
        self._send(_sse(obj, event))

    def _json_turn(self, body: bytes, marker: str, responses: bool) -> None:
        follow_up = b"Wrote " in body
        if follow_up:
            payload = ({"id": "r2", "object": "response", "status": "completed", "model": "m",
                        "output": [{"id": "m2", "type": "message", "role": "assistant",
                                    "status": "completed",
                                    "content": [{"type": "output_text", "text": "Done.",
                                                 "annotations": []}]}]}
                       if responses else
                       {"id": "c2", "object": "chat.completion", "created": 0, "model": "m",
                        "choices": [{"index": 0, "finish_reason": "stop",
                                     "message": {"role": "assistant", "content": "Done."}}]})
            raw = json.dumps(payload).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
            return

        arguments = args_for(marker, cut=True)
        if responses:
            payload = {"id": "r1", "object": "response",
                       "status": "incomplete" if self.variant == "responses-incomplete" else "completed",
                       "incomplete_details": ({"reason": "max_output_tokens"}
                                              if self.variant == "responses-incomplete" else None),
                       "model": "m",
                       "output": [{"id": "fc1", "type": "function_call", "call_id": "call_1",
                                   "name": "write_file", "arguments": arguments,
                                   "status": "incomplete"}]}
        else:
            finish = "length" if self.variant == "chat-length" else "length"
            payload = {"id": "c1", "object": "chat.completion", "created": 0, "model": "m",
                       "choices": [{"index": 0, "finish_reason": finish,
                                    "message": {"role": "assistant", "content": None,
                                                "tool_calls": [{"id": "call_1", "type": "function",
                                                                "function": {"name": "write_file",
                                                                             "arguments": arguments}}]}}]}
        raw = json.dumps(payload).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        if self.variant.endswith("drop"):
            self.wfile.write(raw[: len(raw) // 2])  # body stops mid-JSON
            self.wfile.flush()
            self.close_connection = True
            return
        self.wfile.write(raw)

    def do_POST(self):  # noqa: N802
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else b"{}"
        with STATE.lock:
            STATE.requests += 1
            number = STATE.requests
            STATE.paths.append(self.path)
        marker = MARK_A if number == 1 else MARK_B
        # Shape follows the endpoint the client actually used; the variant only
        # decides how the reply ends. (v1 derived the shape from the variant name,
        # so a Responses-shaped body was sent to a chat request.)
        responses = self.path.rstrip("/").endswith("/responses")
        try:
            wants_stream = bool(json.loads(body or b"{}").get("stream"))
        except json.JSONDecodeError:
            wants_stream = False

        if not wants_stream:
            # The default langchain path is a non-streaming call. Model the same
            # two endings on the JSON wire: an explicit truncation flag, or a body
            # that stops in the middle of the JSON.
            self._json_turn(body, marker, responses)
            return

        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Connection", "close")
        self.end_headers()

        if b"Wrote " in body:  # the tool ran; this is the follow-up turn
            if responses:
                item = {"id": "m2", "type": "message", "role": "assistant", "status": "completed",
                        "content": [{"type": "output_text", "text": "Done.", "annotations": []}]}
                self._sse({"type": "response.output_item.added", "output_index": 0,
                           "item": {**item, "status": "in_progress", "content": []}},
                          "response.output_item.added")
                self._sse({"type": "response.output_text.delta", "item_id": "m2", "output_index": 0,
                           "content_index": 0, "delta": "Done."}, "response.output_text.delta")
                self._sse({"type": "response.output_item.done", "output_index": 0, "item": item},
                          "response.output_item.done")
                self._sse({"type": "response.completed",
                           "response": {"id": "r2", "object": "response", "status": "completed",
                                        "model": "m", "output": [item]}}, "response.completed")
            else:
                self._sse({"id": "c2", "object": "chat.completion.chunk", "created": 0, "model": "m",
                           "choices": [{"index": 0,
                                        "delta": {"role": "assistant", "content": "Done."},
                                        "finish_reason": "stop"}]})
                self._send(b"data: [DONE]\n\n")
            return

        arguments = args_for(marker, cut=True)

        if responses:
            fc = {"id": "fc1", "type": "function_call", "call_id": "call_1",
                  "name": "write_file", "arguments": "", "status": "in_progress"}
            self._sse({"type": "response.created",
                       "response": {"id": "r1", "object": "response", "status": "in_progress",
                                    "model": "m", "output": []}}, "response.created")
            self._sse({"type": "response.output_item.added", "output_index": 0, "item": fc},
                      "response.output_item.added")
            self._sse({"type": "response.function_call_arguments.delta", "item_id": "fc1",
                       "output_index": 0, "delta": arguments},
                      "response.function_call_arguments.delta")
            if self.variant == "responses-incomplete":
                self._sse({"type": "response.incomplete",
                           "response": {"id": "r1", "object": "response", "status": "incomplete",
                                        "model": "m",
                                        "incomplete_details": {"reason": "max_output_tokens"},
                                        "output": [dict(fc, arguments=arguments,
                                                        status="incomplete")]}},
                          "response.incomplete")
            return

        def chunk(delta: dict, finish: str | None = None) -> dict:
            return {"id": "c1", "object": "chat.completion.chunk", "created": 0, "model": "m",
                    "choices": [{"index": 0, "delta": delta, "finish_reason": finish}]}

        self._sse(chunk({"role": "assistant",
                         "tool_calls": [{"index": 0, "id": "call_1", "type": "function",
                                         "function": {"name": "write_file",
                                                      "arguments": arguments}}]}))
        if self.variant == "chat-length":
            self._sse(chunk({}, "length"))
            self._send(b"data: [DONE]\n\n")


def make_handler(variant: str):
    return type("BoundHandler", (Handler,), {"variant": variant})


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--variant", required=True, choices=VARIANTS)
    parser.add_argument("--run", type=int, required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--evidence", required=True)
    parser.add_argument("--timeout", type=float, default=180.0)
    args = parser.parse_args()

    workdir = make_workdir(f"lc-{args.variant}-")
    evidence_dir = Path(args.evidence)
    evidence_dir.mkdir(parents=True, exist_ok=True)

    server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(args.variant))
    port = server.server_address[1]
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base_url = f"http://127.0.0.1:{port}/{args.variant}/v1"
    os.environ["OPENAI_BASE_URL"] = base_url
    os.environ["OPENAI_API_KEY"] = "unused"

    from langchain.agents import create_agent
    from langchain.tools import tool
    import langchain
    import langchain_core

    @tool
    def write_file(path: str, content: str, bench_marker: str = "") -> str:
        """Write a text file to disk."""
        target = workdir / Path(path or TARGET).name
        target.write_text(content, encoding="utf-8")
        with (workdir / "calls.jsonl").open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({
                "marker": bench_marker or "none",
                "bytes": len(content.encode("utf-8")),
                "newline_lines": content.count("\n"),
            }) + "\n")
        return f"Wrote {len(content)} characters to {target.name}"

    started = time.perf_counter()
    error = None
    answer = None
    try:
        agent = create_agent(model="openai:gpt-5.5", tools=[write_file],
                             system_prompt="You are a helpful assistant")
        result = agent.invoke({"messages": [
            {"role": "user", "content": "Write report.txt with the forty lines."}]})
        answer = str(result["messages"][-1].content_blocks)[:300]
    except Exception as exc:  # a client error is data
        error = f"{type(exc).__name__}: {str(exc)[:400]}"
    finally:
        duration = round(time.perf_counter() - started, 3)
        server.shutdown()
        server.server_close()

    raw_path = evidence_dir / f"{args.variant}-run{args.run}.sse"
    raw_path.write_bytes(bytes(STATE.raw))

    target = workdir / TARGET
    disk = {"file_written": False}
    if target.exists():
        data = target.read_text(encoding="utf-8")
        disk = {"file_written": True, "lines": data.count("\n"),
                "bytes": len(data.encode("utf-8")),
                "sha256": hashlib.sha256(data.encode("utf-8")).hexdigest()}

    calls = []
    log = workdir / "calls.jsonl"
    if log.exists():
        calls = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines() if line.strip()]

    record = {
        "framework": "langchain",
        "version_langchain": getattr(langchain, "__version__", "?"),
        "version_langchain_core": getattr(langchain_core, "__version__", "?"),
        "variant": args.variant,
        "run": args.run,
        "requests": STATE.requests,
        "request_paths": STATE.paths,
        "tool_calls": calls,
        "tool_called": bool(calls),
        "disk": disk,
        "answer": answer,
        "error": error,
        "duration_s": duration,
        "evidence": str(raw_path),
        "evidence_sha256": hashlib.sha256(raw_path.read_bytes()).hexdigest(),
        "timestamp": round(time.time(), 3),
        "python": sys.version.split()[0],
    }
    with Path(args.out).open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    print(json.dumps({k: record[k] for k in
                      ("variant", "run", "requests", "request_paths", "tool_called",
                       "disk", "error")}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
