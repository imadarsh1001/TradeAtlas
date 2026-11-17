"""Judged quality layer: framework-scored evidence, recorded and never gating.

deepeval metrics score the LIVE run evidence (question, summary, tool-result
excerpts) with a judge LLM resolved through the model registry — same enabled-only,
gateway-routed governance as agent calls, via a dedicated selector so the cheapest
enabled entry can judge while a stronger entry answers. Scores are recorded paired
with the deterministic outcome per case (evals/quality/, git-ignored): that pairing
is the calibration dataset for the future judge-gating decision (ADR 0007) — until
then this layer NEVER changes a gate result, by construction: the deterministic
results payload is computed and written before this layer runs, and is never
re-read afterwards. The runner imports this module only under the --quality flag,
so CI and replay never construct a judge.
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from deepeval.metrics import FaithfulnessMetric, GEval
from deepeval.models import DeepEvalBaseLLM
from deepeval.test_case import LLMTestCase

try:  # deepeval 4.x renamed the params enum; keep the import working across minor versions
    from deepeval.test_case import SingleTurnParams as EvalParams
except ImportError:  # pragma: no cover - older deepeval
    from deepeval.test_case import LLMTestCaseParams as EvalParams

JUDGE_ENV_VAR = "TRADEATLAS_JUDGE_MODEL"
RUNS_DIR = Path(__file__).resolve().parent / "runs"
QUALITY_DIR = Path(__file__).resolve().parent / "results" / "quality"


class GatewayJudgeModel(DeepEvalBaseLLM):
    """deepeval judge backed by a registry-resolved gateway model.

    The registry owns the judge decision exactly as it owns agent-model decisions:
    enabled entries only, gateway routing, per-entry params — the selector is
    separate (TRADEATLAS_JUDGE_MODEL) so the judge can be a cheaper entry than the
    answering model.
    """

    def __init__(self, chat_model: Any, model_name: str):
        self._chat_model = chat_model
        self._judge_name = model_name
        super().__init__(model=model_name)

    def load_model(self) -> Any:
        return self._chat_model

    def generate(self, prompt: str) -> str:
        from langchain_core.messages import HumanMessage

        response = self._chat_model.invoke([HumanMessage(content=prompt)])
        content = response.content
        return content if isinstance(content, str) else str(content)

    async def a_generate(self, prompt: str) -> str:
        return self.generate(prompt)  # judged scoring runs as a synchronous CLI flow

    def get_model_name(self) -> str:
        return self._judge_name


def resolve_judge(settings: Optional[Any] = None) -> GatewayJudgeModel:
    """The judged layer's model: registry-resolved via TRADEATLAS_JUDGE_MODEL, named errors."""
    selector = os.environ.get(JUDGE_ENV_VAR)
    if not selector:
        raise RuntimeError(
            f"Set {JUDGE_ENV_VAR} to a model registry key or id for judged scoring "
            f"(see tradeatlas/agent/model_registry.py); judged metrics call a judge LLM."
        )
    from tradeatlas.agent.model_registry import build_model_for_entry, resolve_model_entry

    entry = resolve_model_entry(selector)  # enabled-only, named errors
    chat_model = build_model_for_entry(entry, settings=settings)
    return GatewayJudgeModel(chat_model, entry.model)


def _load_record(run_id: str, runs_dir: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    runs_path = Path(runs_dir) if runs_dir is not None else RUNS_DIR
    record_path = runs_path / f"{run_id}.json"
    if not record_path.is_file():
        return None
    return json.loads(record_path.read_text(encoding="utf-8"))


GOLDEN_DIR = Path(__file__).resolve().parent / "golden"


def _suite_questions(persona: str) -> Dict[str, str]:
    """Case id → question text from the golden suite (the results payload doesn't carry questions)."""
    suite_file = GOLDEN_DIR / f"{persona}.json"
    if not suite_file.is_file():
        return {}
    suite = json.loads(suite_file.read_text(encoding="utf-8"))
    return {c["id"]: c.get("question", "") for c in suite.get("cases", [])}


def run_quality(
    persona: str,
    results_payload: Dict[str, Any],
    judge: Optional[GatewayJudgeModel] = None,
    runs_dir: Optional[Path] = None,
    out_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """Score each scored case's live evidence and record it paired with the deterministic outcome.

    Reads the per-case run records (answer + result excerpts) through the run ids in
    the results payload, and the questions from the golden suite; cases without a
    completed run record are skipped and disclosed. The results payload is treated
    as read-only — nothing here writes to it. Returns the quality record it wrote.
    """
    judge = judge if judge is not None else resolve_judge()
    questions = _suite_questions(persona)

    relevance = GEval(
        name="Summary relevance",
        criteria="Does the answer directly address the buyer's question with decision-grade specificity, "
        "naming the market facts a procurement decision needs — and nothing off-topic?",
        evaluation_params=[EvalParams.INPUT, EvalParams.ACTUAL_OUTPUT],
        model=judge,
    )
    faithfulness = FaithfulnessMetric(model=judge, threshold=0.5)  # threshold recorded, never gating

    scored: List[Dict[str, Any]] = []
    skipped: List[str] = []
    for case in results_payload.get("cases", []):
        run_id = case.get("run_id")
        record = _load_record(run_id, runs_dir=runs_dir) if run_id else None
        answer = (record or {}).get("answer")
        if not answer:
            skipped.append(case["id"])
            continue
        excerpts = [
            c.get("result_excerpt")
            for c in record.get("tool_calls", [])
            if c.get("result_excerpt")
        ]
        test_case = LLMTestCase(
            input=questions.get(case["id"], ""),
            actual_output=answer.get("summary", ""),
            retrieval_context=excerpts or None,
        )
        relevance.measure(test_case)
        row: Dict[str, Any] = {
            "case_id": case["id"],
            "run_id": run_id,
            "deterministic_passed": case["passed"],
            "relevance": {"score": round(relevance.score, 3), "reason": relevance.reason},
        }
        if excerpts:
            faithfulness.measure(test_case)
            row["faithfulness"] = {"score": round(faithfulness.score, 3), "reason": faithfulness.reason}
        else:
            row["faithfulness"] = None  # no executed-call evidence to score against
        scored.append(row)

    quality = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "persona": persona,
        "mode": results_payload.get("mode"),
        "judge_model": judge.get_model_name(),
        "gate_note": "judged scores are non-gating (ADR 0007); the deterministic outcome stands",
        "cases": scored,
        "skipped_no_record": skipped,
    }
    quality_dir = Path(out_dir) if out_dir is not None else QUALITY_DIR
    quality_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    path = quality_dir / f"{persona}-{stamp}.json"
    path.write_text(json.dumps(quality, indent=2, ensure_ascii=False), encoding="utf-8")
    quality["path"] = str(path)
    return quality
