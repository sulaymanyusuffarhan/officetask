from datetime import date, datetime
from pydantic import BaseModel, Field, field_validator


class AssetCreate(BaseModel):
    asset_tag: str = Field(min_length=2, max_length=50)
    category: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=160)
    brand: str = Field(default="", max_length=100)
    model: str = Field(default="", max_length=120)
    serial_number: str | None = Field(default=None, max_length=120)
    internal_tag: str = Field(default="", max_length=100)
    location: str = Field(default="Equipment store", max_length=160)
    responsible_user_id: int | None = None
    department_id: int | None = None
    condition: str = Field(default="Good", max_length=30)
    purchase_date: date | None = None
    warranty_until: date | None = None
    notes: str = Field(default="", max_length=5000)

    @field_validator("asset_tag", "category", "name", "brand", "model", "serial_number", "internal_tag", "location", "notes", mode="before")
    @classmethod
    def trim_text(cls, value):
        return value.strip() if isinstance(value, str) else value

    @field_validator("serial_number", mode="after")
    @classmethod
    def blank_serial_is_unknown(cls, value):
        return value or None


class AssetUpdate(BaseModel):
    category: str | None = Field(default=None, min_length=1, max_length=80)
    name: str | None = Field(default=None, min_length=1, max_length=160)
    brand: str | None = Field(default=None, max_length=100)
    model: str | None = Field(default=None, max_length=120)
    serial_number: str | None = Field(default=None, max_length=120)
    internal_tag: str | None = Field(default=None, max_length=100)
    location: str | None = Field(default=None, max_length=160)
    responsible_user_id: int | None = None
    department_id: int | None = None
    condition: str | None = Field(default=None, max_length=30)
    purchase_date: date | None = None
    warranty_until: date | None = None
    notes: str | None = Field(default=None, max_length=5000)


class CustodianAssignmentIn(BaseModel):
    shift_id: int
    custodian_id: int
    effective_from: date
    effective_to: date | None = None
    reason: str = Field(default="", max_length=1000)


class CustodianReplacementIn(BaseModel):
    shift_id: int
    shift_date: date
    original_custodian_id: int
    replacement_custodian_id: int
    reason: str = Field(min_length=3, max_length=1000)


class AuthorizationRolesIn(BaseModel):
    roles: list[str] = Field(default_factory=list, max_length=6)


class AccessoryLinkIn(BaseModel):
    accessory_asset_id: int


class EquipmentInspectionIn(BaseModel):
    condition: str = Field(min_length=1, max_length=30)
    disposition: str = Field(min_length=1, max_length=30)
    notes: str = Field(min_length=3, max_length=3000)


class IssueRequestIn(BaseModel):
    asset_ids: list[int] = Field(min_length=1, max_length=100)
    borrower_id: int | None = None
    borrower_name: str = Field(min_length=1, max_length=160)
    borrower_office: str = Field(min_length=1, max_length=160)
    external: bool = False
    shift_id: int
    shift_date: date
    expected_return_at: datetime
    purpose: str = Field(default="", max_length=5000)

    @field_validator("borrower_name", "borrower_office", "purpose", mode="before")
    @classmethod
    def trim_text(cls, value):
        return value.strip() if isinstance(value, str) else value


class AuthorizationIn(BaseModel):
    method: str = Field(min_length=1, max_length=40)
    remarks: str = Field(min_length=3, max_length=3000)


class IssueIn(BaseModel):
    conditions: dict[str, str] = Field(min_length=1, max_length=100)


class BorrowerAckIn(BaseModel):
    acknowledged: bool
    borrower_name: str | None = Field(default=None, max_length=160)


class ReturnAssetIn(BaseModel):
    asset_id: int
    condition: str = Field(min_length=1, max_length=30)
    damage_notes: str = Field(default="", max_length=3000)


class ReturnIn(BaseModel):
    shift_id: int
    shift_date: date
    returned: list[ReturnAssetIn] = Field(default_factory=list, max_length=100)
    missing_asset_ids: list[int] = Field(default_factory=list, max_length=100)
    notes: str = Field(default="", max_length=3000)


class HandoverIn(BaseModel):
    outgoing_shift_id: int
    incoming_shift_id: int
    shift_date: date
    outgoing_custodian_id: int
    incoming_custodian_id: int
    discrepancies: str = Field(default="", max_length=5000)


class HandoverAckIn(BaseModel):
    discrepancies: str = Field(default="", max_length=5000)


class HandoverReviewIn(BaseModel):
    comment: str = Field(default="", max_length=3000)
