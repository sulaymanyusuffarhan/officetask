"""Manual-first social media reporting. No provider credentials, scraping, or API calls."""
from __future__ import annotations

import csv
import io
import json
import re
import secrets
import zipfile
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse
from xml.sax.saxutils import escape

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from openpyxl import Workbook, load_workbook
from pydantic import BaseModel, ConfigDict, Field, field_validator
from reportlab.lib import colors
from reportlab.lib.pagesizes import landscape, letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.dependencies import ADMIN, HEAD, current_user
from app.db.session import get_db
from app.models.models import SocialAccount, SocialEvidence, SocialOfficer, SocialQuarterlyReport, SocialWeeklyReport, User
from app.services.audit import record_audit

router = APIRouter(prefix="/api/social", tags=["social media manual reporting"])
settings = get_settings()

PLATFORMS = {
    "youtube": "YouTube", "facebook": "Facebook", "instagram": "Instagram", "x": "X", "tiktok": "TikTok"
}
METRICS = (
    "audience_start", "audience_end", "new_followers", "lost_followers", "reach", "impressions", "views",
    "likes", "comments", "shares", "saves", "posts_published", "videos_published",
)
METRIC_LABELS = {
    "audience_start": "Followers/subscribers at period start", "audience_end": "Followers/subscribers at period end",
    "new_followers": "New followers/subscribers", "lost_followers": "Lost followers/subscribers", "reach": "Reach",
    "impressions": "Impressions", "views": "Views", "likes": "Likes", "comments": "Comments",
    "shares": "Shares", "saves": "Saves", "posts_published": "Posts published", "videos_published": "Videos published",
}
INTERACTION_METRICS = ("likes", "comments", "shares")
UPLOAD_MIME = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".pdf": "application/pdf",
               ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", ".csv": "text/csv"}
UPLOAD_LIMIT = 20 * 1024 * 1024
IMPORT_LIMIT = 5 * 1024 * 1024
IMPORT_MAX_ROWS = 200


class MetricValues(BaseModel):
    model_config = ConfigDict(extra="forbid")
    audience_start: int | None = Field(..., ge=0, le=1_000_000_000_000_000)
    audience_end: int | None = Field(..., ge=0, le=1_000_000_000_000_000)
    new_followers: int | None = Field(..., ge=0, le=1_000_000_000_000_000)
    lost_followers: int | None = Field(..., ge=0, le=1_000_000_000_000_000)
    reach: int | None = Field(..., ge=0, le=1_000_000_000_000_000)
    impressions: int | None = Field(..., ge=0, le=1_000_000_000_000_000)
    views: int | None = Field(..., ge=0, le=1_000_000_000_000_000)
    likes: int | None = Field(..., ge=0, le=1_000_000_000_000_000)
    comments: int | None = Field(..., ge=0, le=1_000_000_000_000_000)
    shares: int | None = Field(..., ge=0, le=1_000_000_000_000_000)
    saves: int | None = Field(..., ge=0, le=1_000_000_000_000_000)
    posts_published: int | None = Field(..., ge=0, le=1_000_000_000_000_000)
    videos_published: int | None = Field(..., ge=0, le=1_000_000_000_000_000)


class WeeklyReportIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    platform: Literal["youtube", "facebook", "instagram", "x", "tiktok"]
    account_id: int | None = Field(default=None, gt=0)
    reporting_date: date
    reporting_week: date
    metrics: MetricValues
    best_content: str = Field(default="", max_length=5000)
    recommendations: str = Field(default="", max_length=10000)

    @field_validator("reporting_week")
    @classmethod
    def monday_week(cls, value: date) -> date:
        if value.weekday() != 0:
            raise ValueError("Reporting week must be the Monday starting the Monday-to-Sunday reporting week")
        return value


class AccountIn(BaseModel):
    account_name: str = Field(min_length=1, max_length=160)
    account_handle: str = Field(min_length=1, max_length=160)
    profile_url: str | None = Field(default=None, max_length=500)

    @field_validator("account_name", "account_handle", mode="before")
    @classmethod
    def trim(cls, value):
        return value.strip() if isinstance(value, str) else value

    @field_validator("account_name", "account_handle")
    @classmethod
    def required_after_trim(cls, value):
        if not value:
            raise ValueError("Verified profile name and handle are required")
        return value

    @field_validator("profile_url")
    @classmethod
    def valid_url(cls, value):
        parsed = urlparse(value) if value else None
        if parsed and (parsed.scheme not in {"http", "https"} or not parsed.netloc):
            raise ValueError("Profile link must be an absolute http or https URL")
        return value


class AccountCreateIn(AccountIn):
    platform: Literal["youtube", "facebook", "instagram", "x", "tiktok"]


class OfficersIn(BaseModel):
    user_ids: list[int] = Field(max_length=50)


class ReviewIn(BaseModel):
    decision: Literal["approve", "reject", "correction"]
    comment: str = Field(default="", max_length=5000)

    @field_validator("comment")
    @classmethod
    def require_reason_for_negative_decision(cls, value, info):
        if info.data.get("decision") in {"reject", "correction"} and len(value.strip()) < 3:
            raise ValueError("Provide a reason for rejection or correction")
        return value


class QuarterGenerateIn(BaseModel):
    year: int = Field(ge=2000, le=2200)
    quarter: int = Field(ge=1, le=4)


class QuarterUpdateIn(BaseModel):
    management_notes: str = Field(default="", max_length=20000)


def _is_officer(db: Session, actor: User) -> bool:
    if actor.role_id == HEAD:
        return True
    return actor.role_id != ADMIN and db.scalar(select(SocialOfficer.id).where(SocialOfficer.user_id == actor.id)) is not None


def _require_officer(db: Session, actor: User) -> None:
    if not _is_officer(db, actor):
        raise HTTPException(403, "Only the Head of Office or designated social media officer may access this module")


def _require_head(actor: User) -> None:
    if actor.role_id != HEAD:
        raise HTTPException(403, "Only the Head of Office may configure accounts or review reports")


def _audit(db: Session, actor: User, action: str, entity: str, entity_id, details: dict | None = None) -> None:
    record_audit(db, actor, action, entity, entity_id, details or {})
    db.commit()


def _account(db: Session, platform: str, account_id: int | None = None) -> SocialAccount:
    if account_id is not None:
        row = db.get(SocialAccount, account_id)
        if row is None or row.platform != platform or not row.account_handle:
            raise HTTPException(422, "Select a configured account belonging to this platform")
        return row
    candidates = db.scalars(select(SocialAccount).where(SocialAccount.platform == platform)
                            .order_by(SocialAccount.id)).all()
    configured = [row for row in candidates if row.account_handle]
    if len(configured) == 1:
        return configured[0]
    if len(configured) > 1:
        raise HTTPException(422, f"Select the specific {PLATFORMS[platform]} account for this report")
    raise HTTPException(409, f"Configure the verified official {PLATFORMS[platform]} account before entering statistics")


def _date_string(value: date | datetime | None):
    return value.isoformat() if value else None


def _calculations(platform: str, metrics: dict) -> dict:
    start, end = metrics.get("audience_start"), metrics.get("audience_end")
    if start is not None and end is not None:
        net, net_basis = end - start, "audience_end minus audience_start"
    elif metrics.get("new_followers") is not None and metrics.get("lost_followers") is not None:
        net, net_basis = metrics["new_followers"] - metrics["lost_followers"], "new_followers minus lost_followers"
    else:
        net, net_basis = None, None
    growth = round(net * 100 / start, 2) if net is not None and start not in (None, 0) else None
    interaction_values = [metrics.get(k) for k in INTERACTION_METRICS]
    interaction_total = sum(interaction_values) if all(v is not None for v in interaction_values) else None
    if interaction_total is not None and metrics.get("saves") is not None:
        interaction_total += metrics["saves"]
    if platform in {"youtube", "tiktok"}:
        denominator_name, denominator = "views", metrics.get("views")
    else:
        denominator_name, denominator = "reach", metrics.get("reach")
    rate = round(interaction_total * 100 / denominator, 2) if interaction_total is not None and denominator not in (None, 0) else None
    return {
        "net_follower_growth": net, "net_growth_basis": net_basis, "audience_growth_percent": growth,
        "engagement_interactions": interaction_total, "engagement_denominator": denominator_name,
        "engagement_denominator_value": denominator, "engagement_rate_percent": rate,
        "engagement_formula": ("(likes + comments + shares + saves when supplied) / " + denominator_name + " × 100; unavailable required inputs yield N/A"),
    }


