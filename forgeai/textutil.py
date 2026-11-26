"""Tiny text helpers shared by retrieval, eval generation and the judge."""
from __future__ import annotations

import re
import unicodedata

STOP = set(
    """a an the of to in on for and or is are was were be been being by with at from as that this these those it its
    what which who whom how when where why do does did can could should would will may might must i you we they he she
    my our your their me us them about into than then there here if not no yes any all some per so such also just
    please tell know according documents document policy say says said get got have has had""".split()
)

_WORD = re.compile(r"[a-z0-9]+")
_NUM = re.compile(r"(?<![\w.])-?\d[\d,]*(?:\.\d+)?")


def stem(t: str) -> str:
    if len(t) > 4 and t.endswith("ies"):
        return t[:-3] + "y"
    if len(t) > 3 and t.endswith("s") and not t.endswith("ss"):
        return t[:-1]
    return t


def content_tokens(text: str) -> list[str]:
    return [stem(t) for t in _WORD.findall((text or "").lower()) if t not in STOP]


def norm(text: str) -> str:
    """Lowercase, strip accents/punctuation (keep digits, '.', '-'), collapse whitespace."""
    t = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode().lower()
    t = re.sub(r"(?<=\d),(?=\d{3}\b)", "", t)  # 1,200 -> 1200
    t = re.sub(r"[^a-z0-9.\-%\s]", " ", t)
    t = re.sub(r"(?<!\d)\.|\.(?!\d)", " ", t)  # keep decimal points only
    return re.sub(r"\s+", " ", t).strip()


def numbers(text: str) -> list[float]:
    out = []
    for m in _NUM.findall(text or ""):
        try:
            out.append(float(m.replace(",", "")))
        except ValueError:
            pass
    return out


def sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9\"'(])|\n+", text or "")
    return [p.strip() for p in parts if p and p.strip()]


def overlap(a: list[str] | set[str], b: list[str] | set[str]) -> float:
    a, b = set(a), set(b)
    return len(a & b) / len(a) if a else 0.0


def humanize(name: str) -> str:
    stem_ = re.sub(r"\.[A-Za-z0-9]+$", "", name)
    return re.sub(r"[_\-]+", " ", stem_).strip()


# Generic task verbs/fillers that say what the user wants to DO, not what the documents must CONTAIN.
TOPIC_STOP = set("""look up check compare work out find answer answers question questions how many much left including
include etc give provide explain help understand handle our their its any related level levels""".split())


def topic_tokens(topic: str) -> list[str]:
    toks = [t for t in content_tokens(topic) if t not in TOPIC_STOP]
    return toks or content_tokens(topic)
