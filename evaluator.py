"""
Evaluator — parses a saved agent transcript, feeds it through detector.py
and ledger.py, and prints a coordination report.

Transcript line formats:
    Agent A: <natural language dialogue>
    [EVENT] Agent A <object> <EVENT_NAME>

Dialogue lines are run through the frozen commitment detector; any line
classified COMMITMENT registers a new commitment. [EVENT] lines advance
an existing commitment's state (see ledger.py's docstring for why state
transitions beyond COMMITTED are read from explicit markers rather than
re-derived from prose -- that would require a second, unfrozen grammar,
which this project deliberately does not build).

Pure Python, standard library only.
"""

import re
import sys
from typing import List

from detector import classify
from ledger import Ledger, Commitment

DIALOGUE_LINE = re.compile(r"^Agent\s+(\w+):\s*(.*)$")
EVENT_LINE = re.compile(r"^\[EVENT\]\s+Agent\s+(\w+)\s+(\S+)\s+(\w+)\s*$")


def parse_transcript(path: str) -> Ledger:
    ledger = Ledger()
    with open(path, encoding="utf-8") as f:
        lines = [line.rstrip("\n") for line in f]

    for turn_index, raw_line in enumerate(lines):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        event_match = EVENT_LINE.match(line)
        if event_match:
            agent, obj, event = event_match.groups()
            commitment = ledger.latest_commitment_for(agent, obj)
            ledger.advance(commitment.commitment_id, event, turn_index)
            continue

        dialogue_match = DIALOGUE_LINE.match(line)
        if dialogue_match:
            agent, utterance = dialogue_match.groups()
            result = classify(utterance)
            if result["detector_label"] == "COMMITMENT":
                ledger.register_commitment(
                    agent=agent,
                    verb=result["detected_verb"],
                    obj=result["detected_object"],
                    raw_utterance=utterance,
                    turn_index=turn_index,
                )
            continue

    return ledger


def _describe(c: Commitment) -> str:
    return f"{c.commitment_id} ({c.agent} -> {c.obj}): \"{c.raw_utterance}\""


def print_report(label: str, ledger: Ledger) -> dict:
    report = ledger.coordination_report()
    print(f"\n=== Coordination report: {label} ===")
    print(f"Total commitments registered: {len(ledger.commitments)}")

    print(f"\nMissed commitments ({len(report['missed_commitments'])}):")
    for c in report["missed_commitments"]:
        print(f"  - {_describe(c)}  [state={c.current_state()}]")

    print(f"\nUnverified commitments ({len(report['unverified_commitments'])}):")
    for c in report["unverified_commitments"]:
        print(f"  - {_describe(c)}  [state={c.current_state()}]")

    print(f"\nConflicted commitments ({len(report['conflicted_commitments'])}):")
    for c in report["conflicted_commitments"]:
        print(f"  - {_describe(c)}")

    print(f"\nDependency-not-notified findings ({len(report['dependency_not_notified'])}):")
    for c, dep in report["dependency_not_notified"]:
        print(f"  - {_describe(c)}  [missing prerequisite: {dep}]")

    print(f"\nRework ({len(report['rework'])}):")
    for c in report["rework"]:
        print(f"  - {_describe(c)}")

    counts = {k: len(v) for k, v in report.items()}
    return counts


def compare(labels_and_paths: List[tuple]) -> None:
    all_counts = {}
    for label, path in labels_and_paths:
        ledger = parse_transcript(path)
        counts = print_report(label, ledger)
        all_counts[label] = counts

    print("\n=== Side-by-side summary ===")
    metrics = ["missed_commitments", "unverified_commitments", "conflicted_commitments",
               "dependency_not_notified", "rework"]
    header = f"{'metric':28s}" + "".join(f"{label:>18s}" for label, _ in labels_and_paths)
    print(header)
    for m in metrics:
        row = f"{m:28s}" + "".join(f"{all_counts[label][m]:>18d}" for label, _ in labels_and_paths)
        print(row)


if __name__ == "__main__":
    compare([
        ("chat-only", "transcripts/chat_only.txt"),
        ("chat+ledger", "transcripts/chat_with_ledger.txt"),
    ])
