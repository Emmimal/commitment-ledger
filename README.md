# commitment-ledger

![Python](https://img.shields.io/badge/python-3.12-blue) ![License](https://img.shields.io/badge/license-MIT-green) ![Dependencies](https://img.shields.io/badge/dependencies-stdlib%20only-brightgreen)

A pure-Python commitment-tracking layer for multi-agent coding systems — conflict detection, dependency checks, and coordination reporting in one deterministic pipeline.

Multi-agent coding agents can communicate perfectly well and still duplicate work, miss a dependency, or report something as done that was never checked. This library turns a natural-language commitment ("I'll implement repository/items.py") into explicit, checkable state instead of leaving it buried in a chat transcript — no LLM, no database, no API, nothing beyond the Python standard library.

> Read the full write-up on Towards Data Science → *(link added once published)*

## What It Does

```
Coding-agent conversation
          |
          v
   Commitment Detector        <- frozen grammar, no LLM
          |
          v
   Commitment Ledger          <- immutable event history per commitment
          |
   +------+------+
   v             v
Conflict     Dependency
 Check         Check
   +------+------+
          v
   Coordination Report
```

Three components, one pipeline:

| Component | Job |
|---|---|
| `detector.py` | recognizes a narrow, frozen grammar (`I'll <verb> <object>`, 13-word verb list, 6 concrete-object rules) — no model call |
| `ledger.py` | records each commitment as an append-only event history (`COMMITTED → STARTED → IMPLEMENTED → TESTED → REPORTED → VERIFIED`, plus `ABANDONED`/`CONFLICTED`) and computes five coordination-failure findings mechanically |
| `evaluator.py` | parses a saved transcript, feeds it through the detector and ledger, prints a coordination report |

## Installation

```bash
git clone https://github.com/Emmimal/commitment-ledger.git
cd commitment-ledger
pip install pytest   # only needed to run the test suite
```

No other dependencies. Every runtime module — `detector.py`, `ledger.py`, `evaluator.py` — uses only the Python standard library. No API key, no network access, no database.

## Quick Start

```python
from ledger import Ledger
from detector import classify

ledger = Ledger()

# Detector: turn a natural-language line into a structured event
result = classify("I'll implement repository/items.py.")
# {'detector_label': 'COMMITMENT', 'detected_verb': 'implement',
#  'detected_object': 'repository/items.py', 'detected_object_rule': 'file_path', ...}

if result["detector_label"] == "COMMITMENT":
    c = ledger.register_commitment(
        agent="A",
        verb=result["detected_verb"],
        obj=result["detected_object"],
        raw_utterance="I'll implement repository/items.py.",
        turn_index=0,
    )

ledger.advance(c.commitment_id, "STARTED", 1)
ledger.advance(c.commitment_id, "IMPLEMENTED", 2)

report = ledger.coordination_report()
print(report["missed_commitments"])       # []
print(report["unverified_commitments"])   # []
```

## Running the Demo

Two hand-authored example transcripts of the same small task — one where two agents coordinate through chat only, one where they check the ledger before claiming work:

```bash
python3 evaluator.py
```

```
=== Coordination report: chat-only ===
Total commitments registered: 5
Missed commitments (1): ...
Unverified commitments (1): ...
Conflicted commitments (1): ...
Dependency-not-notified findings (1): ...
Rework (1): ...

=== Coordination report: chat+ledger ===
Total commitments registered: 5
Missed commitments (1): ...
Unverified commitments (1): ...
Conflicted commitments (0):
Dependency-not-notified findings (0):
Rework (0):
```

| Metric | Chat-only | Chat + Ledger |
|---|---|---|
| Missed commitments | 1 | 1 |
| Unverified commitments | 1 | 1 |
| Conflicted commitments | 1 | 0 |
| Dependency not notified | 1 | 0 |
| Rework | 1 | 0 |

The code processing both transcripts is identical — only the dialogue differs. Missed and unverified commitments are unchanged in both conditions: the ledger prevents coordination failures caused by not knowing what another agent already claimed, but it does not make an agent finish a task or independently verify that reported work is correct. See the write-up for the full breakdown.

## Running the Tests

```bash
python3 -m pytest tests/ -v
```

12 tests: a 150-row regression set for the detector (`tests/test_detector.py`, 100% precision/recall/0% false-positive rate against `tests/fixtures/commitment_detector_dataset_v1.csv`) and unit tests for every ledger failure mode (`tests/test_ledger.py`).

## Project Structure

```
commitment-ledger/
├── detector.py              # frozen commitment detector (v1)
├── ledger.py                 # the Commitment Ledger itself
├── evaluator.py               # parses a transcript, prints a coordination report
├── transcripts/
│   ├── chat_only.txt          # baseline: no commitment tracking
│   └── chat_with_ledger.txt   # same task, agents aware of the ledger
├── tests/
│   ├── test_detector.py       # 150-row regression test for detector.py
│   ├── test_ledger.py         # unit tests for the ledger's failure-mode detection
│   └── fixtures/
│       └── commitment_detector_dataset_v1.csv
├── docs/
│   └── archived/
│       └── task-and-agent-protocol.md   # superseded live-agent plan; history only
└── README.md
```

## Commitment Grammar Reference

Four surface forms: `I will <verb> <object>`, `I'll <verb> <object>`, `I am going to <verb> <object>`, `I'm going to <verb> <object>`.

Verb vocabulary: `add, create, delete, implement, modify, remove, rename, refactor, update, fix, test, document, review`.

| Object rule | Example | Matches |
|---|---|---|
| `file_path` | `repository/items.py` | recognized extension, optional directory segments |
| `snake_case` | `stock_tracker` | lowercase, underscore-separated |
| `camel_pascal` | `ItemRepository` | contains a lowercase-to-uppercase transition |
| `dotted_path` | `pricing.rules` | dot-separated segments, each ≥2 characters |
| `quoted` | `"item listing"` | a complete matched quoted span |
| `endpoint_path` | `/items` | leading slash |

Anything else — including a valid verb with a vague object (`"I'll update the pricing rules."`) — is `NOT_A_COMMITMENT`. No semantic fallback.

## Known Limitations

- **One commitment per line.** The detector is anchored to the start of the string it receives, so a commitment clause buried mid-sentence (`"Repository and pricing both look done, so I'll implement /items now."`) is not detected. The example transcripts give each commitment its own line for this reason.
- **Dotted-path ambiguity.** There is no syntactic way to distinguish a mistyped file extension (`repository.pyz`) from a legitimate short module attribute (`models.item`). The detector favors recall — it accepts both — rather than risk silently dropping real commitments like `services.export`.
- **`dependency_not_notified()` resolves to the most recently *inserted* commitment per object, skipping only commitments whose current state is exactly `CONFLICTED`.** A commitment that was conflicted and later advanced further (e.g. `COMMITTED → CONFLICTED → IMPLEMENTED → ABANDONED`) is not excluded by that check, so it can still be selected as the "authoritative" record for its object ahead of the original, legitimate commitment. In the shipped example transcript this happens to produce the correct finding count, but it's a real edge case, not a guarantee — a fix under consideration is skipping any commitment that ever reached `CONFLICTED`, not just ones currently in that state.
- **State transitions past `COMMITTED` are not derived from language.** `STARTED`, `IMPLEMENTED`, `TESTED`, `REPORTED`, and `VERIFIED` come from explicit `[EVENT]` markers in the example transcripts, standing in for what would be real file-diff or test-run signals in a production deployment.
- **The dependency map is hand-written** (`ledger.py`'s `DEPENDENCY_MAP`), not derived from a real codebase.
- **Two agents only.** The conflict-detection logic doesn't structurally assume exactly two, but hasn't been tested against three or more.

## When to Use This

Worth it when:
- Multiple coding agents work against a shared codebase with no pre-assigned file ownership
- One agent's output is another agent's input, and missed handoffs are costly
- You want a coordination-failure trace that doesn't depend on manually re-reading a chat log

Skip it when:
- You're running a single agent — there's no coordination state to track
- Agents already have strictly partitioned, non-overlapping file ownership
- You need verification that the work is *correct* — this system tracks coordination state, not code quality

## License

MIT
