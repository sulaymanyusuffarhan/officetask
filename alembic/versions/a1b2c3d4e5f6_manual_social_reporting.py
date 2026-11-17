"""manual-first TBC Digital social media reporting

Revision ID: a1b2c3d4e5f6
Revises: bf8103392858
Create Date: 2026-11-17
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "bf8103392858"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "social_accounts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("platform", sa.String(length=20), nullable=False),
        sa.Column("account_name", sa.String(length=160), nullable=True),
        sa.Column("account_handle", sa.String(length=160), nullable=True),
        sa.Column("profile_url", sa.String(length=500), nullable=True),
        sa.Column("configured_by_id", sa.Integer(), nullable=False),
        sa.Column("configured_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["configured_by_id"], ["users.id"], name=op.f("fk_social_accounts_configured_by_id_users")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_social_accounts")),
        sa.UniqueConstraint("platform", name="uq_social_accounts_platform"),
    )
    op.create_index("ix_social_accounts_platform", "social_accounts", ["platform"], unique=False)

    op.create_table(
        "social_officers",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("designated_by_id", sa.Integer(), nullable=False),
        sa.Column("designated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["designated_by_id"], ["users.id"], name=op.f("fk_social_officers_designated_by_id_users")),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_social_officers_user_id_users")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_social_officers")),
        sa.UniqueConstraint("user_id", name="uq_social_officers_user_id"),
    )
    op.create_index("ix_social_officers_user_id", "social_officers", ["user_id"], unique=False)

    op.create_table(
        "social_weekly_reports",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("account_id", sa.Integer(), nullable=False),
        sa.Column("platform", sa.String(length=20), nullable=False),
        sa.Column("account_name_snapshot", sa.String(length=160), nullable=False),
        sa.Column("account_handle_snapshot", sa.String(length=160), nullable=False),
        sa.Column("reporting_date", sa.Date(), nullable=False),
        sa.Column("reporting_week", sa.Date(), nullable=False),
        sa.Column("metrics", sa.JSON(), nullable=False),
        sa.Column("best_content", sa.Text(), nullable=False),
        sa.Column("recommendations", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("source_kind", sa.String(length=20), nullable=False),
        sa.Column("entered_by_id", sa.Integer(), nullable=False),
        sa.Column("entered_at", sa.DateTime(), nullable=False),
        sa.Column("submitted_at", sa.DateTime(), nullable=True),
        sa.Column("reviewed_by_id", sa.Integer(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(), nullable=True),
        sa.Column("review_comment", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["social_accounts.id"], name=op.f("fk_social_weekly_reports_account_id_social_accounts")),
        sa.ForeignKeyConstraint(["entered_by_id"], ["users.id"], name=op.f("fk_social_weekly_reports_entered_by_id_users")),
        sa.ForeignKeyConstraint(["reviewed_by_id"], ["users.id"], name=op.f("fk_social_weekly_reports_reviewed_by_id_users")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_social_weekly_reports")),
        sa.UniqueConstraint("account_id", "reporting_week", name="uq_social_account_week"),
    )
    op.create_index("ix_social_weekly_reports_account_id", "social_weekly_reports", ["account_id"], unique=False)
    op.create_index("ix_social_weekly_reports_platform", "social_weekly_reports", ["platform"], unique=False)
    op.create_index("ix_social_weekly_reports_reporting_date", "social_weekly_reports", ["reporting_date"], unique=False)
    op.create_index("ix_social_weekly_reports_reporting_week", "social_weekly_reports", ["reporting_week"], unique=False)
    op.create_index("ix_social_weekly_reports_status", "social_weekly_reports", ["status"], unique=False)

    op.create_table(
        "social_evidence",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("report_id", sa.Integer(), nullable=False),
        sa.Column("original_name", sa.String(length=255), nullable=False),
        sa.Column("stored_name", sa.String(length=100), nullable=False),
        sa.Column("media_type", sa.String(length=120), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("uploaded_by_id", sa.Integer(), nullable=False),
        sa.Column("uploaded_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["report_id"], ["social_weekly_reports.id"], ondelete="CASCADE", name=op.f("fk_social_evidence_report_id_social_weekly_reports")),
        sa.ForeignKeyConstraint(["uploaded_by_id"], ["users.id"], name=op.f("fk_social_evidence_uploaded_by_id_users")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_social_evidence")),
    )
    op.create_index("ix_social_evidence_report_id", "social_evidence", ["report_id"], unique=False)
    op.create_index("ix_social_evidence_stored_name", "social_evidence", ["stored_name"], unique=False)

    op.create_table(
        "social_quarterly_reports",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("report_year", sa.Integer(), nullable=False),
        sa.Column("quarter", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("snapshot", sa.JSON(), nullable=False),
        sa.Column("management_notes", sa.Text(), nullable=False),
        sa.Column("generated_by_id", sa.Integer(), nullable=False),
        sa.Column("generated_at", sa.DateTime(), nullable=False),
        sa.Column("submitted_at", sa.DateTime(), nullable=True),
        sa.Column("reviewed_by_id", sa.Integer(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(), nullable=True),
        sa.Column("review_comment", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["generated_by_id"], ["users.id"], name=op.f("fk_social_quarterly_reports_generated_by_id_users")),
        sa.ForeignKeyConstraint(["reviewed_by_id"], ["users.id"], name=op.f("fk_social_quarterly_reports_reviewed_by_id_users")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_social_quarterly_reports")),
        sa.UniqueConstraint("report_year", "quarter", name="uq_social_year_quarter"),
    )
    op.create_index("ix_social_quarterly_reports_status", "social_quarterly_reports", ["status"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_social_quarterly_reports_status", table_name="social_quarterly_reports")
    op.drop_table("social_quarterly_reports")
    op.drop_index("ix_social_evidence_stored_name", table_name="social_evidence")
    op.drop_index("ix_social_evidence_report_id", table_name="social_evidence")
    op.drop_table("social_evidence")
    for index in ("status", "reporting_week", "reporting_date", "platform", "account_id"):
        op.drop_index(f"ix_social_weekly_reports_{index}", table_name="social_weekly_reports")
    op.drop_table("social_weekly_reports")
    op.drop_index("ix_social_officers_user_id", table_name="social_officers")
    op.drop_table("social_officers")
    op.drop_index("ix_social_accounts_platform", table_name="social_accounts")
    op.drop_table("social_accounts")