def _report_json(db: Session, row: SocialWeeklyReport) -> dict:
    evidence = db.scalars(select(SocialEvidence).where(SocialEvidence.report_id == row.id).order_by(SocialEvidence.id)).all()
    return {
        "id": row.id, "platform": row.platform, "platform_name": PLATFORMS[row.platform],
        "account_id": row.account_id, "account_name": row.account_name_snapshot, "account_handle": row.account_handle_snapshot,
        "reporting_date": _date_string(row.reporting_date), "reporting_week": _date_string(row.reporting_week),
        "reporting_week_end": _date_string(row.reporting_week + timedelta(days=6)), "metrics": row.metrics,
        "calculations": _calculations(row.platform, row.metrics), "best_content": row.best_content,
        "recommendations": row.recommendations, "status": row.status, "source_kind": row.source_kind,
        "source_label": {"manual": "Manually entered", "imported": "Imported from file", "api": "Retrieved through authorized API"}.get(row.source_kind, row.source_kind),
        "entered_by_id": row.entered_by_id, "entered_by": db.get(User, row.entered_by_id).full_name,
        "entered_at": row.entered_at.isoformat() + "Z", "submitted_at": row.submitted_at.isoformat() + "Z" if row.submitted_at else None,
        "reviewed_by_id": row.reviewed_by_id, "reviewed_by": db.get(User, row.reviewed_by_id).full_name if row.reviewed_by_id else None,
        "reviewed_at": row.reviewed_at.isoformat() + "Z" if row.reviewed_at else None,
        "review_comment": row.review_comment, "updated_at": row.updated_at.isoformat() + "Z",
        "evidence": [{"id": e.id, "name": e.original_name, "media_type": e.media_type, "size_bytes": e.size_bytes,
                      "uploaded_by_id": e.uploaded_by_id, "uploaded_at": e.uploaded_at.isoformat() + "Z"} for e in evidence],
    }


def _quarter_json(row: SocialQuarterlyReport, db: Session) -> dict:
    return {"id": row.id, "year": row.report_year, "quarter": row.quarter, "status": row.status,
            "snapshot": row.snapshot, "management_notes": row.management_notes,
            "generated_by_id": row.generated_by_id, "generated_by": db.get(User, row.generated_by_id).full_name,
            "generated_at": row.generated_at.isoformat() + "Z",
            "submitted_at": row.submitted_at.isoformat() + "Z" if row.submitted_at else None,
            "reviewed_by_id": row.reviewed_by_id,
            "reviewed_by": db.get(User, row.reviewed_by_id).full_name if row.reviewed_by_id else None,
            "reviewed_at": row.reviewed_at.isoformat() + "Z" if row.reviewed_at else None,
            "review_comment": row.review_comment}


def _payload(row: dict) -> WeeklyReportIn:
    try:
        return WeeklyReportIn.model_validate(row)
    except Exception as exc:
        raise HTTPException(422, f"Invalid report data: {exc}") from exc


def _can_edit_weekly(db: Session, actor: User, row: SocialWeeklyReport) -> None:
    _require_officer(db, actor)
    if row.status in {"Submitted", "Approved"}:
        raise HTTPException(409, "Submitted or approved reports cannot be modified; wait for a correction request")


def _quarter_bounds(year: int, quarter: int) -> tuple[date, date]:
    start_month = (quarter - 1) * 3 + 1
    start = date(year, start_month, 1)
    end_month = start_month + 2
    next_month = date(year + (end_month == 12), 1 if end_month == 12 else end_month + 1, 1)
    return start, next_month - timedelta(days=1)


def _nullable_sum(rows: list[SocialWeeklyReport], key: str):
    values = [r.metrics.get(key) for r in rows]
    return sum(values) if values and all(v is not None for v in values) else None


def _period_net(rows: list[SocialWeeklyReport], audience_start: int | None, audience_end: int | None):
    if audience_start is not None and audience_end is not None:
        return audience_end - audience_start
    new_followers, lost_followers = _nullable_sum(rows, "new_followers"), _nullable_sum(rows, "lost_followers")
    return new_followers - lost_followers if new_followers is not None and lost_followers is not None else None


def _quarter_account_summary(platform: str, label: str, account: SocialAccount | None,
                             rows: list[SocialWeeklyReport]) -> dict:
    rows.sort(key=lambda r: (r.reporting_week, r.id))
    first, last = (rows[0], rows[-1]) if rows else (None, None)
    begin = first.metrics.get("audience_start") if first else None
    finish = last.metrics.get("audience_end") if last else None
    net = _period_net(rows, begin, finish)
    rate = round(net * 100 / begin, 2) if net is not None and begin else None
    totals = {key: _nullable_sum(rows, key) for key in ("new_followers", "lost_followers", "reach", "impressions", "views", "likes", "comments", "shares", "saves", "posts_published", "videos_published")}
    interactions_complete = all(_nullable_sum(rows, key) is not None for key in INTERACTION_METRICS)
    interaction_total = sum(totals[key] for key in INTERACTION_METRICS) if interactions_complete else None
    if interaction_total is not None and totals["saves"] is not None:
        interaction_total += totals["saves"]
    denominator_name = "views" if platform in {"youtube", "tiktok"} else "reach"
    denominator = totals[denominator_name]
    engagement = round(interaction_total * 100 / denominator, 2) if interaction_total is not None and denominator else None
    return {
        "platform": platform, "platform_name": label, "account_id": account.id if account else None,
        "account_name": first.account_name_snapshot if first else account.account_name if account else None,
        "account_handle": first.account_handle_snapshot if first else account.account_handle if account else None,
        "weeks_reported": len(rows), "weekly_report_ids": [r.id for r in rows],
        "audience_start": begin, "audience_end": finish, "net_follower_growth": net,
        "audience_growth_percent": rate, **totals,
        "engagement_interactions": interaction_total, "engagement_denominator": denominator_name,
        "engagement_rate_percent": engagement,
        "weekly_narratives": [{"report_id": r.id, "reporting_week": r.reporting_week.isoformat(),
                              "best_content": r.best_content, "recommendations": r.recommendations} for r in rows],
    }


def _quarter_snapshot(db: Session, year: int, quarter: int) -> dict:
    start, end = _quarter_bounds(year, quarter)
    accounts = db.scalars(select(SocialAccount).order_by(SocialAccount.platform, SocialAccount.id)).all()
    reports = db.scalars(select(SocialWeeklyReport).where(
        SocialWeeklyReport.status == "Approved", SocialWeeklyReport.reporting_week <= end,
        SocialWeeklyReport.reporting_week >= start - timedelta(days=6)).order_by(SocialWeeklyReport.reporting_week, SocialWeeklyReport.id)).all()
    by_account: dict[int, list[SocialWeeklyReport]] = {}
    for report in reports:
        if report.reporting_week + timedelta(days=6) >= start and report.reporting_week <= end:
            by_account.setdefault(report.account_id, []).append(report)
    results = []
    for platform, label in PLATFORMS.items():
        platform_accounts = [account for account in accounts if account.platform == platform]
        if not platform_accounts:
            results.append(_quarter_account_summary(platform, label, None, []))
        for account in platform_accounts:
            results.append(_quarter_account_summary(platform, label, account, by_account.get(account.id, [])))
    return {"year": year, "quarter": quarter, "start_date": start.isoformat(), "end_date": end.isoformat(),
            "method": "Consolidated separately for each registered account from its approved weekly reports whose Monday-to-Sunday reporting weeks overlap this calendar quarter. Accounts are never combined; no values are synthesized. A total is N/A if any included report marks that metric N/A. Audience growth uses the first reported start and last reported end values.",
            "engagement_formula": "Per account: YouTube/TikTok (likes + comments + shares + saves when reported) / total views × 100. Facebook/Instagram/X use total reach as denominator. Likes/comments/shares and denominator must be available; otherwise N/A. Saves are only included when reported.",
            "platforms": results, "approved_weekly_report_count": len(reports)}


