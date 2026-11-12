"""store users.role as VARCHAR instead of a native enum

Migration ``fd92b05e4505`` converted ``users.role`` into a native PostgreSQL
enum type named ``userrole``. The SQLAlchemy model declares the column as
``String(20)``, so inserts bind the value as ``VARCHAR`` and PostgreSQL
rejects them with::

    DatatypeMismatch: column "role" is of type userrole
    but expression is of type character varying

That made ``POST /api/v1/auth/users`` (create user) fail with a 500, which the
frontend surfaced as the generic "Request failed" message.

This migration converts the column back to ``VARCHAR(20)`` (matching the
model) and drops the now-unused enum type. It is safe to run whether the
column is currently an enum or already a plain varchar.

Revision ID: 20261112_users_role_varchar
Revises: 20261112_widen_mobile
Create Date: 2026-11-12 13:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20261112_users_role_varchar"
down_revision = "20261112_widen_mobile"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    udt_name = bind.execute(
        sa.text(
            """
            SELECT udt_name
            FROM information_schema.columns
            WHERE table_schema = current_schema()
              AND table_name = 'users'
              AND column_name = 'role'
            """
        )
    ).scalar()

    if udt_name is None:
        # users table does not exist yet (fresh database) - nothing to do.
        return

    # Works for both the enum type and an existing varchar column.
    op.execute("ALTER TABLE users ALTER COLUMN role DROP DEFAULT")
    op.execute("ALTER TABLE users ALTER COLUMN role TYPE VARCHAR(20) USING role::text")
    op.execute("ALTER TABLE users ALTER COLUMN role SET DEFAULT 'viewer'")

    # The enum type was introduced solely for users.role, so it is now unused.
    op.execute("DROP TYPE IF EXISTS userrole")
    op.execute("DROP TYPE IF EXISTS userrole_new")


def downgrade() -> None:
    op.execute("DROP TYPE IF EXISTS userrole")
    op.execute(
        "CREATE TYPE userrole AS ENUM ('admin', 'finance_uploader', 'viewer')"
    )
    op.execute("ALTER TABLE users ALTER COLUMN role DROP DEFAULT")
    op.execute(
        "ALTER TABLE users ALTER COLUMN role TYPE userrole "
        "USING role::text::userrole"
    )
    op.execute("ALTER TABLE users ALTER COLUMN role SET DEFAULT 'viewer'")
