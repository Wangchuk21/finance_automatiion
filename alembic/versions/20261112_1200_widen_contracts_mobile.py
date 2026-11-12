"""widen contracts.mobile to match the model (String(50))

The model declares ``Contract.mobile`` as ``String(50)`` but the initial
migration created the column as ``VARCHAR(20)``. Uploads whose mobile cell
cleans to more than 20 characters fail with
``StringDataRightTruncation`` during confirm.

Revision ID: 20261112_widen_mobile
Revises: fd92b05e4505
Create Date: 2026-11-12 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20261112_widen_mobile"
down_revision = "fd92b05e4505"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "contracts",
        "mobile",
        existing_type=sa.String(length=20),
        type_=sa.String(length=50),
        existing_nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "contracts",
        "mobile",
        existing_type=sa.String(length=50),
        type_=sa.String(length=20),
        existing_nullable=True,
    )