def _parse_import(data: bytes, suffix: str) -> tuple[list[str], list[dict]]:
    if suffix == ".csv":
        try:
            text = data.decode("utf-8-sig")
            reader = csv.DictReader(io.StringIO(text))
            rows = []
            for row in reader:
                if len(rows) >= IMPORT_MAX_ROWS:
                    raise HTTPException(422, f"Import is limited to {IMPORT_MAX_ROWS} data rows")
                rows.append(row)
            return list(reader.fieldnames or []), rows
        except (UnicodeDecodeError, csv.Error) as exc:
            raise HTTPException(422, "CSV must be UTF-8 and have a header row") from exc
    if suffix == ".xlsx":
        if not data.startswith(b"PK\x03\x04"):
            raise HTTPException(422, "The file is not a valid XLSX workbook")
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                if sum(info.file_size for info in archive.infolist()) > 50 * 1024 * 1024:
                    raise HTTPException(422, "Uncompressed XLSX contents exceed 50 MB")
            workbook = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
            sheet = workbook.active
            iterator = sheet.iter_rows(values_only=True)
            first = next(iterator, None)
            if first is None:
                workbook.close(); return [], []
            headers = [str(x).strip() if x is not None else "" for x in first]
            rows = []
            for values in iterator:
                if not any(v is not None for v in values): continue
                if len(rows) >= IMPORT_MAX_ROWS:
                    workbook.close()
                    raise HTTPException(422, f"Import is limited to {IMPORT_MAX_ROWS} data rows")
                rows.append(dict(zip(headers, values)))
            workbook.close()
            return headers, rows
        except (zipfile.BadZipFile, KeyError, ValueError) as exc:
            raise HTTPException(422, "Could not read XLSX workbook") from exc
    raise HTTPException(422, "Choose a .csv or .xlsx import file")


def _normalize_import_value(value):
    if value is None:
        return None
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped or stripped.casefold() in {"n/a", "na", "not available", "not applicable"}:
            return None
        return stripped
    return value


def _import_rows(db: Session, rows: list[dict]) -> tuple[list[dict], list[dict]]:
    if len(rows) > IMPORT_MAX_ROWS:
        raise HTTPException(422, f"Import is limited to {IMPORT_MAX_ROWS} data rows")
    expected = {"platform", "reporting_date", "reporting_week", *METRICS, "best_content", "recommendations"}
    prepared, errors, seen = [], [], set()
    accounts: dict[str, list[SocialAccount]] = {}
    for row in db.scalars(select(SocialAccount).order_by(SocialAccount.platform, SocialAccount.id)).all():
        if row.account_handle:
            accounts.setdefault(row.platform, []).append(row)
    for index, raw in enumerate(rows, start=2):
        try:
            normalized = {str(k).strip().lower(): _normalize_import_value(v) for k, v in raw.items() if k is not None}
            absent = expected - set(normalized)
            if absent:
                raise ValueError("Missing columns: " + ", ".join(sorted(absent)))
            platform = str(normalized["platform"]).strip().lower()
            if platform not in PLATFORMS:
                raise ValueError("platform must be youtube, facebook, instagram, x, or tiktok")
            platform_accounts = accounts.get(platform, [])
            if not platform_accounts:
                raise ValueError(f"No official {PLATFORMS[platform]} account is configured")
            selected_handle = normalized.get("account_handle")
            if selected_handle:
                account = next((a for a in platform_accounts if a.account_handle.casefold() == str(selected_handle).casefold()), None)
                if account is None:
                    raise ValueError(f"account_handle does not match a configured {PLATFORMS[platform]} account")
            elif len(platform_accounts) == 1:
                account = platform_accounts[0]
            else:
                raise ValueError(f"account_handle is required because multiple {PLATFORMS[platform]} accounts are configured")
            m = {}
            for key in METRICS:
                val = normalized[key]
                if val is None:
                    m[key] = None
                else:
                    if isinstance(val, bool) or (isinstance(val, float) and not val.is_integer()):
                        raise ValueError(f"{key} must be a whole number or N/A")
                    parsed = int(val)
                    if parsed < 0:
                        raise ValueError(f"{key} cannot be negative")
                    m[key] = parsed
            report_data = {"platform": platform, "account_id": account.id,
                           "reporting_date": normalized["reporting_date"],
                           "reporting_week": normalized["reporting_week"], "metrics": m,
                           "best_content": str(normalized["best_content"] or ""),
                           "recommendations": str(normalized["recommendations"] or "")}
            validated = WeeklyReportIn.model_validate(report_data)
            key = (account.id, validated.reporting_week)
            duplicate = key in seen or db.scalar(select(SocialWeeklyReport.id).where(
                SocialWeeklyReport.account_id == account.id, SocialWeeklyReport.reporting_week == validated.reporting_week))
            if duplicate:
                raise ValueError("Duplicate reporting period already exists in this file or database")
            seen.add(key)
            prepared.append({"row_number": index, "valid": True, **validated.model_dump(mode="json"),
                             "account_handle": account.account_handle, "status": "Ready to import"})
        except Exception as exc:
            errors.append({"row_number": index, "valid": False, "error": str(exc)})
    return prepared, errors


def _xlsx_report(rows: list[dict], title: str) -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Social media report"
    sheet.append([title])
    headers = ["Platform", "Account", "Reporting date", "Week starting", *[METRIC_LABELS[m] for m in METRICS],
               "Net growth", "Audience growth %", "Engagement rate %", "Engagement method", "Best-performing content",
               "Comments and recommendations", "Status", "Source", "Entered by", "Entered at"]
    sheet.append(headers)
    for r in rows:
        m, c = r["metrics"], r["calculations"]
        text_fields = [r["platform_name"], r["account_handle"], r["best_content"], r["recommendations"], r["status"], r["source_label"], r["entered_by"], r["entered_at"]]
        safe = [("'" + str(v)) if str(v or "").startswith(("=", "+", "-", "@", "\t", "\r")) else v for v in text_fields]
        sheet.append([safe[0], safe[1], r["reporting_date"], r["reporting_week"], *[m.get(k) for k in METRICS],
                      c["net_follower_growth"], c["audience_growth_percent"], c["engagement_rate_percent"], c["engagement_formula"], *safe[2:]])
    sheet.freeze_panes = "A3"
    sheet.auto_filter.ref = sheet.dimensions
    for cells in sheet.columns:
        letter = cells[0].column_letter
        sheet.column_dimensions[letter].width = min(36, max(14, max(len(str(c.value or "")) for c in cells) + 2))
    output = io.BytesIO(); workbook.save(output)
    return output.getvalue()


