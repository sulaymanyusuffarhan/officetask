from datetime import date, datetime
from pydantic import BaseModel, ConfigDict, Field, field_validator


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=80, pattern=r"^[A-Za-z0-9._-]+$")
    full_name: str = Field(min_length=1, max_length=160)

    @field_validator("full_name", mode="before")
    @classmethod
    def strip_full_name(cls, value):
        return value.strip() if isinstance(value, str) else value
    password: str = Field(min_length=12, max_length=256)
    role_id: str
    department_id: int | None = None


class UserOut(ORMModel):
    id: int
    username: str
    full_name: str
    role_id: str
    department_id: int | None
    active: bool


class UserUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=1, max_length=160)
    role_id: str | None = None
    department_id: int | None = None
    active: bool | None = None

    @field_validator("full_name", mode="before")
    @classmethod
    def strip_full_name(cls, value):
        return value.strip() if isinstance(value, str) else value


class DepartmentCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)

    @field_validator("name", mode="before")
    @classmethod
    def strip_name(cls, value):
        return value.strip() if isinstance(value, str) else value


class ShiftCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    start_time: str = Field(pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")
    end_time: str = Field(pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")


    @field_validator("name", mode="before")
    @classmethod
    def strip_name(cls, value):
        return value.strip() if isinstance(value, str) else value


class AssignmentCreate(BaseModel):
    work_date: date
    shift_id: int
    employee_id: int
    leader_id: int | None = None
    editor_id: int | None = None
    department_id: int | None = None
    responsibility: str = Field(default="", max_length=120)


class AssignmentUpdate(AssignmentCreate):
    reason: str = Field(min_length=3, max_length=1000)


class TimetableCreate(BaseModel):
    week_start: date


class TaskUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=180)
    instructions: str | None = Field(default=None, max_length=10_000)
    deadline: datetime | None = None
    priority: str | None = None
    employee_id: int | None = None
    reason: str = Field(min_length=3, max_length=1000)

    @field_validator("title", mode="before")
    @classmethod
    def strip_title(cls, value):
        return value.strip() if isinstance(value, str) else value


class TaskCreate(BaseModel):
    title: str = Field(min_length=1, max_length=180)
    description: str = Field(default="", max_length=10_000)
    instructions: str = Field(default="", max_length=10_000)
    employee_ids: list[int] = Field(min_length=1, max_length=50)
    department_id: int | None = None
    shift_id: int | None = None
    assignment_date: date = Field(default_factory=date.today)
    start_date: date = Field(default_factory=date.today)
    deadline: datetime
    priority: str = "Normal"

    @field_validator("title", mode="before")
    @classmethod
    def strip_title(cls, value):
        return value.strip() if isinstance(value, str) else value


class VerificationIn(BaseModel):
    decision: str
    comment: str = Field(default="", max_length=5000)


class AttendanceIn(BaseModel):
    employee_id: int
    work_date: date
    status: str
    reason: str = Field(default="", max_length=5000)


class ShiftReportIn(BaseModel):
    shift_id: int | None = None
    report_date: date
    unfinished: str = Field(default="", max_length=10_000)
    challenges: str = Field(default="", max_length=10_000)
    handover: str = Field(default="", max_length=10_000)
    attendance_notes: str = Field(default="", max_length=10_000)
