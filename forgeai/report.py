"""Requirement 7: honest reporting -> report.md + scorecard.json."""
from __future__ import annotations

import json
from pathlib import Path

from .optimizer import CATEGORIES, CATEGORY_REASON

KNOWN_LIMITS = [
    "The agent and the eval-generator run on a small open model; questions are synthetic and may be easier or "
    "more literal than what real users type.",
    "Expected facts are short literal spans from the documents. A correct answer phrased very differently can be "
    "scored as a miss (the LLM judge may rescue it only when both swapped-order runs agree).",
    "The LLM judge is itself a model: position-swap agreement and a separate judge model reduce, not remove, its biases.",
    "The eval set is small (~30 cases, ~9 held out). One case is several percentage points; treat scores as +/- 10 points.",
    "Not tested: multi-turn conversations, adversarial prompt injection hidden in documents, non-English questions, "
    "very long answers, documents added after the run, live tool failures (weather API outages), latency under load.",
    "Out-of-scope cases are generic or derived from must-refuse topics; subtle near-domain questions are under-represented.",
]


def _likely_reason(r: dict) -> str:
    cat = r.get("category")
    det = (r.get("judge") or {}).get("deterministic", {})
    if cat == "retrieval_miss":
        return f"expected evidence not in retrieved chunks ({', '.join(r['retrieved'][:3])})"
    if cat == "wrong_refusal":
        if r.get("gate") == "retrieval":
            return f"refusal gate fired: retrieval confidence {r['retrieval_confidence']} below threshold"
        return "model refused although the evidence was retrieved"
    if cat == "hallucination":
        if r.get("should_refuse"):
            return "answered a question that should have been refused"
        return f"unsupported terms in answer: {', '.join(det.get('unsupported') or [])}"
    missing = [f for f in r.get("expected_key_facts", []) if f not in (det.get("facts_found") or [])]
    if (r.get("judge") or {}).get("decided_by") == "llm_veto":
        return "deterministic checks passed but both judge orderings said incorrect/ungrounded"
    return f"evidence retrieved but answer missed: {', '.join(missing) or 'n/a'}"


def _table(rows: list[list], head: list[str]) -> list[str]:
    out = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    for r in rows:
        out.append("| " + " | ".join(str(x).replace("|", "/").replace("\n", " ") for x in r) + " |")
    return out


def build_scorecard(ctx: dict) -> dict:
    fin = ctx.get("final", {})
    return {
        "run_id": ctx.get("run_id"), "status": ctx.get("status"), "provider": ctx.get("meta", {}).get("provider"),
        "models": ctx.get("meta", {}).get("models"), "seed": ctx.get("meta", {}).get("seed"),
        "dev_score": fin.get("dev", {}).get("score"), "heldout_score": fin.get("heldout", {}).get("score"),
        "heldout_n": fin.get("heldout", {}).get("n"), "dev_n": fin.get("dev", {}).get("n"),
        "baseline_dev_score": (ctx.get("iterations") or [{}])[0].get("score_after"),
        "stop_reason": ctx.get("stop_reason"),
        "iterations": [{k: i.get(k) for k in ("iteration", "kind", "category", "change", "score_before", "score_after", "decision", "taxonomy", "taxonomy_after", "tokens", "latency_s")} for i in ctx.get("iterations", [])],
        "taxonomy_final_heldout": fin.get("heldout", {}).get("taxonomy"),
        "tools_attached": [t["name"] for t in ctx.get("tool_log", {}).get("attached", [])],
        "tools_rejected": [t["name"] for t in ctx.get("tool_log", {}).get("rejected", [])],
        "judge_selftest": {k: ctx.get("selftest", {}).get(k) for k in ("n", "n_correct", "all_correct")},
        "tournament_winner": (ctx.get("tournament") or {}).get("winner"),
        "budget": ctx.get("usage"),
    }


