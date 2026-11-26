"""Stretch: prompt tournament. 3 strategies; the dev eval set (not an LLM) picks the winner:
highest score, then fewest hallucinations, then lowest token cost."""
from __future__ import annotations

from typing import Callable

from .generator import write_system_prompt
from .llm import LLM, NOOP
from .schemas import AgentDef, Requirements

STRATEGIES = ["tournament_strict", "tournament_concise", "tournament_stepwise"]


def run_tournament(agent: AgentDef, req: Requirements, infos: list[dict], llm: LLM,
                   evaluate: Callable[[AgentDef], dict], emit: Callable = NOOP) -> tuple[AgentDef, dict, dict]:
    rows, evals = [], {}
    for strat in STRATEGIES:
        cand = agent.model_copy(deep=True)
        cand.system_prompt = write_system_prompt(req, infos, agent.tools, llm, template=strat)
        ev = evaluate(cand)
        row = {"strategy": strat.replace("tournament_", ""), "score": ev["score"],
               "hallucinations": ev["taxonomy"].get("hallucination", 0), "tokens": ev["tokens"],
               "taxonomy": ev["taxonomy"], "system_prompt": cand.system_prompt}
        rows.append(row)
        evals[row["strategy"]] = (cand, ev)
        emit("log", message=f"tournament candidate {row['strategy']}: score {row['score']}")
    ranked = sorted(rows, key=lambda r: (-r["score"], r["hallucinations"], r["tokens"]))
    win = ranked[0]["strategy"]
    record = {"rule": "max score, then fewest hallucinations, then fewest tokens (deterministic, not LLM-chosen)",
              "candidates": rows, "ranking": [r["strategy"] for r in ranked], "winner": win}
    return evals[win][0], evals[win][1], record
