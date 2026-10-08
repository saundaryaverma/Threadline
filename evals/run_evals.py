"""Run Threadline's eval suite against a real model and compare with the baseline.

    python -m evals.run_evals                     # run and compare with baseline
    python -m evals.run_evals --update-baseline   # save this run as the new baseline

Exits with code 1 if a critical case fails, any case regresses (passed in the
baseline, fails now), or the pass rate drops below --min-pass-rate. That makes it
usable as a CI gate: a prompt or model change that makes answers worse fails the build.
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path

from evals.checks import run_check

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent / "backend"))
from prompt import build_messages  # noqa: E402

CASES_FILE = ROOT / "cases.json"
BASELINE_FILE = ROOT / "baseline.json"
RESULTS_DIR = ROOT / "results"


def load_cases(path=CASES_FILE):
    cases = json.loads(Path(path).read_text())
    ids = [c["id"] for c in cases]
    dupes = {i for i in ids if ids.count(i) > 1}
    if dupes:
        raise ValueError(f"Duplicate case ids: {sorted(dupes)}")
    return cases


def score_case(case, reply):
    results = []
    for check in case["checks"]:
        passed, reason = run_check(reply, check)
        results.append({"type": check["type"], "passed": passed, "reason": reason})
    return {
        "id": case["id"],
        "tags": case.get("tags", []),
        "critical": case.get("critical", False),
        "passed": all(r["passed"] for r in results),
        "checks": results,
        "reply": reply,
    }


def run(cases, complete):
    """complete(messages) -> reply text. Injected so tests can use a fake model."""
    results = []
    for case in cases:
        history = case.get("history", []) + [{"role": "user", "content": case["prompt"]}]
        started = time.monotonic()
        try:
            reply = complete(build_messages(history))
        except Exception as exc:  # a crashed call is a failed case, not a crashed run
            reply = f"[ERROR] {type(exc).__name__}: {exc}"
        result = score_case(case, reply)
        result["seconds"] = round(time.monotonic() - started, 2)
        results.append(result)
    return results


def compare(results, baseline):
    """Find cases that changed state since the baseline run."""
    before = {r["id"]: r["passed"] for r in baseline.get("results", [])}
    regressions = [r["id"] for r in results if before.get(r["id"]) is True and not r["passed"]]
    fixed = [r["id"] for r in results if before.get(r["id"]) is False and r["passed"]]
    new = [r["id"] for r in results if r["id"] not in before]
    return {"regressions": regressions, "fixed": fixed, "new": new}


def gate(results, diff, min_pass_rate):
    """Return the reasons this run should fail the build (empty list means pass)."""
    reasons = []
    total = len(results)
    rate = sum(r["passed"] for r in results) / total if total else 0
    critical_failures = [r["id"] for r in results if r["critical"] and not r["passed"]]
    if critical_failures:
        reasons.append(f"critical cases failed: {critical_failures}")
    if diff["regressions"]:
        reasons.append(f"regressions since baseline: {diff['regressions']}")
    if rate < min_pass_rate:
        reasons.append(f"pass rate {rate:.0%} is below {min_pass_rate:.0%}")
    return reasons


def summary_markdown(results, diff, reasons, model):
    passed = sum(r["passed"] for r in results)
    lines = [
        f"## Threadline evals: {passed}/{len(results)} passed ({model})",
        "",
        "Result: **" + ("FAIL" if reasons else "PASS") + "**",
    ]
    lines += [f"- {r}" for r in reasons]
    if diff["fixed"]:
        lines.append(f"- Fixed since baseline: {diff['fixed']}")
    lines += ["", "| Case | Tags | Critical | Result | Detail |", "| --- | --- | --- | --- | --- |"]
    for r in results:
        detail = "; ".join(c["reason"] for c in r["checks"] if not c["passed"]) or "ok"
        lines.append(
            f"| {r['id']} | {', '.join(r['tags'])} | {'yes' if r['critical'] else ''} | "
            f"{'pass' if r['passed'] else 'FAIL'} | {detail} |"
        )
    return "\n".join(lines)


def openai_complete(model):
    from openai import OpenAI

    client = OpenAI()

    def complete(messages):
        res = client.chat.completions.create(model=model, messages=messages, temperature=0)
        return res.choices[0].message.content or ""

    return complete


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--model", default=os.environ.get("OPENAI_MODEL", "gpt-4o-mini"))
    parser.add_argument("--min-pass-rate", type=float, default=0.9)
    parser.add_argument("--update-baseline", action="store_true")
    parser.add_argument("--tag", help="only run cases with this tag")
    args = parser.parse_args(argv)

    cases = load_cases()
    if args.tag:
        cases = [c for c in cases if args.tag in c.get("tags", [])]

    results = run(cases, openai_complete(args.model))
    baseline = json.loads(BASELINE_FILE.read_text()) if BASELINE_FILE.exists() else {}
    diff = compare(results, baseline)
    reasons = gate(results, diff, args.min_pass_rate)
    report = summary_markdown(results, diff, reasons, args.model)

    RESULTS_DIR.mkdir(exist_ok=True)
    (RESULTS_DIR / "latest.json").write_text(json.dumps({"model": args.model, "results": results}, indent=2))
    (RESULTS_DIR / "latest.md").write_text(report)
    print(report)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as f:
            f.write(report + "\n")

    if args.update_baseline:
        BASELINE_FILE.write_text(json.dumps({"model": args.model, "results": results}, indent=2))
        print(f"\nSaved baseline to {BASELINE_FILE}")
        return 0
    return 1 if reasons else 0


if __name__ == "__main__":
    sys.exit(main())
