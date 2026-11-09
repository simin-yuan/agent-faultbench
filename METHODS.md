# How this benchmark is measured

This file describes **how** a cell is produced. It deliberately does not describe how
the cases and the clients were chosen.

## 1. Default path

> A client's default path is the entry that its **official quickstart** demonstrates.

For every row the pre-registration records: the entry name, the document URL, the date
it was read, and a complete list of every deviation from that document. Deviations are
kept to the minimum (usually: point the client's base URL at the local server, swap the
demo tool for a file write, and use a scratch directory).

The rule exists because "which entry to test" is the largest degree of freedom in a
cross-framework comparison. Fixing it to an external document removes that freedom.

## 2. Pre-registration

Three commits, in this order, for every measured set:

1. the pre-registration (rules, scope, expected values, prediction) — pushed first;
2. the runs — no commit;
3. the results — committed on their own, then an annotated tag.

Rules are not adjusted to fit results. If the instrument changes after the
pre-registration is pushed, a new amendment is pushed **before** the runs that count.
A prediction that turns out to be wrong is **left in place and marked wrong**; it is
never rewritten.

## 3. What is judged

Four fields, compared cell by cell, three runs each:

| Field | Meaning |
|---|---|
| verdict | did a call reach the tool at all |
| lines | newline-terminated lines in the written file |
| bytes | size of that file |
| sha256 | content hash |

All four must match, on all three runs. A cell whose three runs disagree is reported as
**unstable** and is neither a pass nor a fail.

States: `executed`, `not-executed`, `not-measurable`, `error`. `not-measurable` means
the client never requested the wire endpoint the variant needs — it is excluded from
the denominator, never counted as a pass.

## 4. How a "not executed" is explained (BT)

Not executing can be skill or luck:

- `blocked-by-end-signal` — the client checked that the reply had finished;
- `blocked-by-parse` — a parser rejected the payload; the client never got the chance
  to be wrong;
- `unknown` — the record cannot distinguish the two.

A label needs evidence. `blocked-by-parse` is only written when the captured client log
contains the parse error; otherwise the cell is `unknown`.

The cleanest way to tell them apart is a **control that differs in exactly one
variable**: the same truncated payload, but with a normal end signal. If the control
executes and the truncated variant does not, the client checked the end signal. If
neither executes, the parser was doing the work.

## 5. What the fake server does and does not do

- It speaks the OpenAI Chat Completions and Responses wire formats enough to be a drop-in
  base URL for the clients under test.
- It records every request path, and the exact bytes it sent, per run.
- It answers the second and later requests of a run with a short, tool-call-free reply,
  so a retrying client cannot re-read the same truncated reply and double the evidence.
- It does **not** attempt to imitate a provider's behaviour, latency or error rates.
  It shows what a client does with a given wire response; it says nothing about how
  often such a response occurs in the wild.

## 6. Failures of method we have already made

Recorded because a benchmark that only publishes its successes is not trustworthy.
Each one is a real defect caught before or after a run, and each is now a rule.

| What happened | Why it is dangerous | Rule now |
|---|---|---|
| A judgement that compared only "did it execute", not the file's size | reported a false all-pass; only a human noticing a byte count caught it | compare all four fields |
| A pre-registration and its results in the same commit | the repository cannot prove the rules came first | three commits, rules pushed first |
| Top-level packages pinned, transitive dependencies floating | another machine resolves a different tree | a universal lock file with hashes |
| Evidence read as text on a CRLF checkout | every file looked different by one byte per line | evidence marked binary in `.gitattributes` |
| A results path that the runner overwrote before comparing | the run would be compared against a baseline it had just replaced | the runner refuses to overwrite; expected values come from a git ref |
| A stimulus whose execution left nothing on disk | "executed" and "not executed" became indistinguishable | ask first: if it runs, where does it leave a trace |
| A judgement label written from the design, not from evidence | assumption dressed as measurement | a label without evidence is `unknown` |
| "Any of three runs" used to summarise a cell | turns n=3 into n=1 | require all three |
| A truncated stimulus repeated on every request | one execution counted twice | state what later requests answer |

