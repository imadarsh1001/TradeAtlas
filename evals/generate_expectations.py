"""Regenerate numeric-exact expectations in a golden suite from the current code.

Checked-in by design: numeric expectations are a regression signal, so a data
refresh or intentional computation change regenerates them IN THE SAME CHANGE
(with manifest updates), keeping the suite's drift detection honest.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from evals.runner import RESOLVERS, REQUIRED_FIELDS  # noqa: E402

GOLDEN = Path(__file__).resolve().parent / "golden"


def regenerate(persona: str) -> None:
    suite_path = GOLDEN / f"{persona}.json"
    suite = json.loads(suite_path.read_text(encoding="utf-8"))
    updated = 0
    for case in suite["cases"]:
        missing = [f for f in REQUIRED_FIELDS if f not in case]
        if missing:
            raise ValueError(f"Case '{case.get('id', '?')}': missing fields {missing}")
        if case["kind"] != "numeric-exact":
            continue
        value = RESOLVERS[case["target"]](case["args"])
        case["expected"] = round(float(value), 2)
        updated += 1
    suite_path.write_text(json.dumps(suite, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"{persona}: regenerated {updated} numeric-exact expectations")


if __name__ == "__main__":
    regenerate(sys.argv[1] if len(sys.argv) > 1 else "analyst")
