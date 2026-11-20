"""Report analyzer tests. All fixtures are SYNTHETIC lab reports generated in the test (no real patient data)."""
import io

import pymupdf
import pytest

from app.services import report_service
from app.services.report_parser import parse_line, parse_text

TABLE = [  # (test, value, unit, printed reference range)
    ("Hemoglobin", "11.2", "g/dL", "12.0 - 15.5"),
    ("Glucose, Fasting", "92", "mg/dL", "70 - 99"),
    ("Total Cholesterol", "232", "mg/dL", "< 200"),
    ("HDL Cholesterol", "38", "mg/dL", "> 40"),
    ("LDL Cholesterol", "151", "mg/dL", "< 100"),
    ("Creatinine", "0.9", "mg/dL", "0.6 - 1.2"),
    ("Vitamin D, 25-OH", "19", "ng/mL", "30 - 100"),
]


def make_table_pdf(rows=TABLE, header=True) -> bytes:
    """Multi-column layout: every cell is a separate text object, like real lab PDFs."""
    doc = pymupdf.open()
    page = doc.new_page()
    y = 60
    page.insert_text((50, y), "SYNTHETIC TEST REPORT - not a real patient", fontsize=10)
    y += 20
    page.insert_text((50, y), "Patient ID 000000   Age 45   Page 1 of 1", fontsize=9)
    y += 25
    if header:
        for x, h in zip((50, 230, 300, 380), ("Test", "Result", "Unit", "Reference range")):
            page.insert_text((x, y), h, fontsize=9)
        y += 18
    for name, val, unit, ref in rows:
        for x, cell in zip((50, 230, 300, 380), (name, val, unit, ref)):
            page.insert_text((x, y), cell, fontsize=9)
        y += 16
    return doc.tobytes()


def make_image_only_pdf() -> bytes:
    doc = pymupdf.open()
    page = doc.new_page()
    pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 200, 100), False)
    pix.clear_with(255)
    page.insert_image(pymupdf.Rect(50, 50, 250, 150), pixmap=pix)
    return doc.tobytes()


def png_bytes() -> bytes:
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (60, 30), "white").save(buf, format="PNG")
    return buf.getvalue()


def upload(client, headers, data, name="report.pdf", ctype="application/pdf"):
    return client.post("/api/reports/upload", headers=headers, files={"file": (name, data, ctype)})


# ------------------------------------------------------------------ parser
def test_parser_preserves_printed_units_and_ranges():
    r = parse_line("Vitamin D, 25-OH 19 ng/mL 30 - 100")
    assert (r.parameter, r.value_numeric, r.unit, r.ref_text, r.ref_low, r.ref_high, r.flag) == (
        "Vitamin D (25-OH)", 19.0, "ng/mL", "30 - 100", 30.0, 100.0, "low")
    # mmol/L is kept as printed; nothing is converted
    r = parse_line("Glucose 5.4 mmol/L 3.9 - 5.5")
    assert r.unit == "mmol/L" and r.flag == "normal"


def test_parser_never_assumes_a_range():
    r = parse_line("Hemoglobin 9.1 g/dL")
    assert r.flag == "unknown" and r.ref_text is None and r.flag_source == "none"


def test_parser_uses_lab_flag_when_no_range():
    r = parse_line("Ferritin 8 ng/mL L")
    assert r.flag == "low" and r.flag_source == "lab_flag"


def test_parser_one_sided_ranges_and_qualified_values():
    assert parse_line("LDL Cholesterol 151 mg/dL < 100").flag == "high"
    assert parse_line("HDL Cholesterol 38 mg/dL > 40").flag == "low"
    assert parse_line("eGFR 85 mL/min/1.73m2 >60").flag == "normal"
    # "<0.5" is not a precise number: do not claim in/out of range
    assert parse_line("CRP <0.5 mg/L 0 - 5").flag == "unknown"


def test_parser_rejects_non_result_rows():
    text = "Age 45 Years\nPage 1 of 2\nSample collected 12/03/2026 08:30\nPatient ID 123456\nRef by Dr. 12"
    assert parse_text(text) == []


# ------------------------------------------------------------------ extraction
def test_pdf_table_rows_are_reconstructed():
    text, method, pages = report_service.extract_text(make_table_pdf(), "application/pdf")
    assert method == "text" and pages == 1
    got = {r.parameter: r for r in parse_text(text)}
    assert set(got) == {"Hemoglobin", "Glucose", "Total cholesterol", "HDL cholesterol", "LDL cholesterol",
                        "Creatinine", "Vitamin D (25-OH)"}
    assert got["Hemoglobin"].flag == "low" and got["Glucose"].flag == "normal"
    assert got["Total cholesterol"].ref_text == "< 200"


