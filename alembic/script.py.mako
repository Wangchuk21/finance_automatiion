#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Alembic migration script template."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '${revision}'
down_revision = ${down_revision}
branch_labels = ${branch_labels}
depends_on = ${depends_on}


def upgrade() -> None:
    ${upgrade_ops}


def downgrade() -> None:
    ${downgrade_ops}