"""M2: Add comparison and missing contract fields to uploads

Revision ID: 0bd645936f84
Revises: 0001
Create Date: 2026-10-24 15:10:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '0bd645936f84'
down_revision = '0001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # M2: Add comparison and missing contract fields to uploads
    op.add_column('uploads', sa.Column('previous_upload_id', sa.BigInteger(), nullable=True))
    op.add_column('uploads', sa.Column('comparison_summary', sa.Text(), nullable=True))
    op.add_column('uploads', sa.Column('missing_contracts_count', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('uploads', sa.Column('missing_share', sa.Numeric(precision=5, scale=4), nullable=True))
    op.add_column('uploads', sa.Column('wrong_file_warning', sa.Boolean(), nullable=False, server_default='false'))
    op.add_column('uploads', sa.Column('missing_share_threshold', sa.Numeric(precision=5, scale=4), nullable=False, server_default='0.10'))

    # Add foreign key for previous_upload_id
    op.create_foreign_key('fk_uploads_previous_upload', 'uploads', 'uploads', ['previous_upload_id'], ['id'])

    # Add missing indexes for audit_log
    op.create_index('ix_audit_log_action', 'audit_log', ['action'])
    op.create_index('ix_audit_log_created_at', 'audit_log', ['created_at'])
    op.create_index('ix_audit_log_entity_id', 'audit_log', ['entity_id'])
    op.create_index('ix_audit_log_entity_type', 'audit_log', ['entity_type'])

    # Add TOTP fields to users
    op.add_column('users', sa.Column('totp_secret', sa.String(length=255), nullable=True))
    op.add_column('users', sa.Column('totp_enabled', sa.Boolean(), nullable=False, server_default='false'))
    op.add_column('users', sa.Column('totp_recovery_codes', sa.Text(), nullable=True))
    op.add_column('users', sa.Column('totp_failed_attempts', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('users', sa.Column('totp_locked_until', sa.DateTime(timezone=True), nullable=True))

    # Update user role enum
    op.alter_column('users', 'role', existing_type=sa.VARCHAR(length=50), nullable=False)

    # Update unique constraints on users
    op.create_unique_constraint('uq_users_email', 'users', ['email'])
    op.create_unique_constraint('uq_users_username', 'users', ['username'])
    op.create_index('ix_users_email', 'users', ['email'])
    op.create_index('ix_users_username', 'users', ['username'])


def downgrade() -> None:
    # Drop M2 columns
    op.drop_column('uploads', 'previous_upload_id')
    op.drop_column('uploads', 'comparison_summary')
    op.drop_column('uploads', 'missing_contracts_count')
    op.drop_column('uploads', 'missing_share')
    op.drop_column('uploads', 'wrong_file_warning')
    op.drop_column('uploads', 'missing_share_threshold')

    # Drop TOTP fields from users
    op.drop_column('users', 'totp_secret')
    op.drop_column('users', 'totp_enabled')
    op.drop_column('users', 'totp_recovery_codes')
    op.drop_column('users', 'totp_failed_attempts')
    op.drop_column('users', 'totp_locked_until')

    # Drop M2 indexes
    op.drop_index('ix_audit_log_action', table_name='audit_log')
    op.drop_index('ix_audit_log_created_at', table_name='audit_log')
    op.drop_index('ix_audit_log_entity_id', table_name='audit_log')
    op.drop_index('ix_audit_log_entity_type', table_name='audit_log')

    # Drop user indexes
    op.drop_index('ix_users_email', table_name='users')
    op.drop_index('ix_users_username', table_name='users')
    op.drop_constraint('uq_users_email', 'users', type_='unique')
    op.drop_constraint('uq_users_username', 'users', type_='unique')

    # Revert user role to string
    op.alter_column('users', 'role', existing_type=sa.Enum('super_admin', 'admin', 'uploader', 'viewer', name='userrole', native_enum=False), type_=sa.VARCHAR(length=50), nullable=False, server_default='viewer')