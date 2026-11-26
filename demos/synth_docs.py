"""Generate the demo document folders.

Default (offline, deterministic): writes the seed content below (which was drafted with an LLM using the
committed prompts/synth_*.txt and then frozen so the demos are reproducible).
--llm: regenerate every text document with the configured LLM via prompts/synth_*.txt.
The spares catalogue CSV is always generated in code (seeded) - numbers in a catalogue must be exact.

    python demos/synth_docs.py            # offline seed content
    python demos/synth_docs.py --llm      # LLM-synthesised content (needs a real provider in .env)
"""
from __future__ import annotations

import argparse
import random
import sys
import textwrap
from pathlib import Path

from pydantic import BaseModel

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
DEMOS = ROOT / "demos"

# ------------------------------------------------------------------ seed content
HR = {
    "leave_policy.pdf": ("Leave Policy for Shore Staff", "leave entitlements, sick leave, parental leave, compassionate, study and unpaid leave", [
        ("1. Annual Leave", "Full-time shore staff are entitled to 25 days of paid annual leave per calendar year, in addition to public holidays. Part-time staff receive annual leave pro rata to their contracted hours. Leave requests must be submitted through the HR portal at least 14 days in advance and approved by the line manager. A maximum of 5 days of unused annual leave may be carried over into the next calendar year, and carried-over days must be used by 31 March."),
        ("2. Sick Leave", "Employees receive up to 10 days of paid sick leave per calendar year. A medical certificate is required for any absence longer than 3 consecutive days. Employees must inform their line manager before 10:00 on the first day of absence."),
        ("3. Parental Leave", "Primary caregivers are entitled to 26 weeks of paid parental leave. Secondary caregivers are entitled to 4 weeks of paid parental leave, which must be taken within 12 months of the birth or adoption. Parental leave must be requested at least 8 weeks before the expected start date."),
        ("4. Compassionate Leave", "Employees may take up to 5 days of paid compassionate leave following the death of an immediate family member, and up to 2 days for other relatives."),
        ("5. Study Leave", "Employees may take up to 5 days of paid study leave per year to sit approved professional examinations. Study leave must be approved by the Head of Department."),
        ("6. Unpaid Leave", "Unpaid leave of up to 30 days may be granted in exceptional circumstances. Requests for unpaid leave are approved by the Head of Department and the HR Business Partner."),
    ]),
    "code_of_conduct.docx": ("Code of Conduct", "gifts and hospitality, conflicts of interest, confidentiality, anti-bribery, speaking up, workplace behaviour, social media", [
        ("Gifts and Hospitality", "Employees may accept gifts or hospitality with a value of up to USD 75 from business partners. Any gift above USD 75 must be declared to the Compliance Officer within 5 working days. Cash or cash-equivalent gifts must always be refused."),
        ("Conflicts of Interest", "Employees must declare any actual or potential conflict of interest in writing to their line manager and the Compliance Officer. All staff complete an annual conflict of interest declaration by 31 January each year."),
        ("Confidentiality", "Information classified as Confidential must not be shared outside the company without written approval from a director. Confidential documents must be stored on the company document system and never on personal devices."),
        ("Anti-Bribery", "The company has zero tolerance for bribery. Facilitation payments are prohibited in all countries, including port payments requested by officials. Any request for a bribe must be reported to the Compliance Officer within 24 hours."),
        ("Speaking Up", "Concerns about misconduct can be reported anonymously through the Ethics Hotline on extension 4455. Every report is acknowledged within 2 working days, and retaliation against anyone who speaks up in good faith is a disciplinary offence."),
        ("Workplace Behaviour", "Harassment, bullying and discrimination are not tolerated. Breaches are handled under the disciplinary procedure, and a first written warning remains on the employee file for 12 months."),
        ("Social Media", "Employees must not comment publicly on behalf of the company on social media unless authorised by the Communications Manager."),
    ]),
    "travel_expenses_policy.md": ("Travel and Expenses Policy", "travel arrangements, flights, hotels, per diem, mileage, expense claims, non-reimbursable items", [
        ("Arranging Travel", "All business travel must be arranged through the corporate travel desk at least 10 days before departure. Trips must be pre-approved by the line manager in the HR portal."),
        ("Air Travel", "Economy class must be used for flights shorter than 6 hours. Business class is permitted for flights of 6 hours or more."),
        ("Hotels", "The hotel limit is USD 180 per night in standard cities and USD 250 per night in high-cost cities such as London, Singapore and New York."),
        ("Meals and Per Diem", "A daily meal allowance of USD 60 applies for each full day of travel. Receipts are not required for the meal allowance."),
        ("Private Car Use", "Use of a private car for business travel is reimbursed at USD 0.45 per kilometre."),
        ("Expense Claims", "Expense claims must be submitted within 30 days of returning from travel. Itemised receipts are required for any single expense above USD 25. Claims are approved by the line manager and reimbursed within 10 working days of approval."),
        ("Non-Reimbursable Items", "Traffic fines, personal entertainment, minibar charges and upgrades purchased for personal convenience are not reimbursed."),
    ]),
}

