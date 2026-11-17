"""replace the three reminder templates with one editable SMS message

Production should send a single, consistent payment reminder:

    Dear {customer}, EMI of Nu. {balance_due_short} ({installments_text}) is due
    for {item} (Ref: {reference}). Please pay to A/c {payment_account}; email
    proof to {payment_email}. Thank you.

Revision ID: 20261117_single_reminder_tmpl
Revises: 20261113_backfill_dues
Create Date: 2026-11-17 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20261117_single_reminder_tmpl"
down_revision = "20261113_backfill_dues"
branch_labels = None
depends_on = None


TEMPLATE_NAME = "EMI Payment Reminder"
TEMPLATE_SUBJECT = "EMI Payment Reminder"
TEMPLATE_BODY = (
    "Dear {customer}, EMI of Nu. {balance_due_short} ({installments_text}) is due for "
    "{item} (Ref: {reference}). Please pay to A/c {payment_account}; "
    "email proof to {payment_email}. Thank you."
)
TEMPLATE_VARIABLES = (
    '["customer", "balance_due_short", "installments_text", "item", '
    '"reference", "payment_account", "payment_email"]'
)

OLD_TEMPLATES = [
    (
        "Due Reminder (0-30 Days)",
        "EMI Payment Due Reminder",
        "Dear {customer}, your EMI installment of Nu. {balance_due} for {item} "
        "(Ref: {reference}) is due. Please settle via Scan & Pay or B-Trowa. Bhutan Telecom.",
        '["customer", "balance_due", "item", "reference"]',
    ),
    (
        "Overdue Warning (31-60 Days)",
        "EMI Payment Overdue Warning",
        "Dear {customer}, your EMI installment of Nu. {balance_due} for {item} "
        "(Ref: {reference}) is overdue by 30+ days. Please clear your dues promptly "
        "to avoid penalties. Bhutan Telecom.",
        '["customer", "balance_due", "item", "reference", "aging_bucket"]',
    ),
    (
        "Critical Overdue (61+ Days)",
        "Urgent: EMI Critical Overdue",
        "URGENT: Dear {customer}, your account (Ref: {reference}) has an overdue EMI balance of "
        "Nu. {balance_due} ({aging_bucket}). Immediate settlement is required. "
        "Call 1600 or visit your nearest BT office. Bhutan Telecom.",
        '["customer", "balance_due", "reference", "aging_bucket"]',
    ),
]


UPSERT_SQL = sa.text(
    """
    INSERT INTO notification_templates
        (name, channel, subject, body_template, variables, is_active, created_at, updated_at)
    VALUES
        (:name, 'sms', :subject, :body, :variables, TRUE, now(), now())
    ON CONFLICT (name) DO UPDATE SET
        channel = EXCLUDED.channel,
        subject = EXCLUDED.subject,
        body_template = EXCLUDED.body_template,
        variables = EXCLUDED.variables,
        is_active = TRUE,
        updated_at = now()
    """
)


def _table_exists() -> bool:
    return "notification_templates" in sa.inspect(op.get_bind()).get_table_names()


def upgrade() -> None:
    if not _table_exists():
        return

    bind = op.get_bind()
    bind.execute(
        UPSERT_SQL,
        {
            "name": TEMPLATE_NAME,
            "subject": TEMPLATE_SUBJECT,
            "body": TEMPLATE_BODY,
            "variables": TEMPLATE_VARIABLES,
        },
    )
    bind.execute(
        sa.text("DELETE FROM notification_templates WHERE name <> :name"),
        {"name": TEMPLATE_NAME},
    )


def downgrade() -> None:
    if not _table_exists():
        return

    bind = op.get_bind()
    for name, subject, body, variables in OLD_TEMPLATES:
        bind.execute(
            UPSERT_SQL,
            {
                "name": name,
                "subject": subject,
                "body": body,
                "variables": variables,
            },
        )

    bind.execute(
        sa.text("DELETE FROM notification_templates WHERE name = :name"),
        {"name": TEMPLATE_NAME},
    )
