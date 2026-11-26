"""Requirement 5: hybrid judge.

Deterministic checks first (refusal match, fact coverage with normalised + fuzzy matching, source overlap,
every number / named term in the answer must exist in retrieved text). Then an LLM judge on a SEPARATE
model, run twice with the field order swapped (position bias); disagreement -> "uncertain" -> fall back to
the deterministic verdict. The rubric ignores length (verbosity bias) and the judge is never told who wrote
the answer (self-preference).
"""
from __future__ import annotations

import re

from rapidfuzz import fuzz

from .llm import LLM
from .schemas import AgentReply, EvalCase, JudgeLLMVerdict
from .textutil import content_tokens, humanize, norm, numbers

PASS_COVERAGE = 0.75
_ID = re.compile(r"\b[A-Z]{2,}-\d+\b")
_COMMON = {"The", "This", "That", "These", "Please", "According", "Yes", "Total", "However", "Note", "For", "If",
           "You", "Your", "Our", "Sorry", "Based", "Under", "Per", "Each", "All", "Any", "Employees", "Staff"}


def _num_in(n: float, pool: set[float]) -> bool:
    return any(abs(n - p) <= max(0.01, abs(p) * 1e-6) for p in pool)


def fact_in_answer(fact: str, answer: str) -> bool:
    nf, na = norm(fact), norm(answer)
    if not nf:
        return False
    if nf in na:
        return True
    fnums = numbers(fact)
    if fnums:
        anums = set(numbers(answer))
        if not all(_num_in(n, anums) for n in fnums):
            return False
        words = [t for t in content_tokens(fact) if not re.fullmatch(r"[\d.]+", t)]
        return not words or len(set(words) & set(content_tokens(answer))) / len(set(words)) >= 0.5
    if fuzz.partial_ratio(nf, na) >= 88:
        return True
    ft = set(content_tokens(fact))
    return bool(ft) and len(ft & set(content_tokens(answer))) / len(ft) >= 0.8


def unsupported_terms(answer: str, context: str, question: str) -> list[str]:
    """Numbers and named terms in the answer that appear nowhere in the context, tool output or question."""
    pool_text = f"{context}\n{question}"
    pool_nums = set(numbers(pool_text))
    pool_norm = norm(pool_text)
    bad = [m for m in re.findall(r"(?<![\w.])-?\d[\d,]*(?:\.\d+)?", answer)
           if not _num_in(float(m.replace(",", "")), pool_nums) and float(m.replace(",", "")) not in (1, 2, 3)]
    pool_words = set(pool_norm.split())
    for sent in re.split(r"(?<=[.!?])\s+|\n+", answer):
        for w in sent.split()[1:]:  # first word of a sentence is capitalised anyway
            w = w.strip(".,;:()[]\"'!?")
            if re.fullmatch(r"[A-Z][a-zA-Z]{2,}", w) and w not in _COMMON and w.lower() not in pool_words:
                bad.append(w)
    bad += [i for i in _ID.findall(answer) if i.lower() not in pool_text.lower()]
    return list(dict.fromkeys(bad))


def context_of(reply: AgentReply) -> str:
    parts = [f"(source: {humanize(r['doc'])})\n{r.get('text', '')}" for r in reply.retrieved]
    parts += [f"tool {t.get('tool')}: {t.get('result', t.get('error'))}" for t in reply.tools_used]
    return "\n\n".join(parts)


def deterministic_checks(case: EvalCase, reply: AgentReply) -> dict:
    d: dict = {"refusal_ok": reply.refused == case.should_refuse}
    if case.should_refuse or reply.refused:
        d.update(fact_coverage=None, facts_found=[], source_overlap=None, unsupported=[],
                 det_pass=d["refusal_ok"])
        return d
    found = [f for f in case.expected_key_facts if fact_in_answer(f, reply.answer)]
    cov = len(found) / len(case.expected_key_facts) if case.expected_key_facts else 0.0
    exp = set(case.expected_source_docs)
    src = len(exp & set(reply.sources)) / len(exp) if exp else None
    uns = unsupported_terms(reply.answer, context_of(reply), case.question)
    d.update(fact_coverage=round(cov, 3), facts_found=found, source_overlap=src, unsupported=uns,
             det_pass=cov >= PASS_COVERAGE and not uns)
    return d


