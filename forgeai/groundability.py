"""Requirement 2: groundability guard.

Per must-answer topic: retrieval confidence (deterministic) AND an LLM verdict. Unsupported topics are
moved to must_refuse so the generated agent cannot hallucinate the gap away. Also flags capabilities the
brief implies that no registered tool provides.
"""
from __future__ import annotations

import re

from .llm import LLM
from .retrieval import Retriever
from .schemas import GroundVerdict, Requirements
from .textutil import topic_tokens

# capability -> regex over the brief. None of these exist in the 4-tool registry.
MISSING_CAPABILITIES = {
    "sending emails or messages": r"\b(e-?mail|send (?:a |an )?(?:message|notification)|notify)\b",
    "making bookings or reservations": r"\b(book(?:ing)?s?|reserv(?:e|ation)s?)\b(?! (?:value|keeping))",
    "placing orders or payments": r"\b(place (?:an |the )?orders?|raise (?:a |the )?purchase orders?|make payments?|pay (?:the )?invoices?)\b",
    "creating tickets or updating records": r"\b(create (?:a )?tickets?|update (?:the )?records?|log (?:a )?requests?)\b",
    "live web search": r"\b(search the (?:web|internet)|browse the web|google)\b",
    "translation": r"\btranslat\w*\b",
    "image or document scanning": r"\b(photo|image|scan(?:ned)? (?:receipts?|images?))\b",
}


def check_groundability(req: Requirements, retriever: Retriever, llm: LLM, threshold: float,
                        brief: str = "") -> tuple[Requirements, list[dict]]:
    flags: list[dict] = []
    keep: list[str] = []
    for topic in req.must_answer:
        hits = retriever.search(" ".join(topic_tokens(topic)), k=4)
        conf = max((h.confidence for h in hits), default=0.0)
        v = llm.call("groundability", "groundability", {"topic": topic, "passages": [f"[{h.chunk.doc}] {h.chunk.text[:900]}" for h in hits]},
                     GroundVerdict, role="judge", fallback="mock")
        if conf < threshold * 0.6 or v.verdict == "unsupported":
            verdict = "unsupported"
        elif v.verdict == "partial" or conf < threshold:
            verdict = "partial"
        else:
            verdict = "supported"
        flag = {"type": "groundability", "topic": topic, "verdict": verdict, "retrieval_confidence": round(conf, 3),
                "threshold": threshold, "llm_verdict": v.verdict, "reason": v.reason,
                "evidence": [h.chunk.id for h in hits[:2]]}
        if verdict == "unsupported":
            flag["message"] = "documents do not support this topic - moved to must-refuse"
            if topic not in req.must_refuse:
                req.must_refuse.append(topic)
        else:
            keep.append(topic)
            if verdict == "partial":
                flag["message"] = "only partially supported - agent must answer only what the documents state"
        flags.append(flag)
    if not keep:
        flags.append({"type": "groundability", "verdict": "unsupported", "topic": "ALL",
                      "message": "no must-answer topic is supported by the documents; the agent will refuse almost everything"})
        keep = req.must_answer[:1]  # schema needs one; it is still listed as unsupported above
    req.must_answer = keep

    text = brief or req.scope
    for cap, pat in MISSING_CAPABILITIES.items():
        m = re.search(pat, text, re.I)
        if m:
            flags.append({"type": "tool_gap", "capability": cap, "matched": m.group(0), "verdict": "tool_gap",
                          "message": f"brief implies '{cap}' but no registered tool provides it; requests for it will be refused"})
            topic = f"requests to perform {cap}"
            if topic not in req.must_refuse:
                req.must_refuse.append(topic)
    req.flags = flags
    return req, flags
