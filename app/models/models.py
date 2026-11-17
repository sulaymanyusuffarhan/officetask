from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


def utcnow() -> datetime:
    return datetime.utcnow()


class Role(Base):
    __tablename__ = "roles"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    name: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    users: Mapped[list["User"]] = relationship(back_populates="role")


class Department(Base):
    __tablename__ = "departments"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class Shift(Base):
    __tablename__ = "shifts"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    start_time: Mapped[str] = mapped_column(String(5), nullable=False, default="08:00")
    end_time: Mapped[str] = mapped_column(String(5), nullable=False, default="16:00")
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(80), unique=True, index=True, nullable=False)
    full_name: Mapped[str] = mapped_column(String(160), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role_id: Mapped[str] = mapped_column(ForeignKey("roles.id"), index=True, nullable=False)
    department_id: Mapped[int | None] = mapped_column(ForeignKey("departments.id"))
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    role: Mapped[Role] = relationship(back_populates="users")
    department: Mapped[Department | None] = relationship()


class Timetable(Base):
    __tablename__ = "timetables"
    __table_args__ = (UniqueConstraint("week_start", "version", name="uq_timetable_week_version"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    week_start: Mapped[date] = mapped_column(Date, index=True, nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="Draft", index=True, nullable=False)
    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("timetables.id"))
    approval_comment: Mapped[str | None] = mapped_column(Text)
    change_reason: Mapped[str | None] = mapped_column(Text)
    approved_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    published_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    assignments: Mapped[list["TimetableAssignment"]] = relationship(back_populates="timetable", cascade="all, delete-orphan")


class TimetableAssignment(Base):
    __tablename__ = "timetable_assignments"
    id: Mapped[int] = mapped_column(primary_key=True)
    timetable_id: Mapped[int] = mapped_column(ForeignKey("timetables.id", ondelete="CASCADE"), index=True, nullable=False)
    work_date: Mapped[date] = mapped_column(Date, index=True, nullable=False)
    shift_id: Mapped[int] = mapped_column(ForeignKey("shifts.id"), nullable=False)
    employee_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    leader_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    editor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    department_id: Mapped[int | None] = mapped_column(ForeignKey("departments.id"))
    responsibility: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    timetable: Mapped[Timetable] = relationship(back_populates="assignments")
    shift: Mapped[Shift] = relationship()
    employee: Mapped[User] = relationship(foreign_keys=[employee_id])
    leader: Mapped[User | None] = relationship(foreign_keys=[leader_id])
    editor: Mapped[User | None] = relationship(foreign_keys=[editor_id])


class Task(Base):
    __tablename__ = "tasks"
    __table_args__ = (UniqueConstraint("reference", name="uq_task_reference"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    reference: Mapped[str] = mapped_column(String(30), index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(180), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    instructions: Mapped[str] = mapped_column(Text, default="", nullable=False)
    employee_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    assigner_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    department_id: Mapped[int | None] = mapped_column(ForeignKey("departments.id"))
    shift_id: Mapped[int | None] = mapped_column(ForeignKey("shifts.id"))
    assignment_date: Mapped[date] = mapped_column(Date, default=date.today, nullable=False)
    start_date: Mapped[date] = mapped_column(Date, default=date.today, nullable=False)
    deadline: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    priority: Mapped[str] = mapped_column(String(12), default="Normal", nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="Assigned", index=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    history: Mapped[list["TaskHistory"]] = relationship(back_populates="task", cascade="all, delete-orphan")
    submissions: Mapped[list["Submission"]] = relationship(back_populates="task", cascade="all, delete-orphan")
    employee: Mapped[User] = relationship(foreign_keys=[employee_id])
    assigner: Mapped[User] = relationship(foreign_keys=[assigner_id])


class TaskHistory(Base):
    __tablename__ = "task_history"
    id: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), index=True, nullable=False)
    actor_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    old_status: Mapped[str | None] = mapped_column(String(30))
    new_status: Mapped[str] = mapped_column(String(30), nullable=False)
    note: Mapped[str] = mapped_column(Text, default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    task: Mapped[Task] = relationship(back_populates="history")


class Submission(Base):
    __tablename__ = "submissions"
    id: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), index=True, nullable=False)
    employee_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    report: Mapped[str] = mapped_column(Text, nullable=False)
    notes: Mapped[str] = mapped_column(Text, default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    task: Mapped[Task] = relationship(back_populates="submissions")
    attachments: Mapped[list["Attachment"]] = relationship(back_populates="submission", cascade="all, delete-orphan")


class Attachment(Base):
    __tablename__ = "attachments"
    id: Mapped[int] = mapped_column(primary_key=True)
    submission_id: Mapped[int] = mapped_column(ForeignKey("submissions.id", ondelete="CASCADE"), index=True, nullable=False)
    original_name: Mapped[str] = mapped_column(String(255), nullable=False)
    stored_name: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    media_type: Mapped[str] = mapped_column(String(100), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    submission: Mapped[Submission] = relationship(back_populates="attachments")


class Verification(Base):
    __tablename__ = "verifications"
    id: Mapped[int] = mapped_column(primary_key=True)
    submission_id: Mapped[int] = mapped_column(ForeignKey("submissions.id", ondelete="CASCADE"), index=True, nullable=False)
    reviewer_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    decision: Mapped[str] = mapped_column(String(30), nullable=False)
    comment: Mapped[str] = mapped_column(Text, default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)


class ShiftReport(Base):
    __tablename__ = "shift_reports"
    id: Mapped[int] = mapped_column(primary_key=True)
    submitted_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    shift_id: Mapped[int | None] = mapped_column(ForeignKey("shifts.id"))
    report_date: Mapped[date] = mapped_column(Date, index=True, nullable=False)
    unfinished: Mapped[str] = mapped_column(Text, default="", nullable=False)
    challenges: Mapped[str] = mapped_column(Text, default="", nullable=False)
    handover: Mapped[str] = mapped_column(Text, default="", nullable=False)
    attendance_notes: Mapped[str] = mapped_column(Text, default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)


class AttendanceRecord(Base):
    __tablename__ = "attendance_records"
    __table_args__ = (UniqueConstraint("employee_id", "work_date", name="uq_attendance_employee_date"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    work_date: Mapped[date] = mapped_column(Date, index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    reason: Mapped[str] = mapped_column(Text, default="", nullable=False)
    approved_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[int] = mapped_column(primary_key=True)
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True)
    action: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    entity_type: Mapped[str] = mapped_column(String(80), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(80), nullable=False)
    details: Mapped[str] = mapped_column(Text, default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True, nullable=False)


class EquipmentAsset(Base):
    __tablename__ = "equipment_assets"
    id: Mapped[int] = mapped_column(primary_key=True)
    asset_tag: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    category: Mapped[str] = mapped_column(String(80), index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    brand: Mapped[str] = mapped_column(String(100), default="", nullable=False)
    model: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    serial_number: Mapped[str | None] = mapped_column(String(120), unique=True)
    internal_tag: Mapped[str] = mapped_column(String(100), default="", nullable=False)
    photo_name: Mapped[str | None] = mapped_column(String(100), unique=True)
    location: Mapped[str] = mapped_column(String(160), default="Equipment store", nullable=False)
    responsible_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    department_id: Mapped[int | None] = mapped_column(ForeignKey("departments.id"))
    condition: Mapped[str] = mapped_column(String(30), default="Good", nullable=False)
    availability: Mapped[str] = mapped_column(String(30), default="Available", index=True, nullable=False)
    purchase_date: Mapped[date | None] = mapped_column(Date)
    warranty_until: Mapped[date | None] = mapped_column(Date)
    notes: Mapped[str] = mapped_column(Text, default="", nullable=False)
    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)


class EquipmentAccessoryLink(Base):
    __tablename__ = "equipment_accessory_links"
    __table_args__ = (UniqueConstraint("parent_asset_id", "accessory_asset_id", name="uq_equipment_accessory_pair"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    parent_asset_id: Mapped[int] = mapped_column(ForeignKey("equipment_assets.id"), index=True, nullable=False)
    accessory_asset_id: Mapped[int] = mapped_column(ForeignKey("equipment_assets.id"), index=True, nullable=False)
    linked_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    linked_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)


class EquipmentCustodianAssignment(Base):
    __tablename__ = "equipment_custodian_assignments"
    __table_args__ = (UniqueConstraint("shift_id", "custodian_id", "effective_from", name="uq_equipment_shift_custodian_start"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    shift_id: Mapped[int] = mapped_column(ForeignKey("shifts.id"), index=True, nullable=False)
    custodian_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    effective_from: Mapped[date] = mapped_column(Date, index=True, nullable=False)
    effective_to: Mapped[date | None] = mapped_column(Date, index=True)
    assigned_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    assigned_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    reason: Mapped[str] = mapped_column(Text, default="", nullable=False)


class EquipmentCustodianReplacement(Base):
    __tablename__ = "equipment_custodian_replacements"
    __table_args__ = (UniqueConstraint("shift_id", "shift_date", "original_custodian_id", name="uq_equipment_custodian_replacement_date"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    shift_id: Mapped[int] = mapped_column(ForeignKey("shifts.id"), index=True, nullable=False)
    shift_date: Mapped[date] = mapped_column(Date, index=True, nullable=False)
    original_custodian_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    replacement_custodian_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    designated_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)


class EquipmentAuthorizationRole(Base):
    __tablename__ = "equipment_authorization_roles"
    role_id: Mapped[str] = mapped_column(ForeignKey("roles.id"), primary_key=True)
    configured_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    configured_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)


class EquipmentIssue(Base):
    __tablename__ = "equipment_issues"
    id: Mapped[int] = mapped_column(primary_key=True)
    requester_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    borrower_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True)
    borrower_name: Mapped[str] = mapped_column(String(160), nullable=False)
    borrower_office: Mapped[str] = mapped_column(String(160), default="Office", nullable=False)
    external: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    requested_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    shift_id: Mapped[int] = mapped_column(ForeignKey("shifts.id"), nullable=False)
    shift_date: Mapped[date] = mapped_column(Date, index=True, nullable=False)
    expected_return_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    purpose: Mapped[str] = mapped_column(Text, default="", nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="Pending authorization", index=True, nullable=False)
    authorized_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    authorized_role_id: Mapped[str | None] = mapped_column(String(40))
    authorization_method: Mapped[str | None] = mapped_column(String(40))
    authorization_remarks: Mapped[str] = mapped_column(Text, default="", nullable=False)
    authorized_at: Mapped[datetime | None] = mapped_column(DateTime)
    issued_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    issued_at: Mapped[datetime | None] = mapped_column(DateTime)
    borrower_acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime)
    borrower_acknowledged_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    borrower_acknowledged_name: Mapped[str | None] = mapped_column(String(160))


class EquipmentIssueItem(Base):
    __tablename__ = "equipment_issue_items"
    __table_args__ = (UniqueConstraint("issue_id", "asset_id", name="uq_equipment_issue_asset"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    issue_id: Mapped[int] = mapped_column(ForeignKey("equipment_issues.id"), index=True, nullable=False)
    asset_id: Mapped[int] = mapped_column(ForeignKey("equipment_assets.id"), index=True, nullable=False)
    condition_before: Mapped[str | None] = mapped_column(String(30))
    return_condition: Mapped[str | None] = mapped_column(String(30))
    returned_at: Mapped[datetime | None] = mapped_column(DateTime, index=True)
    received_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    damage_notes: Mapped[str] = mapped_column(Text, default="", nullable=False)
    missing_reported: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    location_before_issue: Mapped[str | None] = mapped_column(String(160))
    responsible_user_before_issue_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    department_before_issue_id: Mapped[int | None] = mapped_column(ForeignKey("departments.id"))


class EquipmentItemEvent(Base):
    __tablename__ = "equipment_item_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    issue_id: Mapped[int] = mapped_column(ForeignKey("equipment_issues.id"), index=True, nullable=False)
    issue_item_id: Mapped[int] = mapped_column(ForeignKey("equipment_issue_items.id"), index=True, nullable=False)
    asset_id: Mapped[int] = mapped_column(ForeignKey("equipment_assets.id"), index=True, nullable=False)
    actor_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    event_type: Mapped[str] = mapped_column(String(40), index=True, nullable=False)
    shift_id: Mapped[int | None] = mapped_column(ForeignKey("shifts.id"), index=True)
    shift_date: Mapped[date | None] = mapped_column(Date, index=True)
    condition: Mapped[str | None] = mapped_column(String(30))
    details: Mapped[str] = mapped_column(Text, default="", nullable=False)
    happened_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True, nullable=False)


class EquipmentHandover(Base):
    __tablename__ = "equipment_handovers"
    __table_args__ = (UniqueConstraint("outgoing_shift_id", "incoming_shift_id", "shift_date", "outgoing_custodian_id", "incoming_custodian_id", name="uq_equipment_handover_pair"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    outgoing_shift_id: Mapped[int] = mapped_column(ForeignKey("shifts.id"), index=True, nullable=False)
    incoming_shift_id: Mapped[int] = mapped_column(ForeignKey("shifts.id"), index=True, nullable=False)
    shift_date: Mapped[date] = mapped_column(Date, index=True, nullable=False)
    outgoing_custodian_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    incoming_custodian_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    outgoing_ack_at: Mapped[datetime | None] = mapped_column(DateTime)
    incoming_ack_at: Mapped[datetime | None] = mapped_column(DateTime)
    discrepancies: Mapped[str] = mapped_column(Text, default="", nullable=False)
    reviewed_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime)
    review_comment: Mapped[str] = mapped_column(Text, default="", nullable=False)


class EquipmentHandoverLine(Base):
    __tablename__ = "equipment_handover_lines"
    __table_args__ = (UniqueConstraint("handover_id", "issue_item_id", name="uq_equipment_handover_issue_item"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    handover_id: Mapped[int] = mapped_column(ForeignKey("equipment_handovers.id"), index=True, nullable=False)
    issue_item_id: Mapped[int] = mapped_column(ForeignKey("equipment_issue_items.id"), nullable=False)
    asset_id: Mapped[int] = mapped_column(ForeignKey("equipment_assets.id"), nullable=False)
    asset_tag_snapshot: Mapped[str] = mapped_column(String(50), nullable=False)


class SocialAccount(Base):
    """One verified office profile per supported platform; never stores login credentials."""
    __tablename__ = "social_accounts"
    id: Mapped[int] = mapped_column(primary_key=True)
    platform: Mapped[str] = mapped_column(String(20), unique=True, index=True, nullable=False)
    account_name: Mapped[str | None] = mapped_column(String(160))
    account_handle: Mapped[str | None] = mapped_column(String(160))
    profile_url: Mapped[str | None] = mapped_column(String(500))
    configured_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    configured_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)


class SocialOfficer(Base):
    __tablename__ = "social_officers"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True, index=True, nullable=False)
    designated_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    designated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)


class SocialWeeklyReport(Base):
    __tablename__ = "social_weekly_reports"
    __table_args__ = (UniqueConstraint("account_id", "reporting_week", name="uq_social_account_week"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("social_accounts.id"), index=True, nullable=False)
    platform: Mapped[str] = mapped_column(String(20), index=True, nullable=False)
    account_name_snapshot: Mapped[str] = mapped_column(String(160), nullable=False)
    account_handle_snapshot: Mapped[str] = mapped_column(String(160), nullable=False)
    reporting_date: Mapped[date] = mapped_column(Date, index=True, nullable=False)
    reporting_week: Mapped[date] = mapped_column(Date, index=True, nullable=False)
    metrics: Mapped[dict] = mapped_column(JSON, nullable=False)
    best_content: Mapped[str] = mapped_column(Text, default="", nullable=False)
    recommendations: Mapped[str] = mapped_column(Text, default="", nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="Draft", index=True, nullable=False)
    source_kind: Mapped[str] = mapped_column(String(20), default="manual", nullable=False)
    entered_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    entered_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime)
    reviewed_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime)
    review_comment: Mapped[str] = mapped_column(Text, default="", nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)


class SocialEvidence(Base):
    __tablename__ = "social_evidence"
    id: Mapped[int] = mapped_column(primary_key=True)
    report_id: Mapped[int] = mapped_column(ForeignKey("social_weekly_reports.id", ondelete="CASCADE"), index=True, nullable=False)
    original_name: Mapped[str] = mapped_column(String(255), nullable=False)
    stored_name: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    media_type: Mapped[str] = mapped_column(String(120), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    uploaded_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)


class SocialQuarterlyReport(Base):
    __tablename__ = "social_quarterly_reports"
    __table_args__ = (UniqueConstraint("report_year", "quarter", name="uq_social_year_quarter"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    report_year: Mapped[int] = mapped_column(Integer, nullable=False)
    quarter: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="Draft", index=True, nullable=False)
    snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)
    management_notes: Mapped[str] = mapped_column(Text, default="", nullable=False)
    generated_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    generated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime)
    reviewed_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime)
    review_comment: Mapped[str] = mapped_column(Text, default="", nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)
