from __future__ import annotations

import io
import json
import secrets
from datetime import date, datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import qrcode
from qrcode.image.svg import SvgPathImage
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.dependencies import current_user, require_roles
from app.core.roles import ADMIN, EDITOR, HEAD
from app.db.session import get_db
from app.models.models import (
    AuditLog, Department, EquipmentAccessoryLink, EquipmentAsset, EquipmentAuthorizationRole,
    EquipmentCustodianAssignment, EquipmentCustodianReplacement, EquipmentHandover,
    EquipmentHandoverLine, EquipmentIssue, EquipmentIssueItem, EquipmentItemEvent, Role,
    Shift, User,
)
from app.schemas_equipment import (
    AccessoryLinkIn, AssetCreate, AssetUpdate, AuthorizationIn, AuthorizationRolesIn,
    BorrowerAckIn, CustodianAssignmentIn, CustodianReplacementIn, HandoverAckIn,
    HandoverIn, HandoverReviewIn, IssueIn, IssueRequestIn, ReturnIn, EquipmentInspectionIn,
)
from app.services.audit import record_audit

router = APIRouter(prefix="/api/equipment", tags=["equipment"])
settings = get_settings()
HEAD_ADMIN = (HEAD, ADMIN)
ASSET_CONDITIONS = {"New", "Good", "Fair", "Poor", "Damaged"}
AUTH_METHODS = {"Head of Office authorization", "Editor authorization", "Other delegated authorization"}


def _utc_naive(value: datetime) -> datetime:
    return value.astimezone(timezone.utc).replace(tzinfo=None) if value.tzinfo else value


def _office_now() -> datetime:
    return datetime.now(ZoneInfo(settings.office_timezone))


def _office_today() -> date:
    return _office_now().date()


def _timestamp(value: datetime | None) -> str | None:
    if value is None:
        return None
    aware = value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
    return aware.isoformat().replace("+00:00", "Z")


def _audit(db: Session, actor: User, action: str, entity: str, entity_id, details: dict | None = None):
    record_audit(db, actor, action, entity, entity_id, details)
    db.commit()


def _active_user(db: Session, user_id: int | None, field: str) -> User | None:
    if user_id is None:
        return None
    user = db.get(User, user_id)
    if not user or not user.active:
        raise HTTPException(422, f"{field} must identify an active user")
    return user


def _asset_json(db: Session, asset: EquipmentAsset) -> dict:
    links = db.scalars(select(EquipmentAccessoryLink).where(EquipmentAccessoryLink.parent_asset_id == asset.id)).all()
    accessories = [db.get(EquipmentAsset, link.accessory_asset_id) for link in links]
    responsible = db.get(User, asset.responsible_user_id) if asset.responsible_user_id else None
    department = db.get(Department, asset.department_id) if asset.department_id else None
    return {
        "id": asset.id, "asset_tag": asset.asset_tag, "category": asset.category, "name": asset.name,
        "brand": asset.brand, "model": asset.model, "serial_number": asset.serial_number,
        "internal_tag": asset.internal_tag, "has_photo": bool(asset.photo_name), "location": asset.location,
        "responsible_user_id": asset.responsible_user_id,
        "responsible_user": responsible.full_name if responsible else None,
        "department_id": asset.department_id, "department": department.name if department else None,
        "condition": asset.condition, "availability": asset.availability,
        "purchase_date": asset.purchase_date.isoformat() if asset.purchase_date else None,
        "warranty_until": asset.warranty_until.isoformat() if asset.warranty_until else None,
        "notes": asset.notes, "accessories": [{"id": a.id, "asset_tag": a.asset_tag, "name": a.name} for a in accessories if a],
        "created_at": _timestamp(asset.created_at), "updated_at": _timestamp(asset.updated_at),
    }


def _issue_json(db: Session, issue: EquipmentIssue) -> dict:
    items = db.scalars(select(EquipmentIssueItem).where(EquipmentIssueItem.issue_id == issue.id)).all()
    assets = []
    for item in items:
        asset = db.get(EquipmentAsset, item.asset_id)
        assets.append({"issue_item_id": item.id, "asset_id": item.asset_id,
                       "asset_tag": asset.asset_tag, "name": asset.name,
                       "condition_before": item.condition_before, "return_condition": item.return_condition,
                       "returned_at": _timestamp(item.returned_at),
                       "received_by_id": item.received_by_id, "missing_reported": item.missing_reported,
                       "damage_notes": item.damage_notes})
    requester = db.get(User, issue.requester_id)
    borrower = db.get(User, issue.borrower_id) if issue.borrower_id else None
    authorizer = db.get(User, issue.authorized_by_id) if issue.authorized_by_id else None
    issuer = db.get(User, issue.issued_by_id) if issue.issued_by_id else None
    shift = db.get(Shift, issue.shift_id)
    return {
        "id": issue.id, "requester_id": issue.requester_id,
        "requester": requester.full_name if requester else "Unknown",
        "borrower_id": issue.borrower_id, "borrower_name": borrower.full_name if borrower else issue.borrower_name,
        "borrower_office": issue.borrower_office, "external": issue.external,
        "requested_at": _timestamp(issue.requested_at), "shift_id": issue.shift_id,
        "shift": shift.name if shift else "", "shift_date": issue.shift_date.isoformat(),
        "expected_return_at": _timestamp(issue.expected_return_at), "purpose": issue.purpose,
        "status": issue.status, "authorized_by_id": issue.authorized_by_id,
        "authorized_by": authorizer.full_name if authorizer else None,
        "authorized_role_id": issue.authorized_role_id,
        "authorization_method": issue.authorization_method, "authorization_remarks": issue.authorization_remarks,
        "authorized_at": _timestamp(issue.authorized_at),
        "issued_by_id": issue.issued_by_id, "issued_by": issuer.full_name if issuer else None,
        "issued_at": _timestamp(issue.issued_at),
        "borrower_acknowledged_at": _timestamp(issue.borrower_acknowledged_at),
        "borrower_acknowledged_by_id": issue.borrower_acknowledged_by_id,
        "borrower_acknowledged_name": issue.borrower_acknowledged_name,
        "items": assets,
        "outstanding_count": sum(x["returned_at"] is None for x in assets),
    }


