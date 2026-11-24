"""Allow multiple verified social profiles per platform.

Revision ID: c7d8e9f0a1b2
Revises: a1b2c3d4e5f6
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "c7d8e9f0a1b2"
down_revision: Union[str, None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint("uq_social_accounts_platform", "social_accounts", type_="unique")
    op.create_unique_constraint("uq_social_platform_handle", "social_accounts", ["platform", "account_handle"])


def downgrade() -> None:
    bind = op.get_bind()
    duplicates = bind.execute(sa.text(
        "SELECT platform FROM social_accounts GROUP BY platform HAVING COUNT(*) > 1 LIMIT 1"
    )).first()
    if duplicates:
        raise RuntimeError("Cannot downgrade while multiple social accounts exist for a platform")
    op.drop_constraint("uq_social_platform_handle", "social_accounts", type_="unique")
    op.create_unique_constraint("uq_social_accounts_platform", "social_accounts", ["platform"])
