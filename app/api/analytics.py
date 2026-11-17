"""Management-only grouped performance summaries for charts and comparisons."""
from collections import defaultdict
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.core.dependencies import HEAD, require_roles
from app.db.session import get_db
from app.models.models import Department, Shift, Task, User

router = APIRouter(prefix="/api/reports", tags=["management analytics"])


def summarize(tasks, key, labels):
    groups = defaultdict(list)
    for task in tasks:
        groups[key(task)].append(task)
    rows = []
    for group_key, group in groups.items():
        group = [task for task in group if task.status != "Cancelled"]
        assigned = len(group)
        if not assigned:
            continue
        submitted = sum(t.status in {"Submitted", "Resubmitted", "Verified", "Correction Requested", "Rejected"} for t in group)
        verified = sum(t.status == "Verified" for t in group)
        rows.append({"key": str(group_key), "label": labels.get(group_key, str(group_key) if group_key is not None else "Not specified"), "assigned": assigned,
            "submitted": submitted, "verified": verified, "pending": assigned - verified,
            "overdue": sum(t.deadline < datetime.utcnow() and t.status not in {"Verified", "Cancelled"} for t in group),
            "submission_rate": round(submitted * 100 / assigned, 1) if assigned else 0,
            "verified_rate": round(verified * 100 / assigned, 1) if assigned else 0})
    return sorted(rows, key=lambda x: x["assigned"], reverse=True)


def period_key(value: date, unit: str):
    if unit == "day": return value.isoformat()
    if unit == "month": return value.strftime("%Y-%m")
    monday = value - timedelta(days=value.weekday())
    return monday.isoformat()


@router.get("/analytics")
def analytics(start: date, end: date, db: Session = Depends(get_db), _actor: User = Depends(require_roles(HEAD))):
    if end < start or (end - start).days > 366:
        from fastapi import HTTPException
        raise HTTPException(422, "Select a valid date range of at most one year")
    tasks = db.scalars(select(Task).where(Task.assignment_date.between(start, end))).all()
    user_labels = {u.id: u.full_name for u in db.scalars(select(User))}
    dept_labels = {d.id: d.name for d in db.scalars(select(Department))}
    shift_labels = {s.id: s.name for s in db.scalars(select(Shift))}
    date_labels = defaultdict(lambda: None)
    for task in tasks:
        date_labels[task.assignment_date] = task.assignment_date.isoformat()
    return {"start": str(start), "end": str(end),
        "by_employee": summarize(tasks, lambda t: t.employee_id, user_labels),
        "by_editor": summarize(tasks, lambda t: t.assigner_id, user_labels),
        "by_department": summarize(tasks, lambda t: t.department_id, dept_labels),
        "by_shift": summarize(tasks, lambda t: t.shift_id, shift_labels),
        "by_day": summarize(tasks, lambda t: period_key(t.assignment_date, "day"), {}),
        "by_week": summarize(tasks, lambda t: period_key(t.assignment_date, "week"), {}),
        "by_month": summarize(tasks, lambda t: period_key(t.assignment_date, "month"), {})}
