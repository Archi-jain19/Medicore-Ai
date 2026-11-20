from datetime import datetime

from pydantic import BaseModel


class LabResultOut(BaseModel):
    id: int
    parameter: str
    printed_name: str | None
    value_text: str
    value_numeric: float | None
    unit: str | None
    ref_low: float | None
    ref_high: float | None
    ref_text: str | None
    flag: str
    flag_source: str
    explanation: dict


class ReportListItem(BaseModel):
    id: int
    original_filename: str
    mime_type: str
    size_bytes: int
    extraction_method: str | None
    page_count: int | None
    status: str
    created_at: datetime
    result_count: int
    flagged_count: int


class ReportDetail(ReportListItem):
    summary: str | None
    sha256: str
    results: list[LabResultOut]
    disclaimer: str