def _roster(db: Session, shift_id: int, shift_date: date) -> list[int]:
    assignments = db.scalars(select(EquipmentCustodianAssignment).where(
        EquipmentCustodianAssignment.shift_id == shift_id,
        EquipmentCustodianAssignment.effective_from <= shift_date,
        or_(EquipmentCustodianAssignment.effective_to.is_(None), EquipmentCustodianAssignment.effective_to >= shift_date),
    )).all()
    roster = {a.custodian_id for a in assignments}
    replacements = db.scalars(select(EquipmentCustodianReplacement).where(
        EquipmentCustodianReplacement.shift_id == shift_id,
        EquipmentCustodianReplacement.shift_date == shift_date)).all()
    for replacement in replacements:
        roster.discard(replacement.original_custodian_id)
        roster.add(replacement.replacement_custodian_id)
    return sorted(roster)


def _require_custodian(db: Session, actor: User, shift_id: int, shift_date: date) -> None:
    if actor.id not in _roster(db, shift_id, shift_date):
        raise HTTPException(403, "Only a custodian assigned or designated as a replacement for this shift may handle the transaction")


def _is_manager(actor: User) -> bool:
    return actor.role_id in {HEAD, ADMIN, EDITOR}


def _issue_visible(db: Session, issue: EquipmentIssue, actor: User) -> bool:
    if _is_manager(actor) or actor.id in {issue.requester_id, issue.borrower_id, issue.authorized_by_id, issue.issued_by_id}:
        return True
    if actor.id in _roster(db, issue.shift_id, issue.shift_date):
        return True
    if issue.status in {"Issued", "Partially returned"}:
        today = _office_today()
        for shift in db.scalars(select(Shift).where(Shift.active.is_(True))).all():
            if actor.id in _roster(db, shift.id, today):
                return True
    items = db.scalars(select(EquipmentIssueItem).where(EquipmentIssueItem.issue_id == issue.id)).all()
    return any(item.received_by_id == actor.id for item in items)


def _issue_event(db: Session, issue: EquipmentIssue, item: EquipmentIssueItem, actor: User,
                 event_type: str, condition: str | None = None, details: str = "",
                 shift_id: int | None = None, shift_date: date | None = None):
    db.add(EquipmentItemEvent(issue_id=issue.id, issue_item_id=item.id, asset_id=item.asset_id,
                              actor_id=actor.id, event_type=event_type,
                              shift_id=shift_id if shift_id is not None else issue.shift_id,
                              shift_date=shift_date if shift_date is not None else issue.shift_date,
                              condition=condition, details=details))


@router.get("/shifts")
def list_equipment_shifts(db: Session = Depends(get_db), actor: User = Depends(current_user)):
    return [{"id": s.id, "name": s.name, "start_time": s.start_time, "end_time": s.end_time}
            for s in db.scalars(select(Shift).where(Shift.active.is_(True)).order_by(Shift.start_time))]


@router.get("/custodians")
def list_custodians(shift_id: int | None = None, shift_date: date | None = None,
                    db: Session = Depends(get_db), actor: User = Depends(current_user)):
    target_date = shift_date or _office_today()
    query = select(EquipmentCustodianAssignment)
    if shift_id:
        query = query.where(EquipmentCustodianAssignment.shift_id == shift_id)
    assignments = db.scalars(query.order_by(EquipmentCustodianAssignment.effective_from.desc())).all()
    result = []
    for assignment in assignments:
        user = db.get(User, assignment.custodian_id)
        shift = db.get(Shift, assignment.shift_id)
        effective = assignment.effective_from <= target_date and (assignment.effective_to is None or assignment.effective_to >= target_date)
        result.append({"id": assignment.id, "shift_id": assignment.shift_id, "shift": shift.name if shift else "",
                       "custodian_id": assignment.custodian_id, "custodian": user.full_name if user else "Unknown",
                       "effective_from": assignment.effective_from.isoformat(),
                       "effective_to": assignment.effective_to.isoformat() if assignment.effective_to else None,
                       "assigned_by_id": assignment.assigned_by_id, "assigned_at": _timestamp(assignment.assigned_at),
                       "reason": assignment.reason, "effective_on_query_date": effective})
    replacements = db.scalars(select(EquipmentCustodianReplacement).where(
        EquipmentCustodianReplacement.shift_date == target_date)).all()
    if shift_id:
        replacements = [r for r in replacements if r.shift_id == shift_id]
    result_replacements = [{"id": r.id, "shift_id": r.shift_id, "shift_date": r.shift_date.isoformat(),
        "original_custodian_id": r.original_custodian_id, "replacement_custodian_id": r.replacement_custodian_id,
        "reason": r.reason, "designated_by_id": r.designated_by_id, "created_at": _timestamp(r.created_at)} for r in replacements]
    return {"date": target_date.isoformat(), "assignments": result, "replacements": result_replacements}


@router.post("/custodians", status_code=201)
def assign_custodian(body: CustodianAssignmentIn, db: Session = Depends(get_db), actor: User = Depends(require_roles(*HEAD_ADMIN))):
    shift = db.get(Shift, body.shift_id)
    user = _active_user(db, body.custodian_id, "Custodian")
    if not shift or not shift.active:
        raise HTTPException(422, "Select an active shift")
    if user.role_id == ADMIN:
        raise HTTPException(422, "System administrators are not operational equipment custodians")
    if body.effective_to and body.effective_to < body.effective_from:
        raise HTTPException(422, "Assignment end date cannot precede its start date")
    row = EquipmentCustodianAssignment(shift_id=body.shift_id, custodian_id=body.custodian_id,
        effective_from=body.effective_from, effective_to=body.effective_to,
        assigned_by_id=actor.id, reason=body.reason)
    db.add(row); db.flush()
    _audit(db, actor, "equipment_custodian_assigned", "equipment_custodian_assignment", row.id,
           {"shift_id": body.shift_id, "custodian_id": body.custodian_id, "effective_from": body.effective_from.isoformat(),
            "effective_to": body.effective_to.isoformat() if body.effective_to else None})
    return {"id": row.id}


@router.post("/custodians/replacements", status_code=201)
def replace_custodian(body: CustodianReplacementIn, db: Session = Depends(get_db), actor: User = Depends(require_roles(*HEAD_ADMIN))):
    shift = db.get(Shift, body.shift_id)
    if not shift:
        raise HTTPException(404, "Shift not found")
    _active_user(db, body.original_custodian_id, "Original custodian")
    replacement = _active_user(db, body.replacement_custodian_id, "Replacement custodian")
    if body.original_custodian_id == body.replacement_custodian_id:
        raise HTTPException(422, "Replacement must be a different person")
    if replacement.role_id == ADMIN or body.original_custodian_id not in _roster(db, body.shift_id, body.shift_date):
        raise HTTPException(422, "Original custodian is not assigned for this shift and date")
    row = EquipmentCustodianReplacement(shift_id=body.shift_id, shift_date=body.shift_date,
        original_custodian_id=body.original_custodian_id, replacement_custodian_id=body.replacement_custodian_id,
        reason=body.reason, designated_by_id=actor.id)
    db.add(row); db.flush()
    _audit(db, actor, "equipment_custodian_replaced", "equipment_custodian_replacement", row.id,
           {"shift_id": body.shift_id, "shift_date": body.shift_date.isoformat(), "original": body.original_custodian_id,
            "replacement": body.replacement_custodian_id, "reason": body.reason})
    return {"id": row.id}


