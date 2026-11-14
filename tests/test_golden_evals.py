"""Golden-eval runner: pass path, malformed rejection, unknown target, regression signal."""

import json

import pytest

from evals.runner import run_suite

PROBE_SUITE = {
    "version": 1,
    "cases": [
        {
            "id": "probe-coverage",
            "persona": "probe",
            "question": "How many months does the pinned Gujarat series observe?",
            "kind": "numeric-exact",
            "target": "coverage_report",
            "args": {"state": "Gujarat", "commodity": "Groundnut", "field": "observed_months"},
            "expected": 94,
        }
    ],
}


def test_analyst_suite_passes_ten_of_ten(tmp_path):
    payload = run_suite("analyst", results_dir=tmp_path)
    assert payload["total"] == 10
    assert payload["passed"] == 10
    assert payload["code_version"]
    assert payload["generated_at"]


def test_results_file_written_with_metadata(tmp_path):
    run_suite("analyst", results_dir=tmp_path)
    results = json.loads((tmp_path / "analyst.json").read_text(encoding="utf-8"))
    assert results["persona"] == "analyst"
    assert len(results["cases"]) == 10
    assert results["cases"][0]["passed"] is True


def test_malformed_case_rejected_naming_case_and_field(tmp_path):
    broken = json.loads(json.dumps(PROBE_SUITE))
    del broken["cases"][0]["expected"]
    path = tmp_path / "probe.json"
    path.write_text(json.dumps(broken), encoding="utf-8")
    with pytest.raises(ValueError, match="probe-coverage.*expected"):
        run_suite("probe", suite_path=path, results_dir=tmp_path)


def test_unknown_target_rejected_naming_case_and_target(tmp_path):
    broken = json.loads(json.dumps(PROBE_SUITE))
    broken["cases"][0]["target"] = "does_not_exist"
    path = tmp_path / "probe.json"
    path.write_text(json.dumps(broken), encoding="utf-8")
    with pytest.raises(ValueError, match="probe-coverage.*does_not_exist"):
        run_suite("probe", suite_path=path, results_dir=tmp_path)


def test_regression_fails_numeric_case(tmp_path):
    drifted = json.loads(json.dumps(PROBE_SUITE))
    drifted["cases"][0]["expected"] = 99999  # simulates a computation change
    path = tmp_path / "probe.json"
    path.write_text(json.dumps(drifted), encoding="utf-8")
    payload = run_suite("probe", suite_path=path, results_dir=tmp_path)
    assert payload["passed"] == 0
    assert payload["cases"][0]["passed"] is False
    assert payload["cases"][0]["scored_value"] == 94.0
