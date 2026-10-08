"""Tests for the eval runner, using a fake model so no API key is needed."""
import json

import pytest

from evals import run_evals
from evals.run_evals import compare, gate, load_cases, run

CASES = [
    {"id": "math", "critical": True, "prompt": "17*23?", "checks": [{"type": "contains_any", "values": ["391"]}]},
    {"id": "color", "prompt": "Sky color?", "checks": [{"type": "contains_any", "values": ["blue"]}]},
]


def fake_model(answers):
    """Answer each prompt from a dict, keyed by the last user message."""
    seen = []

    def complete(messages):
        seen.append(messages)
        return answers[messages[-1]["content"]]

    complete.seen = seen
    return complete


def test_shipped_cases_file_is_valid():
    cases = load_cases()
    assert len(cases) >= 10
    for case in cases:
        assert case["id"] and case["prompt"] and case["checks"]


def test_duplicate_case_ids_are_rejected(tmp_path):
    path = tmp_path / "cases.json"
    path.write_text(json.dumps([CASES[0], CASES[0]]))
    with pytest.raises(ValueError):
        load_cases(path)


def test_run_scores_each_case():
    results = run(CASES, fake_model({"17*23?": "391", "Sky color?": "Green"}))
    assert [r["passed"] for r in results] == [True, False]


def test_run_sends_system_prompt_and_history():
    case = {"id": "memory", "prompt": "My name?", "history": [{"role": "user", "content": "I'm Priya"}],
            "checks": [{"type": "contains_any", "values": ["Priya"]}]}
    model = fake_model({"My name?": "Priya"})
    run([case], model)
    roles = [m["role"] for m in model.seen[0]]
    assert roles == ["system", "user", "user"]


def test_a_model_crash_fails_the_case_without_stopping_the_run():
    def broken(messages):
        raise TimeoutError("too slow")

    results = run(CASES, broken)
    assert len(results) == 2 and not any(r["passed"] for r in results)
    assert "TimeoutError" in results[0]["reply"]


def test_compare_finds_regressions_and_fixes():
    baseline = {"results": [{"id": "math", "passed": True}, {"id": "color", "passed": False}]}
    now = [{"id": "math", "passed": False}, {"id": "color", "passed": True}, {"id": "new", "passed": True}]
    assert compare(now, baseline) == {"regressions": ["math"], "fixed": ["color"], "new": ["new"]}


def test_gate_fails_on_critical_failure():
    results = [{"id": "math", "critical": True, "passed": False}] + [
        {"id": f"c{i}", "critical": False, "passed": True} for i in range(20)
    ]
    reasons = gate(results, {"regressions": []}, min_pass_rate=0.5)
    assert reasons and "critical" in reasons[0]


def test_gate_fails_on_regression_even_with_high_pass_rate():
    results = [{"id": "a", "critical": False, "passed": True}]
    assert gate(results, {"regressions": ["b"]}, min_pass_rate=0.9)


def test_gate_fails_below_min_pass_rate():
    results = [{"id": "a", "critical": False, "passed": True}, {"id": "b", "critical": False, "passed": False}]
    assert gate(results, {"regressions": []}, min_pass_rate=0.9)


def test_gate_passes_clean_run():
    results = [{"id": "a", "critical": True, "passed": True}]
    assert gate(results, {"regressions": []}, min_pass_rate=0.9) == []


def test_main_writes_report_and_exit_code(tmp_path, monkeypatch):
    monkeypatch.setattr(run_evals, "RESULTS_DIR", tmp_path / "results")
    monkeypatch.setattr(run_evals, "BASELINE_FILE", tmp_path / "baseline.json")
    monkeypatch.setattr(run_evals, "load_cases", lambda: CASES)
    monkeypatch.setattr(run_evals, "openai_complete",
                        lambda model: fake_model({"17*23?": "391", "Sky color?": "blue"}))
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)

    assert run_evals.main(["--update-baseline"]) == 0
    assert (tmp_path / "baseline.json").exists()

    # Now the model gets worse on a critical case: the run must fail.
    monkeypatch.setattr(run_evals, "openai_complete",
                        lambda model: fake_model({"17*23?": "about 400", "Sky color?": "blue"}))
    assert run_evals.main([]) == 1
    report = (tmp_path / "results" / "latest.md").read_text()
    assert "FAIL" in report and "math" in report
