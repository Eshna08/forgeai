"""Hybrid retrieval: dense embeddings (fastembed bge-small, or a hashed fallback) + BM25.

`score` ranks chunks (relative); `confidence` is an absolute 0..1 signal used by the refusal gate:
w * cosine + (1-w) * fraction-of-query-terms-present.
"""
from __future__ import annotations

import logging
import random
import zlib
from dataclasses import dataclass

import numpy as np
from rank_bm25 import BM25Okapi

from .config import get_settings
from .ingest import Chunk
from .textutil import content_tokens, humanize, sentences

log = logging.getLogger("forgeai.retrieval")


class Embedder:
    def __init__(self, backend: str = "auto"):
        self.kind = "hash"
        self.model = None
        self.cache: dict[str, np.ndarray] = {}
        if backend in ("auto", "fastembed"):
            try:
                from fastembed import TextEmbedding

                self.model = TextEmbedding("BAAI/bge-small-en-v1.5")
                self.kind = "fastembed"
            except Exception as e:  # offline / not installed
                if backend == "fastembed":
                    raise
                log.warning("fastembed unavailable (%s); using hashed embeddings", e)

    def _hash(self, text: str, dims: int = 1024) -> np.ndarray:
        v = np.zeros(dims, dtype=np.float32)
        toks = content_tokens(text)
        for t in toks + [f"{a}_{b}" for a, b in zip(toks, toks[1:])]:
            h = zlib.crc32(t.encode())
            v[h % dims] += 1.0 if (h >> 16) & 1 else -1.0
        return v

    def embed(self, texts: list[str]) -> np.ndarray:
        missing = [t for t in dict.fromkeys(texts) if t not in self.cache]
        if missing:
            if self.model is not None:
                vecs = list(self.model.embed(missing))
            else:
                vecs = [self._hash(t) for t in missing]
            for t, v in zip(missing, vecs):
                v = np.asarray(v, dtype=np.float32)
                n = np.linalg.norm(v)
                self.cache[t] = v / n if n else v
        if not texts:
            return np.zeros((0, 1), dtype=np.float32)
        return np.vstack([self.cache[t] for t in texts])


_EMBEDDERS: dict[str, Embedder] = {}


def get_embedder(backend: str | None = None) -> Embedder:
    backend = backend or get_settings().embedding_backend
    if backend not in _EMBEDDERS:
        try:
            _EMBEDDERS[backend] = Embedder(backend)
        except Exception as e:  # e.g. agent calibrated with fastembed, model unavailable here
            log.warning("embedder %s unavailable (%s); falling back - refusal threshold may be miscalibrated", backend, e)
            _EMBEDDERS[backend] = Embedder("auto")
    return _EMBEDDERS[backend]


@dataclass
class Hit:
    chunk: Chunk
    score: float
    confidence: float
    dense: float
    lexical: float


class Retriever:
    def __init__(self, chunks: list[Chunk], hybrid_weight: float = 0.5, embedder: Embedder | None = None):
        self.chunks = chunks
        self.w = hybrid_weight
        self.texts = [f"{humanize(c.doc)}\n{c.text}" for c in chunks]
        self.toks = [content_tokens(t) for t in self.texts]
        self.tok_sets = [set(t) for t in self.toks]
        self.bm25 = BM25Okapi(self.toks) if chunks and any(self.toks) else None
        self.emb = embedder or get_embedder()
        self.vecs = self.emb.embed(self.texts) if chunks else None

    def search(self, query: str, k: int = 4) -> list[Hit]:
        if not self.chunks:
            return []
        q = content_tokens(query)
        qs = set(q)
        bm = np.clip(np.asarray(self.bm25.get_scores(q)) if (self.bm25 and q) else np.zeros(len(self.chunks)), 0, None)
        bm_norm = bm / bm.max() if bm.max() > 0 else bm
        dense = np.clip(self.vecs @ self.emb.embed([query])[0], 0, 1)
        cov = np.array([len(qs & s) / len(qs) if qs else 0.0 for s in self.tok_sets])
        rank = self.w * dense + (1 - self.w) * bm_norm
        conf = self.w * dense + (1 - self.w) * cov
        order = np.argsort(-rank, kind="stable")[:k]
        return [Hit(self.chunks[i], float(rank[i]), float(conf[i]), float(dense[i]), float(cov[i])) for i in order]

    def confidence(self, query: str, k: int = 4) -> float:
        hits = self.search(query, k)
        return max((h.confidence for h in hits), default=0.0)


# Calibration probes. Deliberately different from the off-topic questions used in eval generation.
OFF_TOPIC_PROBES = [
    "What is the capital city of Australia?",
    "Write a short poem about autumn leaves.",
    "Who painted the Mona Lisa?",
    "How do I change a flat bicycle tyre?",
    "What is the boiling point of water at sea level?",
    "Recommend a good science fiction movie.",
    "How many players are on a basketball team?",
    "Translate good morning into Japanese.",
    "What is the square root of 144?",
    "Give me a recipe for banana bread.",
    "Who was the first person to walk on the moon?",
    "Explain how photosynthesis works.",
]


def _pct(xs: list[float], p: float) -> float:
    if not xs:
        return 0.0
    xs = sorted(xs)
    return xs[min(len(xs) - 1, max(0, int(round(p / 100 * (len(xs) - 1)))))]


def calibrate_threshold(ret: Retriever, k: int = 4, seed: int = 0) -> tuple[float, dict]:
    """Place the refusal threshold between off-topic and in-domain probe confidences (not a guessed constant)."""
    rng = random.Random(seed)
    probes = []
    for c in rng.sample(ret.chunks, min(30, len(ret.chunks))):
        sents = [s for s in sentences(c.text) if len(s.split()) >= 6]
        if sents:
            probes.append(" ".join(rng.choice(sents).split()[:12]))
    ins = [ret.confidence(q, k) for q in probes]
    offs = [ret.confidence(q, k) for q in OFF_TOPIC_PROBES]
    p10_in, p90_off = _pct(ins, 10), _pct(offs, 90)
    if p10_in > p90_off:
        thr, note = p90_off + 0.35 * (p10_in - p90_off), "separated"
    else:
        thr, note = (_pct(ins, 50) + _pct(offs, 50)) / 2, "overlapping distributions - refusal gate is less reliable"
    thr = round(min(0.9, max(0.05, thr)), 3)
    return thr, {"threshold": thr, "in_domain_p10": round(p10_in, 3), "off_topic_p90": round(p90_off, 3),
                 "n_in": len(ins), "n_off": len(offs), "note": note, "embedder": ret.emb.kind}