@router.get("/authorization-roles")
def get_authorization_roles(db: Session = Depends(get_db), actor: User = Depends(current_user)):
    roles = db.scalars(select(EquipmentAuthorizationRole).order_by(EquipmentAuthorizationRole.role_id)).all()
    return {"roles": [r.role_id for r in roles], "can_configure": actor.role_id == HEAD}


@router.put("/authorization-roles")
def set_authorization_roles(body: AuthorizationRolesIn, db: Session = Depends(get_db), actor: User = Depends(require_roles(HEAD))):
    role_ids = set(body.roles)
    if not role_ids.issubset({r.id for r in db.scalars(select(Role)).all()}):
        raise HTTPException(422, "One or more roles do not exist")
    for old in db.scalars(select(EquipmentAuthorizationRole)).all():
        db.delete(old)
    db.flush()
    for role_id in sorted(role_ids):
        db.add(EquipmentAuthorizationRole(role_id=role_id, configured_by_id=actor.id))
    _audit(db, actor, "equipment_authorization_roles_changed", "equipment_authorization_roles", "all", {"roles": sorted(role_ids)})
    return {"roles": sorted(role_ids)}


@router.get("/assets")
def list_assets(db: Session = Depends(get_db), actor: User = Depends(current_user)):
    assets = db.scalars(select(EquipmentAsset).order_by(EquipmentAsset.asset_tag)).all()
    return [_asset_json(db, a) for a in assets]


@router.post("/assets", status_code=201)
def create_asset(body: AssetCreate, db: Session = Depends(get_db), actor: User = Depends(require_roles(*HEAD_ADMIN))):
    if db.scalar(select(EquipmentAsset.id).where(EquipmentAsset.asset_tag == body.asset_tag)):
        raise HTTPException(409, "Asset number already exists")
    if body.condition not in ASSET_CONDITIONS:
        raise HTTPException(422, "Invalid condition")
    _active_user(db, body.responsible_user_id, "Responsible user")
    if body.department_id and not db.get(Department, body.department_id):
        raise HTTPException(422, "Department not found")
    data = body.model_dump()
    asset = EquipmentAsset(**data, created_by_id=actor.id)
    db.add(asset); db.flush()
    _audit(db, actor, "equipment_asset_created", "equipment_asset", asset.id,
           {"asset_tag": asset.asset_tag, "category": asset.category, "name": asset.name})
    return _asset_json(db, asset)


@router.patch("/assets/{asset_id}")
def update_asset(asset_id: int, body: AssetUpdate, db: Session = Depends(get_db), actor: User = Depends(require_roles(*HEAD_ADMIN))):
    asset = db.get(EquipmentAsset, asset_id)
    if not asset:
        raise HTTPException(404, "Asset not found")
    changes = {}
    for key, value in body.model_dump(exclude_unset=True).items():
        if key == "serial_number" and isinstance(value, str):
            value = value.strip() or None
        if key == "condition":
            if value not in ASSET_CONDITIONS:
                raise HTTPException(422, "Invalid condition")
            if asset.availability == "Damaged" and value != "Damaged":
                raise HTTPException(409, "Use the inspection workflow to clear a damage hold")
            if value == "Damaged" and asset.availability != "Damaged":
                changes["availability"] = {"from": asset.availability, "to": "Damaged"}
                asset.availability = "Damaged"
        if key == "responsible_user_id":
            _active_user(db, value, "Responsible user")
        if key == "department_id" and value and not db.get(Department, value):
            raise HTTPException(422, "Department not found")
        if getattr(asset, key) != value:
            changes[key] = {"from": getattr(asset, key).isoformat() if hasattr(getattr(asset, key), "isoformat") else getattr(asset, key),
                            "to": value.isoformat() if hasattr(value, "isoformat") else value}
            setattr(asset, key, value)
    if changes:
        _audit(db, actor, "equipment_asset_updated", "equipment_asset", asset.id, changes)
    return _asset_json(db, asset)


@router.post("/assets/{asset_id}/inspect")
def inspect_asset(asset_id: int, body: EquipmentInspectionIn, db: Session = Depends(get_db), actor: User = Depends(require_roles(*HEAD_ADMIN))):
    asset = db.get(EquipmentAsset, asset_id)
    if not asset:
        raise HTTPException(404, "Asset not found")
    if db.scalar(select(EquipmentIssueItem.id).where(
            EquipmentIssueItem.asset_id == asset_id, EquipmentIssueItem.returned_at.is_(None))):
        raise HTTPException(409, "Asset remains outstanding and cannot be inspected back into inventory")
    if body.condition not in ASSET_CONDITIONS or body.disposition not in {"Available", "Maintenance", "Damaged", "Retired"}:
        raise HTTPException(422, "Invalid inspection condition or disposition")
    if body.condition == "Damaged" and body.disposition == "Available":
        raise HTTPException(422, "A damaged item cannot be released as available")
    old = {"condition": asset.condition, "availability": asset.availability}
    asset.condition = body.condition
    asset.availability = body.disposition
    _audit(db, actor, "equipment_asset_inspected", "equipment_asset", asset.id,
           {"from": old, "to": {"condition": body.condition, "availability": body.disposition}, "notes": body.notes})
    return _asset_json(db, asset)


@router.post("/assets/{asset_id}/accessories", status_code=201)
def link_accessory(asset_id: int, body: AccessoryLinkIn, db: Session = Depends(get_db), actor: User = Depends(require_roles(*HEAD_ADMIN))):
    parent = db.get(EquipmentAsset, asset_id)
    accessory = db.get(EquipmentAsset, body.accessory_asset_id)
    if not parent or not accessory:
        raise HTTPException(404, "Asset not found")
    if parent.id == accessory.id:
        raise HTTPException(422, "An asset cannot be its own accessory")
    if db.scalar(select(EquipmentAccessoryLink.id).where(EquipmentAccessoryLink.accessory_asset_id == parent.id)):
        raise HTTPException(409, "An accessory cannot also contain other accessories")
    if db.scalar(select(EquipmentAccessoryLink.id).where(EquipmentAccessoryLink.parent_asset_id == accessory.id)):
        raise HTTPException(409, "An asset with accessories cannot be nested as an accessory")
    if db.scalar(select(EquipmentAccessoryLink.id).where(EquipmentAccessoryLink.parent_asset_id == parent.id,
                                                         EquipmentAccessoryLink.accessory_asset_id == accessory.id)):
        raise HTTPException(409, "Accessory is already linked")
    link = EquipmentAccessoryLink(parent_asset_id=parent.id, accessory_asset_id=accessory.id, linked_by_id=actor.id)
    db.add(link); db.flush()
    _audit(db, actor, "equipment_accessory_linked", "equipment_asset", parent.id,
           {"accessory_asset_id": accessory.id, "accessory_asset_tag": accessory.asset_tag})
    return {"id": link.id, "parent_asset_id": parent.id, "accessory_asset_id": accessory.id}


