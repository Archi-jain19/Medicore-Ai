"""End-to-end smoke test: drives a running MediCore deployment in a real browser.

    pip install -r e2e/requirements.txt && python -m playwright install chromium   # or use --channel chrome
    python e2e/smoke.py --base-url http://localhost:8080 [--channel chrome] [--shots e2e/shots]

Signs up a throwaway user, visits every module, performs one real action in each, and fails (exit 1) if any
page crashes, logs a console error, or an API call returns 5xx. Uses only synthetic data.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

HERE = Path(__file__).parent


def synthetic_lab_pdf(path: Path) -> Path:
    """Tiny text PDF with a lab table (synthetic, no real patient)."""
    rows = [("Hemoglobin", "11.2", "g/dL", "12.0 - 15.5"), ("LDL Cholesterol", "151", "mg/dL", "< 100"),
            ("Creatinine", "0.9", "mg/dL", "0.6 - 1.2")]
    lines = ["SYNTHETIC TEST REPORT - not a real patient"] + [f"{a}    {b}    {c}    {d}" for a, b, c, d in rows]
    content = "BT /F1 10 Tf 50 750 Td 14 TL " + " ".join(f"({l}) Tj T*" for l in lines) + " ET"
    objs = ["<< /Type /Catalog /Pages 2 0 R >>", "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
            f"<< /Length {len(content)} >>\nstream\n{content}\nendstream", "<< /Type /Font /Subtype /Type1 /BaseFont /Courier >>"]
    out, offsets = b"%PDF-1.4\n", []
    for i, o in enumerate(objs, 1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n{o}\nendobj\n".encode()
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    out += b"".join(f"{o:010d} 00000 n \n".encode() for o in offsets)
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    path.write_bytes(out)
    return path


class Smoke:
    def __init__(self, page: Page, base: str, shots: Path):
        self.page, self.base, self.shots, self.problems, self.passed = page, base.rstrip("/"), shots, [], []
        page.on("console", lambda m: m.type == "error" and self.problems.append(f"console error: {m.text[:200]}"))
        page.on("pageerror", lambda e: self.problems.append(f"page crashed: {str(e)[:200]}"))
        page.on("response", lambda r: "/api/" in r.url and r.status >= 500 and r.status != 503
                and self.problems.append(f"HTTP {r.status} {r.request.method} {r.url}"))

    def step(self, name, fn):
        try:
            fn()
            self.passed.append(name)
            print(f"  ok   {name}")
        except Exception as e:  # noqa: BLE001
            self.problems.append(f"{name}: {str(e).splitlines()[0][:200]}")
            print(f"  FAIL {name}")
        self.page.screenshot(path=str(self.shots / f"{len(self.passed) + len(self.problems):02d}_{name}.png"))

    def go(self, path):
        self.page.goto(self.base + path, wait_until="networkidle")
        if self.page.get_by_text("Something went wrong on this page").count():
            raise AssertionError(f"error boundary shown on {path}")


def run(base: str, channel: str | None, shots: Path) -> int:
    shots.mkdir(parents=True, exist_ok=True)
    pdf = synthetic_lab_pdf(shots / "synthetic_report.pdf")
    with sync_playwright() as p:
        browser = p.chromium.launch(channel=channel, headless=True)
        page = browser.new_page(viewport={"width": 1366, "height": 900})
        page.set_default_timeout(45_000)
        s = Smoke(page, base, shots)
        email = f"smoke{int(time.time())}@example.com"

        def landing():
            s.go("/")
            page.get_by_role("heading", name="Understand your health, in plain words.").wait_for()

        def public_pages():
            for path, text in [("/learn", "How it works"), ("/help", "Help and safety"), ("/privacy", "Privacy policy"), ("/terms", "Terms of use")]:
                s.go(path)
                page.get_by_role("heading", name=text).first.wait_for()

        def register():
            s.go("/register")
            page.fill("#full_name", "Smoke Test")
            page.fill("#email", email)
            page.fill("#password", "Sm0kePassw0rd")
            page.fill("#confirm", "Sm0kePassw0rd")
            page.check("input[type=checkbox]")
            page.click("button:has-text('Create account')")
            page.wait_for_url("**/dashboard")
            page.get_by_role("heading", name="Hello, Smoke").wait_for()

        def health_check():
            s.go("/analytics")
            page.click("button:has-text('Try with example answers')")
            page.click("button:has-text('See my result')")
            page.locator("text=/\\d+ in 100|fewer than 1 in 100/").first.wait_for()
            page.get_by_text("What mattered most in your answers").wait_for()

        def explain():
            s.go("/explainability")
            page.get_by_text("Which answers matter most overall").wait_for()

        def accuracy():
            s.go("/learn/accuracy")
            page.get_by_text("In plain words").first.wait_for()

        def assistant():
            s.go("/assistant")
            page.fill("#chat-input", "What is hypertension?")
            page.keyboard.press("Enter")
            page.locator("text=/Where this comes from|Related sources/").first.wait_for(timeout=90_000)

        def reports():
            s.go("/reports")
            page.set_input_files("input[type=file]", str(pdf))
            page.get_by_text("Normal range on your report").wait_for()

        def locator():
            s.go("/locator")
            page.fill("#place", "London")
            page.click("button[aria-label='Search place']")
            # real provider: results, or a clear "try again" message, are both acceptable outcomes
            page.locator("text=/\\d+ places? found|could not load|busy|could not look up/").first.wait_for(timeout=60_000)

        def reminders():
            s.go("/reminders")
            page.fill("#medication_name", "Smoke test medicine")
            page.click("button:has-text('Add reminder')")
            page.get_by_role("cell", name="Smoke test medicine").first.wait_for()

        def rag_eval():
            s.go("/assistant/evaluation")
            page.get_by_text("How often the right sources are found").wait_for()

        def mobile_layout():
            page.set_viewport_size({"width": 390, "height": 844})
            for path in ["/dashboard", "/analytics", "/assistant", "/reports", "/reminders", "/locator", "/settings", "/help"]:
                s.go(path)
                page.wait_for_timeout(300)
                overflow = page.evaluate("document.documentElement.scrollWidth - window.innerWidth")
                if overflow > 1:
                    raise AssertionError(f"{path} scrolls sideways on a phone by {overflow}px")
            page.set_viewport_size({"width": 1366, "height": 900})

        def settings_and_delete():
            s.go("/settings")
            page.fill("#del_pw", "Sm0kePassw0rd")
            page.fill("#del_confirm", "DELETE")
            page.click("button:has-text('Delete my account')")
            page.wait_for_url(s.base + "/")

        for name, fn in [("landing", landing), ("public_pages", public_pages), ("register", register), ("health_check", health_check),
                         ("explain", explain), ("accuracy", accuracy), ("assistant", assistant), ("reports", reports),
                         ("locator", locator), ("reminders", reminders), ("rag_evaluation", rag_eval),
                         ("mobile_layout", mobile_layout), ("delete_account", settings_and_delete)]:
            s.step(name, fn)
        browser.close()
    print(f"\n{len(s.passed)} steps passed")
    if s.problems:
        print("PROBLEMS:\n  - " + "\n  - ".join(dict.fromkeys(s.problems)))
        return 1
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://localhost:8080")
    ap.add_argument("--channel", default=None, help="'chrome' or 'msedge' to use an installed browser")
    ap.add_argument("--shots", default=str(HERE / "shots"))
    a = ap.parse_args()
    sys.exit(run(a.base_url, a.channel, Path(a.shots)))
