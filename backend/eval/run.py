"""Score the checks against the labelled cases.

    .venv/bin/python -m eval.run          # code checks only: free, deterministic
    .venv/bin/python -m eval.run --ai     # also the LLM checks (uses your key; results are
                                          # stored, so re-runs of unchanged cases are free)

Writes eval/RESULTS.md. With this few cases, read the numbers as "what it catches and
misses", not as a measured accuracy.
"""

import argparse
import os
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from app import analysis  # noqa: E402
from app.db import engine  # noqa: E402
from app.llm import store  # noqa: E402
from app.llm.rules import JUDGMENT_RULES  # noqa: E402
from app.rules import registry  # noqa: E402
from app.rules.builtin import BUILTIN_RULES  # noqa: E402

from .cases import CASES  # noqa: E402

OUT = Path(__file__).parent / "RESULTS.md"
TYPES = {"check_failed": "Code checks", "needs_judgment": "AI checks"}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ai", action="store_true", help="run the LLM checks too (costs money)")
    args = parser.parse_args()
    if not args.ai:
        os.environ["ANTHROPIC_API_KEY"] = ""
    store.metadata.create_all(engine)
    # Score the shipped built-in rules, never whatever custom rules or on/off switches
    # happen to be in this database, so results don't depend on local test data.
    registry.load = lambda: (list(BUILTIN_RULES), list(JUDGMENT_RULES))

    totals = {t: {"tp": 0, "fn": 0, "fp": 0} for t in TYPES}
    rows = []
    for case in CASES:
        result = analysis.analyze(case["asset"], "eval", enforce_limits=False)
        fired = {f.rule_id: f.type.value for f in result.flags}
        expected, acceptable = case["expected"], case["acceptable"]

        caught = expected & fired.keys()
        missed = expected - fired.keys()
        false = fired.keys() - expected - acceptable
        for rule in caught:
            totals[_type(rule)]["tp"] += 1
        for rule in missed:
            totals[_type(rule)]["fn"] += 1
        for rule in false:
            totals[fired[rule]]["fp"] += 1
        rows.append((case["name"], caught, missed, false, result.ai.status))

    report = _report(rows, totals, args.ai)
    OUT.write_text(report)
    print(report)


def _type(rule_id: str) -> str:
    return "needs_judgment" if rule_id.startswith("llm-") else "check_failed"


def _fmt(rules: set[str]) -> str:
    return ", ".join(f"`{r}`" for r in sorted(rules)) or "–"


def _report(rows, totals, with_ai: bool) -> str:
    lines = [
        "# Evaluation results",
        "",
        f"Run {date.today().isoformat()} on {len(rows)} labelled ads (`eval/cases.py`), "
        + ("code and AI checks." if with_ai else "**code checks only** (AI off)."),
        "",
        "A small, hand-labelled set: this shows what the checks catch and miss, not a measured "
        "accuracy. Labels mark each rule as expected, acceptable either way, or wrong to fire.",
        "",
        "| Checks | Caught | Missed | False flags |",
        "|---|---|---|---|",
    ]
    for t, label in TYPES.items():
        if t == "needs_judgment" and not with_ai:
            continue
        s = totals[t]
        lines.append(f"| {label} | {s['tp']} of {s['tp'] + s['fn']} | {s['fn']} | {s['fp']} |")
    lines += ["", "| Ad | Missed | False flags | AI |", "|---|---|---|---|"]
    for name, _caught, missed, false, ai in rows:
        if not with_ai:
            missed = {r for r in missed if not r.startswith("llm-")}
        lines.append(f"| {name} | {_fmt(missed)} | {_fmt(false)} | {ai} |")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    main()
