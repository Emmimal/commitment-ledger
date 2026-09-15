import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from ledger import Ledger


def test_missed_commitment():
    ledger = Ledger()
    ledger.register_commitment("A", "test", "tests/test_catalog.py", "I will test tests/test_catalog.py.", 0)
    missed = ledger.missed_commitments()
    assert len(missed) == 1
    assert missed[0].obj == "tests/test_catalog.py"


def test_unverified_commitment():
    ledger = Ledger()
    c = ledger.register_commitment("A", "implement", "repository/items.py", "...", 0)
    ledger.advance(c.commitment_id, "STARTED", 1)
    ledger.advance(c.commitment_id, "IMPLEMENTED", 2)
    ledger.advance(c.commitment_id, "TESTED", 3)
    ledger.advance(c.commitment_id, "REPORTED", 4)
    unverified = ledger.unverified_commitments()
    assert len(unverified) == 1
    assert unverified[0].commitment_id == c.commitment_id


def test_verified_commitment_is_not_flagged_unverified():
    ledger = Ledger()
    c = ledger.register_commitment("A", "implement", "repository/items.py", "...", 0)
    for event, t in [("STARTED", 1), ("IMPLEMENTED", 2), ("TESTED", 3), ("REPORTED", 4), ("VERIFIED", 5)]:
        ledger.advance(c.commitment_id, event, t)
    assert ledger.unverified_commitments() == []
    assert ledger.missed_commitments() == []


def test_conflict_does_not_corrupt_original_commitments_history():
    ledger = Ledger()
    original = ledger.register_commitment("A", "implement", "repository/items.py", "...", 0)
    ledger.advance(original.commitment_id, "STARTED", 1)
    ledger.advance(original.commitment_id, "IMPLEMENTED", 2)
    ledger.advance(original.commitment_id, "TESTED", 3)
    ledger.advance(original.commitment_id, "REPORTED", 4)

    duplicate = ledger.register_commitment("B", "implement", "repository/items.py", "...", 5)

    # The duplicate is flagged conflicted.
    assert duplicate.current_state() == "CONFLICTED"
    conflicted = ledger.conflicted_commitments()
    assert len(conflicted) == 1
    assert conflicted[0].commitment_id == duplicate.commitment_id

    # The original's own history must be untouched -- it is still
    # legitimately REPORTED, not retroactively marked as conflicted.
    assert original.current_state() == "REPORTED"
    assert original.reached("CONFLICTED") is False


def test_same_agent_reclaiming_same_object_is_not_a_conflict():
    ledger = Ledger()
    first = ledger.register_commitment("A", "implement", "repository/items.py", "...", 0)
    second = ledger.register_commitment("A", "implement", "repository/items.py", "...", 1)
    assert second.current_state() != "CONFLICTED"


def test_dependency_not_notified():
    ledger = Ledger()
    items = ledger.register_commitment("B", "implement", "/items", "...", 0)
    ledger.advance(items.commitment_id, "STARTED", 1)
    ledger.advance(items.commitment_id, "IMPLEMENTED", 2)
    # Neither repository/items.py nor services/pricing.py were ever committed.
    findings = ledger.dependency_not_notified()
    deps_flagged = {dep for _, dep in findings}
    assert "repository/items.py" in deps_flagged
    assert "services/pricing.py" in deps_flagged


def test_dependency_satisfied_is_not_flagged():
    ledger = Ledger()
    user_model = ledger.register_commitment("A", "implement", "models/item.py", "...", 0)
    for event, t in [("STARTED", 1), ("IMPLEMENTED", 2)]:
        ledger.advance(user_model.commitment_id, event, t)

    repo = ledger.register_commitment("A", "implement", "repository/items.py", "...", 3)
    for event, t in [("STARTED", 4), ("IMPLEMENTED", 5)]:
        ledger.advance(repo.commitment_id, event, t)
    mw = ledger.register_commitment("A", "implement", "services/pricing.py", "...", 6)
    for event, t in [("STARTED", 7), ("IMPLEMENTED", 8)]:
        ledger.advance(mw.commitment_id, event, t)

    items = ledger.register_commitment("B", "implement", "/items", "...", 9)
    ledger.advance(items.commitment_id, "STARTED", 10)
    ledger.advance(items.commitment_id, "IMPLEMENTED", 11)

    findings = ledger.dependency_not_notified()
    assert findings == []


def test_rework_requires_prior_implemented_state():
    ledger = Ledger()
    c = ledger.register_commitment("A", "implement", "repository/items.py", "...", 0)
    ledger.advance(c.commitment_id, "STARTED", 1)
    ledger.advance(c.commitment_id, "ABANDONED", 2)
    # Never reached IMPLEMENTED -- abandoned early, not rework.
    assert ledger.rework() == []

    ledger2 = Ledger()
    c2 = ledger2.register_commitment("A", "implement", "repository/items.py", "...", 0)
    ledger2.advance(c2.commitment_id, "STARTED", 1)
    ledger2.advance(c2.commitment_id, "IMPLEMENTED", 2)
    ledger2.advance(c2.commitment_id, "ABANDONED", 3)
    assert len(ledger2.rework()) == 1