@router.post("/assets/{asset_id}/photo")
async def upload_asset_photo(asset_id: int, file: UploadFile = File(...), db: Session = Depends(get_db), actor: User = Depends(require_roles(*HEAD_ADMIN))):
    asset = db.get(EquipmentAsset, asset_id)
    if not asset:
        raise HTTPException(404, "Asset not found")
    data = await file.read(5 * 1024 * 1024 + 1)
    if len(data) > 5 * 1024 * 1024:
        raise HTTPException(413, "Photo exceeds 5 MB")
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        ext = ".png"
    elif data.startswith(b"\xff\xd8\xff"):
        ext = ".jpg"
    else:
        raise HTTPException(422, "Photo must be a real PNG or JPEG image")
    root = Path(settings.upload_dir).resolve() / "equipment"
    root.mkdir(parents=True, exist_ok=True)
    name = secrets.token_hex(24) + ext
    (root / name).write_bytes(data)
    old = asset.photo_name
    asset.photo_name = name
    _audit(db, actor, "equipment_asset_photo_changed", "equipment_asset", asset.id,
           {"photo_replaced": bool(old), "format": ext.lstrip(".")})
    if old:
        (root / old).unlink(missing_ok=True)
    return {"asset_id": asset.id, "has_photo": True}


@router.get("/assets/{asset_id}/photo")
def get_asset_photo(asset_id: int, db: Session = Depends(get_db), actor: User = Depends(current_user)):
    asset = db.get(EquipmentAsset, asset_id)
    if not asset or not asset.photo_name:
        raise HTTPException(404, "Asset photo not found")
    root = (Path(settings.upload_dir).resolve() / "equipment").resolve()
    path = (root / asset.photo_name).resolve()
    if path.parent != root or not path.is_file():
        raise HTTPException(404, "Asset photo not found")
    return FileResponse(path, media_type="image/png" if path.suffix == ".png" else "image/jpeg")


@router.get("/assets/{asset_id}/qr.svg")
def asset_qr(asset_id: int, db: Session = Depends(get_db), actor: User = Depends(current_user)):
    asset = db.get(EquipmentAsset, asset_id)
    if not asset:
        raise HTTPException(404, "Asset not found")
    image = qrcode.make(asset.asset_tag, image_factory=SvgPathImage)
    output = io.BytesIO(); image.save(output)
    return Response(output.getvalue(), media_type="image/svg+xml", headers={"Content-Disposition": f'inline; filename="{asset.asset_tag}.svg"'})


@router.post("/requests", status_code=201)
def create_issue_request(body: IssueRequestIn, db: Session = Depends(get_db), actor: User = Depends(current_user)):
    if _utc_naive(body.expected_return_at) <= datetime.utcnow():
        raise HTTPException(422, "Expected return time must be in the future")
    if not db.get(Shift, body.shift_id):
        raise HTTPException(422, "Shift not found")
    if body.external:
        if actor.role_id not in {HEAD, EDITOR} or body.borrower_id:
            raise HTTPException(403, "Only Head of Office or Editors can request external-office borrowing")
        borrower_id = None
    else:
        borrower_id = body.borrower_id or actor.id
        if borrower_id != actor.id and actor.role_id not in {HEAD, EDITOR}:
            raise HTTPException(403, "You may only request equipment for yourself")
        _active_user(db, borrower_id, "Borrower")
    asset_ids = set(body.asset_ids)
    if len(asset_ids) != len(body.asset_ids):
        raise HTTPException(422, "Each physical asset can appear only once in a request")
    selected = set(body.asset_ids)
    for asset_id in tuple(selected):
        asset = db.get(EquipmentAsset, asset_id)
        if not asset:
            raise HTTPException(422, f"Asset {asset_id} does not exist")
        selected.update(db.scalars(select(EquipmentAccessoryLink.accessory_asset_id).where(
            EquipmentAccessoryLink.parent_asset_id == asset_id)).all())
    assets = db.scalars(select(EquipmentAsset).where(EquipmentAsset.id.in_(selected))).all()
    if len(assets) != len(selected):
        raise HTTPException(422, "One or more accessories are not registered")
    unavailable = [a.asset_tag for a in assets if a.availability != "Available"]
    if unavailable:
        raise HTTPException(409, "Unavailable assets: " + ", ".join(unavailable))
    without_photos = [a.asset_tag for a in assets if not a.photo_name]
    if without_photos:
        raise HTTPException(422, "Register a private asset photograph before requesting: " + ", ".join(without_photos))
    borrower = db.get(User, borrower_id) if borrower_id else None
    issue = EquipmentIssue(requester_id=actor.id, borrower_id=borrower_id,
        borrower_name=borrower.full_name if borrower else body.borrower_name,
        borrower_office=body.borrower_office, external=body.external,
        shift_id=body.shift_id, shift_date=body.shift_date,
        expected_return_at=_utc_naive(body.expected_return_at), purpose=body.purpose,
        status="Pending authorization")
    db.add(issue); db.flush()
    for asset in assets:
        db.add(EquipmentIssueItem(issue_id=issue.id, asset_id=asset.id))
    db.flush()
    _audit(db, actor, "equipment_issue_requested", "equipment_issue", issue.id,
           {"asset_ids": sorted(selected), "external": issue.external, "borrower_office": issue.borrower_office,
            "expected_return_at": _timestamp(issue.expected_return_at)})
    return _issue_json(db, issue)


@router.get("/requests")
def list_issue_requests(db: Session = Depends(get_db), actor: User = Depends(current_user)):
    issues = db.scalars(select(EquipmentIssue).order_by(EquipmentIssue.requested_at.desc()).limit(500)).all()
    return [_issue_json(db, i) for i in issues if _issue_visible(db, i, actor)]


