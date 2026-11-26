"""Requirement 6: critic-optimizer loop (max 3 iterations).

eval -> classify EVERY failure by rules -> ONE targeted fix for the dominant category -> re-eval ->
revert if the score dropped -> log everything -> early stop (target / budget / gain < 1 point).
"""
from __future__ import annotations

import difflib
import time
from collections import Counter
from typing import Callable

from .ingest import Document
from .judge import judge_case
from .llm import LLM, NOOP, BudgetExceeded
from .runner import AgentRuntime
from .schemas import AgentDef, AgentReply, EvalCase, PromptPatch
from .textutil import norm

CATEGORIES = ["retrieval_miss", "prompt_defect", "hallucination", "wrong_refusal"]
STRICT_RULE = "Every number, name and policy detail in your answer must appear verbatim in the context or tool results; if you cannot point to it, leave it out or refuse."
LENIENT_RULE = "Answer if the context contains the information, even when the question is phrased differently from the documents; only refuse when the context truly lacks it."
CATEGORY_REASON = {
    "retrieval_miss": "the passage holding the expected facts was not in the retrieved top-k",
    "prompt_defect": "the right passage was retrieved but the answer omitted or mangled the expected facts",
    "hallucination": "the answer contained claims not supported by the context, or answered a question it should have refused",
    "wrong_refusal": "the agent refused although the retrieved context contained the answer",
}


# ---------------------------------------------------------------- evaluation
def classify(case: EvalCase, reply: AgentReply, det: dict) -> str:
    if case.should_refuse and not reply.refused:
        return "hallucination"
    retrieved = norm(" ".join(r.get("text", "") for r in reply.retrieved))
    ev = case.evidence or case.expected_key_facts
    if ev and not all(norm(e) in retrieved for e in ev):
        return "retrieval_miss"
    if not ev and case.expected_source_docs and not set(case.expected_source_docs) & {r["doc"] for r in reply.retrieved}:
        return "retrieval_miss"
    if reply.refused:
        return "wrong_refusal"
    if det.get("unsupported"):
        return "hallucination"
    return "prompt_defect"


def run_eval(agent: AgentDef, docs: list[Document], cases: list[EvalCase], llm: LLM, judge_llm: LLM | None = None,
             judge_mode: str = "hybrid") -> dict:
    t0, s0 = time.monotonic(), llm.snapshot()
    rt = AgentRuntime(agent, docs, llm)
    results = []
    for c in cases:
        try:
            reply = rt.ask(c.question)
        except BudgetExceeded:
            raise
        except Exception as e:  # a crashing case is a failing case, not a crashing run
            reply = AgentReply(answer=f"[runner error: {e}]", sources=[], confidence=0, refused=True, gate="error")
        j = judge_case(c, reply, judge_llm or llm, judge_mode)
        cat = None if j["passed"] else classify(c, reply, j["deterministic"])
        results.append({
            "case_id": c.id, "type": c.type, "subtype": c.subtype, "split": c.split, "question": c.question,
            "expected_key_facts": c.expected_key_facts, "should_refuse": c.should_refuse,
            "answer": reply.answer, "sources": reply.sources, "refused": reply.refused, "gate": reply.gate,
            "confidence": reply.confidence, "retrieval_confidence": reply.retrieval_confidence,
            "retrieved": [r["chunk_id"] for r in reply.retrieved],
            "tools_used": [{"tool": t.get("tool"), "args": t.get("args"), "ok": t.get("ok")} for t in reply.tools_used],
            "passed": j["passed"], "category": cat, "judge": j,
        })
    n = len(results)
    passed = sum(r["passed"] for r in results)
    s1 = llm.snapshot()
    return {"score": round(100 * passed / n, 1) if n else 0.0, "n": n, "passed": passed, "results": results,
            "taxonomy": dict(Counter(r["category"] for r in results if r["category"])),
            "tokens": s1["tokens"] - s0["tokens"], "latency_s": round(time.monotonic() - t0, 2)}


# ---------------------------------------------------------------- targeted fixes
def _prompt_diff(old: AgentDef, new: AgentDef) -> str:
    return "".join(difflib.unified_diff((old.full_prompt() + "\n").splitlines(True), (new.full_prompt() + "\n").splitlines(True),
                                        "system_prompt (before)", "system_prompt (after)", n=1))


