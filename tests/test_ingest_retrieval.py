from pathlib import Path

from forgeai.ingest import chunk_document, load_folder, Document
from forgeai.retrieval import Retriever, calibrate_threshold
from forgeai.ingest import chunk_all


def test_loads_all_formats(hr_docs, spares_docs):
    assert {d.type for d in hr_docs} == {"pdf", "docx", "md"}
    csv = next(d for d in spares_docs if d.type == "csv")
    assert len(csv.rows) >= 60 and {"part_id", "unit_price", "lead_time_days", "stock"} <= set(csv.columns)


def test_pdf_lines_unwrapped(hr_docs):
    leave = next(d for d in hr_docs if d.name == "leave_policy.pdf")
    assert "entitled to 25 days of paid annual leave per calendar year, in addition to public holidays." in leave.text


def test_bad_inputs_warn_not_crash(tmp_path: Path):
    (tmp_path / "empty.txt").write_text("", encoding="utf-8")
    (tmp_path / "latin.txt").write_bytes("Caf\xe9 policy: 5 days.".encode("cp1252"))
    (tmp_path / "scan.pdf").write_bytes(b"%PDF-1.4\n1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n2 0 obj << /Type /Pages /Kids [] /Count 0 >> endobj\ntrailer << /Root 1 0 R >>\n%%EOF")
    (tmp_path / "image.png").write_bytes(b"\x89PNG")
    (tmp_path / "nohead.csv").write_text("a,b\n", encoding="utf-8")
    docs, warnings = load_folder(tmp_path)
    assert [d.name for d in docs] == ["latin.txt"] and "Café" in docs[0].text
    joined = " ".join(warnings)
    for needle in ("empty.txt", "latin.txt", "scan.pdf", "image.png", "nohead.csv"):
        assert needle in joined
    assert load_folder(tmp_path / "missing")[0] == []


def test_chunking_overlap_and_csv_rows_atomic(hr_docs, spares_docs):
    d = Document("x.txt", "txt", " ".join(f"Sentence number {i} has some words in it." for i in range(60)))
    ch = chunk_document(d, 300, 80)
    assert len(ch) > 3 and all(len(c.text) <= 380 for c in ch)
    assert ch[0].text.split("\n")[-1] in ch[1].text  # overlap carries the last sentence
    csv = next(x for x in spares_docs if x.type == "csv")
    for c in chunk_document(csv, 400, 100):
        assert all(line.startswith("part_id: SP-") for line in c.text.split("\n"))


def test_hybrid_retrieval_finds_right_doc_and_calibrates(hr_docs):
    r = Retriever(chunk_all(hr_docs, 600, 100), 0.5)
    hit = r.search("How many days of paid sick leave do employees get?", 3)[0]
    assert hit.chunk.doc == "leave_policy.pdf"
    assert r.search("hotel limit per night in high-cost cities", 3)[0].chunk.doc == "travel_expenses_policy.md"
    thr, info = calibrate_threshold(r)
    assert 0.05 <= thr <= 0.9
    assert r.confidence("Who painted the Sistine Chapel ceiling?") < thr <= r.confidence("paid sick leave per calendar year")