@router.post("/requests/{issue_id}/authorize")
def authorize_issue(issue_id: int, body: AuthorizationIn, db: Session = Depends(get_db), actor: User = Depends(current_user)):
    issue = db.get(EquipmentIssue, issue_id)
    if not issue:
        raise HTTPException(404, "Request not found")
    if issue.status != "Pending authorization":
        raise HTTPException(409, "Only a pending request can be authorized")
    if body.method not in AUTH_METHODS:
        raise HTTPException(422, "Select a listed authorization method")
    if body.method == "Head of Office authorization" and actor.role_id != HEAD:
        raise HTTPException(403, "Head of Office authorization must be recorded by the Head of Office")
    if body.method == "Editor authorization" and actor.role_id != EDITOR:
        raise HTTPException(403, "Editor authorization must be recorded by an Editor")
    allowed = set(db.scalars(select(EquipmentAuthorizationRole.role_id)).all())
    if actor.role_id not in allowed:
        raise HTTPException(403, "Your role is not authorized to approve equipment borrowing")
    issue.authorized_by_id = actor.id
    issue.authorized_role_id = actor.role_id
    issue.authorization_method = body.method
    issue.authorization_remarks = body.remarks
    issue.authorized_at = datetime.utcnow()
    issue.status = "Authorized"
    for item in db.scalars(select(EquipmentIssueItem).where(EquipmentIssueItem.issue_id == issue.id)).all():
        _issue_event(db, issue, item, actor, "authorized", details=json.dumps({
            "authorization_method": body.method, "authorizer_role_id": actor.role_id,
            "authorization_remarks": body.remarks}, ensure_ascii=False, sort_keys=True))
    _audit(db, actor, "equipment_issue_authorized", "equipment_issue", issue.id,
           {"authorized_role_id": actor.role_id, "method": body.method, "remarks": body.remarks})
    return _issue_json(db, issue)


@router.post("/requests/{issue_id}/issue")
def issue_equipment(issue_id: int, body: IssueIn, db: Session = Depends(get_db), actor: User = Depends(current_user)):
    issue = db.get(EquipmentIssue, issue_id)
    if not issue:
        raise HTTPException(404, "Request not found")
    if issue.status != "Authorized" or not issue.authorized_by_id or not issue.authorized_at:
        raise HTTPException(409, "A recorded authorization is required before physical issue")
    if issue.shift_date != _office_today():
        raise HTTPException(409, "Physical issue must be recorded on the scheduled shift date")
    _require_custodian(db, actor, issue.shift_id, issue.shift_date)
    if set(body.conditions) != {str(i.asset_id) for i in db.scalars(select(EquipmentIssueItem).where(EquipmentIssueItem.issue_id == issue.id)).all()}:
        raise HTTPException(422, "Record the pre-issue condition for every requested physical asset")
    items = db.scalars(select(EquipmentIssueItem).where(EquipmentIssueItem.issue_id == issue.id)).all()
    locked_assets = db.scalars(select(EquipmentAsset).where(
        EquipmentAsset.id.in_([item.asset_id for item in items])).order_by(EquipmentAsset.id).with_for_update()).all()
    assets_by_id = {asset.id: asset for asset in locked_assets}
    for item in items:
        asset = assets_by_id[item.asset_id]
        condition = body.conditions[str(item.asset_id)]
        if condition not in ASSET_CONDITIONS:
            raise HTTPException(422, f"Invalid condition for {asset.asset_tag}")
        if asset.availability != "Available":
            raise HTTPException(409, f"{asset.asset_tag} is no longer available")
    issue.issued_by_id = actor.id
    issue.issued_at = datetime.utcnow()
    issue.status = "Issued"
    for item in items:
        asset = db.get(EquipmentAsset, item.asset_id)
        item.condition_before = body.conditions[str(item.asset_id)]
        item.location_before_issue = asset.location
        item.responsible_user_before_issue_id = asset.responsible_user_id
        item.department_before_issue_id = asset.department_id
        asset.availability = "Issued"
        asset.location = issue.borrower_office
        asset.responsible_user_id = issue.borrower_id
        _issue_event(db, issue, item, actor, "issued", item.condition_before,
                     f"Issued by custodian {actor.full_name}; authorized by {issue.authorized_by_id}")
    _audit(db, actor, "equipment_physically_issued", "equipment_issue", issue.id,
           {"custodian_id": actor.id, "asset_ids": [i.asset_id for i in items]})
    return _issue_json(db, issue)


@router.post("/requests/{issue_id}/acknowledge")
def acknowledge_borrowing(issue_id: int, body: BorrowerAckIn, db: Session = Depends(get_db), actor: User = Depends(current_user)):
    issue = db.get(EquipmentIssue, issue_id)
    if not issue:
        raise HTTPException(404, "Request not found")
    if issue.status not in {"Issued", "Partially returned"}:
        raise HTTPException(409, "The equipment has not been issued")
    if issue.borrower_acknowledged_at:
        raise HTTPException(409, "Borrower acknowledgement is already recorded")
    if issue.external:
        if actor.id not in _roster(db, issue.shift_id, issue.shift_date) or not body.acknowledged or not body.borrower_name or body.borrower_name.strip().casefold() != issue.borrower_name.strip().casefold():
            raise HTTPException(403, "The shift custodian must record the external borrower's matching acknowledgement")
        issue.borrower_acknowledged_by_id = actor.id
        issue.borrower_acknowledged_name = body.borrower_name.strip()
    else:
        if actor.id != issue.borrower_id or not body.acknowledged:
            raise HTTPException(403, "Only the named borrower can acknowledge receipt")
        issue.borrower_acknowledged_by_id = actor.id
        issue.borrower_acknowledged_name = actor.full_name
    issue.borrower_acknowledged_at = datetime.utcnow()
    for item in db.scalars(select(EquipmentIssueItem).where(EquipmentIssueItem.issue_id == issue.id)).all():
        _issue_event(db, issue, item, actor, "borrower_acknowledged", details=issue.borrower_acknowledged_name or "")
    _audit(db, actor, "equipment_borrower_acknowledged", "equipment_issue", issue.id,
           {"borrower_id": issue.borrower_id, "borrower_name": issue.borrower_acknowledged_name})
    return _issue_json(db, issue)


