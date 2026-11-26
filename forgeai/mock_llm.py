"""Deterministic MockLLM (LLM_PROVIDER=mock).

It does NOT read the rendered prompt; it gets the structured template variables and applies simple,
inspectable heuristics so the whole factory (and its tests) runs offline. It is deliberately imperfect
in the same ways a small model is: it is over-eager with tools, and until a prompt rule tells it to
"combine" passages it answers multi-part questions from a single passage only (a prompt defect the
optimizer has to find and patch).

The same heuristics double as graceful-degradation fallbacks when a real model keeps returning junk.
"""
from __future__ import annotations

import re

from .textutil import content_tokens, humanize, norm, numbers, overlap, sentences, topic_tokens

_UNITS = r"(?:working days|calendar days|days?|weeks?|months?|years?|hours?|points|instalments|metres?|kilometres?|per cent|units?)"
_FACT = re.compile(r"(?:(?:USD|GBP|EUR)\s|[$£€])?\d[\d,]*(?:\.\d+)?(?:\s?%|\s+" + _UNITS + r"\b)?")
_ID = re.compile(r"\b[A-Z]{2,}-\d{2,}\b")


def _row_text(row: dict) -> str:
    return " | ".join(f"{k}: {v}" for k, v in row.items() if k != "file")


def _fact_sentence(passage: str, index: int = 0) -> tuple[str, str] | None:
    cands = [s for s in sentences(passage) if 5 <= len(s.split()) <= 70]
    with_num = [s for s in cands if _FACT.search(s)]
    pool = with_num or cands
    if not pool:
        return None
    s = pool[index % len(pool)]
    m = _FACT.search(s)
    if m:
        fact = m.group().strip()
    else:
        fact = " ".join(s.split()[-4:]).strip(".,;:")
    return s, fact


def _mask(s: str, fact: str) -> str:
    return s.replace(fact, "___", 1).strip()


