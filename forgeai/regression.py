"""Stretch: regression mode. Re-run the OLD eval set against the agent re-indexed over changed docs."""
from __future__ import annotations

import json
from pathlib import Path

from .evalgen import fact_in_text
from .generator import load_agent
from .ingest import load_folder
from .llm import LLM
from .optimizer import run_eval
from .schemas import EvalCase


def run_regression(run_dir: str | Path, new_docs: str | Path, llm: LLM | None = None, judge_mode: str = "hybrid") -> dict:
    run_dir, new_docs = Path(run_dir), Path(new_docs)
    llm = llm or LLM()
    agent = load_agent(run_dir / "agent.yaml")
    cases = [EvalCase.model_validate(c) for c in json.loads((run_dir / "evalset.json").read_text(encoding="utf-8"))["cases"]]
    old = {r["case_id"]: r for r in json.loads((run_dir / "results_final.json").read_text(encoding="utf-8"))["results"]}
    docs, warnings = load_folder(new_docs)
    all_text = "\n".join(d.text for d in docs)
    ev = run_eval(agent, docs, cases, llm, judge_mode=judge_mode)
    rows = []
    for r in ev["results"]:
        c = next(x for x in cases if x.id == r["case_id"])
        was = old.get(c.id, {}).get("passed")
        missing = [f for f in (c.evidence or c.expected_key_facts) if not fact_in_text(f, all_text)]
        if c.origin == "code" and c.subtype == "computation":
            missing = [e for e in c.evidence if not fact_in_text(e, all_text)]
        if missing and not c.should_refuse:
            status = "stale_eval"
        elif was and r["passed"]:
            status = "still_passing"
        elif was and not r["passed"]:
            status = "regression"
        elif not was and r["passed"]:
            status = "newly_passing"
        else:
            status = "still_failing"
        rows.append({"case_id": c.id, "type": c.type, "question": c.question, "status": status,
                     "was_passing": was, "now_passing": r["passed"], "category": r["category"],
                     "missing_facts": missing, "answer": r["answer"][:300]})
    summary = {s: sum(x["status"] == s for x in rows) for s in
               ("still_passing", "regression", "newly_passing", "still_failing", "stale_eval")}
    out = {"new_docs": str(new_docs), "warnings": warnings, "score_now": ev["score"], "summary": summary, "cases": rows}
    (run_dir / "regression.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    (run_dir / "regression_report.md").write_text(regression_md(out), encoding="utf-8")
    return out


def regression_md(o: dict) -> str:
    L = ["# Regression report", "", f"New document folder: `{o['new_docs']}`", "",
         f"Score of the old eval set on the re-indexed agent: **{o['score_now']}%** (stale cases count as failures in this number)", "",
         "| status | count |", "|---|---|", *[f"| {k} | {v} |" for k, v in o["summary"].items()], ""]
    for status, title in (("regression", "Regressions (passed before, fail now)"),
                          ("stale_eval", "Stale eval cases (expected fact no longer in the documents)"),
                          ("newly_passing", "Newly passing"), ("still_failing", "Still failing")):
        rows = [r for r in o["cases"] if r["status"] == status]
        if rows:
            L += [f"## {title}", "", "| id | question | category | note |", "|---|---|---|---|"]
            L += [f"| {r['case_id']} | {r['question'][:90].replace('|', '/')} | {r['category'] or '-'} | "
                  f"{('missing: ' + ', '.join(r['missing_facts'])) if r['missing_facts'] else ''} |" for r in rows]
            L.append("")
    if o["warnings"]:
        L += ["## Ingestion warnings", *[f"- {w}" for w in o["warnings"]], ""]
    L += ["Stale cases should be regenerated (re-run the factory) rather than counted as agent bugs."]
    return "\n".join(L)
