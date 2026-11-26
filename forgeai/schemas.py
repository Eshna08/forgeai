"""Pydantic contracts for every LLM output and every artifact."""
from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, field_validator


def _clean_list(v: Any) -> list[str]:
    if v is None:
        return []
    if isinstance(v, str):
        v = [v]
    out, seen = [], set()
    for x in v:
        s = str(x).strip().strip("-• ").strip()
        if s and s.lower() not in seen:
            seen.add(s.lower())
            out.append(s)
    return out


# ---------- intake ----------
class IntakeQuestions(BaseModel):
    questions: list[str] = Field(default_factory=list)
    v_clean = field_validator("questions", mode="before")(_clean_list)


class IntakeAnswers(BaseModel):
    answers: list[str] = Field(default_factory=list)


class QA(BaseModel):
    question: str
    answer: str
    answered_by: Literal["requester", "forgeai"] = "requester"


class Requirements(BaseModel):
    title: str = "Document assistant"
    scope: str
    audience: str
    tone: str = "professional and concise"
    must_answer: list[str]
    must_refuse: list[str] = Field(default_factory=list)
    out_of_scope_behavior: str = "Politely refuse and say the documents do not cover it."
    clarifications: list[QA] = Field(default_factory=list)
    flags: list[dict] = Field(default_factory=list)

    v_clean = field_validator("must_answer", "must_refuse", mode="before")(_clean_list)

    @field_validator("must_answer")
    @classmethod
    def _non_empty(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError("must_answer needs at least one topic")
        return v[:12]


class GroundVerdict(BaseModel):
    verdict: Literal["supported", "partial", "unsupported"]
    reason: str = ""

    @field_validator("verdict", mode="before")
    @classmethod
    def _low(cls, v: Any) -> str:
        return str(v).strip().lower()


# ---------- generator ----------
class ToolChoice(BaseModel):
    name: str
    justification: str = ""


class ToolProposal(BaseModel):
    tools: list[ToolChoice] = Field(default_factory=list)


class SystemPromptOut(BaseModel):
    system_prompt: str

    @field_validator("system_prompt")
    @classmethod
    def _len(cls, v: str) -> str:
        if len(v.strip()) < 40:
            raise ValueError("system_prompt too short")
        return v.strip()


DEFAULT_CONTRACT = {
    "answer": "string - the answer, grounded only in context/tool results",
    "sources": "list[string] - document names actually used",
    "confidence": "float 0..1",
    "refused": "bool - true when the agent declines",
}


class AgentDef(BaseModel):
    name: str
    description: str = ""
    system_prompt: str
    rules: list[str] = Field(default_factory=list)  # targeted patches appended by the optimizer
    must_refuse: list[str] = Field(default_factory=list)
    chunk_size: int = Field(700, ge=150, le=4000)
    chunk_overlap: int = Field(100, ge=0, le=1000)
    top_k: int = Field(4, ge=1, le=12)
    hybrid_weight: float = Field(0.5, ge=0, le=1)  # weight of dense embeddings vs BM25
    refusal_threshold: float = Field(0.25, ge=0, le=1)
    embedding: str | None = None  # embedder the threshold was calibrated with ("fastembed" | "hash")
    tools: list[str] = Field(default_factory=list)
    output_contract: dict = Field(default_factory=lambda: dict(DEFAULT_CONTRACT))
    refusal_message: str = "I'm sorry, I can't answer that from the documents I have access to."
    max_tool_calls: int = 2

    def full_prompt(self) -> str:
        if not self.rules:
            return self.system_prompt
        return self.system_prompt + "\n\nAdditional rules:\n" + "\n".join(f"- {r}" for r in self.rules)


# ---------- runtime ----------
class ToolCall(BaseModel):
    name: str
    args: dict = Field(default_factory=dict)


def _clamp01(v: Any) -> float:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return 0.5
    return min(1.0, max(0.0, f))


class AgentTurn(BaseModel):
    action: Literal["answer", "tool"] = "answer"
    tool: Optional[ToolCall] = None
    answer: str = ""
    sources: list[str] = Field(default_factory=list)
    confidence: float = 0.5
    refused: bool = False

    v_clean = field_validator("confidence", mode="before")(_clamp01)
    v_sources = field_validator("sources", mode="before")(_clean_list)


class AgentReply(BaseModel):
    """The output contract every generated agent must satisfy (+ diagnostics)."""

    answer: str
    sources: list[str]
    confidence: float = Field(ge=0, le=1)
    refused: bool
    gate: str = ""  # "retrieval" if the deterministic refusal gate fired
    tools_used: list[dict] = Field(default_factory=list)
    retrieval_confidence: float = 0.0
    retrieved: list[dict] = Field(default_factory=list)


# ---------- evals ----------
class EvalCase(BaseModel):
    id: str = ""
    type: Literal["answerable", "out_of_scope", "edge"]
    subtype: str = ""
    question: str
    expected_source_docs: list[str] = Field(default_factory=list)
    expected_key_facts: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)  # strings that must be retrieved for a retrieval hit
    should_refuse: bool = False
    split: Literal["dev", "heldout"] = "dev"
    origin: str = "llm"


class GenQA(BaseModel):
    question: str
    key_facts: list[str]
    v_clean = field_validator("key_facts", mode="before")(_clean_list)


class GenQuestions(BaseModel):
    questions: list[str]
    v_clean = field_validator("questions", mode="before")(_clean_list)


class GenCross(BaseModel):
    question: str
    key_facts_a: list[str]
    key_facts_b: list[str]
    v_clean = field_validator("key_facts_a", "key_facts_b", mode="before")(_clean_list)


class GenFalsePremise(BaseModel):
    question: str
    correct_fact: str


class JudgeLLMVerdict(BaseModel):
    correct: bool
    grounded: bool
    unsupported_claims: list[str] = Field(default_factory=list)
    reason: str = ""


class PromptPatch(BaseModel):
    add_rules: list[str]
    rationale: str = ""
    v_clean = field_validator("add_rules", mode="before")(_clean_list)
