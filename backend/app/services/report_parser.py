"""Lab-report line parser.

Principles
* Units and reference intervals are copied exactly as printed on the report. Nothing is converted, and no
  "universal" range is ever substituted.
* A value is flagged low/high only by comparing it with the range printed next to it, or using the H/L
  flag printed by the laboratory. Without either, the flag is "unknown".
* Rows are accepted only if they look like a result row: a recognised analyte name, or any name followed by a
  value AND a printed reference range. This keeps out headers, dates, ages, IDs and page numbers.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass

# canonical name -> regex of aliases (matched against the lower-cased printed name)
ANALYTES: dict[str, str] = {
    "Hemoglobin": r"^(haemoglobin|hemoglobin|hb|hgb)\b(?!\s*a1c)",
    "HbA1c": r"(hba1c|a1c|glycated ha?emoglobin|glycosylated ha?emoglobin)",
    "Glucose": r"(glucose|blood sugar|fbs|rbs|ppbs)",
    "Total cholesterol": r"^(total\s+)?cholesterol(,?\s*total)?$|^(serum\s+)?cholesterol\b(?!.*(hdl|ldl|vldl|non))",
    "HDL cholesterol": r"\bhdl\b|high[- ]density",
    "LDL cholesterol": r"\bldl\b|low[- ]density",
    "Non-HDL cholesterol": r"non[- ]?hdl",
    "Triglycerides": r"triglyceride",
    "Creatinine": r"creatinine(?!.*(clearance|ratio))",
    "eGFR": r"\begfr\b|glomerular filtration",
    "Urea / BUN": r"^(blood urea nitrogen|bun|urea)\b",
    "Vitamin D (25-OH)": r"vitamin\s*d|25[- ]?(oh|hydroxy)",
    "Vitamin B12": r"(vitamin\s*b\s*12|cobalamin)",
    "Ferritin": r"ferritin",
    "Iron": r"^(serum\s+)?iron\b",
    "TSH": r"\btsh\b|thyroid stimulating",
    "ALT": r"\b(alt|sgpt)\b|alanine (amino)?transferase",
    "AST": r"\b(ast|sgot)\b|aspartate (amino)?transferase",
    "WBC": r"\b(wbc|white blood cell|leu[ck]ocyte|total leu[ck]ocyte count|tlc)\b",
    "RBC": r"\b(rbc|red blood cell)( count)?\b",
    "Platelets": r"platelet",
    "Hematocrit": r"(ha?ematocrit|\bhct\b|\bpcv\b)",
    "MCV": r"\bmcv\b|mean corpuscular volume",
    "Sodium": r"^(serum\s+)?sodium\b|^na\+?$",
    "Potassium": r"^(serum\s+)?potassium\b|^k\+?$",
    "Calcium": r"^(serum\s+)?calcium\b",
    "Uric acid": r"uric acid",
    "CRP": r"\bcrp\b|c[- ]reactive protein",
}
_ANALYTE_RE = {k: re.compile(v, re.I) for k, v in ANALYTES.items()}
_REJECT_NAME = re.compile(
    r"^(page|age|dob|date|time|sample|specimen|patient|name|id|mrn|uhid|phone|tel|ref(erred)?\s*by|doctor|dr\.?|"
    r"report|collected|received|registered|printed|lab|barcode|accession|sex|gender|bill|invoice|visit|room|bed|"
    r"pin|zip|address|email)\b", re.I)

NUM = r"\d+(?:[.,]\d+)?"
_VALUE = rf"(?P<value>[<>≤≥]?\s?{NUM})"
UNIT = r"(?:x\s?10\^?\d+/[a-zµμ]+|10\^?\d+/[a-zµμ]+|[a-zµμ%][a-zµμ%0-9/\.\^]*(?:/[a-z0-9\.]+)?)"
_ROW = re.compile(
    rf"^\s*(?P<name>[A-Za-z][A-Za-z0-9 ,()/%+\-\.']*?[A-Za-z)%+])\s*[:=]?\s+"
    rf"(?:(?P<preflag>[HL])\s+)?{_VALUE}\s*(?P<flag1>\b(?:H|L|HIGH|LOW)\b|\*)?\s*"
    rf"(?P<unit>{UNIT})?\s*(?P<rest>.*)$", re.I)
_RANGE_BETWEEN = re.compile(rf"(?P<lo>{NUM})\s*(?:-|–|—|to)\s*(?P<hi>{NUM})", re.I)
_RANGE_UPPER = re.compile(rf"(?:<=?|≤|up\s*to|less than|below)\s*(?P<hi>{NUM})", re.I)
_RANGE_LOWER = re.compile(rf"(?:>=?|≥|more than|greater than|above)\s*(?P<lo>{NUM})", re.I)
_FLAG_TAIL = re.compile(r"(?:^|\s)(H|L|HIGH|LOW|\*)\s*$", re.I)


@dataclass
class LabResult:
    parameter: str           # canonical name when recognised, otherwise the printed name
    printed_name: str
    value_text: str
    value_numeric: float | None
    unit: str | None
    ref_low: float | None
    ref_high: float | None
    ref_text: str | None
    flag: str                 # low | high | normal | unknown
    flag_source: str          # reference_range | lab_flag | none
    recognised: bool

    def as_dict(self) -> dict:
        return asdict(self)


def _num(s: str | None) -> float | None:
    if s is None:
        return None
    try:
        return float(s.replace(",", "."))
    except ValueError:
        return None


def canonical(name: str) -> str | None:
    n = re.sub(r"\s+", " ", name.lower()).strip(" :.-")
    for canon, rx in _ANALYTE_RE.items():
        if rx.search(n):
            return canon
    return None


def parse_range(text: str) -> tuple[float | None, float | None, str | None]:
    t = text.strip()
    if not t:
        return None, None, None
    m = _RANGE_BETWEEN.search(t)
    if m:
        lo, hi = _num(m.group("lo")), _num(m.group("hi"))
        if lo is not None and hi is not None and lo <= hi:
            return lo, hi, m.group(0).strip()
    m = _RANGE_UPPER.search(t)
    if m:
        return None, _num(m.group("hi")), m.group(0).strip()
    m = _RANGE_LOWER.search(t)
    if m:
        return _num(m.group("lo")), None, m.group(0).strip()
    return None, None, None


def _flag(value: float | None, lo: float | None, hi: float | None, printed: str | None, value_text: str) -> tuple[str, str]:
    qualified = value_text.strip()[:1] in "<>≤≥"
    if value is not None and not qualified and (lo is not None or hi is not None):
        if lo is not None and value < lo:
            return "low", "reference_range"
        if hi is not None and value > hi:
            return "high", "reference_range"
        return "normal", "reference_range"
    if printed:
        p = printed.upper()
        if p in ("H", "HIGH"):
            return "high", "lab_flag"
        if p in ("L", "LOW"):
            return "low", "lab_flag"
    return "unknown", "none"


def parse_line(line: str) -> LabResult | None:
    line = line.replace("\t", " ").strip()
    if len(line) < 4 or len(line) > 200:
        return None
    m = _ROW.match(line)
    if not m:
        return None
    name = m.group("name").strip(" .:-")
    if _REJECT_NAME.match(name) or len(name) < 2:
        return None
    rest = (m.group("rest") or "").strip()
    unit = m.group("unit")
    # a "unit" that is actually the start of a range word, e.g. "to", is not a unit
    if unit and unit.lower() in {"to", "up", "less", "more", "below", "above", "ref", "range", "normal", "h", "l", "high", "low"}:
        rest = f"{unit} {rest}".strip()
        unit = None
    lo, hi, ref_text = parse_range(rest)
    printed_flag = m.group("preflag") or m.group("flag1")
    if not printed_flag:
        t = _FLAG_TAIL.search(rest)
        printed_flag = t.group(1) if t else None
    canon = canonical(name)
    if canon is None and ref_text is None:
        return None           # unknown name and no printed range: too ambiguous to keep
    value_text = m.group("value").replace(" ", "")
    value = _num(value_text.lstrip("<>≤≥"))
    flag, source = _flag(value, lo, hi, printed_flag, value_text)
    return LabResult(
        parameter=canon or name, printed_name=name, value_text=value_text, value_numeric=value,
        unit=unit, ref_low=lo, ref_high=hi, ref_text=ref_text, flag=flag, flag_source=source,
        recognised=canon is not None,
    )


def parse_text(text: str) -> list[LabResult]:
    out, seen = [], set()
    for raw in text.splitlines():
        r = parse_line(raw)
        if r is None:
            continue
        key = (r.parameter.lower(), r.value_text, r.unit)
        if key in seen:
            continue
        seen.add(key)
        out.append(r)
    return out
