"""CLI: build | chat | regress | selftest."""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from .config import get_settings


def _ask_questions(questions: list[str]) -> list[str | None]:
    print("\nForgeAI has a few clarifying questions (press Enter to let ForgeAI answer one itself):")
    out = []
    for i, q in enumerate(questions, 1):
        a = input(f"  Q{i}. {q}\n  > ").strip()
        out.append(a or None)
    return out


def _approve(run_dir: Path):
    def fn(req):
        print("\n" + "=" * 70 + "\n" + (run_dir / "requirements.md").read_text(encoding="utf-8") + "\n" + "=" * 70)
        while True:
            c = input("[a]pprove / [e]dit / [r]eject? ").strip().lower()[:1]
            if c == "a":
                return "approve", None
            if c == "r":
                return "reject", None
            if c == "e":
                p = run_dir / "requirements.json"
                input(f"Edit {p} in your editor, save, then press Enter...")
                try:
                    return "edit", json.loads(p.read_text(encoding="utf-8"))
                except json.JSONDecodeError as e:
                    print(f"Invalid JSON: {e}")
    return fn


def _print_event(ev: dict) -> None:
    t = ev["type"]
    if t == "stage_started":
        print(f"-> {ev['stage']} ...", flush=True)
    elif t == "stage_done":
        print(f"   done {ev['stage']} ({ev['seconds']}s, {ev['tokens']} tokens)", flush=True)
    elif t == "iteration_result":
        print(f"   iteration {ev['iteration']}: {ev.get('category', 'baseline')} score {ev.get('score_before')} -> {ev.get('score_after')} {ev.get('decision', '')}")
    elif t == "flags" and ev.get("kind") == "tools":
        print(f"   tools attached {ev['attached']}; rejected {[r['name'] for r in ev['rejected']]}")
    elif t == "flags" and ev.get("kind") == "groundability":
        for f in ev["flags"]:
            if f.get("verdict") != "supported":
                print(f"   FLAG {f.get('verdict')}: {f.get('topic', f.get('capability'))} - {f.get('message', '')}")
    elif t == "error":
        print(f"   ERROR in {ev.get('stage')}: {ev.get('message')}")


def cmd_build(a) -> int:
    from .pipeline import Pipeline, RunOptions, new_run_id

    brief = Path(a.brief_file).read_text(encoding="utf-8") if a.brief_file else a.brief
    if not brief:
        print("provide --brief or --brief-file", file=sys.stderr)
        return 2
    run_dir = Path(a.out) if a.out else get_settings().runs_dir / (a.run_id or new_run_id())
    opts = RunOptions(non_interactive=a.non_interactive, approve=a.approve, tournament=a.tournament, seed=a.seed,
                      max_tokens=a.max_tokens, max_seconds=a.max_seconds, target_score=a.target, judge_mode=a.judge_mode)
    p = Pipeline(brief, a.docs, run_dir, opts, emit=_print_event, answer_fn=_ask_questions, approval_fn=_approve(run_dir))
    s = p.run()
    print(json.dumps(s, indent=2))
    print(f"\nArtifacts: {run_dir}\nReport:    {run_dir / 'report.md'}")
    return 0 if s["status"] == "completed" else 1


def cmd_chat(a) -> int:
    from .runner import AgentRuntime, reply_json

    rt = AgentRuntime.load(a.agent, a.docs)
    if a.message:
        print(reply_json(rt.ask(a.message), a.verbose))
        return 0
    print(f"Chatting with {rt.agent.name} (tools: {rt.agent.tools}). Ctrl+C or 'exit' to quit.")
    while True:
        try:
            q = input("\nyou> ").strip()
        except (EOFError, KeyboardInterrupt):
            return 0
        if q.lower() in ("exit", "quit"):
            return 0
        if q:
            print(reply_json(rt.ask(q), a.verbose))


def cmd_regress(a) -> int:
    from .regression import run_regression

    out = run_regression(a.run, a.new_docs)
    print(json.dumps(out["summary"], indent=2))
    print(f"score now: {out['score_now']}%  -> {Path(a.run) / 'regression_report.md'}")
    return 0


def cmd_selftest(a) -> int:
    from .judge import judge_selftest
    from .llm import LLM

    r = judge_selftest(LLM(), a.judge_mode)
    for c in r["cases"]:
        print(f"{'ok ' if c['caught'] else 'MISS'} {c['case']}: expected {c['expected_pass']} got {c['judged_pass']} ({c['decided_by']})")
    print(f"{r['n_correct']}/{r['n']}")
    return 0 if r["all_correct"] else 1


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    ap = argparse.ArgumentParser(prog="forgeai", description="The agent that builds agents.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build", help="build, test and optimise an agent from a brief + docs folder")
    b.add_argument("--brief")
    b.add_argument("--brief-file")
    b.add_argument("--docs", required=True)
    b.add_argument("--out", help="run directory (default runs/<run-id>)")
    b.add_argument("--run-id")
    b.add_argument("--non-interactive", action="store_true", help="ForgeAI answers its own clarifying questions")
    b.add_argument("--approve", action="store_true", help="pause for human approval of the requirements")
    b.add_argument("--tournament", action="store_true", help="3-prompt tournament judged by the dev eval split")
    b.add_argument("--seed", type=int, default=42)
    b.add_argument("--max-tokens", type=int)
    b.add_argument("--max-seconds", type=float)
    b.add_argument("--target", type=float, help="target dev score for early stop (default TARGET_SCORE)")
    b.add_argument("--judge-mode", choices=["hybrid", "deterministic"], default="hybrid")
    b.set_defaults(fn=cmd_build)
    c = sub.add_parser("chat", help="chat with any produced agent.yaml")
    c.add_argument("--agent", required=True)
    c.add_argument("--docs", required=True)
    c.add_argument("--message", help="ask one question and exit")
    c.add_argument("--verbose", action="store_true")
    c.set_defaults(fn=cmd_chat)
    r = sub.add_parser("regress", help="re-run an old eval set over changed documents")
    r.add_argument("--run", required=True)
    r.add_argument("--new-docs", required=True)
    r.set_defaults(fn=cmd_regress)
    s = sub.add_parser("selftest", help="judge self-test on known-good / known-bad answers")
    s.add_argument("--judge-mode", choices=["hybrid", "deterministic"], default="hybrid")
    s.set_defaults(fn=cmd_selftest)
    a = ap.parse_args(argv)
    return a.fn(a)
