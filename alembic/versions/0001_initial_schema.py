"""Initial schema creation.

Revision ID: 0001
Revises:
Create Date: 2026-10-24 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create enums
    contract_state = postgresql.ENUM(
        "active",
        "missing_review",
        "closed",
        "reopened",
        name="contractstate",
        create_type=True,
    )
    contract_state.create(op.get_bind(), checkfirst=True)

    installment_status = postgresql.ENUM(
        "pending",
        "partial",
        "paid",
        "overdue",
        "waived",
        name="installmentstatus",
        create_type=True,
    )
    installment_status.create(op.get_bind(), checkfirst=True)

    upload_status = postgresql.ENUM(
        "pending",
        "confirmed",
        "rolled_back",
        name="uploadstatus",
        create_type=True,
    )
    upload_status.create(op.get_bind(), checkfirst=True)

    # Users table (referenced by others)
    op.create_table(
        "users",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("username", sa.String(length=100), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("full_name", sa.String(length=200), nullable=True),
        sa.Column("hashed_password", sa.String(length=255), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, default=True),
        sa.Column("is_superuser", sa.Boolean(), nullable=False, default=False),
        sa.Column("role", sa.String(length=50), nullable=False, default="viewer"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            onupdate=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("last_login", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("username"),
        sa.UniqueConstraint("email"),
    )
    op.create_index("ix_users_email_active", "users", ["email", "is_active"])

    # Contracts table
    op.create_table(
        "contracts",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("reference", sa.String(length=100), nullable=False),
        sa.Column("item", sa.String(length=200), nullable=True),
        sa.Column("brand", sa.String(length=100), nullable=True),
        sa.Column("region", sa.String(length=100), nullable=True),
        sa.Column("cost_center", sa.String(length=100), nullable=True),
        sa.Column("ministry_agency", sa.String(length=200), nullable=True),
        sa.Column("payment_type", sa.String(length=50), nullable=True),
        sa.Column("emi_months", sa.Integer(), nullable=True),
        sa.Column("customer", sa.String(length=200), nullable=True),
        sa.Column("cid", sa.String(length=50), nullable=True),
        sa.Column("mobile", sa.String(length=20), nullable=True),
        sa.Column("contract_date", sa.Date(), nullable=True),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("monthly_deduction", sa.Numeric(precision=15, scale=2), nullable=True),
        sa.Column("sales_amount", sa.Numeric(precision=15, scale=2), nullable=True),
        sa.Column("gst", sa.Numeric(precision=15, scale=2), nullable=True),
        sa.Column(
            "state",
            sa.Enum(
                "active",
                "missing_review",
                "closed",
                "reopened",
                name="contractstate",
                native_enum=False,
            ),
            nullable=False,
            default="active",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            onupdate=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("reference"),
        sa.CheckConstraint("monthly_deduction >= 0", name="ck_monthly_deduction_nonneg"),
        sa.CheckConstraint("sales_amount >= 0", name="ck_sales_amount_nonneg"),
        sa.CheckConstraint("gst >= 0", name="ck_gst_nonneg"),
    )
    op.create_index("ix_contracts_reference", "contracts", ["reference"], unique=True)
    op.create_index("ix_contracts_cid", "contracts", ["cid"])
    op.create_index("ix_contracts_mobile", "contracts", ["mobile"])
    op.create_index("ix_contracts_state", "contracts", ["state"])
    op.create_index("ix_contracts_customer_cid", "contracts", ["customer", "cid"])
    op.create_index("ix_contracts_brand_region", "contracts", ["brand", "region"])

    # Installments table
    op.create_table(
        "installments",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("contract_id", sa.BigInteger(), nullable=False),
        sa.Column("due_month", sa.Date(), nullable=False),
        sa.Column("due_amount", sa.Numeric(precision=15, scale=2), nullable=False),
        sa.Column("received_amount", sa.Numeric(precision=15, scale=2), nullable=False, default="0"),
        sa.Column("salary_amount", sa.Numeric(precision=15, scale=2), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "pending",
                "partial",
                "paid",
                "overdue",
                "waived",
                name="installmentstatus",
                native_enum=False,
            ),
            nullable=False,
            default="pending",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            onupdate=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["contract_id"], ["contracts.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("contract_id", "due_month", name="uq_installment_contract_month"),
        sa.CheckConstraint("due_amount >= 0", name="ck_due_amount_nonneg"),
        sa.CheckConstraint("received_amount >= 0", name="ck_received_amount_nonneg"),
        sa.CheckConstraint("received_amount <= due_amount", name="ck_received_not_exceed_due"),
    )
    op.create_index("ix_installments_contract_id", "installments", ["contract_id"])
    op.create_index("ix_installments_due_month", "installments", ["due_month"])
    op.create_index("ix_installments_status", "installments", ["status"])
    op.create_index("ix_installments_contract_due", "installments", ["contract_id", "due_month"])

    # Uploads table
    op.create_table(
        "uploads",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("file_name", sa.String(length=255), nullable=False),
        sa.Column("checksum", sa.String(length=64), nullable=False),
        sa.Column("uploaded_by", sa.BigInteger(), nullable=False),
        sa.Column(
            "upload_time",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("as_of_date", sa.Date(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "pending",
                "confirmed",
                "rolled_back",
                name="uploadstatus",
                native_enum=False,
            ),
            nullable=False,
            default="pending",
        ),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            onupdate=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["uploaded_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("checksum"),
    )
    op.create_index("ix_uploads_checksum", "uploads", ["checksum"], unique=True)
    op.create_index("ix_uploads_uploaded_by_time", "uploads", ["uploaded_by", "upload_time"])
    op.create_index("ix_uploads_as_of_date", "uploads", ["as_of_date"])
    op.create_index("ix_uploads_status", "uploads", ["status"])

    # Installment history table
    op.create_table(
        "installment_history",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("installment_id", sa.BigInteger(), nullable=False),
        sa.Column("upload_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "previous_status",
            sa.Enum(
                "pending",
                "partial",
                "paid",
                "overdue",
                "waived",
                name="installmentstatus",
                native_enum=False,
            ),
            nullable=True,
        ),
        sa.Column(
            "new_status",
            sa.Enum(
                "pending",
                "partial",
                "paid",
                "overdue",
                "waived",
                name="installmentstatus",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column("previous_received", sa.Numeric(precision=15, scale=2), nullable=True),
        sa.Column("new_received", sa.Numeric(precision=15, scale=2), nullable=False),
        sa.Column(
            "changed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["installment_id"], ["installments.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["upload_id"], ["uploads.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_installment_history_installment_upload",
        "installment_history",
        ["installment_id", "upload_id"],
    )

    # Contract closures table
    op.create_table(
        "contract_closures",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("contract_id", sa.BigInteger(), nullable=False),
        sa.Column("upload_id", sa.BigInteger(), nullable=True),
        sa.Column("reason", sa.String(length=200), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("balance_at_closing", sa.Numeric(precision=15, scale=2), nullable=False),
        sa.Column("closed_by", sa.BigInteger(), nullable=False),
        sa.Column(
            "closed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["closed_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["contract_id"], ["contracts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["upload_id"], ["uploads.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_contract_closures_contract_closed", "contract_closures", ["contract_id", "closed_at"]
    )

    # Contacts table
    op.create_table(
        "contacts",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("cid", sa.String(length=50), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column("mobile", sa.String(length=20), nullable=True),
        sa.Column("source", sa.String(length=50), nullable=False, default="manual"),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("history", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            onupdate=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("cid"),
    )
    op.create_index("ix_contacts_cid", "contacts", ["cid"], unique=True)
    op.create_index("ix_contacts_email", "contacts", ["email"])
    op.create_index("ix_contacts_mobile", "contacts", ["mobile"])

    # Notification templates table
    op.create_table(
        "notification_templates",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("channel", sa.String(length=20), nullable=False),
        sa.Column("subject", sa.String(length=200), nullable=True),
        sa.Column("body_template", sa.Text(), nullable=False),
        sa.Column("variables", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, default=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            onupdate=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )

    # Notifications table
    op.create_table(
        "notifications",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("template_id", sa.BigInteger(), nullable=True),
        sa.Column("recipient_type", sa.String(length=20), nullable=False),
        sa.Column("recipient_id", sa.String(length=100), nullable=False),
        sa.Column("channel", sa.String(length=20), nullable=False),
        sa.Column("subject", sa.String(length=200), nullable=True),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, default="pending"),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("meta", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["template_id"], ["notification_templates.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_notifications_recipient_status",
        "notifications",
        ["recipient_type", "recipient_id", "status"],
    )
    op.create_index("ix_notifications_created", "notifications", ["created_at"])
    op.create_index("ix_notifications_status", "notifications", ["status"])

    # Audit log table
    op.create_table(
        "audit_log",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=True),
        sa.Column("action", sa.String(length=100), nullable=False),
        sa.Column("entity_type", sa.String(length=50), nullable=False),
        sa.Column("entity_id", sa.String(length=100), nullable=False),
        sa.Column("old_values", sa.Text(), nullable=True),
        sa.Column("new_values", sa.Text(), nullable=True),
        sa.Column("ip_address", sa.String(length=45), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_audit_log_entity", "audit_log", ["entity_type", "entity_id"])
    op.create_index("ix_audit_log_user_action", "audit_log", ["user_id", "action"])
    op.create_index("ix_audit_log_created", "audit_log", ["created_at"])


def downgrade() -> None:
    # Drop tables in reverse order
    op.drop_table("audit_log")
    op.drop_table("notifications")
    op.drop_table("notification_templates")
    op.drop_table("contacts")
    op.drop_table("contract_closures")
    op.drop_table("installment_history")
    op.drop_table("uploads")
    op.drop_table("installments")
    op.drop_table("contracts")
    op.drop_table("users")

    # Drop enums
    upload_status = postgresql.ENUM(name="uploadstatus")
    upload_status.drop(op.get_bind(), checkfirst=True)

    installment_status = postgresql.ENUM(name="installmentstatus")
    installment_status.drop(op.get_bind(), checkfirst=True)

    contract_state = postgresql.ENUM(name="contractstate")
    contract_state.drop(op.get_bind(), checkfirst=True)