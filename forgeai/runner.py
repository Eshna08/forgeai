"""Requirement 8: generic chat runner for ANY agent.yaml + docs folder.

retrieve (hybrid) -> deterministic refusal gate -> JSON tool protocol (<= max_tool_calls) -> validated contract.
"""
from __future__ import annotations

import json
from pathlib import Path

from .generator import load_agent
from .ingest import Document, chunk_all, load_folder
from .llm import LLM, Budget
from .retrieval import Retriever, get_embedder
from .schemas import AgentDef, AgentReply, AgentTurn
from .textutil import content_tokens, humanize, numbers
from .tools import run_tool, tool_specs


class AgentRuntime:
    def __init__(self, agent: AgentDef, docs: list[Document], llm: LLM | None = None, today: str | None = None):
        self.agent, self.docs = agent, docs
        self.llm = llm or LLM(budget=Budget(0, 0))  # chat sessions are not run-budgeted
        self.chunks = chunk_all(docs, agent.chunk_size, agent.chunk_overlap)
        # use the embedder the refusal threshold was calibrated with; a different one shifts every confidence score
        self.retriever = Retriever(self.chunks, agent.hybrid_weight, get_embedder(agent.embedding) if agent.embedding else None)
        self.ctx = {"csv": {d.name: d.rows for d in docs if d.rows}, "today": today}
        self.doc_names = [d.name for d in docs]

    @classmethod
    def load(cls, agent_path: str | Path, docs_dir: str | Path, llm: LLM | None = None) -> "AgentRuntime":
        docs, _ = load_folder(docs_dir)
        return cls(load_agent(Path(agent_path)), docs, llm)

    def _match_source(self, s: str) -> str | None:
        s_l = s.lower().strip()
        for n in self.doc_names:
            if s_l in (n.lower(), humanize(n).lower()) or s_l.rsplit(".", 1)[0] == n.lower().rsplit(".", 1)[0]:
                return n
        return None

    def ask(self, question: str) -> AgentReply:
        a = self.agent
        hits = self.retriever.search(question, a.top_k)
        rconf = max((h.confidence for h in hits), default=0.0)
        retrieved = [{"chunk_id": h.chunk.id, "doc": h.chunk.doc, "score": round(h.score, 3),
                      "confidence": round(h.confidence, 3), "text": h.chunk.text} for h in hits]
        base = {"retrieval_confidence": round(rconf, 3), "retrieved": retrieved}
        if rconf < a.refusal_threshold:
            return AgentReply(answer=a.refusal_message, sources=[], confidence=round(1 - rconf, 3), refused=True, gate="retrieval", **base)

        context = "\n\n".join(f"[{i + 1}] (source: {h.chunk.doc})\n{h.chunk.text}" for i, h in enumerate(hits))
        chunks = [{"doc": h.chunk.doc, "text": h.chunk.text} for h in hits]
        results: list[dict] = []
        turn = None
        for step in range(a.max_tool_calls + 1):
            left = a.max_tool_calls - step
            v = {"system_prompt": a.full_prompt(), "tools": tool_specs(a.tools) if left > 0 else [],
                 "tool_calls_left": str(left), "context": context, "chunks": chunks,
                 "tool_results": results, "question": question, "refusal_message": a.refusal_message,
                 "must_refuse": a.must_refuse}
            turn = self.llm.call("agent_answer", "agent_answer", v, AgentTurn,
                                 fallback={"action": "answer", "answer": a.refusal_message, "refused": True, "confidence": 0})
            if turn.action == "tool" and turn.tool and left > 0:
                name = turn.tool.name
                res = run_tool(name, turn.tool.args, self.ctx) if name in a.tools else {"ok": False, "error": f"tool '{name}' is not attached to this agent"}
                results.append({"tool": name, "args": turn.tool.args, **res})
                continue
            break

        refused = turn.refused or turn.action == "tool" or not turn.answer.strip()
        if refused:
            return AgentReply(answer=a.refusal_message, sources=[], confidence=round(min(turn.confidence, 0.5), 3),
                              refused=True, tools_used=results, **base)
        sources = list(dict.fromkeys(s for s in (self._match_source(x) for x in turn.sources) if s))
        if not sources:  # contract requires sources; attribute to the passage that best supports the answer
            at = set(content_tokens(turn.answer)) | {str(n) for n in numbers(turn.answer)}
            best = max(hits, key=lambda h: len(at & (set(content_tokens(h.chunk.text)) | {str(n) for n in numbers(h.chunk.text)})))
            sources = [best.chunk.doc]
        conf = round((turn.confidence + min(1.0, rconf)) / 2, 3)
        return AgentReply(answer=turn.answer.strip(), sources=sources, confidence=conf, refused=False, tools_used=results, **base)


def reply_json(r: AgentReply, verbose: bool = False) -> str:
    d = r.model_dump()
    if not verbose:
        d["retrieved"] = [{k: x[k] for k in ("chunk_id", "confidence")} for x in d["retrieved"]]
    return json.dumps(d, indent=2, ensure_ascii=False)
