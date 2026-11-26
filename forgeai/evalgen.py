"""Requirement 4: eval generator - built FROM the documents, verified deterministically.

* answerable: LLM writes question + key facts from one chunk; every fact must literally appear in that chunk.
* CSV cases: question templates with expected answers computed in code (never by the LLM).
* edge: cross-document, ambiguous phrasing, false premise (+ CSV arithmetic).
* out_of_scope: must have low retrieval confidence OR match a must-refuse topic, else dropped.
Stratified: round-robin over documents so every document is covered. Seeded 70/30 dev/held-out split.
"""
from __future__ import annotations

import random
import re

from .ingest import Chunk, Document
from .llm import LLM
from .retrieval import Retriever
from .schemas import EvalCase, GenCross, GenFalsePremise, GenQA, GenQuestions, Requirements
from .textutil import content_tokens, humanize, norm, overlap

TARGET = {"answerable": 14, "out_of_scope": 8, "edge": 8}
MINIMUM = {"answerable": 12, "out_of_scope": 6, "edge": 6}

# Backup off-topic questions (distinct from the threshold-calibration probes in retrieval.py).
GENERIC_OOS = [
    "What is the best way to train for a marathon?",
    "Can you recommend a holiday destination in Southeast Asia?",
    "What is the population of Canada?",
    "How do I install Python on a Mac?",
    "Who wrote Pride and Prejudice?",
    "What's a good name for a pet goldfish?",
    "How many moons does Jupiter have?",
    "What is the difference between a virus and a bacterium?",
]


def fact_in_text(fact: str, text: str) -> bool:
    nf = norm(fact)
    return bool(nf) and nf in norm(text)


def matches_refuse_topic(q: str, topics: list[str]) -> str | None:
    qt = content_tokens(q)
    for t in topics:
        if overlap(content_tokens(t), qt) >= 0.5:
            return t
    return None


