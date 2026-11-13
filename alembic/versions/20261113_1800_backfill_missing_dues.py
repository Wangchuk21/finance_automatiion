"""backfill missing installment dues inside the contract EMI schedule

Payment-only uploads (sheets without a Monthly Deduction column) could create
or update an installment with ``due_amount`` of NULL/0 even though the month
falls inside the contract's EMI schedule. Example: ``BT250503000007`` had an
October 2026 row with a 4,660 payment but no due amount, which made the
contract-level Balance Due (total due - total received) come out as zero while
the schedule still showed an unpaid month.

This migration fills the due for such rows using the contract's monthly
deduction, adding GST on the first month - the same rule the importer uses.

Revision ID: 20261113_backfill_dues
Revises: 20261112_users_role_varchar
Create Date: 2026-11-13 18:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20261113_backfill_dues"
down_revision = "20261112_users_role_varchar"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    tables = {
        row[0]
        for row in bind.execute(
            sa.text(
                """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = current_schema()
              AND table_name IN ('contracts', 'installments')
            """
            )
        )
    }
    if tables != {"contracts", "installments"}:
        # Fresh database: tables are created by the initial migration.
        return

    op.execute(
        sa.text(
            """
        UPDATE installments AS i
        SET due_amount = ROUND(
                c.monthly_deduction
                + CASE
                    WHEN date_trunc('month', i.due_month)
                         = date_trunc('month', c.start_date)
                    THEN COALESCE(c.gst, 0)
                    ELSE 0
                  END,
                2
            )
        FROM contracts AS c
        WHERE i.contract_id = c.id
          AND (i.due_amount IS NULL OR i.due_amount = 0)
          AND c.monthly_deduction IS NOT NULL
          AND c.monthly_deduction > 0
          AND c.start_date IS NOT NULL
          AND c.emi_months IS NOT NULL
          AND c.emi_months > 0
          AND date_trunc('month', i.due_month)
              >= date_trunc('month', c.start_date)
          AND date_trunc('month', i.due_month)
              < date_trunc('month', c.start_date)
                + make_interval(months => c.emi_months)
          AND COALESCE(i.status::text, '') <> 'waived'
        """
        )
    )


def downgrade() -> None:
    # The original zero/NULL values cannot be distinguished afterwards.
    pass
