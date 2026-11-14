"""Manual agent entry point: answer one question and write its run record.

Usage: uv run python -m tradeatlas.agent "question"

Requires TRADEATLAS_AGENT_MODEL (and provider credentials) for a live run;
offline tests exercise the same graph through scripted replay instead.
"""

import sys
from typing import List, Optional

from tradeatlas.agent.graph import run_agent


def main(argv: Optional[List[str]] = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if len(argv) != 1:
        print('Usage: python -m tradeatlas.agent "question"', file=sys.stderr)
        return 2
    answer, record = run_agent(argv[0])
    if record.failure_reason is not None:
        print(f"Run failed ({record.run_id}): {record.failure_reason}", file=sys.stderr)
        return 1
    print(f"Run record: {record.run_id}")
    print(answer.summary)
    for figure in answer.figures:
        selector = ", ".join(f"{k}={v}" for k, v in figure.selector.items())
        print(f"  - {figure.value:g} {figure.unit} (via {figure.source_tool}[{selector}])")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
