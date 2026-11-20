"""Medical report analysis: validate -> extract text (PDF text layer or OCR) -> parse lab rows -> explain.

Privacy: the uploaded file is processed in memory and NOT stored. Only file metadata (name, type, size,
SHA-256), the extracted lab rows and a summary are saved, and the user can delete them at any time.
"""
from __future__ import annotations

import hashlib
import html
import io
import logging
import os
import re
from functools import lru_cache

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import AppError, ServiceUnavailableError
from app.models import ExtractedLabResult, MedicalReport, User
from app.services.activity import log_activity
from app.services.report_parser import LabResult, parse_text

log = logging.getLogger("medicore.reports")

MAX_PAGES = 20
MIN_TEXT_CHARS_PER_PAGE = 40          # below this a PDF page is treated as scanned
MAX_IMAGE_PIXELS = 40_000_000         # decompression-bomb guard
SIGNATURES = {
    "application/pdf": (b"%PDF-",),
    "image/png": (b"\x89PNG\r\n\x1a\n",),
    "image/jpeg": (b"\xff\xd8\xff",),
}
EXTENSIONS = {".pdf": "application/pdf", ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}

# What each test is (general descriptions in everyday words, not interpretations of a person's result)
GLOSSARY = {
    "Hemoglobin": "Haemoglobin is the part of your red blood cells that carries oxygen around your body. This test is often used to check for anaemia (low iron or too few red blood cells).",
    "HbA1c": "HbA1c shows your average blood sugar over the past two to three months. Doctors use it to check for and keep track of diabetes.",
    "Glucose": "Glucose is the sugar in your blood. The result depends on whether you had eaten before the test.",
    "Total cholesterol": "Cholesterol is a fatty substance in your blood. This number is all your cholesterol added together.",
    "HDL cholesterol": "HDL is the \"good\" cholesterol. It helps carry extra cholesterol away from your arteries, so higher is usually better.",
    "LDL cholesterol": "LDL is the \"bad\" cholesterol. Too much of it can build up in your artery walls and raise the risk of heart problems.",
    "Non-HDL cholesterol": "Non-HDL is your total cholesterol minus the \"good\" HDL, so it includes all the types that can clog arteries.",
    "Triglycerides": "Triglycerides are a type of fat in your blood. Levels can go up after eating or drinking alcohol.",
    "Creatinine": "Creatinine is a waste product from your muscles that your kidneys filter out. Doctors use it to see how well your kidneys work.",
    "eGFR": "eGFR is an estimate of how well your kidneys are cleaning your blood. It is worked out from your creatinine result, age and sex.",
    "Urea / BUN": "Urea is a waste product that your kidneys filter out of your blood.",
    "Vitamin D (25-OH)": "This is the main form of vitamin D in your blood. It shows whether you have enough of this vitamin, which your bones and muscles need.",
    "Vitamin B12": "Vitamin B12 helps keep your nerves and blood cells healthy.",
    "Ferritin": "Ferritin shows how much iron your body has stored. It can also go up when you have inflammation.",
    "Iron": "This is the amount of iron in your blood right now.",
    "TSH": "TSH is a hormone that tells your thyroid gland how hard to work. It is the usual first test for thyroid problems.",
    "ALT": "ALT is a liver enzyme. Doctors check it to see how your liver is doing.",
    "AST": "AST is an enzyme found in your liver, heart and muscles.",
    "WBC": "White blood cells help your body fight infections.",
    "RBC": "Red blood cells carry oxygen from your lungs to the rest of your body.",
    "Platelets": "Platelets are tiny blood cells that help your blood clot when you are cut.",
    "Hematocrit": "Haematocrit is the share of your blood made up of red blood cells.",
    "MCV": "MCV is the average size of your red blood cells.",
    "Sodium": "Sodium is a salt your body needs for fluid balance and for nerves and muscles to work.",
    "Potassium": "Potassium is a mineral that helps your heart and muscles work properly.",
    "Calcium": "Calcium is a mineral your bones, muscles, nerves and heart need.",
    "Uric acid": "Uric acid is a waste product from food and normal body processes. Too much can lead to gout.",
    "CRP": "CRP is a sign of inflammation in your body.",
}
CONTEXT_NOTE = ("A result outside the range does not mean something is wrong. Many things can change a result, like "
                "what you ate or how you were feeling that day. A doctor can look at it together with your health "
                "history and other tests.")


