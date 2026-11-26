from forgeai.generator import build_agent, validate_tools
from forgeai.groundability import check_groundability
from forgeai.ingest import chunk_all
from forgeai.intake import MAX_QUESTIONS, filter_questions, run_intake
from forgeai.retrieval import Retriever, calibrate_threshold
from forgeai.schemas import QA, Requirements

HR_BRIEF = ("I need an assistant that answers HR policy questions for shore staff: leave entitlements, the code of conduct, "
            "travel and expense claims, and our employee pension and retirement plan.")


def test_question_cap_and_filters():
    qs = [f"Question about distinct thing number {w}?" for w in "alpha beta gamma delta epsilon zeta eta theta".split()]
    qs += ["Question about distinct thing number alpha?", "Should it answer HR policy questions for shore staff?"]
    kept, dropped = filter_questions(qs, HR_BRIEF, [])
    assert len(kept) == MAX_QUESTIONS == 5
    reasons = " ".join(d["reason"] for d in dropped)
    assert "duplicate" in reasons and "answerable from the brief" in reasons and "cap" in reasons


def test_intake_interactive_and_auto(hr_docs, llm):
    asked = {}

    def answer_fn(qs):
        asked["qs"] = qs
        return ["Shore-based office staff only"] + [None] * (len(qs) - 1)  # None -> ForgeAI answers

    req, infos, dropped = run_intake(HR_BRIEF, hr_docs, llm, answer_fn)
    assert 0 < len(asked["qs"]) <= 5
    assert req.clarifications[0].answered_by == "requester"
    assert all(c.answered_by == "forgeai" for c in req.clarifications[1:])
    assert any("pension" in t for t in req.must_answer)
    assert len(infos) == 3 and dropped


def _ret(docs):
    r = Retriever(chunk_all(docs, 700, 110), 0.5)
    return r, calibrate_threshold(r)[0]


def test_guard_moves_unsupported_topic_to_must_refuse(hr_docs, llm):
    req = Requirements(scope=HR_BRIEF, audience="shore staff", must_answer=["sick leave", "gifts and hospitality", "employee pension and retirement plan"])
    r, thr = _ret(hr_docs)
    req, flags = check_groundability(req, r, llm, thr, "assistant for HR questions; it should also email the HR team")
    assert "employee pension and retirement plan" in req.must_refuse
    assert "employee pension and retirement plan" not in req.must_answer
    assert {"sick leave", "gifts and hospitality"} <= set(req.must_answer)
    assert any(f["type"] == "tool_gap" and "email" in f["capability"] for f in flags)


def test_tool_validator_hr_rejects_weather_and_csv(hr_docs):
    req = Requirements(scope=HR_BRIEF, audience="shore staff", must_answer=["leave", "code of conduct"])
    proposed = [{"name": n, "justification": "useful"} for n in ("weather", "csv_lookup", "calculator", "current_date")]
    attached, rejected = validate_tools(proposed, HR_BRIEF, req, hr_docs)
    rej = {r["name"]: r["reason"] for r in rejected}
    assert "weather" in rej and "csv_lookup" in rej
    assert "weather" not in [a["name"] for a in attached]


def test_tool_validator_spares_attaches_csv_and_calculator_not_weather(spares_docs, demos):
    brief = (demos / "spares" / "brief.txt").read_text()
    req = Requirements(scope=brief, audience="superintendents", must_answer=["spare parts"])
    attached, rejected = validate_tools([{"name": "weather"}, {"name": "calculator"}], brief, req, spares_docs)
    names = [a["name"] for a in attached]
    assert set(names) == {"csv_lookup", "calculator"}  # csv_lookup added by validator although the LLM omitted it
    assert any(a["attached_by"] == "validator" for a in attached)
    assert "weather" in [r["name"] for r in rejected]


def test_weather_only_from_requester_words(hr_docs):
    req = Requirements(scope="x", audience="y", must_answer=["z"], clarifications=[QA(question="q", answer="check the weather forecast", answered_by="forgeai")])
    att, _ = validate_tools([{"name": "weather"}], "HR questions", req, hr_docs)
    assert not att  # an LLM self-answer can't smuggle a tool in


def test_weather_attached_when_brief_mentions_conditions_at_location(hr_docs):
    req = Requirements(scope="x", audience="crew", must_answer=["port calls"])
    att, _ = validate_tools([{"name": "weather"}], "Assistant for crew: port call info and conditions at the destination port", req, hr_docs)
    assert [a["name"] for a in att] == ["weather"]


def test_build_agent_definition(hr_docs, llm):
    req = Requirements(scope=HR_BRIEF, audience="shore staff", must_answer=["sick leave"], must_refuse=["pension"])
    agent, log = build_agent(HR_BRIEF, req, hr_docs, [{"name": d.name, "summary": d.text[:50]} for d in hr_docs], llm)
    assert agent.tools == [] and {r["name"] for r in log["rejected"]} == {"weather", "csv_lookup", "calculator", "current_date"}
    assert "Non-negotiable rules" in agent.system_prompt and "pension" in agent.system_prompt
    assert set(agent.output_contract) == {"answer", "sources", "confidence", "refused"}
    assert 0 < agent.refusal_threshold < 1 and agent.chunk_size > agent.chunk_overlap
