"""Load a document folder (txt/md/pdf/docx/csv) with clear warnings, and chunk it."""
from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field
from pathlib import Path

from .textutil import humanize, sentences

SUPPORTED = {".txt", ".md", ".pdf", ".docx", ".csv"}
MAX_CSV_TEXT_ROWS = 5000  # ponytail: rows beyond this are reachable via csv_lookup only, not retrieval


@dataclass
class Document:
    name: str
    type: str
    text: str
    rows: list[dict] | None = None
    columns: list[str] | None = None
    warnings: list[str] = field(default_factory=list)

    @property
    def title(self) -> str:
        return humanize(self.name)


@dataclass
class Chunk:
    id: str
    doc: str
    text: str
    index: int


def decode_bytes(raw: bytes, name: str) -> tuple[str, list[str]]:
    for enc in ("utf-8-sig", "utf-8"):
        try:
            return raw.decode(enc), []
        except UnicodeDecodeError:
            pass
    for enc in ("cp1252", "latin-1"):
        try:
            return raw.decode(enc), [f"{name}: not valid UTF-8, decoded as {enc} (check special characters)"]
        except UnicodeDecodeError:
            pass
    return raw.decode("utf-8", "replace"), [f"{name}: undecodable bytes replaced"]


def unwrap_lines(text: str) -> str:
    """Re-join hard-wrapped PDF lines so sentences (and the facts inside them) are not cut in half."""
    out: list[str] = []
    for ln in text.split("\n"):
        s = ln.strip()
        prev = out[-1] if out else ""
        if prev and s and not prev.endswith((".", "!", "?", ":")) and (len(prev) >= 60 or s[0].islower()):
            out[-1] = f"{prev} {s}"
        else:
            out.append(s)
    return "\n".join(out)


def _read_pdf(path: Path) -> tuple[str, list[str]]:
    from pypdf import PdfReader

    try:
        reader = PdfReader(str(path))
        pages = [(p.extract_text() or "") for p in reader.pages]
    except Exception as e:  # corrupt / encrypted
        return "", [f"{path.name}: could not read PDF ({e}) - skipped"]
    text = unwrap_lines("\n".join(pages)).strip()
    if len(text) < 20:
        return "", [f"{path.name}: no extractable text ({len(pages)} pages) - probably a scanned PDF; OCR is not supported, skipped"]
    return text, []


def _read_docx(path: Path) -> tuple[str, list[str]]:
    import docx

    try:
        d = docx.Document(str(path))
    except Exception as e:
        return "", [f"{path.name}: could not read DOCX ({e}) - skipped"]
    parts = [p.text for p in d.paragraphs if p.text.strip()]
    for t in d.tables:
        for row in t.rows:
            parts.append(" | ".join(c.text.strip() for c in row.cells))
    return "\n".join(parts), []


def row_to_text(row: dict) -> str:
    return " | ".join(f"{k}: {v}" for k, v in row.items() if k)


def _read_csv(path: Path) -> tuple[str, list[dict], list[str], list[str]]:
    text, warnings = decode_bytes(path.read_bytes(), path.name)
    try:
        dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel
    reader = csv.DictReader(io.StringIO(text), dialect=dialect)
    rows = [{(k or "").strip(): (v or "").strip() for k, v in r.items() if k is not None} for r in reader]
    cols = [c.strip() for c in (reader.fieldnames or [])]
    if len(rows) > MAX_CSV_TEXT_ROWS:
        warnings.append(f"{path.name}: {len(rows)} rows; only the first {MAX_CSV_TEXT_ROWS} are indexed for retrieval (csv_lookup sees all)")
    body = "\n".join(row_to_text(r) for r in rows[:MAX_CSV_TEXT_ROWS])
    return body, rows, cols, warnings


def load_document(path: Path) -> Document | None:
    ext = path.suffix.lower()
    if ext == ".csv":
        text, rows, cols, w = _read_csv(path)
        doc = Document(path.name, "csv", text, rows, cols, w)
        if not rows:
            doc.warnings.append(f"{path.name}: CSV has no data rows - skipped")
            doc.text = ""
        return doc
    if ext == ".pdf":
        text, w = _read_pdf(path)
    elif ext == ".docx":
        text, w = _read_docx(path)
    else:
        text, w = decode_bytes(path.read_bytes(), path.name)
    doc = Document(path.name, ext.lstrip("."), text.strip(), warnings=w)
    if not doc.text and not w:
        doc.warnings.append(f"{path.name}: empty document - skipped")
    return doc


def load_folder(folder: str | Path) -> tuple[list[Document], list[str]]:
    folder = Path(folder)
    if not folder.is_dir():
        return [], [f"document folder not found: {folder}"]
    docs, warnings = [], []
    for p in sorted(folder.rglob("*")):
        if not p.is_file() or p.name.startswith((".", "~$")):
            continue
        if p.suffix.lower() not in SUPPORTED:
            warnings.append(f"{p.name}: unsupported file type '{p.suffix}' - skipped")
            continue
        d = load_document(p)
        warnings.extend(d.warnings)
        if d.text:
            docs.append(d)
    if not docs:
        warnings.append("no usable documents found")
    return docs, warnings


def doc_info(doc: Document) -> dict:
    info = {"name": doc.name, "type": doc.type, "chars": len(doc.text), "warnings": doc.warnings}
    if doc.rows is not None:
        info.update(columns=doc.columns, n_rows=len(doc.rows), sample_rows=doc.rows[:3],
                    summary=f"CSV table with {len(doc.rows)} rows; columns: {', '.join(doc.columns or [])}")
    else:
        info["summary"] = " ".join(doc.text.split())[:300]
    return info


# ---------------------------------------------------------------- chunking
def _split_long(s: str, size: int) -> list[str]:
    words, out, cur = s.split(), [], ""
    for w in words:
        if cur and len(cur) + len(w) + 1 > size:
            out.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}".strip()
    if cur:
        out.append(cur)
    return out


def chunk_document(doc: Document, size: int = 700, overlap: int = 100) -> list[Chunk]:
    """Sentence-aware packing (facts stay intact); CSV rows are atomic lines, never split."""
    if doc.type == "csv":
        units, overlap = doc.text.split("\n"), 0
    else:
        units = []
        for s in sentences(doc.text):
            units.extend(_split_long(s, size) if len(s) > size else [s])
    chunks: list[list[str]] = []
    cur: list[str] = []
    for u in units:
        if cur and sum(len(x) + 1 for x in cur) + len(u) > size:
            chunks.append(cur)
            carry: list[str] = []
            for x in reversed(cur):
                if sum(len(y) + 1 for y in carry) + len(x) > overlap:
                    break
                carry.insert(0, x)
            cur = carry
        cur.append(u)
    if cur:
        chunks.append(cur)
    return [Chunk(f"{doc.name}#{i}", doc.name, "\n".join(c), i) for i, c in enumerate(chunks)]


def chunk_all(docs: list[Document], size: int, overlap: int) -> list[Chunk]:
    out: list[Chunk] = []
    for d in docs:
        out.extend(chunk_document(d, size, overlap))
    return out