@router.post("/requests/{issue_id}/return")
def return_equipment(issue_id: int, body: ReturnIn, db: Session = Depends(get_db), actor: User = Depends(current_user)):
    issue = db.get(EquipmentIssue, issue_id)
    if not issue:
        raise HTTPException(404, "Request not found")
    if issue.status not in {"Issued", "Partially returned"}:
        raise HTTPException(409, "Only outstanding issued equipment can be returned")
    if body.shift_date != _office_today():
        raise HTTPException(409, "A physical return must be recorded on its actual office-local date")
    _require_custodian(db, actor, body.shift_id, body.shift_date)
    if not body.returned and not body.missing_asset_ids:
        raise HTTPException(422, "Record at least one physically returned or reported-missing item")
    if len({r.asset_id for r in body.returned}) != len(body.returned) or len(set(body.missing_asset_ids)) != len(body.missing_asset_ids):
        raise HTTPException(422, "Duplicate items are not allowed")
    if set(r.asset_id for r in body.returned).intersection(body.missing_asset_ids):
        raise HTTPException(422, "An item cannot be both returned and reported missing in one action")
    items = {i.asset_id: i for i in db.scalars(select(EquipmentIssueItem).where(
        EquipmentIssueItem.issue_id == issue.id).with_for_update()).all()}
    for returned in body.returned:
        item = items.get(returned.asset_id)
        if not item or item.returned_at:
            raise HTTPException(409, "An item is not outstanding on this request")
        if returned.condition not in ASSET_CONDITIONS:
            raise HTTPException(422, "Invalid return condition")
    for asset_id in body.missing_asset_ids:
        if asset_id not in items or items[asset_id].returned_at:
            raise HTTPException(409, "A missing item must be an outstanding item on this request")
    now = datetime.utcnow()
    for returned in body.returned:
        item = items[returned.asset_id]
        asset = db.get(EquipmentAsset, item.asset_id)
        item.returned_at = now
        item.received_by_id = actor.id
        item.return_condition = returned.condition
        item.damage_notes = returned.damage_notes
        item.missing_reported = False
        if returned.condition == "Damaged" or returned.damage_notes:
            asset.condition = "Damaged"
            asset.availability = "Damaged"
        else:
            asset.condition = returned.condition
            asset.availability = "Available"
        asset.location = item.location_before_issue or "Equipment store"
        asset.responsible_user_id = item.responsible_user_before_issue_id
        asset.department_id = item.department_before_issue_id
        _issue_event(db, issue, item, actor, "returned", returned.condition,
                     f"Received by custodian {actor.full_name}; damage: {returned.damage_notes}",
                     shift_id=body.shift_id, shift_date=body.shift_date)
        if returned.condition == "Damaged" or returned.damage_notes:
            _issue_event(db, issue, item, actor, "damage_recorded", returned.condition, returned.damage_notes,
                         shift_id=body.shift_id, shift_date=body.shift_date)
    for asset_id in body.missing_asset_ids:
        item = items[asset_id]
        item.missing_reported = True
        db.get(EquipmentAsset, asset_id).availability = "Missing"
        _issue_event(db, issue, item, actor, "missing_reported", details=body.notes,
                     shift_id=body.shift_id, shift_date=body.shift_date)
    remains = db.scalar(select(EquipmentIssueItem.id).where(
        EquipmentIssueItem.issue_id == issue.id, EquipmentIssueItem.returned_at.is_(None)))
    issue.status = "Partially returned" if remains else "Returned"
    _audit(db, actor, "equipment_partial_return_recorded" if remains else "equipment_issue_returned",
           "equipment_issue", issue.id,
           {"receiving_custodian_id": actor.id, "returned_asset_ids": [x.asset_id for x in body.returned],
            "missing_asset_ids": body.missing_asset_ids, "remaining_outstanding": bool(remains),
            "receiving_shift_id": body.shift_id, "receiving_shift_date": body.shift_date.isoformat()})
    return _issue_json(db, issue)


@router.post("/handovers", status_code=201)
def create_handover(body: HandoverIn, db: Session = Depends(get_db), actor: User = Depends(current_user)):
    if body.outgoing_custodian_id == body.incoming_custodian_id:
        raise HTTPException(422, "Outgoing and incoming custodians must differ")
    if actor.role_id not in {HEAD, ADMIN} and actor.id not in {body.outgoing_custodian_id, body.incoming_custodian_id}:
        raise HTTPException(403, "Only a custodian in this handover or management can create it")
    if not db.get(Shift, body.outgoing_shift_id) or not db.get(Shift, body.incoming_shift_id):
        raise HTTPException(422, "Both shifts must exist")
    outgoing_roster = _roster(db, body.outgoing_shift_id, body.shift_date)
    incoming_roster = _roster(db, body.incoming_shift_id, body.shift_date)
    if body.outgoing_custodian_id not in outgoing_roster or body.incoming_custodian_id not in incoming_roster:
        raise HTTPException(422, "Outgoing and incoming custodians must be assigned or designated for their respective shifts")
    row = EquipmentHandover(outgoing_shift_id=body.outgoing_shift_id, incoming_shift_id=body.incoming_shift_id,
        shift_date=body.shift_date, outgoing_custodian_id=body.outgoing_custodian_id, incoming_custodian_id=body.incoming_custodian_id,
        created_by_id=actor.id, discrepancies=body.discrepancies)
    db.add(row); db.flush()
    outstanding = db.scalars(select(EquipmentIssueItem).join(EquipmentIssue).where(
        EquipmentIssueItem.returned_at.is_(None), EquipmentIssue.status.in_(["Issued", "Partially returned"]))).all()
    for item in outstanding:
        asset = db.get(EquipmentAsset, item.asset_id)
        db.add(EquipmentHandoverLine(handover_id=row.id, issue_item_id=item.id,
            asset_id=item.asset_id, asset_tag_snapshot=asset.asset_tag))
        issue = db.get(EquipmentIssue, item.issue_id)
        _issue_event(db, issue, item, actor, "custody_handover_created",
                     details=json.dumps({"handover_id": row.id, "outgoing_custodian_id": row.outgoing_custodian_id,
                         "incoming_custodian_id": row.incoming_custodian_id,
                         "outgoing_shift_id": row.outgoing_shift_id, "incoming_shift_id": row.incoming_shift_id}, sort_keys=True),
                     shift_id=row.outgoing_shift_id, shift_date=row.shift_date)
    db.flush()
    _audit(db, actor, "equipment_custody_handover_created", "equipment_handover", row.id,
           {"outgoing_shift_id": row.outgoing_shift_id, "incoming_shift_id": row.incoming_shift_id,
            "shift_date": row.shift_date.isoformat(), "outgoing_custodian_id": row.outgoing_custodian_id,
            "incoming_custodian_id": row.incoming_custodian_id,
            "outstanding_issue_item_ids": [i.id for i in outstanding]})
    return _handover_json(db, row)


