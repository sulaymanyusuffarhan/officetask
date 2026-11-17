from __future__ import annotations

import csv
import io
import json
import secrets
from collections import defaultdict, deque
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from threading import Lock
from time import monotonic
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.core.config import get_settings
from app.core.dependencies import ADMIN, EDITOR, HEAD, PLANNER, SHIFT_LEADER, STAFF, current_user, require_roles
from app.core.roles import ROLE_NAMES
from app.core.security import hash_password, verify_password
from app.db.session import get_db
from app.models.models import (Attachment, AttendanceRecord, AuditLog, Department, Role, Shift, ShiftReport,
    Submission, Task, TaskHistory, Timetable, TimetableAssignment, User, Verification)
from app.schemas import (AssignmentCreate, AssignmentUpdate, AttendanceIn, DepartmentCreate, ShiftCreate, ShiftReportIn,
    TaskCreate, TaskUpdate, TimetableCreate, UserCreate, UserUpdate, VerificationIn)
from app.services.audit import record_audit

router = APIRouter(prefix="/api")
settings = get_settings()
ROLES = (HEAD, PLANNER, EDITOR, SHIFT_LEADER, STAFF, ADMIN)
BUSINESS_MANAGERS = (HEAD, EDITOR)
ALLOWED_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg", ".docx", ".xlsx"}
ALLOWED_MIME = {".pdf": "application/pdf", ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"}
PRIORITIES = {"Low", "Normal", "High", "Urgent"}
_login_failures: dict[str, deque[float]] = defaultdict(deque)
_login_lock = Lock()


def utc_naive(value: datetime) -> datetime:
    """Store deadline timestamps consistently as naive UTC in the database."""
    return value.astimezone(timezone.utc).replace(tzinfo=None) if value.tzinfo else value


def audit_commit(db: Session, actor: User, action: str, entity: str, entity_id: object, details: dict | None = None):
    record_audit(db, actor, action, entity, entity_id, details)
    db.commit()


def user_json(user: User) -> dict:
    return {"id": user.id, "username": user.username, "full_name": user.full_name,
        "role_id": user.role_id, "role": ROLE_NAMES.get(user.role_id, user.role_id),
        "department_id": user.department_id, "active": user.active}


def task_json(task: Task) -> dict:
    status = task.status
    if status not in {"Verified", "Cancelled", "Rejected", "Correction Requested", "Submitted", "Resubmitted", "Under Review"} and task.deadline < datetime.utcnow():
        status = "Overdue"
    return {"id": task.id, "reference": task.reference, "title": task.title, "description": task.description,
        "instructions": task.instructions, "employee_id": task.employee_id,
        "employee": task.employee.full_name if task.employee else None, "assigner_id": task.assigner_id,
        "assigner": task.assigner.full_name if task.assigner else None, "department_id": task.department_id,
        "shift_id": task.shift_id, "assignment_date": str(task.assignment_date), "start_date": str(task.start_date),
        "deadline": task.deadline.replace(tzinfo=timezone.utc).isoformat(), "priority": task.priority, "status": status}


@router.get("/auth/csrf")
def issue_login_csrf(request: Request):
    token = request.session.get("csrf_token") or secrets.token_urlsafe(32)
    request.session["csrf_token"] = token
    return {"csrf_token": token}


@router.post("/auth/login")
def login(request: Request, username: Annotated[str, Form()], password: Annotated[str, Form()], db: Session = Depends(get_db)):
    peer, now = (request.client.host if request.client else "unknown"), monotonic()
    with _login_lock:
        attempts = _login_failures[peer]
        while attempts and now - attempts[0] > 900:
            attempts.popleft()
        if len(attempts) >= 5:
            raise HTTPException(429, "Too many failed sign-in attempts; try later")
    user = db.scalar(select(User).where(func.lower(User.username) == username.strip().lower()))
    if not user or not user.active or not verify_password(password, user.password_hash):
        with _login_lock:
            _login_failures[peer].append(now)
        record_audit(db, None, "login_failed", "authentication", "anonymous", {"username": username.strip()[:80], "source": peer})
        db.commit()
        raise HTTPException(401, "Invalid username or password")
    with _login_lock:
        _login_failures.pop(peer, None)
    request.session.clear()
    request.session["user_id"] = user.id
    request.session["csrf_token"] = secrets.token_urlsafe(32)
    audit_commit(db, user, "login", "user", user.id)
    return {"user": user_json(user), "csrf_token": request.session["csrf_token"]}


@router.get("/auth/me")
def me(request: Request, actor: User = Depends(current_user)):
    csrf = request.session.get("csrf_token") or secrets.token_urlsafe(32)
    request.session["csrf_token"] = csrf
    return {"user": user_json(actor), "csrf_token": csrf}


@router.post("/auth/logout")
def logout(request: Request, actor: User = Depends(current_user), db: Session = Depends(get_db)):
    record_audit(db, actor, "logout", "user", actor.id)
    db.commit()
    request.session.clear()
    return {"ok": True}


@router.post("/auth/change-password")
def change_password(request: Request, current_password: str = Form(), new_password: str = Form(),
                    db: Session = Depends(get_db), actor: User = Depends(current_user)):
    if len(new_password) < 12:
        raise HTTPException(422, "New password must contain at least 12 characters")
    if not verify_password(current_password, actor.password_hash):
        raise HTTPException(400, "Current password is incorrect")
    actor.password_hash = hash_password(new_password)
    audit_commit(db, actor, "password_changed", "user", actor.id)
    request.session.clear()
    return {"ok": True}


@router.get("/roles")
def list_roles(_actor: User = Depends(current_user)):
    return [{"id": k, "name": v} for k, v in ROLE_NAMES.items()]


@router.get("/people")
def people(db: Session = Depends(get_db), actor: User = Depends(require_roles(HEAD, PLANNER, EDITOR, SHIFT_LEADER, ADMIN))):
    visible = {HEAD, EDITOR, SHIFT_LEADER, STAFF}
    query = select(User).where(User.active.is_(True), User.role_id.in_(visible))
    if actor.role_id == EDITOR:
        scheduled = select(TimetableAssignment.employee_id).join(Timetable).where(Timetable.status == "Published",
            TimetableAssignment.editor_id == actor.id, TimetableAssignment.work_date.between(date.today(), date.today() + timedelta(days=6)))
        query = query.where(User.id.in_(scheduled))
    elif actor.role_id == SHIFT_LEADER:
        scheduled = select(TimetableAssignment.employee_id).join(Timetable).where(Timetable.status == "Published",
            TimetableAssignment.leader_id == actor.id, TimetableAssignment.work_date == date.today())
        query = query.where(User.id.in_(scheduled))
    if actor.role_id == ADMIN:
        query = select(User).where(User.active.is_(True), User.role_id == ADMIN)
    return [user_json(u) for u in db.scalars(query.order_by(User.full_name))]


@router.get("/users")
def list_users(db: Session = Depends(get_db), _actor: User = Depends(require_roles(ADMIN, HEAD))):
    return [user_json(u) for u in db.scalars(select(User).order_by(User.full_name))]


@router.post("/users", status_code=201)
def create_user(body: UserCreate, db: Session = Depends(get_db), actor: User = Depends(require_roles(ADMIN))):
    if not db.get(Role, body.role_id):
        raise HTTPException(422, "Unknown role")
    if body.department_id and not db.get(Department, body.department_id):
        raise HTTPException(422, "Unknown department")
    if db.scalar(select(User).where(func.lower(User.username) == body.username.lower())):
        raise HTTPException(409, "Username already exists")
    user = User(username=body.username, full_name=body.full_name.strip(), password_hash=hash_password(body.password),
        role_id=body.role_id, department_id=body.department_id)
    db.add(user); db.flush()
    audit_commit(db, actor, "user_created", "user", user.id, {"username": user.username, "role": user.role_id})
    return user_json(user)


@router.patch("/users/{user_id}/active")
def set_user_active(user_id: int, active: bool, db: Session = Depends(get_db), actor: User = Depends(require_roles(ADMIN))):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(404, "User not found")
    user.active = active
    audit_commit(db, actor, "user_active_changed", "user", user.id, {"active": active})
    return user_json(user)


@router.patch("/users/{user_id}")
def update_user(user_id: int, body: UserUpdate, db: Session = Depends(get_db), actor: User = Depends(require_roles(ADMIN))):
    target = db.get(User, user_id)
    if not target:
        raise HTTPException(404, "User not found")
    if target.id == actor.id and body.active is False:
        raise HTTPException(409, "You cannot disable your own administrator account")
    changes = {}
    for field in ("full_name", "role_id", "department_id", "active"):
        value = getattr(body, field)
        if value is None:
            continue
        if field == "role_id" and not db.get(Role, value):
            raise HTTPException(422, "Unknown role")
        if field == "department_id" and not db.get(Department, value):
            raise HTTPException(422, "Unknown department")
        old = getattr(target, field)
        if old != value:
            changes[field] = {"previous": old, "new": value}
            setattr(target, field, value)
    if not changes:
        raise HTTPException(422, "No changes supplied")
    audit_commit(db, actor, "user_updated", "user", target.id, {"changes": changes})
    return user_json(target)


@router.post("/users/{user_id}/reset-password")
def reset_user_password(user_id: int, password: str = Form(min_length=12), db: Session = Depends(get_db), actor: User = Depends(require_roles(ADMIN))):
    target = db.get(User, user_id)
    if not target:
        raise HTTPException(404, "User not found")
    target.password_hash = hash_password(password)
    audit_commit(db, actor, "user_password_reset", "user", target.id)
    return {"ok": True}


@router.get("/departments")
def list_departments(db: Session = Depends(get_db), _actor: User = Depends(current_user)):
    return [{"id": x.id, "name": x.name, "active": x.active} for x in db.scalars(select(Department).order_by(Department.name))]


@router.post("/departments", status_code=201)
def add_department(body: DepartmentCreate, db: Session = Depends(get_db), actor: User = Depends(require_roles(ADMIN))):
    item = Department(name=body.name.strip()); db.add(item); db.flush()
    audit_commit(db, actor, "department_created", "department", item.id, {"name": item.name})
    return {"id": item.id, "name": item.name}


@router.get("/shifts")
def list_shifts(db: Session = Depends(get_db), _actor: User = Depends(current_user)):
    return [{"id": x.id, "name": x.name, "start_time": x.start_time, "end_time": x.end_time, "active": x.active}
        for x in db.scalars(select(Shift).order_by(Shift.start_time))]


@router.post("/shifts", status_code=201)
def add_shift(body: ShiftCreate, db: Session = Depends(get_db), actor: User = Depends(require_roles(ADMIN))):
    if body.end_time <= body.start_time:
        raise HTTPException(422, "Shift end must be later than shift start; overnight shifts are not supported")
    item = Shift(name=body.name.strip(), start_time=body.start_time, end_time=body.end_time); db.add(item); db.flush()
    audit_commit(db, actor, "shift_created", "shift", item.id, {"name": item.name})
    return {"id": item.id, "name": item.name, "start_time": item.start_time, "end_time": item.end_time}


def get_timetable(db: Session, item_id: int) -> Timetable:
    item = db.scalar(select(Timetable).options(joinedload(Timetable.assignments).joinedload(TimetableAssignment.shift),
        joinedload(Timetable.assignments).joinedload(TimetableAssignment.employee),
        joinedload(Timetable.assignments).joinedload(TimetableAssignment.leader),
        joinedload(Timetable.assignments).joinedload(TimetableAssignment.editor)).where(Timetable.id == item_id))
    if not item:
        raise HTTPException(404, "Timetable not found")
    return item


def can_edit_timetable(item: Timetable, actor: User):
    if item.status in {"Approved", "Published", "Archived"}:
        raise HTTPException(409, "Timetable is locked; make a new version")
    if actor.role_id == PLANNER and (item.created_by_id != actor.id or item.status not in {"Draft", "Returned for Correction"}):
        raise HTTPException(403, "Planner can only edit their own draft or returned timetable")
    if actor.role_id not in {PLANNER, HEAD}:
        raise HTTPException(403, "Not allowed")


def assignment_json(a: TimetableAssignment):
    return {"id": a.id, "work_date": str(a.work_date), "shift_id": a.shift_id, "shift": a.shift.name if a.shift else "",
        "employee_id": a.employee_id, "employee": a.employee.full_name if a.employee else "",
        "leader_id": a.leader_id, "leader": a.leader.full_name if a.leader else "",
        "editor_id": a.editor_id, "editor": a.editor.full_name if a.editor else "",
        "department_id": a.department_id, "responsibility": a.responsibility}


@router.post("/timetables", status_code=201)
def create_timetable(body: TimetableCreate, db: Session = Depends(get_db), actor: User = Depends(require_roles(PLANNER, HEAD))):
    if body.week_start.weekday() != 0:
        raise HTTPException(422, "week_start must be a Monday")
    version = (db.scalar(select(func.max(Timetable.version)).where(Timetable.week_start == body.week_start)) or 0) + 1
    item = Timetable(week_start=body.week_start, version=version, created_by_id=actor.id); db.add(item); db.flush()
    audit_commit(db, actor, "timetable_created", "timetable", item.id, {"week_start": str(body.week_start), "version": version})
    return {"id": item.id, "week_start": str(item.week_start), "version": version, "status": item.status}


@router.get("/timetables")
def list_timetables(week_start: date | None = None, db: Session = Depends(get_db), actor: User = Depends(current_user)):
    if actor.role_id == ADMIN:
        raise HTTPException(403, "Technical administrators do not receive business planning access")
    query = select(Timetable).options(joinedload(Timetable.assignments).joinedload(TimetableAssignment.shift),
        joinedload(Timetable.assignments).joinedload(TimetableAssignment.employee),
        joinedload(Timetable.assignments).joinedload(TimetableAssignment.leader),
        joinedload(Timetable.assignments).joinedload(TimetableAssignment.editor))
    if week_start:
        query = query.where(Timetable.week_start == week_start)
    if actor.role_id in {STAFF, SHIFT_LEADER, EDITOR}:
        query = query.where(Timetable.status == "Published")
    elif actor.role_id == PLANNER:
        query = query.where((Timetable.created_by_id == actor.id) | (Timetable.status == "Published"))
    result = []
    for item in db.scalars(query.order_by(Timetable.week_start.desc(), Timetable.version.desc())).unique():
        items = item.assignments
        if actor.role_id in {STAFF, SHIFT_LEADER, EDITOR}:
            items = [a for a in items if actor.id in {a.employee_id, a.leader_id, a.editor_id}]
        result.append({"id": item.id, "week_start": str(item.week_start), "week_end": str(item.week_start + timedelta(days=6)),
            "version": item.version, "status": item.status, "approval_comment": item.approval_comment,
            "change_reason": item.change_reason, "assignments": [assignment_json(a) for a in items]})
    return result


def check_assignment_conflict(item: Timetable, body: AssignmentCreate, shift: Shift, skip_id: int | None = None):
    new_people = {body.employee_id, body.leader_id, body.editor_id} - {None}
    for old in item.assignments:
        if old.id == skip_id or old.work_date != body.work_date:
            continue
        old_shift = old.shift
        if shift.start_time < old_shift.end_time and old_shift.start_time < shift.end_time:
            if new_people.intersection({old.employee_id, old.leader_id, old.editor_id} - {None}):
                raise HTTPException(409, "Employee has an overlapping assignment on this date")


def validate_assignment(db: Session, item: Timetable, body: AssignmentCreate, skip_id: int | None = None):
    if not item.week_start <= body.work_date <= item.week_start + timedelta(days=6):
        raise HTTPException(422, "Assignment date must be in the timetable week")
    shift = db.get(Shift, body.shift_id)
    if not shift or not shift.active:
        raise HTTPException(422, "Select an active shift")
    people_ids = {body.employee_id, body.leader_id, body.editor_id} - {None}
    people = db.scalars(select(User).where(User.id.in_(people_ids), User.active.is_(True))).all()
    if len(people) != len(people_ids):
        raise HTTPException(422, "Selected employee, leader or editor is not active")
    check_assignment_conflict(item, body, shift, skip_id)
    return shift


@router.post("/timetables/{item_id}/assignments", status_code=201)
def add_assignment(item_id: int, body: AssignmentCreate, db: Session = Depends(get_db), actor: User = Depends(current_user)):
    item = get_timetable(db, item_id); can_edit_timetable(item, actor)
    validate_assignment(db, item, body)
    assignment = TimetableAssignment(timetable_id=item.id, **body.model_dump()); db.add(assignment); db.flush()
    audit_commit(db, actor, "timetable_assignment_added", "timetable_assignment", assignment.id,
        {"employee_id": body.employee_id, "date": str(body.work_date), "shift_id": body.shift_id})
    return {"id": assignment.id, "timetable_id": item.id}


@router.put("/timetables/{item_id}/assignments/{assignment_id}")
def update_assignment(item_id: int, assignment_id: int, body: AssignmentUpdate,
    db: Session = Depends(get_db), actor: User = Depends(current_user)):
    item = get_timetable(db, item_id); can_edit_timetable(item, actor)
    assignment = db.get(TimetableAssignment, assignment_id)
    if not assignment or assignment.timetable_id != item.id:
        raise HTTPException(404, "Assignment not found")
    validate_assignment(db, item, body, skip_id=assignment.id)
    previous = {"work_date": str(assignment.work_date), "employee_id": assignment.employee_id,
        "shift_id": assignment.shift_id, "leader_id": assignment.leader_id, "editor_id": assignment.editor_id,
        "responsibility": assignment.responsibility}
    assignment_data = body.model_dump(exclude={"reason"})
    for key, value in assignment_data.items():
        setattr(assignment, key, value)
    audit_commit(db, actor, "timetable_assignment_changed", "timetable_assignment", assignment.id,
        {"reason": body.reason, "previous": previous, "new": body.model_dump(mode="json", exclude={"reason"})})
    return {"id": assignment.id, "updated": True}


@router.delete("/timetables/{item_id}/assignments/{assignment_id}")
def remove_assignment(item_id: int, assignment_id: int, db: Session = Depends(get_db), actor: User = Depends(current_user)):
    item = get_timetable(db, item_id); can_edit_timetable(item, actor)
    assignment = db.get(TimetableAssignment, assignment_id)
    if not assignment or assignment.timetable_id != item.id:
        raise HTTPException(404, "Assignment not found")
    old = {"date": str(assignment.work_date), "employee_id": assignment.employee_id, "shift_id": assignment.shift_id}
    db.delete(assignment); audit_commit(db, actor, "timetable_assignment_removed", "timetable_assignment", assignment_id, old)
    return {"ok": True}


def clone_timetable(source: Timetable, week_start: date, actor: User, db: Session, change_reason: str | None = None):
    version = (db.scalar(select(func.max(Timetable.version)).where(Timetable.week_start == week_start)) or 0) + 1
    target = Timetable(week_start=week_start, version=version, created_by_id=actor.id, parent_id=source.id, change_reason=change_reason)
    db.add(target); db.flush()
    offset = (week_start - source.week_start).days
    for a in source.assignments:
        target.assignments.append(TimetableAssignment(work_date=a.work_date + timedelta(days=offset), shift_id=a.shift_id,
            employee_id=a.employee_id, leader_id=a.leader_id, editor_id=a.editor_id,
            department_id=a.department_id, responsibility=a.responsibility))
    db.flush()
    return target


@router.post("/timetables/{item_id}/copy", status_code=201)
def copy_timetable(item_id: int, body: TimetableCreate, db: Session = Depends(get_db), actor: User = Depends(require_roles(PLANNER, HEAD))):
    if body.week_start.weekday() != 0:
        raise HTTPException(422, "week_start must be a Monday")
    source = get_timetable(db, item_id)
    if actor.role_id == PLANNER and source.created_by_id != actor.id:
        raise HTTPException(403, "Planner may only copy their own timetable")
    target = clone_timetable(source, body.week_start, actor, db)
    audit_commit(db, actor, "timetable_copied", "timetable", target.id, {"source_id": source.id})
    return {"id": target.id, "week_start": str(target.week_start), "version": target.version, "status": target.status}


@router.post("/timetables/{item_id}/new-version", status_code=201)
def timetable_version(item_id: int, reason: str = Form(), db: Session = Depends(get_db), actor: User = Depends(require_roles(PLANNER, HEAD))):
    source = get_timetable(db, item_id)
    if len(reason.strip()) < 3:
        raise HTTPException(422, "Provide a reason for the new published timetable version")
    if source.status != "Published":
        raise HTTPException(409, "Only a published timetable may be versioned")
    if actor.role_id == PLANNER and source.created_by_id != actor.id:
        raise HTTPException(403, "Planner may only version their own timetable")
    target = clone_timetable(source, source.week_start, actor, db, change_reason=reason.strip())
    audit_commit(db, actor, "timetable_version_created", "timetable", target.id,
        {"source_id": source.id, "previous_version": source.version, "reason": reason.strip()})
    return {"id": target.id, "week_start": str(target.week_start), "version": target.version, "status": target.status}


@router.post("/timetables/{item_id}/submit")
def submit_timetable(item_id: int, db: Session = Depends(get_db), actor: User = Depends(require_roles(PLANNER, HEAD))):
    item = get_timetable(db, item_id); can_edit_timetable(item, actor)
    if not item.assignments:
        raise HTTPException(409, "Add at least one assignment before submitting")
    item.status = "Submitted"
    audit_commit(db, actor, "timetable_submitted", "timetable", item.id)
    return {"id": item.id, "status": item.status}


@router.post("/timetables/{item_id}/review")
def review_timetable(item_id: int, decision: str = Form(), comment: str = Form(""),
                     db: Session = Depends(get_db), actor: User = Depends(require_roles(HEAD))):
    item = get_timetable(db, item_id)
    if item.status not in {"Submitted", "Under Review"}:
        raise HTTPException(409, "Only submitted plans can be reviewed")
    statuses = {"under_review": "Under Review", "return": "Returned for Correction", "approve": "Approved"}
    if decision not in statuses:
        raise HTTPException(422, "Invalid review decision")
    item.status = statuses[decision]; item.approval_comment = comment
    item.approved_by_id = actor.id if decision == "approve" else None
    audit_commit(db, actor, "timetable_reviewed", "timetable", item.id, {"decision": decision, "comment": comment})
    return {"id": item.id, "status": item.status, "comment": comment}


@router.post("/timetables/{item_id}/publish")
def publish_timetable(item_id: int, db: Session = Depends(get_db), actor: User = Depends(require_roles(HEAD))):
    item = get_timetable(db, item_id)
    if item.status != "Approved" or not item.assignments:
        raise HTTPException(409, "Only an approved, non-empty timetable can be published")
    item.status = "Published"; item.published_at = datetime.utcnow()
    audit_commit(db, actor, "timetable_published", "timetable", item.id, {"version": item.version})
    return {"id": item.id, "status": item.status, "published_at": item.published_at.isoformat()}


def get_task(db: Session, task_id: int) -> Task:
    task = db.scalar(select(Task).options(joinedload(Task.employee), joinedload(Task.assigner)).where(Task.id == task_id))
    if not task:
        raise HTTPException(404, "Task not found")
    return task


def visible_task(task: Task, actor: User, db: Session):
    if actor.role_id == HEAD or actor.id == task.employee_id or (actor.role_id == EDITOR and actor.id == task.assigner_id):
        return
    if actor.role_id == SHIFT_LEADER:
        members = set(db.scalars(select(TimetableAssignment.employee_id).join(Timetable).where(
            Timetable.status == "Published", TimetableAssignment.leader_id == actor.id,
            TimetableAssignment.work_date == date.today())))
        if task.employee_id in members:
            return
    raise HTTPException(403, "You cannot access this task")


@router.post("/timetables/{item_id}/archive")
def archive_timetable(item_id: int, db: Session = Depends(get_db), actor: User = Depends(require_roles(HEAD))):
    item = get_timetable(db, item_id)
    if item.status != "Published" or item.week_start + timedelta(days=6) >= date.today():
        raise HTTPException(409, "Only a completed published week can be archived")
    item.status = "Archived"
    audit_commit(db, actor, "timetable_archived", "timetable", item.id, {"version": item.version})
    return {"id": item.id, "status": item.status}


@router.post("/tasks", status_code=201)
def create_tasks(body: TaskCreate, db: Session = Depends(get_db), actor: User = Depends(require_roles(HEAD, EDITOR))):
    if body.priority not in PRIORITIES:
        raise HTTPException(422, "Invalid priority")
    if body.deadline.date() < body.start_date:
        raise HTTPException(422, "Deadline cannot precede task start")
    if len(set(body.employee_ids)) != len(body.employee_ids):
        raise HTTPException(422, "Duplicate employee assignments are not allowed")
    people = db.scalars(select(User).where(User.id.in_(body.employee_ids), User.active.is_(True))).all()
    if len(people) != len(body.employee_ids) or any(p.role_id not in {STAFF, SHIFT_LEADER, EDITOR, HEAD} for p in people):
        raise HTTPException(422, "Select active employee accounts")
    if actor.role_id == EDITOR:
        scheduled = db.execute(select(TimetableAssignment.employee_id, TimetableAssignment.shift_id).join(Timetable).where(
            Timetable.status == "Published", TimetableAssignment.editor_id == actor.id,
            TimetableAssignment.work_date == body.assignment_date)).all()
        scheduled_by_employee = defaultdict(set)
        for employee_id, shift_id in scheduled:
            scheduled_by_employee[employee_id].add(shift_id)
        if not set(body.employee_ids).issubset(scheduled_by_employee):
            raise HTTPException(403, "Editors may assign only employees allocated to their published shift on that date")
        if body.shift_id is not None and any(body.shift_id not in scheduled_by_employee[employee_id] for employee_id in body.employee_ids):
            raise HTTPException(403, "The selected shift does not match the employee's published allocation")
    created = []
    for person in people:
        task = Task(reference=f"OT-{date.today():%Y%m%d}-{secrets.token_hex(4).upper()}", title=body.title.strip(),
            description=body.description, instructions=body.instructions, employee_id=person.id, assigner_id=actor.id,
            department_id=body.department_id, shift_id=body.shift_id, assignment_date=body.assignment_date,
            start_date=body.start_date, deadline=utc_naive(body.deadline), priority=body.priority)
        db.add(task); db.flush()
        db.add(TaskHistory(task_id=task.id, actor_id=actor.id, new_status="Assigned", note="Task assigned"))
        record_audit(db, actor, "task_assigned", "task", task.id, {"employee_id": person.id, "reference": task.reference})
        created.append(task)
    db.commit()
    return [task_json(t) for t in created]


@router.get("/tasks")
def list_tasks(status_filter: str | None = None, db: Session = Depends(get_db), actor: User = Depends(current_user)):
    if actor.role_id in {ADMIN, PLANNER}:
        raise HTTPException(403, "This role does not receive daily task access")
    query = select(Task).options(joinedload(Task.employee), joinedload(Task.assigner)).order_by(Task.deadline)
    if actor.role_id == STAFF:
        query = query.where(Task.employee_id == actor.id)
    elif actor.role_id == EDITOR:
        query = query.where(Task.assigner_id == actor.id)
    elif actor.role_id == SHIFT_LEADER:
        members = set(db.scalars(select(TimetableAssignment.employee_id).join(Timetable).where(
            Timetable.status == "Published", TimetableAssignment.leader_id == actor.id,
            TimetableAssignment.work_date == date.today()))) | {actor.id}
        query = query.where(Task.employee_id.in_(members))
    if status_filter:
        query = query.where(Task.status == status_filter)
    return [task_json(t) for t in db.scalars(query).unique()]


@router.patch("/tasks/{task_id}")
def update_task(task_id: int, body: TaskUpdate, db: Session = Depends(get_db), actor: User = Depends(current_user)):
    task = get_task(db, task_id)
    if actor.role_id != HEAD and not (actor.role_id == EDITOR and actor.id == task.assigner_id):
        raise HTTPException(403, "Only the assigning editor or head may change this task")
    if task.status in {"Verified", "Cancelled"}:
        raise HTTPException(409, "Verified or cancelled task cannot be edited")
    changes = {}
    for key in ("title", "instructions", "deadline", "priority", "employee_id"):
        value = getattr(body, key)
        if value is None:
            continue
        if key == "priority" and value not in PRIORITIES:
            raise HTTPException(422, "Invalid priority")
        if key == "employee_id":
            new_employee = db.get(User, value)
            if not new_employee or not new_employee.active:
                raise HTTPException(422, "Select an active employee")
            if actor.role_id == EDITOR and not db.scalar(select(TimetableAssignment.id).join(Timetable).where(
                Timetable.status == "Published", TimetableAssignment.editor_id == actor.id,
                TimetableAssignment.employee_id == value, TimetableAssignment.work_date == task.assignment_date)):
                raise HTTPException(403, "Editors may reassign only within their published shift for the task date")
        if key == "deadline":
            value = utc_naive(value)
        old = getattr(task, key)
        if old != value:
            changes[key] = {"previous": str(old), "new": str(value)}
            setattr(task, key, value)
    if not changes:
        raise HTTPException(422, "No changes provided")
    if "employee_id" in changes:
        old_status = task.status
        task.status = "Assigned"
        db.add(TaskHistory(task_id=task.id, actor_id=actor.id, old_status=old_status, new_status="Assigned",
                           note=f"Reassigned: {body.reason}"))
    audit_commit(db, actor, "task_changed", "task", task.id, {"reason": body.reason, "changes": changes})
    return task_json(task)


@router.post("/tasks/{task_id}/acknowledge")
def acknowledge_task(task_id: int, db: Session = Depends(get_db), actor: User = Depends(require_roles(STAFF, EDITOR, SHIFT_LEADER, HEAD))):
    task = get_task(db, task_id)
    if task.employee_id != actor.id or task.status != "Assigned":
        raise HTTPException(409, "Only the assigned employee can acknowledge an assigned task")
    old = task.status; task.status = "Acknowledged"
    db.add(TaskHistory(task_id=task.id, actor_id=actor.id, old_status=old, new_status=task.status))
    audit_commit(db, actor, "task_acknowledged", "task", task.id)
    return task_json(task)


@router.post("/tasks/{task_id}/start")
def start_task(task_id: int, db: Session = Depends(get_db), actor: User = Depends(require_roles(STAFF, EDITOR, SHIFT_LEADER, HEAD))):
    task = get_task(db, task_id)
    if task.employee_id != actor.id or task.status not in {"Assigned", "Acknowledged"}:
        raise HTTPException(409, "Only the assigned employee can start this task")
    old = task.status; task.status = "In Progress"
    db.add(TaskHistory(task_id=task.id, actor_id=actor.id, old_status=old, new_status=task.status))
    audit_commit(db, actor, "task_started", "task", task.id)
    return task_json(task)


@router.post("/tasks/{task_id}/submit")
async def submit_task(task_id: int, report: Annotated[str, Form()], notes: Annotated[str, Form()] = "",
    files: Annotated[list[UploadFile] | None, File()] = None, db: Session = Depends(get_db),
    actor: User = Depends(require_roles(STAFF, EDITOR, SHIFT_LEADER, HEAD))):
    task = get_task(db, task_id)
    if task.employee_id != actor.id:
        raise HTTPException(403, "Only the assigned employee may submit work")
    if task.status not in {"Assigned", "Acknowledged", "In Progress", "Correction Requested", "Rejected"}:
        raise HTTPException(409, "This task is not open for submission")
    if not report.strip():
        raise HTTPException(422, "Completion report is required")
    next_status = "Submitted" if task.status in {"Assigned", "Acknowledged", "In Progress"} else "Resubmitted"
    directory = Path(settings.upload_dir).resolve(); directory.mkdir(parents=True, exist_ok=True)
    files_written: list[Path] = []
    submission = Submission(task_id=task.id, employee_id=actor.id, report=report.strip(), notes=notes.strip())
    db.add(submission); db.flush()
    try:
        if files and len(files) > 10:
            raise HTTPException(422, "A submission may include at most 10 attachments")
        for upload in files or []:
            original = (upload.filename or "").replace("\\", "/").split("/")[-1]
            ext = Path(original).suffix.lower()
            data = await upload.read(settings.max_upload_size_mb * 1024 * 1024 + 1)
            if ext not in ALLOWED_EXTENSIONS or not data or len(data) > settings.max_upload_size_mb * 1024 * 1024:
                raise HTTPException(422, f"Unsupported or oversized attachment: {original[:100]}")
            valid = ((ext == ".pdf" and data.startswith(b"%PDF-"))
                or (ext == ".png" and data.startswith(b"\x89PNG\r\n\x1a\n"))
                or (ext in {".jpg", ".jpeg"} and data.startswith(b"\xff\xd8\xff"))
                or (ext in {".docx", ".xlsx"} and data.startswith(b"PK\x03\x04")))
            if not valid:
                raise HTTPException(422, "Attachment content does not match its allowed extension")
            stored = secrets.token_hex(24) + ext
            path = directory / stored; path.write_bytes(data); files_written.append(path)
            safe_name = "".join(c for c in original if c.isprintable() and c not in "\r\n")[:255] or "attachment" + ext
            db.add(Attachment(submission_id=submission.id, original_name=safe_name, stored_name=stored,
                media_type=ALLOWED_MIME[ext], size_bytes=len(data)))
        old = task.status; task.status = next_status
        db.add(TaskHistory(task_id=task.id, actor_id=actor.id, old_status=old, new_status=task.status))
        record_audit(db, actor, "task_submitted", "task", task.id, {"submission_id": submission.id, "attachments": len(files_written)})
        db.commit()
    except Exception:
        db.rollback()
        for path in files_written:
            path.unlink(missing_ok=True)
        raise
    return {"submission_id": submission.id, "task_id": task.id, "status": next_status}


@router.get("/tasks/{task_id}/submissions")
def submissions(task_id: int, db: Session = Depends(get_db), actor: User = Depends(current_user)):
    task = get_task(db, task_id); visible_task(task, actor, db)
    rows = db.scalars(select(Submission).options(joinedload(Submission.attachments)).where(Submission.task_id == task_id).order_by(Submission.id)).unique().all()
    latest_id = rows[-1].id if rows else None
    return [{"id": s.id, "task_id": s.task_id, "employee_id": s.employee_id, "report": s.report, "notes": s.notes,
        "reviewable": s.id == latest_id, "created_at": s.created_at.isoformat(),
        "attachments": [{"id": a.id, "name": a.original_name, "size": a.size_bytes} for a in s.attachments]} for s in rows]


@router.post("/tasks/{task_id}/start-review")
def start_task_review(task_id: int, db: Session = Depends(get_db), actor: User = Depends(require_roles(HEAD, EDITOR))):
    task = get_task(db, task_id)
    if actor.role_id == EDITOR and task.assigner_id != actor.id:
        raise HTTPException(403, "Editors may only review tasks they assigned")
    if task.status not in {"Submitted", "Resubmitted"}:
        raise HTTPException(409, "Task has no new submission awaiting review")
    old = task.status; task.status = "Under Review"
    db.add(TaskHistory(task_id=task.id, actor_id=actor.id, old_status=old, new_status=task.status))
    audit_commit(db, actor, "task_review_started", "task", task.id)
    return {"task_id": task.id, "status": task.status}


@router.post("/submissions/{submission_id}/verify")
def verify_submission(submission_id: int, body: VerificationIn, db: Session = Depends(get_db), actor: User = Depends(require_roles(HEAD, EDITOR))):
    submission = db.get(Submission, submission_id)
    if not submission:
        raise HTTPException(404, "Submission not found")
    task = get_task(db, submission.task_id)
    latest_submission = db.scalar(select(func.max(Submission.id)).where(Submission.task_id == task.id))
    if submission.id != latest_submission:
        raise HTTPException(409, "Only the latest resubmission can be verified")
    if actor.id == task.employee_id:
        raise HTTPException(403, "An employee cannot verify their own work")
    if actor.role_id == EDITOR and actor.id != task.assigner_id:
        raise HTTPException(403, "Editors can only verify work they assigned")
    if task.status not in {"Submitted", "Resubmitted", "Under Review"}:
        raise HTTPException(409, "Task is not awaiting review")
    statuses = {"approve": "Verified", "request_correction": "Correction Requested", "reject": "Rejected"}
    if body.decision not in statuses:
        raise HTTPException(422, "Decision must be approve, request_correction, or reject")
    old = task.status; task.status = statuses[body.decision]
    db.add(Verification(submission_id=submission.id, reviewer_id=actor.id, decision=body.decision, comment=body.comment))
    db.add(TaskHistory(task_id=task.id, actor_id=actor.id, old_status=old, new_status=task.status, note=body.comment))
    audit_commit(db, actor, "submission_reviewed", "submission", submission.id, {"decision": body.decision, "comment": body.comment})
    return {"task_id": task.id, "status": task.status}


@router.post("/tasks/{task_id}/reopen")
def reopen_task(task_id: int, reason: str = Form(), db: Session = Depends(get_db), actor: User = Depends(require_roles(HEAD))):
    task = get_task(db, task_id)
    if task.status != "Verified" or len(reason.strip()) < 3:
        raise HTTPException(409, "Only verified work can be reopened; provide an audit reason")
    task.status = "Correction Requested"
    db.add(TaskHistory(task_id=task.id, actor_id=actor.id, old_status="Verified", new_status=task.status, note=reason.strip()))
    audit_commit(db, actor, "verified_task_reopened", "task", task.id, {"reason": reason.strip()})
    return task_json(task)


@router.post("/tasks/{task_id}/cancel")
def cancel_task(task_id: int, reason: str = Form(), db: Session = Depends(get_db), actor: User = Depends(require_roles(HEAD, EDITOR))):
    task = get_task(db, task_id)
    if actor.role_id == EDITOR and task.assigner_id != actor.id:
        raise HTTPException(403, "Editors may only cancel tasks they assigned")
    if task.status in {"Verified", "Cancelled"} or len(reason.strip()) < 3:
        raise HTTPException(409, "Task cannot be cancelled; provide a reason and choose an open task")
    old = task.status; task.status = "Cancelled"
    db.add(TaskHistory(task_id=task.id, actor_id=actor.id, old_status=old, new_status="Cancelled", note=reason.strip()))
    audit_commit(db, actor, "task_cancelled", "task", task.id, {"reason": reason.strip()})
    return task_json(task)


@router.get("/attachments/{attachment_id}")
def download_attachment(attachment_id: int, db: Session = Depends(get_db), actor: User = Depends(current_user)):
    attachment = db.scalar(select(Attachment).options(joinedload(Attachment.submission).joinedload(Submission.task)).where(Attachment.id == attachment_id))
    if not attachment:
        raise HTTPException(404, "Attachment not found")
    visible_task(attachment.submission.task, actor, db)
    path = Path(settings.upload_dir).resolve() / attachment.stored_name
    if not path.is_file():
        raise HTTPException(404, "Attachment file missing")
    return FileResponse(path, media_type=attachment.media_type, filename=attachment.original_name)


@router.post("/shift-reports", status_code=201)
def create_shift_report(body: ShiftReportIn, db: Session = Depends(get_db), actor: User = Depends(require_roles(HEAD, EDITOR, SHIFT_LEADER))):
    item = ShiftReport(submitted_by_id=actor.id, **body.model_dump()); db.add(item); db.flush()
    audit_commit(db, actor, "shift_report_submitted", "shift_report", item.id, {"date": str(item.report_date)})
    return {"id": item.id, "date": str(item.report_date)}


@router.get("/shift-reports")
def list_shift_reports(report_date: date | None = None, db: Session = Depends(get_db), _actor: User = Depends(require_roles(HEAD, EDITOR, SHIFT_LEADER))):
    query = select(ShiftReport).order_by(ShiftReport.report_date.desc(), ShiftReport.created_at.desc())
    if report_date:
        query = query.where(ShiftReport.report_date == report_date)
    return [{"id": x.id, "date": str(x.report_date), "shift_id": x.shift_id, "submitted_by": x.submitted_by_id,
        "unfinished": x.unfinished, "challenges": x.challenges, "handover": x.handover,
        "attendance_notes": x.attendance_notes, "created_at": x.created_at.isoformat()} for x in db.scalars(query)]


@router.post("/attendance", status_code=201)
def record_attendance(body: AttendanceIn, db: Session = Depends(get_db), actor: User = Depends(require_roles(HEAD, ADMIN))):
    if body.status not in {"Present", "Absent", "Leave", "Reassigned"}:
        raise HTTPException(422, "Invalid attendance status")
    if not db.get(User, body.employee_id):
        raise HTTPException(404, "Employee not found")
    item = db.scalar(select(AttendanceRecord).where(AttendanceRecord.employee_id == body.employee_id,
        AttendanceRecord.work_date == body.work_date))
    if item:
        item.status, item.reason, item.approved_by_id = body.status, body.reason, actor.id
    else:
        item = AttendanceRecord(employee_id=body.employee_id, work_date=body.work_date, status=body.status,
            reason=body.reason, approved_by_id=actor.id); db.add(item)
    db.flush(); audit_commit(db, actor, "attendance_recorded", "attendance", item.id,
        {"employee_id": body.employee_id, "status": body.status, "reason": body.reason})
    return {"id": item.id, "date": str(item.work_date), "status": item.status}


def report_rows(db: Session, start: date, end: date):
    tasks = db.scalars(select(Task).options(joinedload(Task.employee)).where(Task.assignment_date.between(start, end))).unique().all()
    attendees = db.scalars(select(AttendanceRecord).where(AttendanceRecord.work_date.between(start, end))).all()
    exceptions_map = {(a.employee_id, a.work_date): a for a in attendees}
    planned = db.scalars(select(TimetableAssignment).join(Timetable).where(Timetable.status == "Published",
        TimetableAssignment.work_date.between(start, end)).options(joinedload(TimetableAssignment.employee),
        joinedload(TimetableAssignment.shift))).unique().all()
    by_employee: dict[int, list[Task]] = defaultdict(list)
    planned_by_employee: dict[int, list[TimetableAssignment]] = defaultdict(list)
    for task in tasks: by_employee[task.employee_id].append(task)
    for assignment in planned: planned_by_employee[assignment.employee_id].append(assignment)
    rows = []
    for uid in sorted(set(by_employee) | set(planned_by_employee)):
        user = db.get(User, uid); own = [t for t in by_employee[uid] if t.status != "Cancelled"]; assigned = len(own)
        submitted = sum(bool(t.submissions) or t.status in {"Submitted", "Resubmitted", "Verified", "Correction Requested", "Rejected"} for t in own)
        verified = sum(t.status == "Verified" for t in own)
        overdue = sum(t.deadline < datetime.utcnow() and t.status != "Verified" for t in own)
        plan = planned_by_employee[uid]
        exceptions = [f"{a.work_date} {exceptions_map[(uid, a.work_date)].status}: {exceptions_map[(uid, a.work_date)].reason}" for a in plan if (uid, a.work_date) in exceptions_map and exceptions_map[(uid, a.work_date)].status in {"Leave", "Absent", "Reassigned"}]
        rows.append({"employee_id": uid, "employee": user.full_name if user else "Unknown",
            "planned_shifts": [{"date": str(a.work_date), "shift": a.shift.name} for a in plan],
            "assigned": assigned, "submitted": submitted, "verified": verified, "pending": assigned - verified,
            "overdue": overdue, "exceptions": exceptions, "submission_rate": round(submitted / assigned * 100, 1) if assigned else 0.0,
            "verified_completion_rate": round(verified / assigned * 100, 1) if assigned else 0.0})
    return rows, tasks


def validate_range(start: date, end: date):
    if end < start or (end - start).days > 366:
        raise HTTPException(422, "Select a valid date range of at most one year")


@router.get("/reports/dashboard")
def dashboard(db: Session = Depends(get_db), _actor: User = Depends(require_roles(HEAD))):
    today = date.today(); week_start = today - timedelta(days=today.weekday())
    tasks = db.scalars(select(Task)).all(); counts: dict[str, int] = defaultdict(int)
    for task in tasks:
        state = task.status
        if task.deadline < datetime.utcnow() and state in {"Assigned", "Acknowledged", "In Progress"}: state = "Overdue"
        counts[state] += 1
    staff_total = db.scalar(select(func.count(User.id)).where(User.active.is_(True), User.role_id != ADMIN)) or 0
    staff_today = db.scalar(select(func.count(func.distinct(TimetableAssignment.employee_id))).join(Timetable).where(
        Timetable.status == "Published", TimetableAssignment.work_date == today)) or 0
    rows, _ = report_rows(db, week_start, today)
    return {"staff_total": staff_total, "staff_planned_today": staff_today, "tasks_total": len(tasks),
        "tasks_assigned_today": sum(t.assignment_date == today for t in tasks), "in_progress": counts["In Progress"],
        "submitted": counts["Submitted"] + counts["Resubmitted"], "verified": counts["Verified"],
        "pending": sum(counts[s] for s in ("Assigned", "Acknowledged", "In Progress", "Overdue")),
        "overdue": counts["Overdue"], "rejected": counts["Rejected"], "correction_requested": counts["Correction Requested"],
        "weekly_performance": rows}


@router.get("/reports/performance")
def performance(start: date, end: date, db: Session = Depends(get_db), _actor: User = Depends(require_roles(HEAD))):
    validate_range(start, end); rows, _ = report_rows(db, start, end)
    return {"start": str(start), "end": str(end), "employees": rows}


@router.get("/reports/shift-comparison")
def shift_comparison(report_date: date, db: Session = Depends(get_db), _actor: User = Depends(require_roles(HEAD))):
    reports = db.scalars(select(ShiftReport).where(ShiftReport.report_date == report_date)).all()
    tasks = db.scalars(select(Task).where(Task.assignment_date == report_date)).all()
    by_shift = defaultdict(list)
    reports_by_shift = defaultdict(list)
    for task in tasks: by_shift[task.shift_id].append(task)
    for report in reports: reports_by_shift[report.shift_id].append(report)
    shift_ids = set(by_shift) | set(reports_by_shift)
    rows = []
    for shift_id in sorted(shift_ids, key=lambda x: x or 0):
        items = [t for t in by_shift[shift_id] if t.status != "Cancelled"]
        handovers = reports_by_shift[shift_id]
        submitted_count = sum(t.status in {"Submitted", "Resubmitted", "Verified", "Correction Requested", "Rejected"} for t in items)
        verified_count = sum(t.status == "Verified" for t in items)
        rows.append({"shift_id": shift_id, "assigned": len(items), "submitted": submitted_count,
            "verified": verified_count, "pending": len(items) - verified_count,
            "overdue": sum(t.deadline < datetime.utcnow() and t.status != "Verified" for t in items),
            "report": " / ".join(x.handover for x in handovers if x.handover),
            "challenges": " / ".join(x.challenges for x in handovers if x.challenges),
            "unfinished": " / ".join(x.unfinished for x in handovers if x.unfinished),
            "submitted_by": [x.submitted_by_id for x in handovers]})
    return {"date": str(report_date), "shifts": rows}


@router.get("/reports/tasks.csv")
def export_tasks_csv(start: date, end: date, db: Session = Depends(get_db), _actor: User = Depends(require_roles(HEAD))):
    validate_range(start, end); rows, _ = report_rows(db, start, end)
    output = io.StringIO(); fields = ["employee_id", "employee", "assigned", "submitted", "verified", "pending", "overdue", "submission_rate", "verified_completion_rate", "exceptions"]
    writer = csv.DictWriter(output, fieldnames=fields); writer.writeheader()
    def safe_cell(value):
        text = str(value or "")
        return "'" + text if text.startswith(("=", "+", "-", "@", "\t", "\r")) else text
    for row in rows:
        data = {**row, "exceptions": "; ".join(row["exceptions"])}
        writer.writerow({key: safe_cell(value) for key, value in data.items()})
    return StreamingResponse(iter([output.getvalue()]), media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=office-performance.csv"})


@router.get("/audit")
def audit_history(limit: int = 100, db: Session = Depends(get_db), _actor: User = Depends(require_roles(HEAD, ADMIN))):
    rows = db.scalars(select(AuditLog).order_by(AuditLog.created_at.desc()).limit(max(1, min(500, limit)))).all()
    return [{"id": x.id, "actor_id": x.actor_id, "action": x.action, "entity_type": x.entity_type,
        "entity_id": x.entity_id, "details": json.loads(x.details or "{}"), "created_at": x.created_at.isoformat()} for x in rows]