class MockLLM:
    def respond(self, task: str, v: dict) -> dict:
        fn = getattr(self, "t_" + task.split(":")[0], None)
        if fn is None:
            raise ValueError(f"MockLLM has no handler for task {task}")
        return fn(v)

    # ------------------------------------------------------------ intake
    def t_intake_questions(self, v: dict) -> dict:
        brief = v.get("brief", "")
        return {"questions": [
            "Who exactly is the primary audience for this assistant?",
            "What tone should the assistant use with users?",
            "Are there topics the assistant must never discuss?",
            "Should every answer cite the source document?",
            "How should the assistant respond to questions the documents do not cover?",
            "Which languages must the assistant support?",
            f"Do you want {' '.join(brief.split()[2:14])}?",  # answerable from the brief -> filtered
        ]}

    def t_intake_self_answer(self, v: dict) -> dict:
        brief = v.get("brief", "")
        aud = _audience(brief)
        out = []
        for q in v.get("questions", []):
            ql = q.lower()
            if "audience" in ql:
                out.append(f"{aud}, as stated in the brief.")
            elif "tone" in ql:
                out.append("Professional, friendly and concise.")
            elif "never" in ql or "refuse" in ql:
                out.append("Anything not covered by the documents, and personal data about individuals.")
            elif "cite" in ql or "source" in ql:
                out.append("Yes, always cite the source document.")
            elif "not cover" in ql or "outside" in ql:
                out.append("Politely decline and suggest contacting the responsible team.")
            elif "language" in ql:
                out.append("English only.")
            else:
                out.append("Use your best judgement based on the documents.")
        return {"answers": out}

    def t_requirements(self, v: dict) -> dict:
        brief = v.get("brief", "")
        topics = _topics(brief)
        if len(topics) < 3:
            topics += [humanize(d["name"]) for d in v.get("docs", [])]
        return {
            "title": "Assistant for " + _audience(brief),
            "scope": " ".join(brief.split())[:300],
            "audience": _audience(brief),
            "tone": "professional, friendly and concise",
            "must_answer": topics[:8],
            "must_refuse": ["personal or confidential data about individual people",
                            "legal or medical advice"],
            "out_of_scope_behavior": "Politely decline and say the documents do not cover it.",
        }

    def t_groundability(self, v: dict) -> dict:
        cov = overlap(topic_tokens(v.get("topic", "")), content_tokens(" ".join(v.get("passages", []))))
        verdict = "supported" if cov >= 0.6 else "partial" if cov >= 0.34 else "unsupported"
        return {"verdict": verdict, "reason": f"{cov:.0%} of topic terms appear in the retrieved passages"}

    # ------------------------------------------------------------ generator
    def t_tool_proposal(self, v: dict) -> dict:
        # Over-eager on purpose: small models attach everything. The deterministic validator must prune.
        return {"tools": [{"name": t["name"], "justification": "Could be useful for some user questions."}
                          for t in v.get("registry", [])]}

    def t_system_prompt(self, v: dict, style: str = "standard") -> dict:
        r = v.get("requirements", {})
        lines = [
            f"You are {r.get('title', 'an assistant')}, helping {r.get('audience', 'users')}.",
            f"Scope: {r.get('scope', '')}",
            f"Tone: {r.get('tone', 'professional')}.",
            "Topics you answer: " + "; ".join(r.get("must_answer", [])) + ".",
            "Answer only from the context passages and tool results. Cite the documents you used.",
        ]
        if style == "strict":
            lines.append("If any part of the answer is not explicitly stated in the context, refuse.")
        elif style == "concise":
            lines.append("Answer in one or two sentences, quoting the exact figure from the context.")
        elif style == "stepwise":
            lines.append("First find every relevant passage, then combine the facts from all of them into one answer.")
        return {"system_prompt": "\n".join(lines)}

    def t_tournament_strict(self, v: dict) -> dict:
        return self.t_system_prompt(v, "strict")

    def t_tournament_concise(self, v: dict) -> dict:
        return self.t_system_prompt(v, "concise")

    def t_tournament_stepwise(self, v: dict) -> dict:
        return self.t_system_prompt(v, "stepwise")

    # ------------------------------------------------------------ runtime agent
    def t_agent_answer(self, v: dict) -> dict:
        q = v.get("question", "")
        ql = q.lower()
        prompt = v.get("system_prompt", "").lower()
        refusal = {"action": "answer", "answer": v.get("refusal_message", "I can't answer that."),
                   "sources": [], "confidence": 0.1, "refused": True}
        qt = content_tokens(q)
        for topic in v.get("must_refuse", []):
            if overlap(content_tokens(topic), qt) >= 0.5:
                return refusal
        tools = {t["name"] for t in v.get("tools", [])}
        results = v.get("tool_results", [])
        used = {r.get("tool") for r in results}
        left = int(v.get("tool_calls_left", 0))
        chunks = v.get("chunks", [])
        ids = _ID.findall(q)
        if left > 0 and "csv_lookup" in tools and ids and "csv_lookup" not in used:
            return {"action": "tool", "tool": {"name": "csv_lookup", "args": {"query": ids[0]}}}
        qty = re.search(r"\b(\d+)\s+(?:units?|pieces?|pcs|items?)\b", ql)
        if left > 0 and "calculator" in tools and qty and "calculator" not in used:
            price = _find_price(results, chunks, ids)
            if price:
                return {"action": "tool", "tool": {"name": "calculator", "args": {"expression": f"{qty.group(1)} * {price}"}}}
        if left > 0 and "current_date" in tools and re.search(r"\btoday\b|days (?:left|until|remaining)", ql) and "current_date" not in used:
            return {"action": "tool", "tool": {"name": "current_date", "args": {}}}

        # Small-model failure mode: without an explicit instruction it only reads the FIRST passage.
        reads_all = any(w in prompt for w in ("combine", "every passage", "all passages", "every context passage"))
        units: list[tuple[str, str]] = []
        for r in results:  # exact tool rows first: they win ties against loosely retrieved passages
            res = r.get("result") or {}
            for row in res.get("matches", []) if isinstance(res, dict) else []:
                units.append((row.get("file", "tool"), _row_text(row)))
        for c in chunks if reads_all else chunks[:1]:
            units += [(c["doc"], s) for s in sentences(c["text"])]
        qs = set(qt)
        scored = sorted(((len(qs & set(content_tokens(s))), i, d, s) for i, (d, s) in enumerate(units)),
                        key=lambda x: (-x[0], x[1]))
        lenient = "answer if the context contains" in prompt
        min_score = 1 if lenient else 2
        if not scored or scored[0][0] < min_score:
            return refusal
        picked = [scored[0]]
        if "combine" in prompt:
            for cand in scored[1:]:
                if cand[0] >= min_score and cand[3] != picked[0][3] and (cand[2] != picked[0][2] or cand[0] >= picked[0][0] * 0.6):
                    picked.append(cand)
                    break
        answer = " ".join(p[3] for p in picked)
        calc = next((r for r in results if r.get("tool") == "calculator" and r.get("ok")), None)
        if calc:
            res = calc["result"]
            answer = f"Total: {res['expression']} = {res['result']:.2f}. " + answer
        sources = list(dict.fromkeys(p[2] for p in picked if p[2] != "tool"))
        conf = min(1.0, scored[0][0] / max(1, len(qs)))
        return {"action": "answer", "answer": answer, "sources": sources, "confidence": round(conf, 2), "refused": False}

    # ------------------------------------------------------------ eval generation
    def t_eval_answerable(self, v: dict) -> dict:
        fs = _fact_sentence(v.get("passage", ""), int(v.get("variant", 0)))
        if not fs:
            return {"question": "", "key_facts": []}
        s, fact = fs
        return {"question": f"According to the {humanize(v.get('doc', 'documents'))}, what completes this statement: \"{_mask(s, fact)}\"?",
                "key_facts": [fact]}

    def t_eval_cross(self, v: dict) -> dict:
        a = _fact_sentence(v.get("passage_a", ""), int(v.get("variant", 0)))
        b = _fact_sentence(v.get("passage_b", ""), int(v.get("variant", 0)))
        if not a or not b:
            return {"question": "", "key_facts_a": [], "key_facts_b": []}
        q = (f"Two-part question: (a) according to the {humanize(v.get('doc_a', ''))}, what completes \"{_mask(*a)}\"; "
             f"and (b) according to the {humanize(v.get('doc_b', ''))}, what completes \"{_mask(*b)}\"?")
        return {"question": q, "key_facts_a": [a[1]], "key_facts_b": [b[1]]}

    def t_eval_ambiguous(self, v: dict) -> dict:
        q = re.sub(r"^According to the [^,]+, ", "", v.get("question", ""))
        q = q.replace("what completes this statement:", "so basically").rstrip("?")
        words = q.split()
        longest = max(range(len(words)), key=lambda i: (len(words[i].strip('".,')), -i), default=None)
        if longest is not None and "___" not in words[longest]:  # informal typo: drop the vowels of the longest word
            w = words[longest]
            words[longest] = w[0] + re.sub(r"[aeiou]", "", w[1:])
        q = " ".join(words)
        return {"question": f"quick one - {q[:1].lower() + q[1:]}??", "key_facts": v.get("key_facts", [])}

    def t_eval_false_premise(self, v: dict) -> dict:
        fs = _fact_sentence(v.get("passage", ""), int(v.get("variant", 0)))
        if not fs or not numbers(fs[1]):
            return {"question": "", "correct_fact": ""}
        s, fact = fs
        n = numbers(fact)[0]
        wrong = fact.replace(re.search(r"\d[\d,]*(?:\.\d+)?", fact).group(), f"{n * 2 + 3:g}", 1)
        return {"question": f"I was told that \"{s.replace(fact, wrong, 1)}\" - is that right?", "correct_fact": fact}

    def t_eval_out_of_scope(self, v: dict) -> dict:
        return {"questions": [
            "What will the weather be like in Paris tomorrow?",
            "Can you write me a poem about the ocean?",
            "Who won the 2018 FIFA World Cup?",
            "Which cryptocurrency should I invest in this month?",
            "How do I bake sourdough bread at home?",
            "Explain quantum entanglement in simple terms.",
            "What is the plot of the novel Moby Dick?",
            "How do I reset my home Wi-Fi router?",
        ]}

    # ------------------------------------------------------------ judge / optimizer
    def t_judge(self, v: dict) -> dict:
        ans, ctx = v.get("answer", ""), v.get("context", "")
        facts = v.get("expected_facts", [])
        na = norm(ans)
        hit = [f for f in facts if norm(f) in na or (numbers(f) and set(numbers(f)) <= set(numbers(ans)))]
        correct = bool(facts) and len(hit) / len(facts) >= 0.75
        cn = set(numbers(ctx)) | set(numbers(v.get("question", "")))
        extra = [str(n) for n in numbers(ans) if n not in cn]
        return {"correct": correct, "grounded": not extra, "unsupported_claims": extra,
                "reason": f"{len(hit)}/{len(facts)} expected facts present"}

    def t_prompt_patch(self, v: dict) -> dict:
        return {"add_rules": [
            "When a question has several parts or needs more than one passage, combine the relevant facts from every context passage and answer each part.",
            "Quote figures (numbers, limits, durations, prices) exactly as written in the context.",
        ], "rationale": "Failures show facts present in retrieved context but missing from answers."}


