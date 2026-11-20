from fastapi import APIRouter, File, Request, UploadFile, status
from fastapi.responses import Response
from sqlalchemy import select

from app.api.deps import CurrentUser, DbSession
from app.core.config import get_settings
from app.core.errors import AppError, NotFoundError
from app.core.rate_limit import limiter
from app.models import MedicalReport
from app.schemas.reports import LabResultOut, ReportDetail, ReportListItem
from app.services import report_service
from app.services.activity import log_activity

router = APIRouter(prefix="/reports", tags=["reports"])
DISCLAIMER = ("Each result is compared only with the normal range printed on your own lab report. This is for your "
              "information and is not a diagnosis. Please go through your results with a doctor.")


def _owned(db, user, report_id: int) -> MedicalReport:
    r = db.scalar(select(MedicalReport).where(MedicalReport.id == report_id, MedicalReport.user_id == user.id))
    if r is None:
        raise NotFoundError("We could not find that report.")
    return r


def _item(r: MedicalReport) -> dict:
    return {
        "id": r.id, "original_filename": r.original_filename, "mime_type": r.mime_type, "size_bytes": r.size_bytes,
        "extraction_method": r.extraction_method, "page_count": r.page_count, "status": r.status,
        "created_at": r.created_at, "result_count": len(r.lab_results),
        "flagged_count": sum(x.flag in ("high", "low") for x in r.lab_results),
    }


def _detail(r: MedicalReport) -> ReportDetail:
    results = [LabResultOut(id=x.id, parameter=x.parameter, printed_name=x.printed_name, value_text=x.value_text,
                            value_numeric=x.value_numeric, unit=x.unit, ref_low=x.ref_low, ref_high=x.ref_high,
                            ref_text=x.ref_text, flag=x.flag, flag_source=x.flag_source,
                            explanation=report_service.explain(x)) for x in r.lab_results]
    return ReportDetail(**_item(r), summary=r.summary, sha256=r.sha256, results=results, disclaimer=DISCLAIMER)


@router.post("/upload", response_model=ReportDetail, status_code=status.HTTP_201_CREATED)
@limiter.limit("10/minute")
def upload(request: Request, db: DbSession, user: CurrentUser, file: UploadFile = File(...)):
    """Upload a PDF/PNG/JPG lab report. The file is analysed in memory and not stored."""
    limit = get_settings().max_upload_mb * 1024 * 1024
    data = file.file.read(limit + 1)
    if len(data) > limit:
        raise AppError(f"That file is too big (the limit is {get_settings().max_upload_mb} MB). Try a smaller file or a lower-resolution photo.", code="file_too_large",
                       status_code=413)
    report = report_service.analyse_upload(db, user, file.filename or "report", file.content_type, data)
    return _detail(report)


@router.get("", response_model=list[ReportListItem])
def list_reports(db: DbSession, user: CurrentUser):
    rows = db.scalars(select(MedicalReport).where(MedicalReport.user_id == user.id)
                      .order_by(MedicalReport.created_at.desc()))
    return [_item(r) for r in rows]


@router.get("/{report_id}", response_model=ReportDetail)
def get_report(report_id: int, db: DbSession, user: CurrentUser):
    return _detail(_owned(db, user, report_id))


@router.get("/{report_id}/summary.pdf")
def download_summary(report_id: int, db: DbSession, user: CurrentUser):
    r = _owned(db, user, report_id)
    pdf = report_service.summary_pdf(r)
    stem = r.original_filename.rsplit(".", 1)[0][:60]
    return Response(pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="medicore-summary-{r.id}-{stem}.pdf"'})


@router.delete("/{report_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_report(report_id: int, db: DbSession, user: CurrentUser):
    r = _owned(db, user, report_id)
    db.delete(r)
    log_activity(db, user.id, "report.delete", "medical_report", report_id)
    db.commit()