def _pdf_report(rows: list[dict], title: str) -> bytes:
    output = io.BytesIO(); styles = getSampleStyleSheet()
    doc = SimpleDocTemplate(output, pagesize=landscape(letter), title=title, leftMargin=24, rightMargin=24)
    story = [Paragraph(escape(title), styles["Title"]), Spacer(1, 10)]
    header = ["Platform / account", "Week", "Audience start → end", "Net", "Growth %", "Reach", "Impressions", "Views", "Likes", "Comments", "Shares", "Saves", "Engagement %", "Posts", "Videos", "Status / source"]
    data = [header]
    for r in rows:
        m, c = r["metrics"], r["calculations"]
        fmt = lambda v: "N/A" if v is None else str(v)
        platform = f'{r["platform_name"]} {r["account_handle"]}'
        data.append([Paragraph(escape(platform), styles["BodyText"]), r["reporting_week"],
                     f'{fmt(m.get("audience_start"))} → {fmt(m.get("audience_end"))}', fmt(c["net_follower_growth"]),
                     fmt(c["audience_growth_percent"]), fmt(m.get("reach")), fmt(m.get("impressions")), fmt(m.get("views")),
                     fmt(m.get("likes")), fmt(m.get("comments")), fmt(m.get("shares")), fmt(m.get("saves")),
                     fmt(c["engagement_rate_percent"]), fmt(m.get("posts_published")), fmt(m.get("videos_published")),
                     f'{r["status"]} / {r["source_label"]}'])
    widths = [68, 42, 68, 30, 36, 38, 42, 34, 30, 36, 34, 30, 42, 32, 36, 72]
    table = Table(data, repeatRows=1, colWidths=widths)
    table.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#173d73")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white), ("GRID", (0, 0), (-1, -1), .35, colors.HexColor("#cbd5e1")),
        ("FONTSIZE", (0, 0), (-1, -1), 6), ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f1f5f9")])]))
    story.append(table); doc.build(story)
    return output.getvalue()


def _safe_excel(value):
    text = str(value or "")
    return "'" + text if text.startswith(("=", "+", "-", "@", "\t", "\r")) else value


def _quarter_xlsx_report(row: SocialQuarterlyReport) -> bytes:
    workbook = Workbook(); summary = workbook.active; summary.title = "Quarter summary"
    snapshot = row.snapshot
    summary.append([f"TBC Digital social media · Q{row.quarter} {row.report_year}"])
    summary.append(["Status", row.status]); summary.append(["Generated from approved weekly reports", snapshot["approved_weekly_report_count"]])
    summary.append(["Methodology", snapshot["method"]]); summary.append(["Management analysis and recommendations", _safe_excel(row.management_notes)])
    summary.append(["Engagement formula", snapshot["engagement_formula"]])
    sheet = workbook.create_sheet("Platform results")
    headers = ["Platform", "Account", "Approved weeks", "Audience start", "Audience end", "Net growth", "Growth %",
               "New followers", "Lost followers", "Reach", "Impressions", "Views", "Likes", "Comments", "Shares", "Saves",
               "Posts published", "Videos published", "Engagement rate %", "Weekly report IDs"]
    sheet.append(headers)
    for p in snapshot["platforms"]:
        sheet.append([_safe_excel(p["platform_name"]), _safe_excel(p.get("account_handle") or "N/A"), p["weeks_reported"],
            p["audience_start"], p["audience_end"], p["net_follower_growth"], p["audience_growth_percent"],
            p["new_followers"], p["lost_followers"], p["reach"], p["impressions"], p["views"], p["likes"], p["comments"],
            p["shares"], p["saves"], p["posts_published"], p["videos_published"], p["engagement_rate_percent"],
            ", ".join(map(str, p["weekly_report_ids"]))])
    sheet.freeze_panes = "A2"; sheet.auto_filter.ref = sheet.dimensions
    for cells in sheet.columns:
        sheet.column_dimensions[cells[0].column_letter].width = min(36, max(14, max(len(str(c.value or "")) for c in cells) + 2))
    output = io.BytesIO(); workbook.save(output); return output.getvalue()


def _quarter_pdf_report(row: SocialQuarterlyReport) -> bytes:
    output = io.BytesIO(); styles = getSampleStyleSheet()
    doc = SimpleDocTemplate(output, pagesize=landscape(letter), title=f"Social media Q{row.quarter} {row.report_year}")
    snapshot = row.snapshot
    source_summary = "Source weekly report IDs: " + "; ".join(
        f"{p['platform_name']}: {', '.join(map(str, p['weekly_report_ids'])) or 'N/A'}" for p in snapshot["platforms"])
    story = [Paragraph(f"TBC Digital social media · Q{row.quarter} {row.report_year}", styles["Title"]),
             Paragraph(f"Status: {escape(row.status)} · Consolidated from {snapshot['approved_weekly_report_count']} approved weekly reports", styles["Normal"]),
             Spacer(1, 8), Paragraph("Method: " + escape(snapshot["method"]), styles["BodyText"]),
             Spacer(1, 6), Paragraph("Engagement formula: " + escape(snapshot["engagement_formula"]), styles["BodyText"]),
             Spacer(1, 6), Paragraph(escape(source_summary), styles["BodyText"]), Spacer(1, 8)]
    if row.management_notes:
        story.extend([Paragraph("Management analysis and recommendations", styles["Heading2"]),
                      Paragraph(escape(row.management_notes).replace("\n", "<br/>"), styles["BodyText"]), Spacer(1, 8)])
    data = [["Platform", "Account", "Weeks", "Audience start", "Audience end", "Net", "Growth %", "New", "Lost", "Reach", "Impressions", "Views", "Likes", "Comments", "Shares", "Saves", "Posts", "Videos", "Engagement %"]]
    for p in snapshot["platforms"]:
        fmt = lambda v: "N/A" if v is None else str(v)
        data.append([p["platform_name"], p.get("account_handle") or "N/A", p["weeks_reported"], fmt(p["audience_start"]),
            fmt(p["audience_end"]), fmt(p["net_follower_growth"]), fmt(p["audience_growth_percent"]),
            fmt(p["new_followers"]), fmt(p["lost_followers"]), fmt(p["reach"]), fmt(p["impressions"]), fmt(p["views"]),
            fmt(p["likes"]), fmt(p["comments"]), fmt(p["shares"]), fmt(p["saves"]), fmt(p["posts_published"]),
            fmt(p["videos_published"]), fmt(p["engagement_rate_percent"])])
    widths = [48, 55, 28, 43, 43, 30, 34, 30, 30, 38, 44, 32, 28, 34, 30, 28, 30, 32, 40]
    table = Table(data, repeatRows=1, colWidths=widths)
    table.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#173d73")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white), ("GRID", (0, 0), (-1, -1), .35, colors.HexColor("#cbd5e1")),
        ("FONTSIZE", (0, 0), (-1, -1), 6), ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f1f5f9")])]))
    story.append(table); doc.build(story); return output.getvalue()


@router.get("/access")
def social_access(db: Session = Depends(get_db), actor: User = Depends(current_user)):
    return {"allowed": _is_officer(db, actor), "is_head": actor.role_id == HEAD}


def _duplicate_account_handle(db: Session, platform: str, handle: str, exclude_id: int | None = None) -> bool:
    existing = db.scalars(select(SocialAccount).where(SocialAccount.platform == platform)).all()
    return any(row.id != exclude_id and row.account_handle and row.account_handle.casefold() == handle.casefold()
               for row in existing)


@router.get("/accounts")
def social_accounts(db: Session = Depends(get_db), actor: User = Depends(current_user)):
    _require_officer(db, actor)
    rows = db.scalars(select(SocialAccount).order_by(SocialAccount.platform, SocialAccount.account_handle, SocialAccount.id)).all()
    return [{"id": row.id, "platform": row.platform, "platform_name": PLATFORMS[row.platform],
             "configured": bool(row.account_handle), "account_name": row.account_name,
             "account_handle": row.account_handle, "profile_url": row.profile_url,
             "updated_at": row.updated_at.isoformat() + "Z"}
            for row in rows]