SPARES_SUPPLIERS = {
    "supplier_a_terms.pdf": ("Nordic Marine Supply - Terms of Supply", "discounts, minimum order, delivery terms, warranty, payment terms, returns", [
        ("Volume Discounts", "Nordic Marine Supply grants a 5% discount on orders above USD 5,000 and a 10% discount on orders above USD 20,000. Discounts apply to the order total before freight."),
        ("Minimum Order", "The minimum order value is USD 500. Orders below the minimum incur a handling fee of USD 45."),
        ("Delivery", "Delivery is DAP (Delivered at Place) to the ports of Rotterdam, Hamburg and Gothenburg. Expedited delivery within 72 hours is available for a surcharge of 15% of the order value."),
        ("Warranty", "All parts carry a warranty of 12 months from installation or 18 months from delivery, whichever comes first."),
        ("Payment Terms", "Payment is due within 30 days of invoice. A late payment interest of 1.5% per month applies to overdue invoices."),
        ("Returns", "Unused parts may be returned within 60 days of delivery subject to a restocking fee of 10%."),
    ]),
    "supplier_b_terms.pdf": ("Asia Pacific Ship Parts - Supplier Terms", "discounts, minimum order, delivery terms, warranty, payment terms, certificates", [
        ("Volume Discounts", "Asia Pacific Ship Parts offers a 7% discount on orders above USD 10,000. There is no discount on orders below USD 10,000."),
        ("Minimum Order", "The minimum order value is USD 1,000."),
        ("Delivery", "Delivery is FOB Singapore. Standard dispatch is within 5 working days of order confirmation, and the buyer arranges onward freight."),
        ("Warranty", "Parts carry a warranty of 6 months from delivery."),
        ("Payment Terms", "Payment is due within 45 days of invoice. Orders above USD 50,000 require a 30% advance payment."),
        ("Certificates", "Class certificates from DNV or ABS are supplied free of charge for critical engine parts on request."),
    ]),
}

ADMISSIONS = {
    "admissions_policy.pdf": ("Undergraduate Admissions Policy", "application deadlines, entry requirements, interviews, offers, deferral", [
        ("Application Deadlines", "Applications for September entry open on 1 September of the previous year. The deadline for applications to Medicine and Law is 15 October. The deadline for all other undergraduate programmes is 31 January. Late applications are considered only if places remain."),
        ("Entry Requirements", "The standard offer for Engineering is AAA at A-level including Mathematics and Physics. The standard offer for Business Management is ABB. The International Baccalaureate equivalent for Engineering is 36 points with 6 in Higher Level Mathematics."),
        ("Interviews", "Applicants to Medicine are invited to a multiple mini interview held in December. Other programmes do not normally interview."),
        ("Offers and Decisions", "Decisions on applications received by 31 January are made by 31 March. Applicants must reply to offers by 1 June."),
        ("Deferred Entry", "Deferred entry for one year is accepted for most programmes, except Medicine."),
    ]),
    "international_students.txt": ("International Students Guide", "English language requirements, visas, arrival", [
        ("English Language Requirements", "International applicants whose first language is not English need an IELTS Academic score of 6.5 overall with no component below 6.0. Engineering and Medicine require IELTS 7.0 overall. A TOEFL iBT score of 92 is accepted as equivalent to IELTS 6.5."),
        ("Pre-sessional English", "Applicants who are up to 0.5 below the required IELTS score may join the 10-week pre-sessional English course starting in July."),
        ("Visa Support", "The university issues a Confirmation of Acceptance for Studies once the offer is unconditional and a deposit of GBP 3,000 has been paid."),
        ("Arrival", "International students are met at the airport during the arrival week, which begins on 15 September. On-campus accommodation is guaranteed for first-year international students who apply by 30 June."),
    ]),
    "fees_and_scholarships.docx": ("Fees and Scholarships", "tuition fees per year, course length, deposit, scholarships, payment plans", [
        ("Tuition Fees", "Annual tuition for home students is GBP 9,250. Annual tuition for international students is GBP 24,500 for Engineering and GBP 19,800 for Business Management."),
        ("Course Length", "Engineering is a 4-year integrated master's programme. Business Management is a 3-year bachelor's programme."),
        ("Scholarships", "The Global Excellence Scholarship awards GBP 5,000 per year to international students who achieve AAA or 38 IB points. The Community Bursary provides GBP 2,000 per year to home students with household income below GBP 30,000."),
        ("Scholarship Applications", "Scholarship applications close on 1 May. Recipients are notified by 15 June."),
        ("Payment Plans", "Tuition can be paid in 3 instalments in October, January and April. A discount of 2% applies when the full annual fee is paid before 30 September."),
    ]),
}