class EvalGenerator:
    def __init__(self, docs: list[Document], chunks: list[Chunk], retriever: Retriever, req: Requirements,
                 threshold: float, llm: LLM, seed: int = 0):
        self.docs, self.chunks, self.ret, self.req, self.thr, self.llm = docs, chunks, retriever, req, threshold, llm
        self.rng = random.Random(seed)
        self.seed = seed
        self.dropped: list[dict] = []
        self.by_doc: dict[str, list[Chunk]] = {}
        for c in chunks:
            if len(c.text) >= 80:
                self.by_doc.setdefault(c.doc, []).append(c)
        for v in self.by_doc.values():
            self.rng.shuffle(v)
        self.text_docs = [d.name for d in docs if not d.rows and d.name in self.by_doc]
        self.csv_docs = [d for d in docs if d.rows]

    def _drop(self, kind: str, q: str, reason: str) -> None:
        self.dropped.append({"type": kind, "question": q, "reason": reason})

    # ------------------------------------------------------------ answerable (text)
    def _answerable_from(self, chunk: Chunk, variant: int) -> EvalCase | None:
        try:
            g = self.llm.call("eval_answerable", "eval_answerable",
                              {"doc": chunk.doc, "passage": chunk.text, "variant": str(variant),
                               "audience": self.req.audience}, GenQA)
        except Exception as e:
            self._drop("answerable", "", f"generation failed: {e}")
            return None
        facts = [f for f in g.key_facts if fact_in_text(f, chunk.text)]
        bad = [f for f in g.key_facts if f not in facts]
        if bad:
            self._drop("answerable", g.question, f"facts not literally in source chunk: {bad}")
        if not facts or len(g.question) < 15:
            return None
        return EvalCase(type="answerable", subtype="single_doc", question=g.question.strip(),
                        expected_source_docs=[chunk.doc], expected_key_facts=facts[:3], evidence=facts[:3])

    # ------------------------------------------------------------ CSV (computed in code)
    def _csv_cases(self, doc: Document, n_lookup: int, n_calc: int) -> tuple[list[EvalCase], list[EvalCase]]:
        cols = doc.columns or []
        rows = doc.rows or []
        id_col = next((c for c in cols if re.search(r"(^|_)(id|code|sku)$", c, re.I)), None) or next(
            (c for c in cols if len({r.get(c) for r in rows}) == len(rows)), cols[0])
        name_col = next((c for c in cols if "name" in c.lower() or "description" in c.lower()), None)

        def num(v: str) -> float | None:
            try:
                return float(str(v).replace(",", "").replace("$", ""))
            except ValueError:
                return None

        numeric = [c for c in cols if c != id_col and all(num(r.get(c, "")) is not None for r in rows[:50])]
        textual = [c for c in cols if c not in numeric and c not in (id_col, name_col)]
        price_col = next((c for c in numeric if re.search(r"price|cost|fee|rate", c, re.I)), None)
        sample = self.rng.sample(rows, min(len(rows), n_lookup + n_calc))
        look, calc = [], []

        def label(r: dict) -> str:
            return f"{r[name_col]} ({r[id_col]})" if name_col else str(r[id_col])

        for i, r in enumerate(sample[:n_lookup]):
            col = (numeric + textual)[i % max(1, len(numeric + textual))] if (numeric or textual) else None
            if not col:
                break
            val = r[col]
            look.append(EvalCase(type="answerable", subtype="csv_lookup", origin="code",
                                 question=f"What is the {humanize(col)} of {label(r)}?",
                                 expected_source_docs=[doc.name], expected_key_facts=[val], evidence=[str(r[id_col])]))
        if price_col:
            for r in sample[n_lookup:]:
                qty = self.rng.randint(2, 12)
                total = qty * num(r[price_col])
                calc.append(EvalCase(type="edge", subtype="computation", origin="code",
                                     question=f"What would {qty} units of {label(r)} cost in total at the catalogue {humanize(price_col)}?",
                                     expected_source_docs=[doc.name], expected_key_facts=[f"{total:.2f}"],
                                     evidence=[str(r[id_col]), r[price_col]]))
        return look, calc

    # ------------------------------------------------------------ edge
    def _cross(self, a: Chunk, b: Chunk, variant: int) -> EvalCase | None:
        try:
            g = self.llm.call("eval_cross", "eval_cross", {"doc_a": a.doc, "passage_a": a.text, "doc_b": b.doc,
                                                           "passage_b": b.text, "variant": str(variant)}, GenCross)
        except Exception as e:
            self._drop("edge", "", f"generation failed: {e}")
            return None
        fa = [f for f in g.key_facts_a if fact_in_text(f, a.text)]
        fb = [f for f in g.key_facts_b if fact_in_text(f, b.text)]
        if not fa or not fb:
            self._drop("edge", g.question, "cross-document facts not verifiable in both source chunks")
            return None
        return EvalCase(type="edge", subtype="cross_document", question=g.question,
                        expected_source_docs=list(dict.fromkeys([a.doc, b.doc])),
                        expected_key_facts=fa[:2] + fb[:2], evidence=fa[:2] + fb[:2])

    def _ambiguous(self, base: EvalCase) -> EvalCase | None:
        try:
            g = self.llm.call("eval_ambiguous", "eval_ambiguous", {"question": base.question, "key_facts": base.expected_key_facts}, GenQA)
        except Exception as e:
            self._drop("edge", base.question, f"rephrase failed: {e}")
            return None
        if overlap(content_tokens(g.question), content_tokens(base.question)) > 0.95 and g.question.strip() == base.question.strip():
            return None
        return EvalCase(type="edge", subtype="ambiguous_phrasing", question=g.question,
                        expected_source_docs=base.expected_source_docs, expected_key_facts=base.expected_key_facts,
                        evidence=base.evidence)

    def _false_premise(self, chunk: Chunk, variant: int) -> EvalCase | None:
        try:
            g = self.llm.call("eval_false_premise", "eval_false_premise", {"doc": chunk.doc, "passage": chunk.text, "variant": str(variant)}, GenFalsePremise)
        except Exception as e:
            self._drop("edge", "", f"generation failed: {e}")
            return None
        if not g.question or not fact_in_text(g.correct_fact, chunk.text):
            self._drop("edge", g.question, "false-premise correct fact not in source chunk")
            return None
        if norm(g.correct_fact) in norm(g.question):
            self._drop("edge", g.question, "premise is not actually false (correct fact appears in question)")
            return None
        return EvalCase(type="edge", subtype="false_premise", question=g.question, expected_source_docs=[chunk.doc],
                        expected_key_facts=[g.correct_fact], evidence=[g.correct_fact])

    # ------------------------------------------------------------ out of scope
    def _oos(self, n: int) -> list[EvalCase]:
        cands: list[tuple[str, str]] = [(f"Can you tell me about {t}?", "must_refuse_template") for t in self.req.must_refuse]
        try:
            g = self.llm.call("eval_out_of_scope", "eval_out_of_scope",
                              {"domain": self.req.scope, "must_answer": self.req.must_answer,
                               "must_refuse": self.req.must_refuse, "n": str(n)}, GenQuestions)
            cands += [(q, "llm") for q in g.questions]
        except Exception as e:
            self._drop("out_of_scope", "", f"generation failed: {e}")
        cands += [(q, "generic_backup") for q in GENERIC_OOS]
        out = []
        for q, origin in cands:
            topic = matches_refuse_topic(q, self.req.must_refuse)
            conf = self.ret.confidence(q)
            if topic or conf < self.thr:
                out.append(EvalCase(type="out_of_scope", subtype="must_refuse_topic" if topic else "off_domain",
                                    question=q, should_refuse=True, origin=origin))
            else:
                self._drop("out_of_scope", q, f"retrieval confidence {conf:.2f} >= threshold {self.thr:.2f} and no must-refuse match (might be answerable)")
            if len(out) >= n:
                break
        return out

    # ------------------------------------------------------------ orchestration
    def generate(self) -> list[EvalCase]:
        cases: list[EvalCase] = []
        look, calc = [], []
        for d in self.csv_docs:
            l, c = self._csv_cases(d, 4, 2)
            look += l
            calc += c
        cases += look

        # answerable from text, round-robin over docs (stratified coverage)
        need = max(TARGET["answerable"] - len(look), 0) if self.text_docs else 0
        answerable: list[EvalCase] = []
        attempts, i = 0, 0
        pointers = {d: 0 for d in self.text_docs}
        seen_q: set[str] = set()
        while len(answerable) < need and attempts < need * 3 and self.text_docs:
            doc = self.text_docs[i % len(self.text_docs)]
            i += 1
            chunks = self.by_doc[doc]
            p = pointers[doc]
            pointers[doc] += 1
            attempts += 1
            c = self._answerable_from(chunks[p % len(chunks)], p // len(chunks))
            if c and c.question not in seen_q:
                seen_q.add(c.question)
                answerable.append(c)
        cases += answerable

        # edge cases
        edge: list[EvalCase] = list(calc)
        docs_with_chunks = self.text_docs or list(self.by_doc)
        for k in range(4):
            if len([e for e in edge if e.subtype == "cross_document"]) >= 3 or not docs_with_chunks:
                break
            if len(docs_with_chunks) >= 2:
                da, db = docs_with_chunks[k % len(docs_with_chunks)], docs_with_chunks[(k + 1) % len(docs_with_chunks)]
                a, b = self.by_doc[da][-1 - k % len(self.by_doc[da])], self.by_doc[db][-1 - (k + 1) % len(self.by_doc[db])]
            else:
                ch = self.by_doc[docs_with_chunks[0]]
                if len(ch) < 2:
                    break
                a, b = ch[k % len(ch)], ch[(k + 1) % len(ch)]
            e = self._cross(a, b, k)
            if e:
                edge.append(e)
        for base in answerable[:3]:
            e = self._ambiguous(base)
            if e:
                edge.append(e)
        fp = 0
        for k, doc in enumerate(docs_with_chunks * 3):
            if fp >= 2:
                break
            ch = self.by_doc[doc]
            e = self._false_premise(ch[(k + 1) % len(ch)], k)
            if e:
                edge.append(e)
                fp += 1
        cases += edge[: max(TARGET["edge"], MINIMUM["edge"])]
        cases += self._oos(TARGET["out_of_scope"])

        # coverage repair: every document must be the expected source of at least one case
        covered = {d for c in cases for d in c.expected_source_docs}
        for doc in self.by_doc:
            if doc not in covered:
                for p, ch in enumerate(self.by_doc[doc][:3]):
                    c = self._answerable_from(ch, p)
                    if c:
                        cases.append(c)
                        break
        return self._finalize(cases)

    def _finalize(self, cases: list[EvalCase]) -> list[EvalCase]:
        prefix = {"answerable": "A", "out_of_scope": "O", "edge": "E"}
        counters = {k: 0 for k in prefix}
        for c in cases:
            counters[c.type] += 1
            c.id = f"{prefix[c.type]}{counters[c.type]:02d}"
        rng = random.Random(self.seed + 1)
        for t in prefix:
            group = [c for c in cases if c.type == t]
            rng.shuffle(group)
            n_held = round(len(group) * 0.3)
            for j, c in enumerate(group):
                c.split = "heldout" if j < n_held else "dev"
        return cases


def evalset_stats(cases: list[EvalCase], docs: list[str]) -> dict:
    by_type = {t: sum(c.type == t for c in cases) for t in ("answerable", "out_of_scope", "edge")}
    covered = {d for c in cases for d in c.expected_source_docs}
    return {"total": len(cases), "by_type": by_type,
            "by_subtype": {s: sum(c.subtype == s for c in cases) for s in sorted({c.subtype for c in cases})},
            "dev": sum(c.split == "dev" for c in cases), "heldout": sum(c.split == "heldout" for c in cases),
            "docs_covered": sorted(covered & set(docs)), "docs_uncovered": sorted(set(docs) - covered),
            "meets_minimums": all(by_type[k] >= v for k, v in MINIMUM.items()) and len(cases) >= 24}


def generate_evalset(docs, chunks, retriever, req, threshold, llm, seed=0) -> tuple[list[EvalCase], dict]:
    g = EvalGenerator(docs, chunks, retriever, req, threshold, llm, seed)
    cases = g.generate()
    stats = evalset_stats(cases, [d.name for d in docs])
    return cases, {"stats": stats, "dropped": g.dropped}