def _handover_json(db: Session, row: EquipmentHandover) -> dict:
    outgoing = db.get(User, row.outgoing_custodian_id)
    incoming = db.get(User, row.incoming_custodian_id)
    outgoing_shift = db.get(Shift, row.outgoing_shift_id)
    incoming_shift = db.get(Shift, row.incoming_shift_id)
    lines = db.scalars(select(EquipmentHandoverLine).where(EquipmentHandoverLine.handover_id == row.id)).all()
    outstanding_items = []
    for line in lines:
        issue_item = db.get(EquipmentIssueItem, line.issue_item_id)
        issue = db.get(EquipmentIssue, issue_item.issue_id)
        outstanding_items.append({"issue_item_id": line.issue_item_id, "issue_id": issue.id,
            "asset_id": line.asset_id, "asset_tag": line.asset_tag_snapshot,
            "borrower_name": issue.borrower_name, "borrower_office": issue.borrower_office,
            "expected_return_at": _timestamp(issue.expected_return_at),
            "currently_outstanding": issue_item.returned_at is None})
    return {"id": row.id, "outgoing_shift_id": row.outgoing_shift_id,
        "outgoing_shift": outgoing_shift.name if outgoing_shift else "",
        "incoming_shift_id": row.incoming_shift_id,
        "incoming_shift": incoming_shift.name if incoming_shift else "",
        "shift_date": row.shift_date.isoformat(), "outgoing_custodian_id": row.outgoing_custodian_id,
        "outgoing_custodian": outgoing.full_name if outgoing else "Unknown",
        "incoming_custodian_id": row.incoming_custodian_id,
        "incoming_custodian": incoming.full_name if incoming else "Unknown",
        "created_at": _timestamp(row.created_at), "outgoing_ack_at": _timestamp(row.outgoing_ack_at),
        "incoming_ack_at": _timestamp(row.incoming_ack_at),
        "discrepancies": row.discrepancies, "reviewed_by_id": row.reviewed_by_id,
        "reviewed_at": _timestamp(row.reviewed_at), "review_comment": row.review_comment,
        "outstanding_items": outstanding_items}


@router.get("/handovers")
def list_handovers(db: Session = Depends(get_db), actor: User = Depends(current_user)):
    rows = db.scalars(select(EquipmentHandover).order_by(EquipmentHandover.created_at.desc()).limit(300)).all()
    visible = [r for r in rows if actor.role_id in {HEAD, ADMIN} or actor.id in {r.outgoing_custodian_id, r.incoming_custodian_id}]
    return [_handover_json(db, r) for r in visible]


@router.post("/handovers/{handover_id}/acknowledge")
def acknowledge_handover(handover_id: int, body: HandoverAckIn, db: Session = Depends(get_db), actor: User = Depends(current_user)):
    row = db.get(EquipmentHandover, handover_id)
    if not row:
        raise HTTPException(404, "Handover not found")
    now = datetime.utcnow()
    if actor.id == row.outgoing_custodian_id:
        if row.outgoing_ack_at:
            raise HTTPException(409, "Outgoing custodian already acknowledged")
        row.outgoing_ack_at = now
    elif actor.id == row.incoming_custodian_id:
        if row.incoming_ack_at:
            raise HTTPException(409, "Incoming custodian already acknowledged")
        row.incoming_ack_at = now
    else:
        raise HTTPException(403, "Only the named custodians can acknowledge this handover")
    if body.discrepancies.strip():
        row.discrepancies = (row.discrepancies + "\n" + f"{actor.full_name}: {body.discrepancies.strip()}").strip()
    for line in db.scalars(select(EquipmentHandoverLine).where(EquipmentHandoverLine.handover_id == row.id)).all():
        item = db.get(EquipmentIssueItem, line.issue_item_id)
        issue = db.get(EquipmentIssue, item.issue_id)
        _issue_event(db, issue, item, actor, "custody_handover_acknowledged",
                     details=json.dumps({"handover_id": row.id, "discrepancies": body.discrepancies}, ensure_ascii=False))
    _audit(db, actor, "equipment_handover_acknowledged", "equipment_handover", row.id,
           {"custodian_id": actor.id, "discrepancies": body.discrepancies})
    return _handover_json(db, row)


@router.post("/handovers/{handover_id}/review")
def review_handover(handover_id: int, body: HandoverReviewIn, db: Session = Depends(get_db), actor: User = Depends(require_roles(HEAD))):
    row = db.get(EquipmentHandover, handover_id)
    if not row:
        raise HTTPException(404, "Handover not found")
    if not row.outgoing_ack_at or not row.incoming_ack_at:
        raise HTTPException(409, "Both custodians must acknowledge before management review")
    row.reviewed_by_id = actor.id; row.reviewed_at = datetime.utcnow(); row.review_comment = body.comment
    for line in db.scalars(select(EquipmentHandoverLine).where(EquipmentHandoverLine.handover_id == row.id)).all():
        item = db.get(EquipmentIssueItem, line.issue_item_id)
        issue = db.get(EquipmentIssue, item.issue_id)
        _issue_event(db, issue, item, actor, "custody_handover_reviewed",
                     details=json.dumps({"handover_id": row.id, "comment": body.comment}, ensure_ascii=False))
    _audit(db, actor, "equipment_handover_reviewed", "equipment_handover", row.id, {"comment": body.comment})
    return _handover_json(db, row)


@router.get("/dashboard")
def equipment_dashboard(db: Session = Depends(get_db), actor: User = Depends(current_user)):
    utc_now = datetime.utcnow(); local_now = _office_now(); today = local_now.date()
    shifts = db.scalars(select(Shift).where(Shift.active.is_(True)).order_by(Shift.start_time)).all()
    current = next((s for s in shifts if s.start_time <= local_now.strftime("%H:%M") < s.end_time), None)
    ordered = shifts
    previous = None; incoming = None
    if current and ordered:
        idx = ordered.index(current); previous = ordered[(idx - 1) % len(ordered)]; incoming = ordered[(idx + 1) % len(ordered)]
    def custodian_rows(shift):
        if not shift: return []
        return [{"id": uid, "name": db.get(User, uid).full_name} for uid in _roster(db, shift.id, today) if db.get(User, uid)]
    count = lambda query: len(db.scalars(query).all())
    issued_events = db.scalars(select(EquipmentItemEvent).where(
        EquipmentItemEvent.event_type == "issued", EquipmentItemEvent.shift_id == current.id,
        EquipmentItemEvent.shift_date == today) if current else select(EquipmentItemEvent).where(False)).all()
    returned_events = db.scalars(select(EquipmentItemEvent).where(
        EquipmentItemEvent.event_type == "returned", EquipmentItemEvent.shift_id == current.id,
        EquipmentItemEvent.shift_date == today) if current else select(EquipmentItemEvent).where(False)).all()
    return {
        "date": today.isoformat(), "current_shift": {"id": current.id, "name": current.name} if current else None,
        "current_shift_custodians": custodian_rows(current),
        "previous_shift": {"id": previous.id, "name": previous.name} if previous else None,
        "previous_shift_custodians": custodian_rows(previous),
        "incoming_shift": {"id": incoming.id, "name": incoming.name} if incoming else None,
        "incoming_shift_custodians": custodian_rows(incoming),
        "equipment_in_custody": count(select(EquipmentAsset).where(EquipmentAsset.availability == "Issued")),
        "issued_during_current_shift": len(issued_events),
        "returned_during_current_shift": len(returned_events),
        "outstanding_equipment": count(select(EquipmentIssueItem).join(EquipmentIssue).where(
            EquipmentIssueItem.returned_at.is_(None), EquipmentIssue.status.in_(["Issued", "Partially returned"]))),
        "overdue_equipment": count(select(EquipmentIssueItem).join(EquipmentIssue).where(
            EquipmentIssueItem.returned_at.is_(None), EquipmentIssue.status.in_(["Issued", "Partially returned"]),
            EquipmentIssue.expected_return_at < utc_now)),
        "missing_equipment": count(select(EquipmentAsset).where(EquipmentAsset.availability == "Missing")),
        "damaged_equipment": count(select(EquipmentAsset).where(EquipmentAsset.availability == "Damaged")),
        "pending_authorization": count(select(EquipmentIssue).where(EquipmentIssue.status == "Pending authorization")),
        "awaiting_inspection": count(select(EquipmentAsset).where(EquipmentAsset.availability == "Damaged")),
    }


