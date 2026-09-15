"""
Regression test for the frozen detector: reruns the 150-row labeled set
and asserts the same result the detector was frozen against (100%
precision/recall, 0% false-positive rate). This is an engineering
regression test, not a statistical claim -- if any future change to
detector.py breaks this, that is the signal to stop and diagnose, not
to edit this test to pass.
"""

import csv
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from detector import classify

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "commitment_detector_dataset_v1.csv")


def _load_rows():
    with open(FIXTURE, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def test_150_row_regression_is_perfect():
    rows = _load_rows()
    assert len(rows) == 150

    tp = fp = fn = tn = 0
    errors = []
    for row in rows:
        gold_positive = row["gold_label"] == "COMMITMENT"
        detector_positive = classify(row["utterance"])["detector_label"] == "COMMITMENT"
        if gold_positive and detector_positive:
            tp += 1
        elif gold_positive and not detector_positive:
            fn += 1
            errors.append(row)
        elif not gold_positive and detector_positive:
            fp += 1
            errors.append(row)
        else:
            tn += 1

    assert not errors, f"Detector regressed on {len(errors)} rows: {[r['id'] for r in errors]}"
    assert tp == 60
    assert tn == 90
    assert fp == 0
    assert fn == 0


def test_boundary_pair_object_rule_controls_classification():
    """The specific boundary pair that tests whether the concrete-object
    rule, not human intuition, controls classification."""
    assert classify("I'll update pricing.rules.")["detector_label"] == "COMMITMENT"
    assert classify("I'll update the pricing rules.")["detector_label"] == "NOT_A_COMMITMENT"


def test_ordinary_capitalized_words_are_not_identifiers():
    for sentence in [
        "I will implement Something.",
        "I will update Python.",
        "I will fix Repository.",
    ]:
        assert classify(sentence)["detector_label"] == "NOT_A_COMMITMENT"


def test_documented_dotted_path_limitation_is_still_accepted():
    """repository.pyz is a known, documented limitation (accepted risk,
    not a bug) -- see ledger.py / detector.py comments. This test exists
    so a future change can't silently alter that documented behavior
    without the test failing and forcing a conscious decision."""
    result = classify("I will update repository.pyz.")
    assert result["detector_label"] == "COMMITMENT"
    assert result["detected_object_rule"] == "dotted_path"