def build_report(ctx: dict) -> str:
    meta, req, agent = ctx.get("meta", {}), ctx.get("requirements") or {}, ctx.get("agent") or {}
    fin = ctx.get("final", {})
    dev, held = fin.get("dev", {}), fin.get("heldout", {})
    L = [f"# ForgeAI report - {req.get('title', ctx.get('run_id'))}", "",
         f"- Run: `{ctx.get('run_id')}` | status: **{ctx.get('status')}** | provider: `{meta.get('provider')}` "
         f"| agent model: `{meta.get('models', {}).get('agent')}` | judge model: `{meta.get('models', {}).get('judge')}` | seed: {meta.get('seed')}",
         ""]
    if meta.get("provider") == "mock":
        L += ["> **This run used the deterministic MockLLM (no real model).** Scores show the factory's mechanics, "
              "not the quality of a real model. Re-run with a real provider for meaningful numbers.", ""]
    if held:
        L += ["## Headline", "",
              f"**Held-out score: {held['score']}%** ({held['passed']}/{held['n']} cases) - this is the number to quote.",
              f"Dev score (used by tournament/optimizer, therefore optimistic): {dev.get('score')}% ({dev.get('passed')}/{dev.get('n')}).",
              f"Stop reason: {ctx.get('stop_reason')}", ""]
        if held["score"] >= 100 or dev.get("score", 0) >= 100:
            L += ["> **100% here is NOT a claim that the agent is correct.** It means every case in a small synthetic "
                  f"set ({held['n']} held-out cases) passed. See *Known limits* for everything that was not tested.", ""]

    L += ["## Agent definition summary", "",
          f"- name: `{agent.get('name')}`; tools: {', '.join(agent.get('tools', [])) or 'none'}",
          f"- retrieval: chunk_size={agent.get('chunk_size')}, overlap={agent.get('chunk_overlap')}, top_k={agent.get('top_k')}, "
          f"hybrid_weight(dense)={agent.get('hybrid_weight')}, refusal_threshold={agent.get('refusal_threshold')}",
          f"- output contract: {', '.join(agent.get('output_contract', {}).keys())}",
          f"- optimizer-added rules: {len(agent.get('rules', []))}", "", "<details><summary>System prompt</summary>", "",
          "```", agent.get("system_prompt", "") + ("\n\nAdditional rules:\n" + "\n".join("- " + r for r in agent.get("rules", [])) if agent.get("rules") else ""),
          "```", "</details>", ""]

    calib = (ctx.get("tool_log") or {}).get("calibration")
    if calib:
        L += [f"Refusal threshold calibration: {calib}", ""]

    tl = ctx.get("tool_log") or {}
    L += ["## Tools attached / rejected", ""]
    L += _table([[t["name"], "attached", t.get("attached_by", ""), t.get("rule", "")] for t in tl.get("attached", [])] +
                [[t["name"], "rejected", t.get("proposed_by", ""), t.get("reason", "")] for t in tl.get("rejected", [])],
                ["tool", "decision", "by", "reason"]) + [""]

    flags = req.get("flags") or []
    L += ["## Groundability flags", ""]
    if flags:
        L += _table([[f.get("topic", f.get("capability", "")), f.get("verdict"), f.get("retrieval_confidence", "-"),
                      f.get("llm_verdict", "-"), f.get("message", f.get("reason", ""))] for f in flags],
                    ["topic / capability", "verdict", "retrieval conf", "LLM verdict", "action"]) + [""]
    else:
        L += ["No flags.", ""]
    if ctx.get("ingest_warnings"):
        L += ["Ingestion warnings:", *[f"- {w}" for w in ctx["ingest_warnings"]], ""]

    es = ctx.get("eval_stats") or {}
    if es:
        L += ["## Eval set", "", f"{es.get('total')} cases: {es.get('by_type')}; subtypes {es.get('by_subtype')}; "
              f"dev {es.get('dev')} / held-out {es.get('heldout')}. Documents covered: {len(es.get('docs_covered', []))}, "
              f"uncovered: {es.get('docs_uncovered') or 'none'}. Dropped during verification: {ctx.get('eval_dropped', 0)}.", ""]
        if not es.get("meets_minimums"):
            L += ["> Eval set is BELOW the target minimums (>=24 cases, >=12/6/6 per type) - scores are less reliable.", ""]

    st = ctx.get("selftest")
    if st:
        L += ["## Judge self-test", "", f"{st['n_correct']}/{st['n']} known-good/known-bad answers judged as expected.", ""]
        L += _table([[r["case"], r["expected_pass"], r["judged_pass"], "ok" if r["caught"] else "**MISSED**", r["decided_by"]] for r in st["cases"]],
                    ["case", "expected pass", "judged pass", "result", "decided by"]) + [""]

    t = ctx.get("tournament")
    if t:
        L += ["## Prompt tournament (dev split)", "", f"Rule: {t['rule']}. Winner: **{t['winner']}**.", ""]
        L += _table([[c["strategy"], c["score"], c["hallucinations"], c["tokens"]] for c in t["candidates"]],
                    ["strategy", "dev score", "hallucinations", "tokens"]) + [""]

    its = ctx.get("iterations") or []
    if its:
        L += ["## Per-iteration scorecard (dev split)", ""]
        L += _table([[i["iteration"], i.get("category", "baseline"), i.get("change", "-"), i.get("score_before", "-"),
                      i.get("score_after", "-"), i.get("decision", "-"), len(i.get("fixed_ids", [])),
                      len(i.get("regression_ids", [])), i.get("tokens", "-"), i.get("latency_s", "-")] for i in its],
                    ["iter", "target", "change", "before", "after", "decision", "fixed", "regressions", "tokens", "seconds"]) + [""]
        L += ["### Failure taxonomy per iteration", ""]
        L += _table([[i["iteration"], *[(i.get("taxonomy_after") or i.get("taxonomy") or {}).get(c, 0) for c in CATEGORIES]] for i in its],
                    ["iter", *CATEGORIES]) + [""]
        for i in its:
            if i.get("diff"):
                L += [f"<details><summary>Iteration {i['iteration']} diff ({i['category']})</summary>", "", "```diff", i["diff"], "```", "</details>", ""]

    if held:
        L += ["## Final failure taxonomy (held-out)", ""]
        L += _table([[c, held.get("taxonomy", {}).get(c, 0), CATEGORY_REASON[c]] for c in CATEGORIES], ["category", "count", "meaning"]) + [""]

    fails = [r for part in (held, dev) for r in part.get("results", []) if not r["passed"]]
    L += ["## What still fails and why", ""]
    if fails:
        L += _table([[r["case_id"], r["split"], r["type"] + "/" + r["subtype"], r["question"][:100], r["category"], _likely_reason(r)] for r in fails],
                    ["case", "split", "type", "question", "category", "likely reason"]) + [""]
    elif held or dev:
        L += ["No case in the dev or held-out split fails. That does not mean the agent is flawless - only that this small "
              "synthetic set found nothing. See the limits below.", ""]
    else:
        L += ["The run did not reach evaluation, so nothing was measured.", ""]

    if ctx.get("error"):
        L += ["## Run failure", "", f"Stage **{ctx['error']['stage']}** failed: `{ctx['error']['message']}`", "",
              "Artifacts written before the failure are kept in the run folder.", ""]

    u = ctx.get("usage") or {}
    L += ["## Budget and cost", "", f"Tokens: {u.get('tokens')} (cap {u.get('max_tokens')}), LLM calls: {u.get('calls')}, "
          f"wall clock: {u.get('elapsed_s')}s (cap {u.get('max_seconds')}s), fallbacks used: {u.get('fallbacks')}.",]
    if ctx.get("budget_grace"):
        L += [f"> Budget exhausted: {ctx['budget_grace']}."]
    L += [""]
    L += ["## Known limits of this evaluation", "", *[f"- {x}" for x in KNOWN_LIMITS], ""]
    return "\n".join(L)


def write_report(run_dir: Path, ctx: dict) -> None:
    try:
        md = build_report(ctx)
    except Exception as e:  # the report must exist even if a section breaks
        md = f"# ForgeAI report (degraded)\n\nReport rendering failed: {e}\n\nStatus: {ctx.get('status')}\n\n## What still fails and why\n\nUnknown - see results_final.json.\n\n## Known limits of this evaluation\n\n" + "\n".join("- " + x for x in KNOWN_LIMITS)
    (run_dir / "report.md").write_text(md, encoding="utf-8")
    (run_dir / "scorecard.json").write_text(json.dumps(build_scorecard(ctx), indent=2, default=str), encoding="utf-8")