# --------------------------------------------------------------------------- validation
def validate_upload(filename: str, declared_type: str | None, data: bytes) -> str:
    s = get_settings()
    if not data:
        raise AppError("That file is empty. Please choose another one.", code="empty_file")
    if len(data) > s.max_upload_mb * 1024 * 1024:
        raise AppError(f"That file is too big (the limit is {s.max_upload_mb} MB). Try a smaller file or a lower-resolution photo.", code="file_too_large", status_code=413)
    ext = os.path.splitext(filename.lower())[1]
    by_ext = EXTENSIONS.get(ext)
    by_magic = next((m for m, sigs in SIGNATURES.items() if any(data.startswith(sig) for sig in sigs)), None)
    if by_magic is None or by_ext is None:
        raise AppError("Please upload a PDF, JPG or PNG file.", code="unsupported_type", status_code=415)
    if by_magic != by_ext:
        raise AppError("That file does not look like a real PDF or image. Please check it and try again.", code="type_mismatch", status_code=415)
    if declared_type and declared_type not in (by_magic, "application/octet-stream"):
        raise AppError("That file does not look like a real PDF or image. Please check it and try again.", code="type_mismatch", status_code=415)
    return by_magic


def safe_filename(name: str) -> str:
    base = os.path.basename(name.replace("\\", "/"))
    base = re.sub(r"[^\w.\- ()]", "_", base).strip() or "report"
    return base[:200]


# --------------------------------------------------------------------------- OCR
@lru_cache
def ocr_available() -> bool:
    try:
        import pytesseract  # noqa: PLC0415

        cmd = os.environ.get("TESSERACT_CMD")
        if cmd:
            pytesseract.pytesseract.tesseract_cmd = cmd
        pytesseract.get_tesseract_version()
        return True
    except Exception:  # noqa: BLE001 - missing binary raises several error types
        return False


def _ocr_image(img) -> str:
    import pytesseract  # noqa: PLC0415

    if not ocr_available():
        raise ServiceUnavailableError(
            "This looks like a scan or a photo, and we cannot read those on this server right now. Please upload a PDF "
            "where you can select the text.", code="ocr_unavailable")
    gray = img.convert("L")
    return pytesseract.image_to_string(gray, config="--psm 6")


# --------------------------------------------------------------------------- extraction
def _pdf_rows(page) -> str:
    """Rebuild visual table rows from word boxes (cells of one row share a baseline)."""
    words = page.get_text("words")
    rows: list[list[tuple[float, float, str]]] = []
    for x0, y0, x1, y1, w, *_ in sorted(words, key=lambda t: ((t[1] + t[3]) / 2, t[0])):
        yc = (y0 + y1) / 2
        if rows and abs(rows[-1][0][1] - yc) <= 3.0:
            rows[-1].append((x0, yc, w))
        else:
            rows.append([(x0, yc, w)])
    return "\n".join(" ".join(w for _, _, w in sorted(r)) for r in rows)


def extract_text(data: bytes, mime: str) -> tuple[str, str, int]:
    """Returns (text, method, page_count). method is 'text' or 'ocr'."""
    if mime == "application/pdf":
        import pymupdf  # noqa: PLC0415

        try:
            doc = pymupdf.open(stream=data, filetype="pdf")
        except Exception as exc:  # noqa: BLE001
            raise AppError("We could not open that PDF. It may be damaged. Try downloading or saving it again.", code="invalid_pdf") from exc
        if doc.needs_pass:
            raise AppError("That PDF is password protected. Please remove the password and upload it again.", code="encrypted_pdf")
        if doc.page_count > MAX_PAGES:
            raise AppError(f"That PDF is too long (the limit is {MAX_PAGES} pages). Please upload only the pages with your results.", code="too_many_pages")
        texts, scanned = [], []
        for page in doc:
            t = _pdf_rows(page)
            texts.append(t)
            scanned.append(len(t.strip()) < MIN_TEXT_CHARS_PER_PAGE)
        if not all(scanned):
            return "\n".join(texts), "text", doc.page_count
        from PIL import Image  # noqa: PLC0415

        ocr = []
        for page in doc:
            pix = page.get_pixmap(dpi=300)
            ocr.append(_ocr_image(Image.open(io.BytesIO(pix.tobytes("png")))))
        return "\n".join(ocr), "ocr", doc.page_count
    from PIL import Image  # noqa: PLC0415

    Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS
    try:
        img = Image.open(io.BytesIO(data))
        img.verify()
        img = Image.open(io.BytesIO(data))
    except Exception as exc:  # noqa: BLE001 - includes DecompressionBombError
        raise AppError("We could not read that image. Try a clearer photo or a PDF.", code="invalid_image") from exc
    return _ocr_image(img), "ocr", 1


