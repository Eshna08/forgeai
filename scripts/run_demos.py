"""Run the three demonstrations end to end, unattended, and write full artifacts to runs/<name>_demo.

    python scripts/run_demos.py                 # all three
    python scripts/run_demos.py --only hr       # one
    python scripts/run_demos.py --no-tournament

Uses whatever provider .env configures (LLM_PROVIDER=mock for an offline dry run).
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from forgeai.pipeline import Pipeline, RunOptions  # noqa: E402
from forgeai.regression import run_regression  # noqa: E402

DEMOS = ["hr", "spares", "admissions"]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", choices=DEMOS)
    ap.add_argument("--no-tournament", action="store_true")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--judge-mode", choices=["hybrid", "deterministic"], default="hybrid",
                    help="deterministic skips the LLM judge (use when the judge model's daily token cap is tight)")
    ap.add_argument("--target", type=float, default=100.0, help="dev score the optimizer aims for (100 = always try to fix)")
    a = ap.parse_args()
    if not (ROOT / "demos" / "hr" / "docs").exists():
        import demos.synth_docs as s  # noqa: F401

        sys.argv = ["synth_docs"]
        s.main()
    rows = []
    for name in [a.only] if a.only else DEMOS:
        d = ROOT / "demos" / name
        rd = ROOT / "runs" / f"{name}_demo"
        shutil.rmtree(rd, ignore_errors=True)
        print(f"\n=== {name}: {d / 'brief.txt'}")
        opts = RunOptions(non_interactive=True, tournament=not a.no_tournament, seed=a.seed, target_score=a.target, judge_mode=a.judge_mode)
        s = Pipeline((d / "brief.txt").read_text(encoding="utf-8"), d / "docs", rd, opts,
                     emit=lambda ev: print(f"  {ev['type']:<18} {ev.get('stage', '')} {ev.get('message', '')}".rstrip()) if ev["type"] in ("stage_started", "error") else None).run()
        rows.append((name, s))
        if name == "hr" and s["status"] == "completed":
            r = run_regression(rd, d / "docs_v2", judge_mode=a.judge_mode)
            print(f"  regression vs docs_v2: {r['summary']}")
    print("\n| demo | status | dev | held-out | stop reason |\n|---|---|---|---|---|")
    for name, s in rows:
        print(f"| {name} | {s['status']} | {s['dev_score']} | {s['heldout_score']} | {s['stop_reason']} |")
    return 0 if all(s["status"] == "completed" for _, s in rows) else 1


if __name__ == "__main__":
    sys.exit(main())
