"""Requirement 3: agent generator -> declarative agent.yaml.

LLM proposes tools + writes the system prompt; deterministic code validates tools, sets retrieval
parameters from document statistics, calibrates the refusal threshold, and appends non-negotiable rules.
"""
from __future__ import annotations

import re
from pathlib import Path

import yaml

from .ingest import Document, chunk_all
from .llm import LLM
from .retrieval import Retriever, calibrate_threshold
from .schemas import AgentDef, Requirements, SystemPromptOut, ToolProposal
from .tools import REGISTRY, tool_specs

WEATHER_RE = (r"\b(weather|forecasts?|temperatures?|rain\w*|winds?|storms?|sea state|swell|travel conditions|climate"
              r"|conditions (?:at|in) (?:the )?(?:port|location|destination)|current location|at (?:a|their|the) location)\b")
CALC_RE = r"\b(calculat\w*|comput\w*|costs?|costing|prices?|pricing|totals?|sum|quantit\w*|budgets?|how much|discounts?|amounts?|estimat\w*|fees?|tuition|quotes?)\b"
DATE_RE = r"\b(dates?|today|deadlines?|days? (?:left|until|remaining)|expir\w*|due dates?|how long until|this week)\b"
NUMERIC_COL_RE = r"(price|cost|qty|quantity|stock|amount|fee|rate)"


def _requester_text(brief: str, req: Requirements) -> str:
    answers = " ".join(c.answer for c in req.clarifications if c.answered_by == "requester")
    return f"{brief} {answers}"


def validate_tools(proposed: list[dict], brief: str, req: Requirements, docs: list[Document]) -> tuple[list[dict], list[dict]]:
    """Deterministic gate. A tool is attached only if a rule says it is clearly needed."""
    text = _requester_text(brief, req)
    topics = " ".join(req.must_answer)
    csvs = [d for d in docs if d.rows]
    numeric_csv = any(re.search(NUMERIC_COL_RE, c or "", re.I) for d in csvs for c in (d.columns or []))
    need = {
        "weather": (bool(re.search(WEATHER_RE, text, re.I)), "brief mentions weather / sea or travel conditions",
                    "brief never mentions weather, sea state or travel conditions"),
        "csv_lookup": (bool(csvs), f"CSV present: {', '.join(d.name for d in csvs)}", "no CSV file in the document folder"),
        "calculator": (bool(re.search(CALC_RE, f'{text} {topics}', re.I)) or (numeric_csv and bool(re.search(r"\b(order|procure|purchas|buy)", text, re.I))),
                       "brief involves costs / quantities / totals", "brief involves no costs, quantities or arithmetic"),
        "current_date": (bool(re.search(DATE_RE, f'{text} {topics}', re.I)), "brief involves dates / deadlines",
                         "brief involves no dates or deadlines"),
    }
    attached, rejected = [], []
    names = {p["name"]: p for p in proposed}
    for name, p in names.items():
        if name not in REGISTRY:
            rejected.append({"name": name, "proposed_by": "llm", "reason": "not in the tool registry"})
        elif need[name][0]:
            attached.append({"name": name, "attached_by": "llm+validator", "justification": p.get("justification", ""), "rule": need[name][1]})
        else:
            rejected.append({"name": name, "proposed_by": "llm", "justification": p.get("justification", ""), "reason": need[name][2]})
    for name in ("csv_lookup",):  # a CSV without csv_lookup is a factory defect too
        if need[name][0] and name not in names:
            attached.append({"name": name, "attached_by": "validator", "justification": "", "rule": need[name][1] + " (LLM omitted it)"})
    return attached, rejected


def retrieval_params(docs: list[Document]) -> dict:
    text_docs = [d for d in docs if not d.rows]
    avg = sum(len(d.text) for d in text_docs) / max(1, len(text_docs))
    size = 600 if avg < 6000 else 900
    return {"chunk_size": size, "chunk_overlap": size // 6, "top_k": 5 if len(docs) > 3 else 4,
            "hybrid_weight": 0.35 if any(d.rows for d in docs) else 0.5}


NON_NEGOTIABLE = """Non-negotiable rules (added by ForgeAI; do not remove):
1. Answer ONLY from the context passages and tool results you are given. If they do not contain the answer, set "refused": true.
2. Never invent numbers, names, dates, prices or policies. Copy figures exactly as written.
3. Put the names of the documents you actually used in "sources".
4. Refuse these topics even if asked politely: {refuse}."""


def enforce_guards(prompt: str, req: Requirements) -> str:
    prompt = prompt.split("Non-negotiable rules (added by ForgeAI")[0].rstrip()
    return prompt + "\n\n" + NON_NEGOTIABLE.format(refuse="; ".join(req.must_refuse) or "none listed")


def write_system_prompt(req: Requirements, infos: list[dict], tools: list[str], llm: LLM, template: str = "system_prompt") -> str:
    out = llm.call(template, template, {"requirements": req.model_dump(exclude={"clarifications", "flags"}),
                                        "docs": [{"name": i["name"], "summary": i["summary"][:200]} for i in infos],
                                        "tools": tool_specs(tools)}, SystemPromptOut, fallback="mock")
    return enforce_guards(out.system_prompt, req)


def build_agent(brief: str, req: Requirements, docs: list[Document], infos: list[dict], llm: LLM, seed: int = 0) -> tuple[AgentDef, dict]:
    prop = llm.call("tool_proposal", "tool_proposal", {"brief": brief, "requirements": req.model_dump(exclude={"clarifications", "flags"}),
                                                       "registry": tool_specs(), "has_csv": any(d.rows for d in docs)},
                    ToolProposal, fallback={"tools": []})
    attached, rejected = validate_tools([t.model_dump() for t in prop.tools], brief, req, docs)
    tools = [a["name"] for a in attached]
    params = retrieval_params(docs)
    ret = Retriever(chunk_all(docs, params["chunk_size"], params["chunk_overlap"]), params["hybrid_weight"])
    thr, calib = calibrate_threshold(ret, params["top_k"], seed)
    agent = AgentDef(
        name=re.sub(r"[^a-z0-9]+", "_", req.title.lower()).strip("_")[:40] or "agent",
        description=req.scope[:300],
        system_prompt=write_system_prompt(req, infos, tools, llm),
        must_refuse=list(req.must_refuse),
        tools=tools,
        refusal_threshold=thr,
        embedding=calib["embedder"],
        refusal_message="I'm sorry, I can't answer that from the documents I have access to.",
        **params,
    )
    return agent, {"proposed": [t.model_dump() for t in prop.tools], "attached": attached, "rejected": rejected, "calibration": calib}


def save_agent(agent: AgentDef, path: Path) -> None:
    path.write_text(yaml.safe_dump(agent.model_dump(), sort_keys=False, allow_unicode=True, width=120), encoding="utf-8")


def load_agent(path: Path) -> AgentDef:
    return AgentDef.model_validate(yaml.safe_load(Path(path).read_text(encoding="utf-8")))
