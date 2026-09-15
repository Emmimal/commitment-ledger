"""
Commitment Ledger — pure Python, standard library only.

Turns commitments extracted by detector.py into an explicit, append-only
event history per commitment, and mechanically flags coordination
failures from that history plus a frozen dependency map.

No LLM, database, vector store, API, or framework involved. State
transitions beyond the initial COMMITTED event (STARTED, IMPLEMENTED,
TESTED, REPORTED, VERIFIED, ABANDONED) are driven by explicit events fed
in by the caller — in a real deployment these would come from actual
file diffs / test-run results; in this project they are read from
explicit [EVENT] markers in the example transcripts (see evaluator.py
and transcripts/README notes). CONFLICTED is the one event the ledger
generates itself, at registration time.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Tuple

# Frozen dependency map for the "Minimal Item Catalog Feature" example
# task (see README).
DEPENDENCY_MAP: Dict[str, List[str]] = {
    "models/item.py": [],
    "repository/items.py": ["models/item.py"],
    "services/pricing.py": ["models/item.py"],
    "/items": ["repository/items.py", "services/pricing.py"],
    "tests/test_catalog.py": [
        "models/item.py", "repository/items.py", "services/pricing.py", "/items",
    ],
}

HAPPY_PATH = ["COMMITTED", "STARTED", "IMPLEMENTED", "TESTED", "REPORTED", "VERIFIED"]
TERMINAL_FAILURE_EVENTS = {"ABANDONED", "CONFLICTED"}
IMPLEMENTED_OR_LATER = {"IMPLEMENTED", "TESTED", "REPORTED", "VERIFIED"}


@dataclass
class Commitment:
    commitment_id: str
    agent: str
    verb: str
    obj: str
    raw_utterance: str
    turn_index: int
    history: List[Tuple[str, int]] = field(default_factory=list)  # (event, turn_index)

    def add_event(self, event: str, turn_index: int) -> None:
        self.history.append((event, turn_index))

    def current_state(self) -> str:
        return self.history[-1][0] if self.history else "UNKNOWN"

    def reached(self, event: str) -> bool:
        return any(e == event for e, _ in self.history)

    def is_terminal_failure(self) -> bool:
        return self.current_state() in TERMINAL_FAILURE_EVENTS


class Ledger:
    def __init__(self) -> None:
        self.commitments: Dict[str, Commitment] = {}
        self._next_id = 1
        # object -> commitment_id of the currently active (non-conflicted) owner
        self._active_by_object: Dict[str, str] = {}

    def _new_id(self) -> str:
        cid = f"C{self._next_id}"
        self._next_id += 1
        return cid

    def register_commitment(self, agent: str, verb: str, obj: str,
                             raw_utterance: str, turn_index: int) -> Commitment:
        """Register a new COMMITTED event.

        Mechanically detects a conflict if a different agent already holds
        an active (non-terminal) commitment on the same object. This is
        the ledger's core value over leaving commitments in the chat
        stream: the conflict is caught the instant the second claim is
        made, not discovered later by accident.

        Only the NEW (duplicate) commitment is marked CONFLICTED. The
        original commitment's own history is never rewritten just because
        someone else later re-claims its object -- its legitimate
        progress (e.g. already REPORTED) must not be corrupted by a
        redundant claim made against it.
        """
        existing_id = self._active_by_object.get(obj)
        commitment = Commitment(
            commitment_id=self._new_id(),
            agent=agent, verb=verb, obj=obj,
            raw_utterance=raw_utterance, turn_index=turn_index,
        )
        commitment.add_event("COMMITTED", turn_index)
        self.commitments[commitment.commitment_id] = commitment

        if existing_id is not None:
            existing = self.commitments[existing_id]
            if existing.agent != agent and not existing.is_terminal_failure():
                commitment.add_event("CONFLICTED", turn_index)
                return commitment  # do not become the new active owner

        self._active_by_object[obj] = commitment.commitment_id
        return commitment

    def advance(self, commitment_id: str, event: str, turn_index: int) -> None:
        if commitment_id not in self.commitments:
            raise KeyError(f"Unknown commitment id: {commitment_id}")
        self.commitments[commitment_id].add_event(event, turn_index)

    def latest_commitment_for(self, agent: str, obj: str) -> Commitment:
        """Most recently registered commitment matching (agent, obj) --
        used when advancing state from transcript [EVENT] lines, since an
        object can have more than one commitment (e.g. a conflicted
        duplicate)."""
        matches = [c for c in self.commitments.values()
                   if c.agent == agent and c.obj == obj]
        if not matches:
            raise KeyError(f"No commitment found for agent={agent!r} obj={obj!r}")
        return matches[-1]

    # ---- Mechanical failure-mode detection (all computed, none self-reported) ----

    def missed_commitments(self) -> List[Commitment]:
        """Never progressed beyond COMMITTED or STARTED."""
        return [c for c in self.commitments.values()
                if c.current_state() in ("COMMITTED", "STARTED")]

    def unverified_commitments(self) -> List[Commitment]:
        """Reached REPORTED but never VERIFIED."""
        return [c for c in self.commitments.values()
                if c.reached("REPORTED") and not c.reached("VERIFIED")]

    def conflicted_commitments(self) -> List[Commitment]:
        return [c for c in self.commitments.values() if c.reached("CONFLICTED")]

    def dependency_not_notified(self) -> List[Tuple[Commitment, str]]:
        """A commitment reaches IMPLEMENTED (or later) while a declared
        prerequisite object has no commitment that has itself reached
        IMPLEMENTED (or later)."""
        findings: List[Tuple[Commitment, str]] = []
        latest_by_object: Dict[str, Commitment] = {}
        for c in self.commitments.values():
            if c.current_state() == "CONFLICTED":
                continue
            latest_by_object[c.obj] = c

        for c in self.commitments.values():
            if not any(c.reached(e) for e in IMPLEMENTED_OR_LATER):
                continue
            for dep in DEPENDENCY_MAP.get(c.obj, []):
                dep_commitment = latest_by_object.get(dep)
                if dep_commitment is None or not any(
                    dep_commitment.reached(e) for e in IMPLEMENTED_OR_LATER
                ):
                    findings.append((c, dep))
        return findings

    def rework(self) -> List[Commitment]:
        """Reached IMPLEMENTED (or later), then was abandoned."""
        return [c for c in self.commitments.values()
                if c.current_state() == "ABANDONED"
                and any(c.reached(e) for e in IMPLEMENTED_OR_LATER)]

    def coordination_report(self) -> Dict[str, list]:
        return {
            "missed_commitments": self.missed_commitments(),
            "unverified_commitments": self.unverified_commitments(),
            "conflicted_commitments": self.conflicted_commitments(),
            "dependency_not_notified": self.dependency_not_notified(),
            "rework": self.rework(),
        }