def test_scanned_pdf_uses_ocr_or_reports_unavailable(monkeypatch):
    report_service.ocr_available.cache_clear()
    if report_service.ocr_available():
        text, method, _ = report_service.extract_text(make_image_only_pdf(), "application/pdf")
        assert method == "ocr"
    else:
        with pytest.raises(report_service.ServiceUnavailableError) as e:
            report_service.extract_text(make_image_only_pdf(), "application/pdf")
        assert e.value.code == "ocr_unavailable"


# ------------------------------------------------------------------ API
def test_upload_analyse_list_detail_download_delete(client, auth_headers, monkeypatch):
    monkeypatch.setattr(report_service, "_learn_more", lambda p: None)  # keep test independent of the KB
    h = auth_headers()
    r = upload(client, h, make_table_pdf())
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["status"] == "processed" and body["extraction_method"] == "text"
    assert body["result_count"] == 7 and body["flagged_count"] == 5
    hb = next(x for x in body["results"] if x["parameter"] == "Hemoglobin")
    assert hb["unit"] == "g/dL" and hb["ref_text"] == "12.0 - 15.5" and hb["flag"] == "low"
    assert "lower than the normal range printed on your lab report" in hb["explanation"]["status"]
    assert "(12.0 - 15.5 g/dL)" in hb["explanation"]["status"]          # the report's own range and unit, unchanged
    assert "oxygen" in hb["explanation"]["what_it_measures"]
    assert "not a diagnosis" in body["summary"]

    listed = client.get("/api/reports", headers=h).json()
    assert [x["id"] for x in listed] == [body["id"]]
    pdf = client.get(f"/api/reports/{body['id']}/summary.pdf", headers=h)
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
    assert "attachment" in pdf.headers["content-disposition"]
    assert client.delete(f"/api/reports/{body['id']}", headers=h).status_code == 204
    assert client.get("/api/reports", headers=h).json() == []


def test_reports_are_private(client, auth_headers, monkeypatch):
    monkeypatch.setattr(report_service, "_learn_more", lambda p: None)
    a, b = auth_headers("a@example.com"), auth_headers("b@example.com")
    rid = upload(client, a, make_table_pdf()).json()["id"]
    assert client.get(f"/api/reports/{rid}", headers=b).status_code == 404
    assert client.get(f"/api/reports/{rid}/summary.pdf", headers=b).status_code == 404
    assert client.delete(f"/api/reports/{rid}", headers=b).status_code == 404
    assert client.get("/api/reports", headers=b).json() == []


def test_upload_validation(client, auth_headers, monkeypatch):
    h = auth_headers()
    assert client.post("/api/reports/upload", files={"file": ("r.pdf", make_table_pdf(), "application/pdf")}).status_code == 401
    # wrong type / spoofed extension / empty
    assert upload(client, h, b"hello world", "notes.txt", "text/plain").status_code == 415
    assert upload(client, h, png_bytes(), "fake.pdf", "application/pdf").status_code == 415
    assert upload(client, h, b"", "empty.pdf").status_code == 400
    # size limit
    from app.core import config
    monkeypatch.setattr(config.get_settings(), "max_upload_mb", 0)
    r = upload(client, h, make_table_pdf())
    assert r.status_code == 413 and r.json()["error"]["code"] == "file_too_large"


def test_encrypted_pdf_rejected(client, auth_headers):
    doc = pymupdf.open()
    doc.new_page().insert_text((50, 50), "Hemoglobin 13 g/dL 12 - 15")
    data = doc.tobytes(encryption=pymupdf.PDF_ENCRYPT_AES_256, user_pw="secret", owner_pw="secret")
    r = upload(client, auth_headers(), data)
    assert r.status_code == 400 and r.json()["error"]["code"] == "encrypted_pdf"


def test_pdf_without_lab_values(client, auth_headers):
    doc = pymupdf.open()
    doc.new_page().insert_text((50, 50), "This letter contains no laboratory results at all, only prose text.")
    r = upload(client, auth_headers(), doc.tobytes())
    assert r.status_code == 201 and r.json()["status"] == "no_results" and r.json()["results"] == []
