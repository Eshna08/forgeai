import pytest

from forgeai.evalgen import fact_in_text, generate_evalset
from forgeai.ingest import chunk_all
from forgeai.judge import deterministic_checks, judge_case, judge_selftest, llm_judge
from forgeai.retrieval import Retriever, calibrate_threshold
from forgeai.schemas import AgentReply, EvalCase, JudgeLLMVerdict, Requirements


def _gen(docs, llm, must_refuse=("employee pension and retirement plan",)):
    chunks = chunk_all(docs, 600, 100)
    r = Retriever(chunks, 0.5)
    thr = calibrate_threshold(r)[0]
    req = Requirements(scope="HR policy assistant for shore staff", audience="shore staff", must_answer=["leave"], must_refuse=list(must_refuse))
    cases, log = generate_evalset(docs, chunks, r, req, thr, llm, seed=1)
    return cases, log, chunks


@pytest.mark.parametrize("which", ["hr_docs", "spares_docs"])
def test_evalset_size_types_coverage_and_verified_facts(which, request, llm):
    docs = request.getfixturevalue(which)
    cases, log, chunks = _gen(docs, llm)
    st = log["stats"]
    assert st["total"] >= 24 and st["meets_minimums"]
    assert st["by_type"]["answerable"] >= 12 and st["by_type"]["out_of_scope"] >= 6 and st["by_type"]["edge"] >= 6
    assert not st["docs_uncovered"]
    alltext = "\n".join(d.text for d in docs)
    for c in cases:
        if c.type != "out_of_scope" and c.subtype != "computation":
            assert c.expected_key_facts and all(fact_in_text(f, alltext) for f in c.expected_key_facts), c
    assert {c.split for c in cases} == {"dev", "heldout"}
    assert 0.2 <= st["heldout"] / st["total"] <= 0.4
    assert any(c.subtype == "must_refuse_topic" for c in cases)


def test_csv_cases_computed_in_code(spares_docs, llm):
    cases, _, _ = _gen(spares_docs, llm)
    csv = next(d for d in spares_docs if d.rows)
    by_id = {r["part_id"]: r for r in csv.rows}
    calc = [c for c in cases if c.subtype == "computation"]
    assert calc
    for c in calc:
        qty = int(c.question.split("What would ")[1].split()[0])
        pid = c.evidence[0]
        assert c.expected_key_facts == [f"{qty * float(by_id[pid]['unit_price']):.2f}"] and c.origin == "code"


def _reply(answer, refused=False, ctx="Employees receive 25 days of annual leave."):
    return AgentReply(answer=answer, sources=["a.md"], confidence=0.8, refused=refused,
                      retrieved=[{"chunk_id": "a.md#0", "doc": "a.md", "text": ctx}])


def test_deterministic_checks():
    case = EvalCase(type="answerable", question="How much leave?", expected_key_facts=["25 days"], expected_source_docs=["a.md"])
    ok = deterministic_checks(case, _reply("You get 25 days of annual leave."))
    assert ok["det_pass"] and ok["fact_coverage"] == 1 and ok["source_overlap"] == 1
    bad = deterministic_checks(case, _reply("You get 25 days plus 5 bonus days from the Wellness Fund."))
    assert not bad["det_pass"] and "5" in bad["unsupported"] and "Wellness" in bad["unsupported"]
    assert deterministic_checks(case, _reply("25 days", refused=True))["refusal_ok"] is False
    assert not deterministic_checks(case, _reply("You get twenty days."))["det_pass"]


def test_judge_selftest_catches_known_bad(llm):
    r = judge_selftest(llm)
    assert r["n"] >= 6 and r["all_correct"], r


class _DisagreeLLM:
    """Says 'correct' when the context comes first and 'incorrect' when the answer comes first."""

    def call(self, task, template, vars, schema, **kw):
        good = vars["first_label"] == "CONTEXT"
        return JudgeLLMVerdict(correct=good, grounded=good)


def test_position_swap_disagreement_falls_back_to_deterministic():
    case = EvalCase(id="X", type="answerable", question="How much leave?", expected_key_facts=["25 days"])
    lj = llm_judge(case, _reply("25 days of annual leave."), _DisagreeLLM())
    assert lj["status"] == "uncertain" and lj["correct"] is None
    res = judge_case(case, _reply("25 days of annual leave."), _DisagreeLLM())
    assert res["passed"] is True and res["decided_by"] == "deterministic_fallback_uncertain"


class _VetoLLM:
    def call(self, task, template, vars, schema, **kw):
        return JudgeLLMVerdict(correct=False, grounded=False, unsupported_claims=["x"])


def test_llm_veto_when_both_orders_agree():
    case = EvalCase(id="X", type="answerable", question="How much leave?", expected_key_facts=["25 days"])
    res = judge_case(case, _reply("25 days of annual leave."), _VetoLLM())
    assert res["passed"] is False and res["decided_by"] == "llm_veto"