@router.post("/accounts", status_code=201)
def create_account(body: AccountCreateIn, db: Session = Depends(get_db), actor: User = Depends(current_user)):
    _require_head(actor)
    if _duplicate_account_handle(db, body.platform, body.account_handle):
        raise HTTPException(409, "That handle is already registered for this platform")
    row = SocialAccount(platform=body.platform, account_name=body.account_name, account_handle=body.account_handle,
                        profile_url=body.profile_url, configured_by_id=actor.id)
    db.add(row); db.flush()
    _audit(db, actor, "social_account_registered", "social_account", row.id,
           {"platform": body.platform, "account_handle": body.account_handle})
    return {"id": row.id, "platform": row.platform, "configured": True}


@router.put("/accounts/{account_id}")
def update_account(account_id: int, body: AccountIn, db: Session = Depends(get_db), actor: User = Depends(current_user)):
    _require_head(actor)
    row = db.get(SocialAccount, account_id)
    if not row:
        raise HTTPException(404, "Social account not found")
    if _duplicate_account_handle(db, row.platform, body.account_handle, exclude_id=row.id):
        raise HTTPException(409, "That handle is already registered for this platform")
    old_handle = row.account_handle
    row.account_name, row.account_handle, row.profile_url = body.account_name, body.account_handle, body.profile_url
    row.updated_at = datetime.utcnow()
    _audit(db, actor, "social_account_updated", "social_account", row.id,
           {"platform": row.platform, "previous_handle": old_handle, "account_handle": body.account_handle})
    return {"id": row.id, "platform": row.platform, "configured": True}


@router.get("/officers")
def get_officers(db: Session = Depends(get_db), actor: User = Depends(current_user)):
    _require_head(actor)
    officers = db.scalars(select(SocialOfficer).order_by(SocialOfficer.id)).all()
    users = db.scalars(select(User).where(User.active.is_(True), User.role_id != "system_administrator").order_by(User.full_name)).all()
    return {"user_ids": [o.user_id for o in officers],
            "users": [{"id": u.id, "name": u.full_name, "role": u.role_id} for u in users]}


@router.put("/officers")
def set_officers(body: OfficersIn, db: Session = Depends(get_db), actor: User = Depends(current_user)):
    _require_head(actor)
    if len(set(body.user_ids)) != len(body.user_ids):
        raise HTTPException(422, "Duplicate officer user IDs are not allowed")
    users = db.scalars(select(User).where(User.id.in_(body.user_ids), User.active.is_(True), User.role_id != "system_administrator")).all() if body.user_ids else []
    if len(users) != len(body.user_ids):
        raise HTTPException(422, "Select active non-administrator accounts")
    for old in db.scalars(select(SocialOfficer)).all():
        db.delete(old)
    db.flush()
    for user_id in body.user_ids:
        db.add(SocialOfficer(user_id=user_id, designated_by_id=actor.id))
    _audit(db, actor, "social_officers_configured", "social_officer", "all", {"user_ids": body.user_ids})
    return {"user_ids": body.user_ids}