def apply_fix(category: str, agent: AgentDef, failures: list[dict], llm: LLM) -> tuple[AgentDef, dict]:
    new = agent.model_copy(deep=True)
    if category == "retrieval_miss":
        if agent.top_k < 8:
            new.top_k = agent.top_k + 2
            what = f"top_k {agent.top_k} -> {new.top_k}"
        else:
            new.chunk_size = max(300, int(agent.chunk_size * 0.7))
            new.chunk_overlap = new.chunk_size // 6
            what = f"chunk_size {agent.chunk_size} -> {new.chunk_size}"
        diff = f"- {what.split(' -> ')[0]}\n+ {what.split(' ')[0]} {what.split(' -> ')[1]}"
    elif category == "prompt_defect":
        examples = [{"question": f["question"], "expected_facts": f["expected_key_facts"], "answer": f["answer"][:400]}
                    for f in failures[:5]]
        patch = llm.call("prompt_patch", "prompt_patch", {"system_prompt": agent.full_prompt(), "failures": examples},
                         PromptPatch, fallback="mock")
        add = [r for r in patch.add_rules[:2] if r not in new.rules]
        new.rules += add
        what = f"prompt patch: +{len(add)} rule(s) ({patch.rationale[:120]})"
        diff = _prompt_diff(agent, new)
    elif category == "hallucination":
        if STRICT_RULE not in new.rules:
            new.rules.append(STRICT_RULE)
        new.refusal_threshold = round(min(0.95, agent.refusal_threshold + 0.05), 3)
        what = f"stricter grounding rule + refusal_threshold {agent.refusal_threshold} -> {new.refusal_threshold}"
        diff = _prompt_diff(agent, new) + f"\n- refusal_threshold: {agent.refusal_threshold}\n+ refusal_threshold: {new.refusal_threshold}"
    elif category == "wrong_refusal":
        if LENIENT_RULE not in new.rules:
            new.rules.append(LENIENT_RULE)
        new.refusal_threshold = round(max(0.02, agent.refusal_threshold - 0.05), 3)
        what = f"'answer if context contains it' rule + refusal_threshold {agent.refusal_threshold} -> {new.refusal_threshold}"
        diff = _prompt_diff(agent, new) + f"\n- refusal_threshold: {agent.refusal_threshold}\n+ refusal_threshold: {new.refusal_threshold}"
    else:
        raise ValueError(category)
    return new, {"category": category, "summary": what, "diff": diff}


# ---------------------------------------------------------------- loop
def optimize(agent: AgentDef, evaluate: Callable[[AgentDef], dict], llm: LLM, max_iter: int = 3,
             target: float = 90.0, emit: Callable = NOOP, baseline: dict | None = None) -> dict:
    max_iter = min(max_iter, 3)
    cur = baseline or evaluate(agent)
    iterations = [{"iteration": 0, "kind": "baseline", "score_before": None, "score_after": cur["score"],
                   "taxonomy": cur["taxonomy"], "tokens": cur["tokens"], "latency_s": cur["latency_s"]}]
    emit("iteration_result", **iterations[0])
    tried: set[str] = set()
    stop = f"max_iterations ({max_iter}) reached"
    for it in range(1, max_iter + 1):
        if cur["score"] >= target:
            stop = f"target reached ({cur['score']} >= {target})"
            break
        failures = [r for r in cur["results"] if not r["passed"]]
        if not failures:
            stop = "no failures left"
            break
        counts = Counter(r["category"] for r in failures)
        ranked = sorted((c for c in counts if c not in tried), key=lambda c: (-counts[c], CATEGORIES.index(c)))
        if not ranked:
            stop = "every failure category already targeted"
            break
        cat = ranked[0]
        targeted = [r for r in failures if r["category"] == cat]
        t0, s0 = time.monotonic(), llm.snapshot()
        try:
            cand, change = apply_fix(cat, agent, targeted, llm)
            new = evaluate(cand)
        except BudgetExceeded as e:
            stop = f"budget exhausted: {e}"
            iterations.append({"iteration": it, "kind": "aborted", "category": cat, "reason": str(e)})
            break
        prev = {r["case_id"]: r["passed"] for r in cur["results"]}
        now = {r["case_id"]: r["passed"] for r in new["results"]}
        fixed = [r["case_id"] for r in targeted if now.get(r["case_id"])]
        newly = [k for k, v in now.items() if v and not prev.get(k)]
        regress = [k for k, v in now.items() if not v and prev.get(k)]
        gain = round(new["score"] - cur["score"], 1)
        reverted = new["score"] < cur["score"]
        rec = {"iteration": it, "kind": "fix", "category": cat, "why": f"{counts[cat]} of {len(failures)} failures are {cat}: {CATEGORY_REASON[cat]}",
               "change": change["summary"], "diff": change["diff"], "targeted_failure_ids": [r["case_id"] for r in targeted],
               "fixed_ids": fixed, "newly_passing_ids": newly, "regression_ids": regress,
               "score_before": cur["score"], "score_after": new["score"], "gain": gain,
               "decision": "reverted (score dropped)" if reverted else "kept",
               "taxonomy_before": cur["taxonomy"], "taxonomy_after": new["taxonomy"],
               "tokens": llm.snapshot()["tokens"] - s0["tokens"], "latency_s": round(time.monotonic() - t0, 2)}
        iterations.append(rec)
        emit("iteration_result", **{k: v for k, v in rec.items() if k != "diff"})
        tried.add(cat)
        if not reverted:
            agent, cur = cand, new
        if gain < 1:
            stop = f"early stop: iteration {it} gained {gain} points (< 1)" + (" and was reverted" if reverted else "")
            break
    return {"agent": agent, "final_eval": cur, "iterations": iterations, "stop_reason": stop}
