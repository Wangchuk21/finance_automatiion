# revision identifiers, used by Alembic.
revision = '20261024_2155_ext_cell'

down_revision = '0bd645936f84'
branch_labels = None
depends_on = None

from alembic import op
import sqlalchemy as sa

def upgrade() -> None:
    # Drop constraint that received_amount <= due_amount
    op.drop_constraint('ck_received_not_exceed_due', 'installments', type_='check')
    # Make due_amount nullable
    op.alter_column('installments', 'due_amount', existing_type=sa.Numeric(15, 2), nullable=True)
    # Add external_amount column
    op.add_column('installments', sa.Column('external_amount', sa.Numeric(15, 2), nullable=True))
    # Add cell_status column
    op.add_column('installments', sa.Column('cell_status', sa.String(20), nullable=True))

def downgrade() -> None:
    # Remove external_amount and cell_status columns
    op.drop_column('installments', 'cell_status')
    op.drop_column('installments', 'external_amount')
    # Revert due_amount to non-nullable
    op.alter_column('installments', 'due_amount', existing_type=sa.Numeric(15, 2), nullable=False)
    # Recreate the original check constraint
    op.create_check_constraint('ck_received_not_exceed_due', 'installments', "received_amount <= due_amount")