def _audience(brief: str) -> str:
    m = re.search(r"\bfor ([^.,:;()]+)", brief)
    return " ".join(m.group(1).split()[:6]) if m else "end users"


def _topics(brief: str) -> list[str]:
    m = re.search(r":", brief) or re.search(r"\babout\b|\bcovering\b|\bincluding\b|\bon\b", brief)
    tail = brief[m.end():] if m else brief
    out = []
    for p in re.split(r"[,;]|\band also\b|\.\s", tail):
        p = re.sub(r"^\s*(and|also|plus|the)\s+", "", p.strip().rstrip("."), flags=re.I).strip()
        if 1 <= len(p.split()) <= 10:
            out.append(p)
    return list(dict.fromkeys(out))


def _find_price(results: list[dict], chunks: list[dict], ids: list[str]) -> str | None:
    lines: list[str] = []
    for r in results:
        res = r.get("result") or {}
        for row in res.get("matches", []) if isinstance(res, dict) else []:
            lines.append(_row_text(row))
    for c in chunks:
        lines += c["text"].split("\n")
    if ids:
        lines = [l for l in lines if ids[0] in l] or lines
    for l in lines:
        m = re.search(r"\b\w*(?:price|cost)\w*:\s*\$?([\d,]+(?:\.\d+)?)", l, re.I)
        if m:
            return m.group(1).replace(",", "")
    return None

