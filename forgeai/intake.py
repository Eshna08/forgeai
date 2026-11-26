"""Requirement 1: intake interviewer (<= 5 questions, enforced in code) -> requirements.json/.md."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

from .ingest import Document, doc_info
from .llm import LLM, NOOP
from .schemas import QA, IntakeAnswers, IntakeQuestions, Requirements
from .textutil import content_tokens, overlap

MAX_QUESTIONS = 5

# answer_fn(questions) -> list of answers; None / "" for an item means "let ForgeAI answer it"
AnswerFn = Callable[[list[str]], "list[str | None] | None"]


def inspect_docs(docs: list[Document]) -> list[dict]:
    return [doc_info(d) for d in docs]


def filter_questions(questions: list[str], brief: str, infos: list[dict]) -> tuple[list[str], list[dict]]:
    """Drop duplicates and questions already answered by the brief or the doc inventory; hard cap at 5."""
    brief_t = set(content_tokens(brief))
    docs_t = set(content_tokens(" ".join(f"{i['name']} {i['summary']}" for i in infos)))
    kept, dropped, seen = [], [], set()
    for q in questions:
        qt = set(content_tokens(q))
        key = " ".join(sorted(qt))
        if not qt or key in seen:
            dropped.append({"question": q, "reason": "duplicate or empty"})
        elif len(qt) >= 3 and overlap(qt, brief_t) >= 0.7:
            dropped.append({"question": q, "reason": "answerable from the brief"})
        elif len(qt) >= 3 and overlap(qt, docs_t) >= 0.85:
            dropped.append({"question": q, "reason": "answerable from the documents"})
        else:
            kept.append(q)
        seen.add(key)
    for q in kept[MAX_QUESTIONS:]:
        dropped.append({"question": q, "reason": f"over the {MAX_QUESTIONS}-question cap"})
    return kept[:MAX_QUESTIONS], dropped


def run_intake(brief: str, docs: list[Document], llm: LLM, answer_fn: AnswerFn | None = None,
               emit: Callable = NOOP) -> tuple[Requirements, list[dict], list[dict]]:
    infos = inspect_docs(docs)
    slim = [{k: i[k] for k in ("name", "type", "summary") if k in i} | (
        {"columns": i["columns"], "sample_rows": i["sample_rows"]} if "columns" in i else {}) for i in infos]
    qs = llm.call("intake_questions", "intake_questions", {"brief": brief, "docs": slim, "max_questions": str(MAX_QUESTIONS)},
                  IntakeQuestions, fallback={"questions": []}).questions
    kept, dropped = filter_questions(qs, brief, infos)
    emit("questions_asked", questions=kept, dropped=dropped)

    answers: list[str | None] = [None] * len(kept)
    if answer_fn and kept:
        got = answer_fn(kept) or []
        answers = [(got[i] if i < len(got) else None) for i in range(len(kept))]
    auto_idx = [i for i, a in enumerate(answers) if not (a and a.strip())]
    if auto_idx:
        auto_q = [kept[i] for i in auto_idx]
        auto = llm.call("intake_self_answer", "intake_self_answer", {"brief": brief, "docs": slim, "questions": auto_q},
                        IntakeAnswers, fallback="mock").answers
        for j, i in enumerate(auto_idx):
            answers[i] = auto[j] if j < len(auto) else "No preference; use the documents."
    qa = [QA(question=q, answer=a or "", answered_by="forgeai" if i in auto_idx else "requester")
          for i, (q, a) in enumerate(zip(kept, answers))]

    req = llm.call("requirements", "requirements",
                   {"brief": brief, "docs": slim, "clarifications": [x.model_dump() for x in qa]},
                   Requirements, fallback="mock")
    req.clarifications = qa
    return req, infos, dropped


def requirements_md(req: Requirements) -> str:
    L = [f"# Requirements: {req.title}", "", f"**Scope:** {req.scope}", "", f"**Audience:** {req.audience}", "",
         f"**Tone:** {req.tone}", "", "## Must answer", *[f"- {t}" for t in req.must_answer], "",
         "## Must refuse", *[f"- {t}" for t in req.must_refuse], "",
         f"**Out-of-scope behaviour:** {req.out_of_scope_behavior}", ""]
    if req.clarifications:
        L += ["## Clarifying questions", *[f"- **Q:** {c.question}\n  **A ({c.answered_by}):** {c.answer}" for c in req.clarifications], ""]
    if req.flags:
        L += ["## Groundability / capability flags", *[f"- **{f.get('verdict', f.get('type'))}** - {f.get('topic', f.get('capability', ''))}: {f.get('message', f.get('reason', ''))}" for f in req.flags], ""]
    return "\n".join(L)


def write_requirements(req: Requirements, out_dir: Path) -> None:
    (out_dir / "requirements.json").write_text(json.dumps(req.model_dump(), indent=2), encoding="utf-8")
    (out_dir / "requirements.md").write_text(requirements_md(req), encoding="utf-8")
