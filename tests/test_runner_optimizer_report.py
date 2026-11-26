from forgeai.optimizer import apply_fix, classify, optimize
from forgeai.report import build_report
from forgeai.runner import AgentRuntime
from forgeai.schemas import AgentDef, AgentReply, EvalCase


def _agent(**kw):
    base = dict(name="t", system_prompt="You answer HR questions from the context.", refusal_threshold=0.3, tools=[],
                must_refuse=["employee pension and retirement plan"])
    base.update(kw)
    return AgentDef(**base)


def test_runner_answers_with_valid_contract(hr_docs, llm):
    rt = AgentRuntime(_agent(), hr_docs, llm)
    r = rt.ask("How many days of paid sick leave do employees receive per calendar year?")
    assert not r.refused and "10 days" in r.answer and r.sources == ["leave_policy.pdf"]
    assert 0 <= r.confidence <= 1 and AgentReply.model_validate(r.model_dump())


def test_runner_refusal_gate_and_must_refuse(hr_docs, llm):
    rt = AgentRuntime(_agent(), hr_docs, llm)
    g = rt.ask("Who painted the Sistine Chapel ceiling?")
    assert g.refused and g.gate == "retrieval" and g.sources == [] and g.answer == rt.agent.refusal_message
    p = rt.ask("How does the employee pension and retirement plan work for leave?")
    assert p.refused


def test_runner_tool_protocol_max_two_calls(spares_docs, llm):
    rt = AgentRuntime(_agent(tools=["csv_lookup", "calculator"], hybrid_weight=0.35, refusal_threshold=0.1), spares_docs, llm)
    row = next(d for d in spares_docs if d.rows).rows[2]
    r = rt.ask(f"What would 3 units of {row['name']} ({row['part_id']}) cost in total at the catalogue unit price?")
    assert [t["tool"] for t in r.tools_used] == ["csv_lookup", "calculator"]
    assert f"{3 * float(row['unit_price']):.2f}" in r.answer


def test_runner_blocks_unattached_tool(hr_docs, llm, monkeypatch):
    rt = AgentRuntime(_agent(refusal_threshold=0.0), hr_docs, llm)
    from forgeai.schemas import AgentTurn
    turns = iter([AgentTurn(action="tool", tool={"name": "weather", "args": {"location": "Oslo"}}),
                  AgentTurn(answer="Sick leave is 10 days.", sources=["leave policy"], confidence=0.9)])
    monkeypatch.setattr(rt.llm, "call", lambda *a, **k: next(turns))
    r = rt.ask("sick leave days")
    assert r.tools_used[0]["ok"] is False and "not attached" in r.tools_used[0]["error"]
    assert r.sources == ["leave_policy.pdf"]  # contract: sources normalised to real file names


def test_classify_rules():
    c = EvalCase(type="answerable", question="q", expected_key_facts=["25 days"])
    hit = [{"chunk_id": "a#0", "doc": "a", "text": "You get 25 days."}]
    miss = [{"chunk_id": "b#0", "doc": "b", "text": "nothing"}]
    mk = lambda refused, ret, ans="x": AgentReply(answer=ans, sources=[], confidence=0.5, refused=refused, retrieved=ret)  # noqa: E731
    assert classify(c, mk(False, miss), {}) == "retrieval_miss"
    assert classify(c, mk(True, hit), {}) == "wrong_refusal"
    assert classify(c, mk(False, hit), {"unsupported": ["99"]}) == "hallucination"
    assert classify(c, mk(False, hit), {"unsupported": []}) == "prompt_defect"
    oos = EvalCase(type="out_of_scope", question="q", should_refuse=True)
    assert classify(oos, mk(False, hit), {}) == "hallucination"


def _fake_eval(score, cats):
    res = [{"case_id": f"C{i}", "passed": i < score // 10, "category": None if i < score // 10 else cats[i % len(cats)],
            "question": "q", "expected_key_facts": [], "answer": ""} for i in range(10)]
    return {"score": float(score), "results": res, "taxonomy": {}, "tokens": 1, "latency_s": 0.0}


def test_optimizer_reverts_on_drop_and_stops(llm):
    scores = iter([50, 40])
    out = optimize(_agent(), lambda a: _fake_eval(next(scores), ["retrieval_miss"]), llm, max_iter=3, target=90)
    it = out["iterations"][1]
    assert it["decision"].startswith("reverted") and it["score_after"] == 40
    assert out["agent"].top_k == _agent().top_k  # change was reverted
    assert "early stop" in out["stop_reason"] and len(out["iterations"]) == 2


def test_optimizer_max_three_iterations_and_targets(llm):
    scores = iter([40, 50, 60, 70, 80])
    out = optimize(_agent(), lambda a: _fake_eval(next(scores), ["retrieval_miss", "prompt_defect", "hallucination", "wrong_refusal"]), llm, max_iter=5, target=95)
    fixes = [i for i in out["iterations"] if i["kind"] == "fix"]
    assert len(fixes) == 3 and "max_iterations" in out["stop_reason"]
    assert len({f["category"] for f in fixes}) == 3 and all(f["diff"] for f in fixes)


def test_optimizer_target_and_plateau(llm):
    assert "target reached" in optimize(_agent(), lambda a: _fake_eval(100, ["x"]), llm, target=90)["stop_reason"]
    scores = iter([50, 50])
    out = optimize(_agent(), lambda a: _fake_eval(next(scores), ["prompt_defect"]), llm, target=90)
    assert "gained 0.0" in out["stop_reason"] and out["iterations"][1]["decision"] == "kept"


def test_targeted_fixes_are_minimal(llm):
    a = _agent()
    n, ch = apply_fix("hallucination", a, [], llm)
    assert n.refusal_threshold > a.refusal_threshold and n.system_prompt == a.system_prompt and len(n.rules) == 1
    n, ch = apply_fix("wrong_refusal", a, [], llm)
    assert n.refusal_threshold < a.refusal_threshold
    n, ch = apply_fix("prompt_defect", a, [{"question": "q", "expected_key_facts": ["f"], "answer": "a"}], llm)
    assert n.rules and "+- " in ch["diff"] or "+" in ch["diff"]


def _ctx(score, fails):
    res = [{"case_id": "A1", "split": "heldout", "type": "answerable", "subtype": "single_doc", "question": "q?", "passed": not fails,
            "category": "prompt_defect" if fails else None, "expected_key_facts": ["x"], "retrieved": [], "judge": {"deterministic": {}}}]
    part = {"score": score, "n": 1, "passed": int(not fails), "results": res, "taxonomy": {"prompt_defect": 1} if fails else {}}
    return {"run_id": "r", "status": "completed", "meta": {"provider": "mock", "models": {}}, "final": {"dev": part, "heldout": part}}


def test_report_has_failure_section_and_never_silent_100():
    md = build_report(_ctx(0.0, True))
    assert "## What still fails and why" in md and "A1" in md and "Known limits of this evaluation" in md
    md100 = build_report(_ctx(100.0, False))
    assert "NOT a claim that the agent is correct" in md100 and "Not tested:" in md100
    assert "## What still fails and why" in md100