@router.get("/template.csv")
def csv_template(db: Session = Depends(get_db), actor: User = Depends(current_user)):
    _require_officer(db, actor)
    headers = ["platform", "account_handle", "reporting_date", "reporting_week", *METRICS, "best_content", "recommendations"]
    output = io.StringIO(); writer = csv.writer(output); writer.writerow(headers)
    return StreamingResponse(iter([output.getvalue()]), media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=social-weekly-import-template.csv"})


@router.get("/template.xlsx")
def xlsx_template(db: Session = Depends(get_db), actor: User = Depends(current_user)):
    _require_officer(db, actor)
    workbook = Workbook(); sheet = workbook.active; sheet.title = "Weekly data"
    headers = ["platform", "account_handle", "reporting_date", "reporting_week", *METRICS, "best_content", "recommendations"]
    sheet.append(headers)
    instructions = workbook.create_sheet("Instructions")
    instructions.append(["Enter one weekly record per row on the Weekly data sheet."])
    instructions.append(["Allowed platform values: youtube, facebook, instagram, x, tiktok. Enter the configured account handle when multiple accounts exist on that platform."])
    instructions.append(["Reporting week must be the Monday date for that Monday-to-Sunday period."])
    instructions.append(["Enter a whole number including 0, or N/A when unavailable. Do not invent or estimate values."])
    instructions.append(["This blank template contains no social media statistics. Fill with source-verified data before import."])
    output = io.BytesIO(); workbook.save(output); output.seek(0)
    return StreamingResponse(output, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=social-weekly-import-template.xlsx"})


@router.get("/weekly")
def list_weekly(start: date | None = None, end: date | None = None, platform: str | None = None,
               account_id: int | None = None, db: Session = Depends(get_db), actor: User = Depends(current_user)):
    _require_officer(db, actor)
    query = select(SocialWeeklyReport).order_by(SocialWeeklyReport.reporting_week.desc(), SocialWeeklyReport.platform)
    if start: query = query.where(SocialWeeklyReport.reporting_week >= start)
    if end: query = query.where(SocialWeeklyReport.reporting_week <= end)
    if platform:
        if platform not in PLATFORMS: raise HTTPException(422, "Unknown platform filter")
        query = query.where(SocialWeeklyReport.platform == platform)
    if account_id is not None:
        query = query.where(SocialWeeklyReport.account_id == account_id)
    return [_report_json(db, r) for r in db.scalars(query).all()]


@router.post("/weekly", status_code=201)
def create_weekly(body: WeeklyReportIn, db: Session = Depends(get_db), actor: User = Depends(current_user)):
    _require_officer(db, actor)
    account = _account(db, body.platform, body.account_id)
    if db.scalar(select(SocialWeeklyReport.id).where(SocialWeeklyReport.account_id == account.id,
            SocialWeeklyReport.reporting_week == body.reporting_week)):
        raise HTTPException(409, "A report already exists for this account and reporting week")
    row = SocialWeeklyReport(account_id=account.id, platform=body.platform, account_name_snapshot=account.account_name,
        account_handle_snapshot=account.account_handle, reporting_date=body.reporting_date, reporting_week=body.reporting_week,
        metrics=body.metrics.model_dump(), best_content=body.best_content.strip(), recommendations=body.recommendations.strip(),
        status="Draft", source_kind="manual", entered_by_id=actor.id)
    db.add(row); db.flush()
    _audit(db, actor, "social_weekly_report_created", "social_weekly_report", row.id,
           {"platform": body.platform, "reporting_week": body.reporting_week.isoformat(), "source_kind": "manual"})
    return _report_json(db, row)


@router.put("/weekly/{report_id}")
def update_weekly(report_id: int, body: WeeklyReportIn, db: Session = Depends(get_db), actor: User = Depends(current_user)):
    _require_officer(db, actor)
    row = db.get(SocialWeeklyReport, report_id)
    if not row: raise HTTPException(404, "Weekly report not found")
    _can_edit_weekly(db, actor, row)
    if body.platform != row.platform: raise HTTPException(422, "A report's platform cannot be changed")
    if body.account_id is not None and body.account_id != row.account_id:
        raise HTTPException(422, "A report's account cannot be changed")
    if db.scalar(select(SocialWeeklyReport.id).where(SocialWeeklyReport.account_id == row.account_id,
            SocialWeeklyReport.reporting_week == body.reporting_week, SocialWeeklyReport.id != row.id)):
        raise HTTPException(409, "A report already exists for this account and reporting week")
    old = {"status": row.status, "reporting_week": row.reporting_week.isoformat(), "metrics": row.metrics}
    row.reporting_date, row.reporting_week = body.reporting_date, body.reporting_week
    row.metrics, row.best_content, row.recommendations = body.metrics.model_dump(), body.best_content.strip(), body.recommendations.strip()
    row.status = "Draft"; row.submitted_at = None; row.review_comment = ""; row.reviewed_by_id = None; row.reviewed_at = None
    row.updated_at = datetime.utcnow()
    db.flush()
    _audit(db, actor, "social_weekly_report_corrected", "social_weekly_report", row.id,
           {"previous": old, "new_reporting_week": row.reporting_week.isoformat()})
    return _report_json(db, row)


def _validate_evidence(data: bytes, suffix: str, original: str):
    if not data or len(data) > UPLOAD_LIMIT: raise HTTPException(422, "Evidence file must be non-empty and at most 20 MB")
    ok = ((suffix == ".png" and data.startswith(b"\x89PNG\r\n\x1a\n"))
          or (suffix in {".jpg", ".jpeg"} and data.startswith(b"\xff\xd8\xff"))
          or (suffix == ".pdf" and data.startswith(b"%PDF-"))
          or (suffix == ".xlsx" and _is_xlsx(data))
          or (suffix == ".csv" and _is_utf8_csv(data)))
    if suffix not in UPLOAD_MIME or not ok:
        raise HTTPException(422, f"Unsupported or invalid evidence file: {original[:100]}")


def _is_xlsx(data: bytes) -> bool:
    if not data.startswith(b"PK\x03\x04"):
        return False
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            names = set(archive.namelist())
            return ("[Content_Types].xml" in names and "xl/workbook.xml" in names
                    and sum(info.file_size for info in archive.infolist()) <= 50 * 1024 * 1024)
    except zipfile.BadZipFile:
        return False


def _is_utf8_csv(data: bytes) -> bool:
    try: data.decode("utf-8-sig"); return True
    except UnicodeDecodeError: return False


@router.post("/weekly/{report_id}/evidence", status_code=201)
async def upload_evidence(report_id: int, files: list[UploadFile] = File(...), db: Session = Depends(get_db), actor: User = Depends(current_user)):
    _require_officer(db, actor)
    row = db.get(SocialWeeklyReport, report_id)
    if not row: raise HTTPException(404, "Weekly report not found")
    _can_edit_weekly(db, actor, row)
    existing_count = len(db.scalars(select(SocialEvidence.id).where(SocialEvidence.report_id == row.id)).all())
    if not files or len(files) > 10 or existing_count + len(files) > 10:
        raise HTTPException(422, "A weekly report may have at most ten evidence files")
    directory = Path(settings.upload_dir).resolve() / "social"; directory.mkdir(parents=True, exist_ok=True)
    stored_paths: list[Path] = []
    try:
        for uploaded in files:
            original = (uploaded.filename or "evidence").replace("\\", "/").split("/")[-1]
            suffix = Path(original).suffix.lower()
            data = await uploaded.read(UPLOAD_LIMIT + 1)
            _validate_evidence(data, suffix, original)
            stored = secrets.token_hex(24) + suffix
            path = directory / stored; path.write_bytes(data); stored_paths.append(path)
            safe_name = "".join(ch for ch in original if ch.isprintable() and ch not in "\r\n")[:255] or "evidence" + suffix
            db.add(SocialEvidence(report_id=row.id, original_name=safe_name, stored_name=stored,
                                  media_type=UPLOAD_MIME[suffix], size_bytes=len(data), uploaded_by_id=actor.id))
        db.flush()
        _audit(db, actor, "social_weekly_evidence_uploaded", "social_weekly_report", row.id,
               {"file_count": len(files)})
        return _report_json(db, row)
    except Exception:
        db.rollback()
        for path in stored_paths: path.unlink(missing_ok=True)
        raise


@router.get("/evidence/{evidence_id}")
def download_evidence(evidence_id: int, db: Session = Depends(get_db), actor: User = Depends(current_user)):
    _require_officer(db, actor)
    item = db.get(SocialEvidence, evidence_id)
    if not item: raise HTTPException(404, "Evidence not found")
    path = Path(settings.upload_dir).resolve() / "social" / item.stored_name
    if not path.is_file(): raise HTTPException(404, "Evidence file is unavailable")
    return FileResponse(path, media_type=item.media_type, filename=item.original_name,
                        headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"})


@router.post("/weekly/{report_id}/submit")
def submit_weekly(report_id: int, db: Session = Depends(get_db), actor: User = Depends(current_user)):
    _require_officer(db, actor)
    row = db.get(SocialWeeklyReport, report_id)
    if not row: raise HTTPException(404, "Weekly report not found")
    _can_edit_weekly(db, actor, row)
    if not db.scalar(select(SocialEvidence.id).where(SocialEvidence.report_id == row.id)):
        raise HTTPException(409, "Upload supporting analytics evidence before submitting the weekly report")
    row.status, row.submitted_at = "Submitted", datetime.utcnow()
    _audit(db, actor, "social_weekly_report_submitted", "social_weekly_report", row.id,
           {"platform": row.platform, "reporting_week": row.reporting_week.isoformat()})
    return _report_json(db, row)


@router.post("/weekly/{report_id}/review")
def review_weekly(report_id: int, body: ReviewIn, db: Session = Depends(get_db), actor: User = Depends(current_user)):
    _require_head(actor)
    row = db.get(SocialWeeklyReport, report_id)
    if not row: raise HTTPException(404, "Weekly report not found")
    if row.status != "Submitted": raise HTTPException(409, "Only submitted weekly reports can be reviewed")
    if row.entered_by_id == actor.id: raise HTTPException(403, "An approver cannot approve their own report")
    row.status = {"approve": "Approved", "reject": "Rejected", "correction": "Returned for Correction"}[body.decision]
    row.review_comment = body.comment.strip(); row.reviewed_by_id = actor.id; row.reviewed_at = datetime.utcnow()
    _audit(db, actor, "social_weekly_report_reviewed", "social_weekly_report", row.id,
           {"decision": body.decision, "comment": body.comment.strip()})
    return _report_json(db, row)


@router.post("/imports/preview")
async def import_preview(file: UploadFile = File(...), db: Session = Depends(get_db), actor: User = Depends(current_user)):
    _require_officer(db, actor)
    name = (file.filename or "").lower(); suffix = Path(name).suffix
    if suffix not in {".csv", ".xlsx"}: raise HTTPException(422, "Import file must be CSV or XLSX")
    data = await file.read(IMPORT_LIMIT + 1)
    if not data or len(data) > IMPORT_LIMIT: raise HTTPException(422, "Import file must be non-empty and at most 5 MB")
    headers, rows = _parse_import(data, suffix)
    if not headers: raise HTTPException(422, "Import file is empty or has no header row")
    prepared, errors = _import_rows(db, rows)
    return {"filename": file.filename, "total_rows": len(rows), "ready_count": len(prepared), "error_count": len(errors),
            "rows": prepared, "errors": errors, "can_commit": bool(prepared) and not errors}


@router.post("/imports/commit")
async def import_commit(file: UploadFile = File(...), db: Session = Depends(get_db), actor: User = Depends(current_user)):
    _require_officer(db, actor)
    name = (file.filename or "").lower(); suffix = Path(name).suffix
    if suffix not in {".csv", ".xlsx"}: raise HTTPException(422, "Import file must be CSV or XLSX")
    data = await file.read(IMPORT_LIMIT + 1)
    if not data or len(data) > IMPORT_LIMIT: raise HTTPException(422, "Import file must be non-empty and at most 5 MB")
    headers, source_rows = _parse_import(data, suffix)
    prepared, errors = _import_rows(db, source_rows)
    if errors: raise HTTPException(422, {"message": "Import preview has validation errors; correct the file and preview it again", "errors": errors})
    directory = Path(settings.upload_dir).resolve() / "social"; directory.mkdir(parents=True, exist_ok=True)
    stored = secrets.token_hex(24) + suffix
    path = directory / stored; path.write_bytes(data)
    created = []
    try:
        for item in prepared:
            platform = item["platform"]; account = db.get(SocialAccount, item["account_id"])
            if account is None:
                raise HTTPException(409, "A selected social account was removed; preview the import again")
            body = WeeklyReportIn.model_validate({k: item[k] for k in ("platform", "account_id", "reporting_date", "reporting_week", "metrics", "best_content", "recommendations")})
            row = SocialWeeklyReport(account_id=account.id, platform=platform, account_name_snapshot=account.account_name or "",
                account_handle_snapshot=account.account_handle or "", reporting_date=body.reporting_date, reporting_week=body.reporting_week,
                metrics=body.metrics.model_dump(), best_content=body.best_content.strip(), recommendations=body.recommendations.strip(),
                status="Draft", source_kind="imported", entered_by_id=actor.id)
            db.add(row); db.flush(); created.append(row.id)
            db.add(SocialEvidence(report_id=row.id, original_name=(file.filename or "import." + suffix)[:255], stored_name=stored,
                media_type=UPLOAD_MIME[suffix], size_bytes=len(data), uploaded_by_id=actor.id))
        record_audit(db, actor, "social_import_batch_committed", "social_import", stored,
                     {"filename": file.filename, "reports_created": len(created), "report_ids": created})
        db.commit()
    except IntegrityError as exc:
        db.rollback(); path.unlink(missing_ok=True)
        raise HTTPException(409, "A report in the import conflicts with a period saved concurrently; preview the file again") from exc
    except Exception:
        db.rollback(); path.unlink(missing_ok=True); raise
    return {"created_count": len(created), "report_ids": created, "source_kind": "imported"}


@router.post("/quarters/generate", status_code=201)
def generate_quarter(body: QuarterGenerateIn, db: Session = Depends(get_db), actor: User = Depends(current_user)):
    _require_officer(db, actor)
    snapshot = _quarter_snapshot(db, body.year, body.quarter)
    row = db.scalar(select(SocialQuarterlyReport).where(SocialQuarterlyReport.report_year == body.year,
                                                        SocialQuarterlyReport.quarter == body.quarter))
    if row:
        if row.status not in {"Draft", "Returned for Correction", "Rejected"}:
            raise HTTPException(409, "Submitted or approved quarterly reports cannot be regenerated")
        row.snapshot = snapshot; row.status = "Draft"; row.generated_by_id = actor.id; row.generated_at = datetime.utcnow()
        row.submitted_at = None; row.reviewed_at = None; row.reviewed_by_id = None; row.review_comment = ""
        row.management_notes = ""; row.updated_at = datetime.utcnow()
        _audit(db, actor, "social_quarterly_report_regenerated", "social_quarterly_report", row.id,
               {"year": body.year, "quarter": body.quarter, "approved_weekly_report_count": snapshot["approved_weekly_report_count"]})
    else:
        row = SocialQuarterlyReport(report_year=body.year, quarter=body.quarter, status="Draft", snapshot=snapshot, generated_by_id=actor.id)
        db.add(row); db.flush()
        _audit(db, actor, "social_quarterly_report_generated", "social_quarterly_report", row.id,
               {"year": body.year, "quarter": body.quarter, "approved_weekly_report_count": snapshot["approved_weekly_report_count"]})
    return _quarter_json(row, db)


@router.get("/quarters")
def list_quarters(db: Session = Depends(get_db), actor: User = Depends(current_user)):
    _require_officer(db, actor)
    rows = db.scalars(select(SocialQuarterlyReport).order_by(SocialQuarterlyReport.report_year.desc(), SocialQuarterlyReport.quarter.desc())).all()
    return [_quarter_json(r, db) for r in rows]


@router.put("/quarters/{quarter_id}")
def update_quarter(quarter_id: int, body: QuarterUpdateIn, db: Session = Depends(get_db), actor: User = Depends(current_user)):
    _require_officer(db, actor)
    row = db.get(SocialQuarterlyReport, quarter_id)
    if not row: raise HTTPException(404, "Quarterly report not found")
    if row.status not in {"Draft", "Returned for Correction", "Rejected"}:
        raise HTTPException(409, "Submitted or approved quarterly reports cannot be modified")
    old_status, old_notes = row.status, row.management_notes
    row.management_notes = body.management_notes.strip(); row.status = "Draft"
    row.review_comment = ""; row.reviewed_by_id = None; row.reviewed_at = None; row.submitted_at = None
    _audit(db, actor, "social_quarterly_report_updated", "social_quarterly_report", row.id,
           {"previous_status": old_status, "previous_notes": old_notes, "new_notes": row.management_notes})
    return _quarter_json(row, db)


@router.post("/quarters/{quarter_id}/submit")
def submit_quarter(quarter_id: int, db: Session = Depends(get_db), actor: User = Depends(current_user)):
    _require_officer(db, actor)
    row = db.get(SocialQuarterlyReport, quarter_id)
    if not row: raise HTTPException(404, "Quarterly report not found")
    if row.status not in {"Draft", "Returned for Correction", "Rejected"}: raise HTTPException(409, "Quarterly report is not editable")
    if row.snapshot.get("approved_weekly_report_count", 0) < 1:
        raise HTTPException(409, "At least one approved weekly report is needed before quarterly submission")
    row.status = "Submitted"; row.submitted_at = datetime.utcnow()
    _audit(db, actor, "social_quarterly_report_submitted", "social_quarterly_report", row.id,
           {"year": row.report_year, "quarter": row.quarter})
    return _quarter_json(row, db)


@router.post("/quarters/{quarter_id}/review")
def review_quarter(quarter_id: int, body: ReviewIn, db: Session = Depends(get_db), actor: User = Depends(current_user)):
    _require_head(actor)
    row = db.get(SocialQuarterlyReport, quarter_id)
    if not row: raise HTTPException(404, "Quarterly report not found")
    if row.status != "Submitted": raise HTTPException(409, "Only submitted quarterly reports can be reviewed")
    if row.generated_by_id == actor.id: raise HTTPException(403, "An approver cannot approve a quarterly report they generated")
    row.status = {"approve": "Approved", "reject": "Rejected", "correction": "Returned for Correction"}[body.decision]
    row.review_comment = body.comment.strip(); row.reviewed_by_id = actor.id; row.reviewed_at = datetime.utcnow()
    _audit(db, actor, "social_quarterly_report_reviewed", "social_quarterly_report", row.id,
           {"decision": body.decision, "comment": body.comment.strip()})
    return _quarter_json(row, db)


def _weekly_rows(db: Session, start: date | None, end: date | None, platform: str | None, account_id: int | None = None) -> list[dict]:
    query = select(SocialWeeklyReport).order_by(SocialWeeklyReport.reporting_week, SocialWeeklyReport.platform)
    if start: query = query.where(SocialWeeklyReport.reporting_week >= start)
    if end: query = query.where(SocialWeeklyReport.reporting_week <= end)
    if platform:
        if platform not in PLATFORMS: raise HTTPException(422, "Unknown platform filter")
        query = query.where(SocialWeeklyReport.platform == platform)
    if account_id is not None:
        query = query.where(SocialWeeklyReport.account_id == account_id)
    rows = db.scalars(query).all()
    return [_report_json(db, row) for row in rows]


@router.get("/analytics")
def social_analytics(start: date, end: date, grain: Literal["week", "month", "quarter"] = "week", platform: str | None = None,
                    db: Session = Depends(get_db), actor: User = Depends(current_user)):
    _require_officer(db, actor)
    if end < start or (end - start).days > 1100: raise HTTPException(422, "Select a valid range of up to three years")
    rows = db.scalars(select(SocialWeeklyReport).where(SocialWeeklyReport.status == "Approved",
        SocialWeeklyReport.reporting_week <= end, SocialWeeklyReport.reporting_week >= start - timedelta(days=6))
        .order_by(SocialWeeklyReport.reporting_week, SocialWeeklyReport.id)).all()
    if platform:
        if platform not in PLATFORMS: raise HTTPException(422, "Unknown platform filter")
        rows = [r for r in rows if r.platform == platform]
    rows = [row for row in rows if row.reporting_week + timedelta(days=6) >= start and row.reporting_week <= end]
    grouped: dict[tuple[str, int, str], list[SocialWeeklyReport]] = {}
    for row in rows:
        if grain == "week":
            period = row.reporting_week.isoformat()
        elif grain == "month":
            period = f"{row.reporting_week.year:04d}-{row.reporting_week.month:02d}"
        else:
            period = f"{row.reporting_week.year:04d}-Q{(row.reporting_week.month - 1) // 3 + 1}"
        grouped.setdefault((row.platform, row.account_id, period), []).append(row)
    accounts_by_id = {a.id: a for a in db.scalars(select(SocialAccount)).all()}
    series = []
    for (plat, account_id, period), batch in sorted(grouped.items(), key=lambda x: (x[0][2], x[0][0], x[0][1])):
        batch.sort(key=lambda r: (r.reporting_week, r.id))
        first, last = batch[0], batch[-1]
        start_audience, end_audience = first.metrics.get("audience_start"), last.metrics.get("audience_end")
        growth = _period_net(batch, start_audience, end_audience)
        growth_pct = round(growth * 100 / start_audience, 2) if growth is not None and start_audience else None
        totals = {key: _nullable_sum(batch, key) for key in METRICS if key not in {"audience_start", "audience_end"}}
        engagements_complete = all(totals[k] is not None for k in INTERACTION_METRICS)
        engagements = sum(totals[k] for k in INTERACTION_METRICS) if engagements_complete else None
        if engagements is not None and totals["saves"] is not None: engagements += totals["saves"]
        denominator_key = "views" if plat in {"youtube", "tiktok"} else "reach"
        denominator = totals[denominator_key]
        engagement = round(engagements * 100 / denominator, 2) if engagements is not None and denominator else None
        account = accounts_by_id.get(account_id)
        report_handle = batch[-1].account_handle_snapshot or (account.account_handle if account else "")
        series.append({"platform": plat, "platform_name": PLATFORMS[plat], "account_id": account_id,
                       "account_name": batch[-1].account_name_snapshot or (account.account_name if account else None),
                       "account_handle": report_handle,
                       "series_name": f"{PLATFORMS[plat]} {report_handle}".strip(),
                       "period": period, "weeks_reported": len(batch),
                       "audience_start": start_audience, "audience_end": end_audience, "net_follower_growth": growth,
                       "audience_growth_percent": growth_pct, **totals, "engagement_interactions": engagements,
                       "engagement_rate_percent": engagement, "engagement_denominator": denominator_key})
    previous_by_account = {}
    change_keys = ("net_follower_growth", "audience_growth_percent", "engagement_rate_percent", "reach",
                   "impressions", "views", "posts_published", "videos_published")
    for point in sorted(series, key=lambda item: (item["platform"], item["account_id"], item["period"])):
        account_key = (point["platform"], point["account_id"])
        previous = previous_by_account.get(account_key)
        point["previous_period"] = previous["period"] if previous else None
        point["changes_vs_previous"] = ({key: point[key] - previous[key] if point[key] is not None and previous[key] is not None else None
                                          for key in change_keys} if previous else {key: None for key in change_keys})
        previous_by_account[account_key] = point
    summaries = []
    configured_accounts = db.scalars(select(SocialAccount).order_by(SocialAccount.platform, SocialAccount.id)).all()
    summary_accounts = [(platform, label, account) for platform, label in PLATFORMS.items()
                        for account in configured_accounts if account.platform == platform]
    for plat, label in PLATFORMS.items():
        if not any(account.platform == plat for account in configured_accounts):
            summary_accounts.append((plat, label, None))
    for plat, label, account in summary_accounts:
        batch = sorted([r for r in rows if r.platform == plat and (account is None or r.account_id == account.id)], key=lambda r: (r.reporting_week, r.id))
        first, last = (batch[0], batch[-1]) if batch else (None, None)
        audience_start = first.metrics.get("audience_start") if first else None
        audience_end = last.metrics.get("audience_end") if last else None
        net = _period_net(batch, audience_start, audience_end)
        growth_pct = round(net * 100 / audience_start, 2) if net is not None and audience_start else None
        totals = {key: _nullable_sum(batch, key) for key in METRICS if key not in {"audience_start", "audience_end"}}
        interactions = (sum(totals[k] for k in INTERACTION_METRICS)
                        if batch and all(totals[k] is not None for k in INTERACTION_METRICS) else None)
        if interactions is not None and totals["saves"] is not None: interactions += totals["saves"]
        denominator_name = "views" if plat in {"youtube", "tiktok"} else "reach"
        denominator = totals[denominator_name]
        engagement = round(interactions * 100 / denominator, 2) if interactions is not None and denominator else None
        account_handle = first.account_handle_snapshot if first else account.account_handle if account else None
        summaries.append({"platform": plat, "platform_name": label, "account_id": account.id if account else None,
                          "account_handle": account_handle,
                          "series_name": f"{label} {account_handle}" if account_handle else label,
                          "weeks_reported": len(batch), "audience_start": audience_start, "audience_end": audience_end, "net_follower_growth": net,
                          "audience_growth_percent": growth_pct, **totals, "engagement_interactions": interactions,
                          "engagement_rate_percent": engagement, "engagement_denominator": denominator_name})
    return {"start": start.isoformat(), "end": end.isoformat(), "grain": grain, "platform_filter": platform,
            "approved_weekly_report_count": len(rows), "series": series, "platform_summary": summaries,
            "formula": "YouTube/TikTok engagement = (likes + comments + shares + reported saves) / views × 100. Facebook/Instagram/X use reach as denominator. All likes/comments/shares are required; N/A inputs make the rate N/A. Saves are added only when reported. No missing value is substituted with zero."}


@router.get("/exports.xlsx")
def export_weekly_xlsx(start: date | None = None, end: date | None = None, platform: str | None = None,
                       account_id: int | None = None, db: Session = Depends(get_db), actor: User = Depends(current_user)):
    _require_officer(db, actor)
    rows = _weekly_rows(db, start, end, platform, account_id)
    output = _xlsx_report(rows, f"Social media weekly reports · {start or 'all'} to {end or 'all'}")
    return StreamingResponse(iter([output]), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=social-weekly-reports.xlsx"})


@router.get("/exports.pdf")
def export_weekly_pdf(start: date | None = None, end: date | None = None, platform: str | None = None,
                      account_id: int | None = None, db: Session = Depends(get_db), actor: User = Depends(current_user)):
    _require_officer(db, actor)
    output = _pdf_report(_weekly_rows(db, start, end, platform, account_id), "Social media weekly performance reports")
    return StreamingResponse(iter([output]), media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=social-weekly-reports.pdf"})


@router.get("/quarters/{quarter_id}/exports.xlsx")
def export_quarter_xlsx(quarter_id: int, db: Session = Depends(get_db), actor: User = Depends(current_user)):
    _require_officer(db, actor)
    row = db.get(SocialQuarterlyReport, quarter_id)
    if not row: raise HTTPException(404, "Quarterly report not found")
    output = _quarter_xlsx_report(row)
    return StreamingResponse(iter([output]), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename=social-q{row.quarter}-{row.report_year}.xlsx"})


@router.get("/quarters/{quarter_id}/exports.pdf")
def export_quarter_pdf(quarter_id: int, db: Session = Depends(get_db), actor: User = Depends(current_user)):
    _require_officer(db, actor)
    row = db.get(SocialQuarterlyReport, quarter_id)
    if not row: raise HTTPException(404, "Quarterly report not found")
    output = _quarter_pdf_report(row)
    return StreamingResponse(iter([output]), media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=social-q{row.quarter}-{row.report_year}.pdf"})