BRIEFS = {
    "hr": "I need an assistant that answers HR policy questions for shore staff: leave entitlements, the code of conduct, travel and expense claims, and our employee pension and retirement plan.",
    "spares": "I need a procurement assistant for our ship superintendents: look up spare parts in the catalogue, compare suppliers and their terms, check lead times and stock levels, and work out order costs including quantity discounts.",
    "admissions": "I need an assistant that answers prospective students' questions about undergraduate admissions: application deadlines and how many days are left, entry requirements, English language requirements for international students, tuition fees and total course cost, and scholarships.",
}


# ------------------------------------------------------------------ writers
def write_pdf(path: Path, title: str, sections: list[tuple[str, str]]) -> None:
    """Minimal valid text PDF (Helvetica), no external dependency."""
    lines = [title, ""]
    for h, body in sections:
        lines += [h] + textwrap.wrap(body, 92) + [""]
    pages = [lines[i:i + 52] for i in range(0, len(lines), 52)]

    def esc(s: str) -> str:
        return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")

    objs = ["<< /Type /Catalog /Pages 2 0 R >>", None, "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    kids = []
    for pg in pages:
        stream = "BT /F1 10 Tf 50 800 Td 14 TL\n" + "".join(f"({esc(l)}) Tj T*\n" for l in pg) + "ET"
        objs.append(f"<< /Length {len(stream.encode('latin-1'))} >>\nstream\n{stream}\nendstream")
        objs.append(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 3 0 R >> >> /Contents {len(objs)} 0 R >>")
        kids.append(len(objs))
    objs[1] = f"<< /Type /Pages /Kids [{' '.join(f'{k} 0 R' for k in kids)}] /Count {len(kids)} >>"
    out, offsets = bytearray(b"%PDF-1.4\n"), []
    for i, o in enumerate(objs, 1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n{o}\nendobj\n".encode("latin-1")
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    out += "".join(f"{o:010d} 00000 n \n" for o in offsets).encode()
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    path.write_bytes(bytes(out))


def write_docx(path: Path, title: str, sections: list[tuple[str, str]]) -> None:
    import docx

    d = docx.Document()
    d.add_heading(title, 0)
    for h, body in sections:
        d.add_heading(h, 1)
        d.add_paragraph(body)
    d.save(str(path))


def write_text(path: Path, title: str, sections: list[tuple[str, str]]) -> None:
    md = path.suffix == ".md"
    parts = [f"# {title}" if md else title.upper(), ""]
    for h, body in sections:
        parts += [f"## {h}" if md else h, body, ""]
    path.write_text("\n".join(parts), encoding="utf-8")


def write_doc(folder: Path, name: str, title: str, sections) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    p = folder / name
    {".pdf": write_pdf, ".docx": write_docx}.get(p.suffix, write_text)(p, title, sections)


def spares_catalogue(path: Path, seed: int = 7, n: int = 64) -> None:
    import csv

    rng = random.Random(seed)
    parts = {
        "Main Engine": ["Fuel injector nozzle", "Cylinder liner", "Piston ring set", "Exhaust valve spindle", "Turbocharger bearing", "Fuel pump plunger", "Starting air valve", "Cylinder head gasket"],
        "Auxiliary Engine": ["Lube oil filter element", "Fuel filter cartridge", "Cooling water pump seal", "Governor actuator", "Connecting rod bearing", "Thermostat element"],
        "Pumps": ["Centrifugal pump impeller", "Mechanical seal kit", "Ballast pump shaft sleeve", "Bilge pump diaphragm", "Pump coupling insert"],
        "Electrical": ["Circuit breaker 63A", "Generator AVR module", "Navigation light LED unit", "Motor contactor 40A", "Insulation monitor relay"],
        "Deck Machinery": ["Windlass brake lining", "Mooring winch hydraulic motor seal kit", "Crane slewing bearing seal", "Wire rope 24mm per metre", "Hatch cover rubber packing per metre"],
        "Safety": ["Lifejacket light", "Fire hose 20m", "SCBA cylinder 6.8L", "EEBD hood", "Immersion suit"],
    }
    suppliers = ["Nordic Marine Supply", "Asia Pacific Ship Parts", "Global Engine Components"]
    price_band = {"Main Engine": (400, 9000), "Auxiliary Engine": (40, 1800), "Pumps": (90, 2500),
                  "Electrical": (60, 3200), "Deck Machinery": (25, 4800), "Safety": (30, 1400)}
    rows, i = [], 1
    while len(rows) < n:
        for cat, names in parts.items():
            for nm in names:
                if len(rows) >= n:
                    break
                variant = "" if i <= 34 else rng.choice([" (heavy duty)", " (OEM)", " (type B)"])
                lo, hi = price_band[cat]
                rows.append({"part_id": f"SP-{i:04d}", "name": nm + variant, "category": cat,
                             "supplier": rng.choice(suppliers), "unit_price": f"{rng.uniform(lo, hi):.2f}",
                             "lead_time_days": rng.choice([3, 5, 7, 10, 14, 21, 28, 42]), "stock": rng.choice([0, 0, 1, 2, 4, 6, 10, 15, 25, 40])})
                i += 1
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


class _Sections(BaseModel):
    sections: list[dict]


def llm_sections(llm, template: str, title: str, outline: str, fallback):
    out = llm.call("synth", template, {"doc_title": title, "outline": outline}, _Sections)
    secs = [(s.get("heading", ""), s.get("body", "")) for s in out.sections if s.get("body")]
    return secs or fallback


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--llm", action="store_true", help="synthesise text docs with the configured LLM")
    a = ap.parse_args()
    llm = None
    if a.llm:
        from forgeai.llm import LLM

        llm = LLM()
        if llm.is_mock:
            sys.exit("--llm needs a real provider (set LLM_PROVIDER/LLM_API_KEY in .env)")

    def gen(folder: Path, spec: dict, template: str):
        for name, (title, outline, secs) in spec.items():
            if llm:
                secs = llm_sections(llm, template, title, outline, secs)
            write_doc(folder, name, title, secs)

    gen(DEMOS / "hr" / "docs", HR, "synth_hr")
    gen(DEMOS / "spares" / "docs", SPARES_SUPPLIERS, "synth_spares")
    spares_catalogue(DEMOS / "spares" / "docs" / "spares_catalogue.csv")
    gen(DEMOS / "admissions" / "docs", ADMISSIONS, "synth_admissions")

    # changed HR docs for the regression demo: leave 25 -> 28 days, hotel cap 180 -> 200, study leave removed
    v2 = {k: (t, o, [(h, b.replace("25 days of paid annual leave", "28 days of paid annual leave")
                       .replace("USD 180 per night", "USD 200 per night")) for h, b in s if not h.startswith("5. Study")])
          for k, (t, o, s) in HR.items()}
    for name, (title, _, secs) in v2.items():  # always from the frozen seed so the diff is known
        write_doc(DEMOS / "hr" / "docs_v2", name, title, secs)
    for key, brief in BRIEFS.items():
        (DEMOS / key / "brief.txt").write_text(brief + "\n", encoding="utf-8")
    print("demo documents written under", DEMOS)


if __name__ == "__main__":
    main()
