import re
import csv

COMMITMENT_VERBS = {
    "add", "create", "delete", "implement", "modify", "remove",
    "rename", "refactor", "update", "fix", "test", "document", "review",
}

# Anchored to the very start of the utterance. This is what naturally
# excludes hedged ("I think I will..."), third-person ("Agent B will..."),
# and modal-uncertainty ("I might...") forms without any special-casing.
CANDIDATE_PATTERN = re.compile(
    r"^\s*i(?:'ll| will| am going to|'m going to)\s+"
    r"(?P<verb>[a-z]+)\s+"
    r"(?P<object>.+?)\s*[.!]?\s*$",
    re.IGNORECASE,
)

SURFACE_FORM_PATTERNS = {
    "I_will": re.compile(r"^\s*i\s+will\b", re.IGNORECASE),
    "Ill": re.compile(r"^\s*i'll\b", re.IGNORECASE),
    "I_am_going_to": re.compile(r"^\s*i\s+am\s+going\s+to\b", re.IGNORECASE),
    "Im_going_to": re.compile(r"^\s*i'm\s+going\s+to\b", re.IGNORECASE),
}

LEADING_ARTICLE = re.compile(r"^(the|a|an)\s+", re.IGNORECASE)
TRAILING_PUNCT = re.compile(r"[\s.!,;:]+$")

# --- Concrete-object rules (fullmatch only; each is checked as a whole span) ---
RULE_QUOTED = re.compile(r'^(?:"[^"]+"|\'[^\']+\')$')
RULE_ENDPOINT = re.compile(r"^/[\w\-/{}]+$")
RULE_FILE_PATH = re.compile(
    r"^[\w\-]+(?:/[\w\-]+)*\.(?:py|js|ts|tsx|jsx|json|md|yaml|yml|txt)$"
)
RULE_SNAKE_CASE = re.compile(r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)+$")
RULE_CAMEL_PASCAL = re.compile(r"^(?=[A-Za-z][A-Za-z0-9]*$)(?=.*[a-z][A-Z])[A-Za-z][A-Za-z0-9]*$")

# dotted_path is deliberately more restrictive than a bare "word.word" pattern.
# Amendment 1 (post grammar-vs-150-set testing): the naive version accepted
# degenerate single-letter segment chains, e.g. "a.b.c.d". Each dotted_path
# segment must now be >=2 characters.
#
# Amendment 1 also originally tried to reject "fake extension" shapes, e.g.
# "repository.pyz", by requiring any 2-4-lowercase-letter final segment to be
# a recognized extension. That rule was reverted: it has no way to
# distinguish a mistyped extension ("pyz") from a legitimate short
# dotted-path attribute ("item", "log", "rules") — both are structurally just
# short lowercase strings, so the same rule that blocks "repository.pyz"
# also blocked the real, already-labeled commitment "models.user". Between
# the two error types this rule traded, a false negative (silently dropping
# real commitments like "services.email" or "config.settings" whenever the
# final segment happens to be short) is worse for the coordination
# experiment than the false positive it prevented (a contrived typo unlikely
# to occur in real agent dialogue). Accepted as a documented limitation
# rather than solved: this detector cannot always distinguish a typo'd file
# extension from a legitimate short module attribute using syntax alone.
RULE_DOTTED_PATH_RAW = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{1,}(?:\.[A-Za-z_][A-Za-z0-9_]{1,})+$")


def _dotted_path_match(obj: str) -> bool:
    if not RULE_DOTTED_PATH_RAW.match(obj):
        return False
    segments = obj.split(".")
    if any(len(seg) < 2 for seg in segments):
        return False
    return True


OBJECT_RULES_IN_ORDER = [
    ("quoted", RULE_QUOTED),
    ("endpoint_path", RULE_ENDPOINT),
    ("file_path", RULE_FILE_PATH),
    ("snake_case", RULE_SNAKE_CASE),
    ("camel_pascal", RULE_CAMEL_PASCAL),
    ("dotted_path", _dotted_path_match),
]


def strip_object(raw_object: str) -> str:
    obj = TRAILING_PUNCT.sub("", raw_object).strip()
    obj = LEADING_ARTICLE.sub("", obj).strip()
    return obj


def concrete_object_rule(obj: str):
    for rule_name, matcher in OBJECT_RULES_IN_ORDER:
        is_match = matcher(obj) if callable(matcher) and not hasattr(matcher, "match") else bool(matcher.match(obj))
        if is_match:
            return rule_name
    return None


