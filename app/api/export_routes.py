"""Report exports kept separate from the workflow API for clear access control."""
import io
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from openpyxl import Workbook
from reportlab.lib import colors
from reportlab.lib.pagesizes import landscape, letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.core.dependencies import HEAD, require_roles
from app.db.session import get_db
from app.models.models import User
from app.api.routes import report_rows

router = APIRouter(prefix="/api/reports", tags=["report exports"])
COLUMNS = ["Employee", "Planned shifts", "Assigned", "Submitted", "Verified", "Pending", "Overdue", "Submission rate %", "Verified completion %", "Exceptions"]


def safe_spreadsheet_text(value):
    text = str(value or "")
    return "'" + text if text.startswith(("=", "+", "-", "@", "\t", "\r")) else text


def get_report(db: Session, start: date, end: date):
    if end < start or (end - start).days > 366:
        raise HTTPException(422, "Select a valid range of up to one year")
    return report_rows(db, start, end)[0]


@router.get("/tasks.xlsx")
def export_xlsx(start: date, end: date, db: Session = Depends(get_db), _actor: User = Depends(require_roles(HEAD))):
    rows = get_report(db, start, end)
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Office performance"
    sheet.append([f"Performance report: {start} to {end}"])
    sheet.append(COLUMNS)
    for row in rows:
        planned = "; ".join(f"{s['date']} {s['shift']}" for s in row["planned_shifts"])
        sheet.append([safe_spreadsheet_text(row["employee"]), safe_spreadsheet_text(planned), row["assigned"], row["submitted"], row["verified"], row["pending"],
                      row["overdue"], row["submission_rate"], row["verified_completion_rate"], safe_spreadsheet_text("; ".join(row["exceptions"]))])
    sheet.freeze_panes = "A3"
    sheet.auto_filter.ref = sheet.dimensions
    for col in sheet.columns:
        letter = col[0].column_letter
        sheet.column_dimensions[letter].width = min(38, max(15, max(len(str(cell.value or "")) for cell in col) + 2))
    output = io.BytesIO()
    workbook.save(output)
    output.seek(0)
    return StreamingResponse(output, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename=office-performance-{start}-{end}.xlsx"})


@router.get("/tasks.pdf")
def export_pdf(start: date, end: date, db: Session = Depends(get_db), _actor: User = Depends(require_roles(HEAD))):
    rows = get_report(db, start, end)
    output = io.BytesIO()
    document = SimpleDocTemplate(output, pagesize=landscape(letter), title="Office performance report")
    styles = getSampleStyleSheet()
    story = [Paragraph("Office task performance", styles["Title"]), Paragraph(f"{start} to {end}", styles["Normal"]), Spacer(1, 12)]
    data = [["Employee", "Assigned", "Submitted", "Verified", "Pending", "Overdue", "Submit %", "Verified %", "Exceptions"]]
    for row in rows:
        data.append([row["employee"], row["assigned"], row["submitted"], row["verified"], row["pending"], row["overdue"],
                     row["submission_rate"], row["verified_completion_rate"], "; ".join(row["exceptions"]) or "—"])
    table = Table(data, repeatRows=1)
    table.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#173d73")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white), ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cbd5e1")),
        ("FONTSIZE", (0, 0), (-1, -1), 8), ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f1f5f9")])]))
    story.append(table)
    story.append(Spacer(1, 8))
    story.append(Paragraph("Submitted work and verified completion are reported separately. Exceptions reflect recorded leave, absence or reassignment.", styles["Normal"]))
    document.build(story)
    output.seek(0)
    return StreamingResponse(output, media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=office-performance-{start}-{end}.pdf"})