@router.get("/reports/{report_name}")
def equipment_report(report_name: str, db: Session = Depends(get_db), actor: User = Depends(require_roles(HEAD, ADMIN))):
    allowed = {"custodians", "issued-by-custodian", "received-by-custodian", "currently-borrowed",
               "external-borrowing", "overdue", "missing", "damaged", "handovers"}
    if report_name not in allowed:
        raise HTTPException(404, "Equipment report not found")
    if report_name == "custodians":
        rows = db.scalars(select(EquipmentCustodianAssignment).order_by(EquipmentCustodianAssignment.shift_id,
            EquipmentCustodianAssignment.effective_from.desc())).all()
        replacements = db.scalars(select(EquipmentCustodianReplacement).order_by(
            EquipmentCustodianReplacement.shift_date.desc())).all()
        handovers = db.scalars(select(EquipmentHandover).order_by(EquipmentHandover.created_at.desc())).all()
        return {"assignments": [{"assignment_id": r.id, "shift_id": r.shift_id, "shift": db.get(Shift, r.shift_id).name,
            "custodian_id": r.custodian_id, "custodian": db.get(User, r.custodian_id).full_name,
            "effective_from": r.effective_from.isoformat(), "effective_to": r.effective_to.isoformat() if r.effective_to else None,
            "assigned_by": db.get(User, r.assigned_by_id).full_name, "assigned_at": _timestamp(r.assigned_at),
            "reason": r.reason} for r in rows],
            "replacements": [{"shift_id": r.shift_id, "shift": db.get(Shift, r.shift_id).name,
                "shift_date": r.shift_date.isoformat(), "original_custodian": db.get(User, r.original_custodian_id).full_name,
                "replacement_custodian": db.get(User, r.replacement_custodian_id).full_name,
                "designated_by": db.get(User, r.designated_by_id).full_name, "created_at": _timestamp(r.created_at),
                "reason": r.reason} for r in replacements],
            "handovers": [_handover_json(db, r) for r in handovers]}
    if report_name == "issued-by-custodian":
        rows = db.scalars(select(EquipmentIssue).where(EquipmentIssue.issued_by_id.is_not(None)).order_by(EquipmentIssue.issued_at.desc())).all()
        return [_issue_json(db, r) for r in rows]
    if report_name == "received-by-custodian":
        events = db.scalars(select(EquipmentItemEvent).where(EquipmentItemEvent.event_type == "returned").order_by(EquipmentItemEvent.happened_at.desc())).all()
        return [{"event_id": e.id, "received_by_id": e.actor_id, "received_by": db.get(User, e.actor_id).full_name,
            "asset_id": e.asset_id, "asset_tag": db.get(EquipmentAsset, e.asset_id).asset_tag,
            "issue_id": e.issue_id, "condition": e.condition, "received_at": _timestamp(e.happened_at), "details": e.details} for e in events]
    if report_name in {"currently-borrowed", "external-borrowing", "overdue"}:
        query = select(EquipmentIssue).order_by(EquipmentIssue.expected_return_at)
        if report_name == "external-borrowing": query = query.where(EquipmentIssue.external.is_(True), EquipmentIssue.status.in_(["Issued", "Partially returned", "Returned"]))
        else: query = query.where(EquipmentIssue.status.in_(["Issued", "Partially returned"]))
        if report_name == "overdue": query = query.where(EquipmentIssue.expected_return_at < datetime.utcnow())
        return [_issue_json(db, r) for r in db.scalars(query).all()]
    if report_name in {"missing", "damaged"}:
        target = "Missing" if report_name == "missing" else "Damaged"
        assets = db.scalars(select(EquipmentAsset).where(EquipmentAsset.availability == target).order_by(EquipmentAsset.asset_tag)).all()
        return [_asset_json(db, a) for a in assets]
    rows = db.scalars(select(EquipmentHandover).order_by(EquipmentHandover.created_at.desc())).all()
    return [_handover_json(db, r) for r in rows]


@router.get("/reports/assets/{asset_id}/history")
def asset_history(asset_id: int, db: Session = Depends(get_db), actor: User = Depends(require_roles(HEAD, ADMIN))):
    asset = db.get(EquipmentAsset, asset_id)
    if not asset:
        raise HTTPException(404, "Asset not found")
    events = db.scalars(select(EquipmentItemEvent).where(EquipmentItemEvent.asset_id == asset_id).order_by(EquipmentItemEvent.happened_at)).all()
    audits = db.scalars(select(AuditLog).where(AuditLog.entity_type == "equipment_asset", AuditLog.entity_id == str(asset_id)).order_by(AuditLog.created_at)).all()
    return {"asset": _asset_json(db, asset),
        "events": [{"event_type": e.event_type, "actor_id": e.actor_id, "actor": db.get(User, e.actor_id).full_name,
                    "issue_id": e.issue_id, "condition": e.condition, "details": e.details,
                    "happened_at": _timestamp(e.happened_at)} for e in events],
        "changes": [{"action": a.action, "actor_id": a.actor_id,
                     "actor": db.get(User, a.actor_id).full_name if a.actor_id else "System",
                     "details": a.details, "created_at": _timestamp(a.created_at)} for a in audits]}