# --------------------------------------------------------------------------- explanation
# A linked passage must literally mention the analyte; semantic closeness alone produced wrong links
# (e.g. "haemoglobin" -> a heart-attack page). No link is better than a misleading one.
LEARN_TERMS = {
    "Hemoglobin": ["haemoglobin", "hemoglobin"], "HbA1c": ["hba1c", "a1c", "glycated", "glycosylated"],
    "Glucose": ["glucose", "blood sugar"], "Total cholesterol": ["cholesterol"], "HDL cholesterol": ["hdl", "high-density"],
    "LDL cholesterol": ["ldl", "low-density"], "Non-HDL cholesterol": ["non-hdl"], "Triglycerides": ["triglyceride"],
    "Creatinine": ["creatinine"], "eGFR": ["egfr", "glomerular filtration"], "Urea / BUN": ["urea"],
    "Vitamin D (25-OH)": ["vitamin d", "25-hydroxyvitamin"], "Vitamin B12": ["b12", "cobalamin"], "Ferritin": ["ferritin"],
    "Iron": ["iron"], "TSH": ["tsh", "thyroid-stimulating"], "ALT": ["alanine aminotransferase", " alt "],
    "AST": ["aspartate aminotransferase", " ast "], "WBC": ["white blood cell", "leukocyte"], "RBC": ["red blood cell"],
    "Platelets": ["platelet"], "Hematocrit": ["haematocrit", "hematocrit"], "MCV": ["mean corpuscular volume", "mcv"],
    "Sodium": ["sodium"], "Potassium": ["potassium"], "Calcium": ["calcium"], "Uric acid": ["uric acid"],
    "CRP": ["c-reactive protein", "crp"],
}


@lru_cache(maxsize=128)
def _learn_more(parameter: str) -> dict | None:
    """Best-ranked trusted passage that actually mentions the analyte (if the knowledge base is built)."""
    try:
        from app.rag.retriever import get_retriever  # noqa: PLC0415

        r = get_retriever()
        terms = LEARN_TERMS.get(parameter)
        if r is None or not terms:
            return None
        q = f"{parameter} blood test"
        cfg = r.config
        for e in r.score(r.vector_search(q, 25), q):
            text = f" {e.title} {e.text} ".lower()
            if e.similarity >= cfg.min_similarity and any(t in text for t in terms):
                return {"title": e.title, "url": e.url, "source": e.source, "published": e.published}
        return None
    except Exception:  # noqa: BLE001 - explanations must not fail the request
        log.exception("learn-more lookup failed")
        return None


def explain(r: ExtractedLabResult) -> dict:
    unit = f" {r.unit}" if r.unit else ""
    val = f"{r.value_text}{unit}"
    ref = f" ({r.ref_text}{unit})" if r.ref_text else ""
    if r.flag in ("high", "low") and r.flag_source == "reference_range":
        status = (f"Your result ({val}) is {'higher' if r.flag == 'high' else 'lower'} than the normal range printed "
                  f"on your lab report{ref}.")
    elif r.flag in ("high", "low"):
        status = f"Your lab report marks this result ({val}) as {r.flag}."
    elif r.flag == "normal":
        status = f"Your result ({val}) is inside the normal range printed on your lab report{ref}."
    else:
        status = (f"Your report does not show a normal range next to this result ({val}), so we cannot tell whether "
                  "it is in range. Different labs use different ranges, so we do not guess.")
    return {
        "what_it_measures": GLOSSARY.get(r.parameter),
        "status": status,
        "context": CONTEXT_NOTE if r.flag in ("high", "low") else None,
        "learn_more": _learn_more(r.parameter) if r.parameter in GLOSSARY else None,
    }