def llm_judge(case: EvalCase, reply: AgentReply, llm: LLM) -> dict:
    ctx = context_of(reply)[:6000]
    facts = list(case.expected_key_facts)
    blocks = {"CONTEXT": ctx, "CANDIDATE ANSWER": reply.answer}
    verdicts = []
    for order in (("CONTEXT", "CANDIDATE ANSWER"), ("CANDIDATE ANSWER", "CONTEXT")):
        v = {"question": case.question, "expected_facts": facts if order[0] == "CONTEXT" else facts[::-1],
             "first_label": order[0], "first_block": blocks[order[0]],
             "second_label": order[1], "second_block": blocks[order[1]],
             "answer": reply.answer, "context": ctx}
        try:
            verdicts.append(llm.call("judge", "judge", v, JudgeLLMVerdict, role="judge", cache=True))
        except Exception as e:
            return {"status": "error", "error": str(e)[:200]}
    a, b = verdicts
    agree = a.correct == b.correct and a.grounded == b.grounded
    return {"status": "agree" if agree else "uncertain", "correct": a.correct if agree else None,
            "grounded": a.grounded if agree else None, "unsupported_claims": a.unsupported_claims,
            "order_a": a.model_dump(), "order_b": b.model_dump()}


def judge_case(case: EvalCase, reply: AgentReply, llm: LLM | None, mode: str = "hybrid") -> dict:
    det = deterministic_checks(case, reply)
    res = {"case_id": case.id, "deterministic": det, "llm": None, "decided_by": "deterministic"}
    passed = det["det_pass"]
    if mode == "hybrid" and llm is not None and not case.should_refuse and not reply.refused:
        lj = llm_judge(case, reply, llm)
        res["llm"] = lj
        if lj["status"] == "agree":
            ok = lj["correct"] and lj["grounded"]
            if passed and not ok:
                passed, res["decided_by"] = False, "llm_veto"
            elif not passed and ok and not det["unsupported"] and det["fact_coverage"] is not None:
                passed, res["decided_by"] = True, "llm_override_paraphrase"
            else:
                res["decided_by"] = "agreement"
        else:
            res["decided_by"] = "deterministic_fallback_" + lj["status"]
    res["passed"] = bool(passed)
    return res


# ---------------------------------------------------------------- self-test
_CTX = ("Full-time employees receive 25 days of paid annual leave per calendar year. "
        "Expense claims must be submitted within 30 days of travel.")


def _reply(answer: str, refused: bool = False) -> AgentReply:
    return AgentReply(answer=answer, sources=[] if refused else ["leave_policy.md"], confidence=0.8, refused=refused,
                      retrieved=[{"chunk_id": "leave_policy.md#0", "doc": "leave_policy.md", "text": _CTX}])


SELFTEST = [
    ("known-good answer", False, "How many days of annual leave do full-time employees get?", ["25 days"],
     "Full-time employees receive 25 days of paid annual leave per year.", False, True),
    ("verbose answer padded with an unsupported claim", False, "How many days of annual leave do full-time employees get?", ["25 days"],
     "Full-time employees receive 25 days of paid annual leave, plus 12 days of paid sick leave and a Christmas bonus "
     "under the Wellbeing Charter, which is a very generous package overall.", False, False),
    ("wrong number", False, "How many days of annual leave do full-time employees get?", ["25 days"],
     "Full-time employees receive 20 days of paid annual leave.", False, False),
    ("refused although the answer is in context", False, "When must expense claims be submitted?", ["30 days"],
     "", True, False),
    ("answered an out-of-scope question", True, "What is the company pension contribution rate?", [],
     "The company contributes 8% to your pension.", False, False),
    ("correct refusal of out-of-scope question", True, "What is the company pension contribution rate?", [],
     "", True, True),
    ("long but fully supported answer (length must not matter)", False, "When must expense claims be submitted?", ["30 days"],
     "Expense claims must be submitted within 30 days of travel. In other words, once you are back from your trip, "
     "make sure the claim goes in before 30 days have passed, as stated in the policy.", False, True),
]


def judge_selftest(llm: LLM | None, mode: str = "hybrid") -> dict:
    rows = []
    for i, (name, should_refuse, q, facts, ans, refused, expect_pass) in enumerate(SELFTEST):
        case = EvalCase(id=f"ST{i + 1}", type="out_of_scope" if should_refuse else "answerable", question=q,
                        expected_key_facts=facts, should_refuse=should_refuse, expected_source_docs=[] if should_refuse else ["leave_policy.md"])
        r = judge_case(case, _reply(ans or "I can't answer that.", refused), llm, mode)
        rows.append({"case": name, "expected_pass": expect_pass, "judged_pass": r["passed"],
                     "caught": r["passed"] == expect_pass, "decided_by": r["decided_by"],
                     "unsupported": r["deterministic"].get("unsupported")})
    return {"cases": rows, "n": len(rows), "n_correct": sum(r["caught"] for r in rows),
            "all_correct": all(r["caught"] for r in rows)}