def surface_form_match(utterance: str):
    for name, pattern in SURFACE_FORM_PATTERNS.items():
        if pattern.match(utterance):
            return name
    return None


def classify(utterance: str):
    """Returns dict with detector_label, detected_verb, detected_object,
    detected_object_rule, surface_form_match."""
    sform = surface_form_match(utterance)
    m = CANDIDATE_PATTERN.match(utterance)
    if not m:
        return {
            "detector_label": "NOT_A_COMMITMENT",
            "detected_verb": "",
            "detected_object": "",
            "detected_object_rule": "",
            "surface_form_match": sform or "",
        }

    verb = m.group("verb").lower()
    raw_object = m.group("object")
    stripped_object = strip_object(raw_object)

    if verb not in COMMITMENT_VERBS:
        return {
            "detector_label": "NOT_A_COMMITMENT",
            "detected_verb": verb,
            "detected_object": stripped_object,
            "detected_object_rule": "",
            "surface_form_match": sform or "",
        }

    obj_rule = concrete_object_rule(stripped_object)
    if obj_rule is None:
        return {
            "detector_label": "NOT_A_COMMITMENT",
            "detected_verb": verb,
            "detected_object": stripped_object,
            "detected_object_rule": "",
            "surface_form_match": sform or "",
        }

    return {
        "detector_label": "COMMITMENT",
        "detected_verb": verb,
        "detected_object": stripped_object,
        "detected_object_rule": obj_rule,
        "surface_form_match": sform or "",
    }


def run(input_csv, output_csv):
    results = []
    with open(input_csv, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            gold = row["gold_label"]
            det = classify(row["utterance"])
            is_positive_gold = gold == "COMMITMENT"
            is_positive_det = det["detector_label"] == "COMMITMENT"
            correct = is_positive_gold == is_positive_det
            results.append({
                "id": row["id"],
                "utterance": row["utterance"],
                "gold_label": gold,
                "detector_label": det["detector_label"],
                "detected_verb": det["detected_verb"],
                "detected_object": det["detected_object"],
                "detected_object_rule": det["detected_object_rule"],
                "surface_form_match": det["surface_form_match"],
                "correct": correct,
            })

    tp = sum(1 for r in results if r["gold_label"] == "COMMITMENT" and r["detector_label"] == "COMMITMENT")
    fn = sum(1 for r in results if r["gold_label"] == "COMMITMENT" and r["detector_label"] == "NOT_A_COMMITMENT")
    # For precision/recall/FPR purposes, both NOT_A_COMMITMENT and NOT_MY_COMMITMENT
    # gold labels count as "not a commitment for this agent" — negatives.
    fp = sum(1 for r in results if r["gold_label"] != "COMMITMENT" and r["detector_label"] == "COMMITMENT")
    tn = sum(1 for r in results if r["gold_label"] != "COMMITMENT" and r["detector_label"] == "NOT_A_COMMITMENT")

    precision = tp / (tp + fp) if (tp + fp) else float("nan")
    recall = tp / (tp + fn) if (tp + fn) else float("nan")
    fpr = fp / (fp + tn) if (fp + tn) else float("nan")

    with open(output_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "id", "utterance", "gold_label", "detector_label", "detected_verb",
            "detected_object", "detected_object_rule", "surface_form_match", "correct",
        ])
        writer.writeheader()
        for r in results:
            writer.writerow(r)

    return {
        "tp": tp, "fp": fp, "fn": fn, "tn": tn,
        "precision": precision, "recall": recall, "false_positive_rate": fpr,
        "total": len(results),
        "errors": [r for r in results if not r["correct"]],
    }


if __name__ == "__main__":
    summary = run(
        "/mnt/user-data/outputs/commitment_detector_dataset_v1.csv",
        "/mnt/user-data/outputs/commitment_detector_results_v1.csv",
    )
    print(f"Total rows: {summary['total']}")
    print(f"TP={summary['tp']}  FP={summary['fp']}  FN={summary['fn']}  TN={summary['tn']}")
    print(f"Precision: {summary['precision']:.4f}")
    print(f"Recall: {summary['recall']:.4f}")
    print(f"False-positive rate: {summary['false_positive_rate']:.4f}")
    print()
    print(f"Misclassified rows ({len(summary['errors'])}):")
    for e in summary["errors"]:
        print(f"  id={e['id']} gold={e['gold_label']} detector={e['detector_label']} "
              f"| utterance: {e['utterance']}")
