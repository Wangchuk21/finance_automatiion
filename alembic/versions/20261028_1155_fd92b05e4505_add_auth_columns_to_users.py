"""add auth columns to users

Revision ID: fd92b05e4505
Revises: 20261024_2155_add_external_and_cell_status
Create Date: 2026-10-28 11:55:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'fd92b05e4505'
down_revision = '20261024_2155_ext_cell'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add auth columns to users
    op.add_column('users', sa.Column('password_hash', sa.String(length=255), nullable=False, server_default=''))
    op.add_column('users', sa.Column('must_change_password', sa.Boolean(), nullable=False, server_default='true'))
    op.add_column('users', sa.Column('password_changed_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('users', sa.Column('password_history', sa.Text(), nullable=True))
    op.add_column('users', sa.Column('token_version', sa.Integer(), nullable=False, server_default='1'))
    op.add_column('users', sa.Column('failed_login_count', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('users', sa.Column('locked_until', sa.DateTime(timezone=True), nullable=True))
    op.add_column('users', sa.Column('temp_password_expires_at', sa.DateTime(timezone=True), nullable=True))

    # Map old role values to new ones before changing enum type
    op.execute("UPDATE users SET role = 'admin' WHERE role = 'ADMIN'")
    op.execute("UPDATE users SET role = 'finance_uploader' WHERE role = 'UPLOADER'")
    op.execute("UPDATE users SET role = 'viewer' WHERE role = 'VIEWER'")
    op.execute("UPDATE users SET role = 'admin' WHERE role = 'SUPER_ADMIN'")

    # Update role enum - remove super_admin, uploader; add finance_uploader
    # First, create the new enum type
    op.execute("CREATE TYPE userrole_new AS ENUM ('admin', 'finance_uploader', 'viewer')")
    # Update the column to use new enum
    op.execute("ALTER TABLE users ALTER COLUMN role TYPE userrole_new USING role::text::userrole_new")
    # Drop old enum and rename new
    op.execute("DROP TYPE userrole")
    op.execute("ALTER TYPE userrole_new RENAME TO userrole")

    # Remove old columns
    op.drop_column('users', 'is_superuser')
    op.drop_column('users', 'session_expires_at')
    op.drop_column('users', 'hashed_password')
    op.drop_column('users', 'password_change_required')
    op.drop_column('users', 'session_token')

    # Remove session_token index if exists
    op.drop_index('ix_users_session_token', table_name='users', if_exists=True)

    # Update unique constraints - they should already exist from initial schema
    # The autogenerate detected changes but they might be just metadata


def downgrade() -> None:
    # Re-add old columns
    op.add_column('users', sa.Column('hashed_password', sa.String(length=255), nullable=False, server_default=''))
    op.add_column('users', sa.Column('password_change_required', sa.Boolean(), nullable=False, server_default='true'))
    op.add_column('users', sa.Column('session_token', sa.String(length=255), nullable=True))
    op.add_column('users', sa.Column('session_expires_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('users', sa.Column('is_superuser', sa.Boolean(), nullable=False, server_default='false'))

    # Restore old role enum
    op.execute("CREATE TYPE userrole_old AS ENUM ('super_admin', 'admin', 'uploader', 'viewer')")
    op.execute("ALTER TABLE users ALTER COLUMN role TYPE userrole_old USING role::text::userrole_old")
    op.execute("DROP TYPE userrole")
    op.execute("ALTER TYPE userrole_old RENAME TO userrole")

    # Remove new columns
    op.drop_column('users', 'password_hash')
    op.drop_column('users', 'must_change_password')
    op.drop_column('users', 'password_changed_at')
    op.drop_column('users', 'password_history')
    op.drop_column('users', 'token_version')
    op.drop_column('users', 'failed_login_count')
    op.drop_column('users', 'locked_until')
    op.drop_column('users', 'temp_password_expires_at')

    # Recreate session_token index
    op.create_index('ix_users_session_token', 'users', ['session_token'], unique=False)