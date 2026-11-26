import pytest

from forgeai.llm import LLM, Budget, BudgetExceeded, LLMError, repair_json
from forgeai.schemas import GroundVerdict


def test_repair_json_variants():
    assert repair_json('```json\n{"a": 1,}\n```') == {"a": 1}
    assert repair_json('Sure! {"ok": True, "x": None}') == {"ok": True, "x": None}
    with pytest.raises(ValueError):
        repair_json("no json here")


def test_retries_then_validates(monkeypatch):
    llm = LLM()
    outputs = iter(["not json", '{"verdict": "maybe"}', '{"verdict": "Supported", "reason": "x"}'])
    monkeypatch.setattr(llm, "_complete", lambda *a, **k: next(outputs))
    v = llm.call("groundability", "groundability", {"topic": "t", "passages": []}, GroundVerdict)
    assert v.verdict == "supported" and llm.stats["validation_retries"] == 2


def test_fallback_and_error(monkeypatch):
    llm = LLM()
    monkeypatch.setattr(llm, "_complete", lambda *a, **k: "garbage")
    with pytest.raises(LLMError):
        llm.call("groundability", "groundability", {"topic": "t", "passages": []}, GroundVerdict)
    v = llm.call("groundability", "groundability", {"topic": "leave", "passages": ["leave"]}, GroundVerdict, fallback="mock")
    assert v.verdict == "supported" and llm.stats["fallbacks"] == 1


def test_budget_enforced():
    llm = LLM(budget=Budget(max_tokens=10))
    with pytest.raises(BudgetExceeded):
        for _ in range(5):
            llm.call("groundability", "groundability", {"topic": "t", "passages": []}, GroundVerdict)
    assert llm.stats["tokens_in"] > 0


def test_judge_role_uses_separate_model():
    llm = LLM()
    assert llm.model_for("judge") != llm.model_for("agent")