def build_summary(results: list[LabResult]) -> str:
    if not results:
        return ("We could not find any lab results in this file. We look for a test name, a number, and ideally a unit "
                "and a normal range on each line. A clearer photo or a PDF you can select text from usually works best.")
    n = len(results)
    out = [r for r in results if r.flag in ("high", "low")]
    unknown = [r for r in results if r.flag == "unknown"]
    parts = [f"We found {n} result{'s' if n != 1 else ''} in your report."]
    if out:
        names = ", ".join(f"{r.parameter} ({r.value_text}{' ' + r.unit if r.unit else ''}, "
                          f"{'higher' if r.flag == 'high' else 'lower'})" for r in out)
        parts.append(f"{len(out)} {'is' if len(out) == 1 else 'are'} outside the normal range printed on your report: {names}.")
    else:
        parts.append("None of the results that have a printed normal range are outside it.")
    if unknown:
        parts.append(f"{len(unknown)} result{'s' if len(unknown) != 1 else ''} had no normal range, so we could not check "
                     f"{'it' if len(unknown) == 1 else 'them'}.")
    parts.append("This is not a diagnosis. Please go through your results with a doctor.")
    return " ".join(parts)


# --------------------------------------------------------------------------- orchestration
def analyse_upload(db: Session, user: User, filename: str, declared_type: str | None, data: bytes) -> MedicalReport:
    mime = validate_upload(filename, declared_type, data)
    text, method, pages = extract_text(data, mime)
    results = parse_text(text)
    report = MedicalReport(
        user_id=user.id, original_filename=safe_filename(filename), mime_type=mime, size_bytes=len(data),
        sha256=hashlib.sha256(data).hexdigest(), extraction_method=method, page_count=pages,
        status="processed" if results else "no_results", summary=build_summary(results),
    )
    report.lab_results = [
        ExtractedLabResult(parameter=r.parameter, printed_name=r.printed_name, value_text=r.value_text,
                           value_numeric=r.value_numeric, unit=r.unit, ref_low=r.ref_low, ref_high=r.ref_high,
                           ref_text=r.ref_text, flag=r.flag, flag_source=r.flag_source)
        for r in results
    ]
    db.add(report)
    db.flush()
    log_activity(db, user.id, "report.upload", "medical_report", report.id,
                 {"results": len(results), "method": method})
    db.commit()
    db.refresh(report)
    return report


# --------------------------------------------------------------------------- PDF export
def summary_pdf(report: MedicalReport) -> bytes:
    import pymupdf  # noqa: PLC0415

    e = html.escape
    rows = "".join(
        f"<tr><td>{e(r.parameter)}</td><td>{e(r.value_text)}</td><td>{e(r.unit or '')}</td>"
        f"<td>{e(r.ref_text or '—')}</td><td class='{r.flag}'>{e({'high': 'Higher', 'low': 'Lower', 'normal': 'In range', 'unknown': 'No range'}[r.flag])}</td></tr>"
        for r in report.lab_results
    )
    doc_html = f"""
    <h1>Your lab results summary</h1>
    <p class='meta'>File: {e(report.original_filename)} · read on {report.created_at:%d %b %Y} ·
    {e('scanned image' if report.extraction_method == 'ocr' else 'PDF text')}</p>
    <p>{e(report.summary or '')}</p>
    <table><tr><th>Test</th><th>Your result</th><th>Unit</th><th>Normal range on your report</th><th>Compared with range</th></tr>{rows}</table>
    <p class='note'>Each result is compared only with the normal range printed on your original lab report (or the
    lab's own High/Low mark). This summary is for your information. It is not a diagnosis or medical advice. Please go
    through your results with a doctor.</p>"""
    css = """
    * { font-family: sans-serif; }
    h1 { font-size: 16px; color: #1e3a5f; }
    p { font-size: 10px; line-height: 1.4; }
    .meta, .note { color: #555; }
    table { border-collapse: collapse; width: 100%; font-size: 9px; }
    th { background: #eef2f7; text-align: left; }
    th, td { border: 1px solid #ccd; padding: 3px; }
    .high, .low { color: #b42318; font-weight: bold; }
    """
    story = pymupdf.Story(html=doc_html, user_css=css)
    writer = pymupdf.DocumentWriter(buf := io.BytesIO())
    rect = pymupdf.paper_rect("a4") + (36, 36, -36, -36)
    more = True
    while more:
        dev = writer.begin_page(pymupdf.paper_rect("a4"))
        more, _ = story.place(rect)
        story.draw(dev)
        writer.end_page()
    writer.close()
    return buf.getvalue()
