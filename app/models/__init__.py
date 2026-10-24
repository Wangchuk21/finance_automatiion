"""SQLAlchemy models for all tables."""

import enum
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class ContractState(str, enum.Enum):
    """Contract state enumeration."""

    ACTIVE = "active"
    MISSING_REVIEW = "missing_review"
    CLOSED = "closed"
    REOPENED = "reopened"


class InstallmentStatus(str, enum.Enum):
    """Installment status enumeration."""

    PENDING = "pending"
    PARTIAL = "partial"
    PAID = "paid"
    OVERDUE = "overdue"
    WAIVED = "waived"


class UploadStatus(str, enum.Enum):
    """Upload status enumeration."""

    PENDING = "pending"
    CONFIRMED = "confirmed"
    ROLLED_BACK = "rolled_back"


class Contract(Base):
    """Main contracts table."""

    __tablename__ = "contracts"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    reference: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    item: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    brand: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    region: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    cost_center: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    ministry_agency: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    payment_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    emi_months: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    customer: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    cid: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, index=True)
    mobile: Mapped[Optional[str]] = mapped_column(String(20), nullable=True, index=True)

    # Dates
    contract_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    start_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    end_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)

    # Financial
    monthly_deduction: Mapped[Optional[Decimal]] = mapped_column(Numeric(15, 2), nullable=True)
    sales_amount: Mapped[Optional[Decimal]] = mapped_column(Numeric(15, 2), nullable=True)
    gst: Mapped[Optional[Decimal]] = mapped_column(Numeric(15, 2), nullable=True)

    # State
    state: Mapped[ContractState] = mapped_column(
        Enum(ContractState, native_enum=False),
        default=ContractState.ACTIVE,
        nullable=False,
        index=True,
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Relationships
    installments: Mapped[list["Installment"]] = relationship(
        "Installment", back_populates="contract", lazy="dynamic"
    )
    closures: Mapped[list["ContractClosure"]] = relationship(
        "ContractClosure", back_populates="contract", lazy="dynamic"
    )

    __table_args__ = (
        Index("ix_contracts_customer_cid", "customer", "cid"),
        Index("ix_contracts_brand_region", "brand", "region"),
        CheckConstraint("monthly_deduction >= 0", name="ck_monthly_deduction_nonneg"),
        CheckConstraint("sales_amount >= 0", name="ck_sales_amount_nonneg"),
        CheckConstraint("gst >= 0", name="ck_gst_nonneg"),
    )

    def __repr__(self) -> str:
        return f"<Contract(id={self.id}, reference='{self.reference}', state='{self.state}')>"


class Installment(Base):
    """Installments for each contract."""

    __tablename__ = "installments"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    contract_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("contracts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    due_month: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    due_amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    received_amount: Mapped[Decimal] = mapped_column(Numeric(15, 2), default=Decimal("0"), nullable=False)
    salary_amount: Mapped[Optional[Decimal]] = mapped_column(Numeric(15, 2), nullable=True)
    status: Mapped[InstallmentStatus] = mapped_column(
        Enum(InstallmentStatus, native_enum=False),
        default=InstallmentStatus.PENDING,
        nullable=False,
        index=True,
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Relationships
    contract: Mapped["Contract"] = relationship("Contract", back_populates="installments")
    history: Mapped[list["InstallmentHistory"]] = relationship(
        "InstallmentHistory", back_populates="installment", lazy="dynamic"
    )

    __table_args__ = (
        UniqueConstraint("contract_id", "due_month", name="uq_installment_contract_month"),
        CheckConstraint("due_amount >= 0", name="ck_due_amount_nonneg"),
        CheckConstraint("received_amount >= 0", name="ck_received_amount_nonneg"),
        CheckConstraint("received_amount <= due_amount", name="ck_received_not_exceed_due"),
        Index("ix_installments_contract_due", "contract_id", "due_month"),
    )

    def __repr__(self) -> str:
        return f"<Installment(id={self.id}, contract_id={self.contract_id}, due_month={self.due_month}, status={self.status})>"


class InstallmentHistory(Base):
    """History of installment status changes per upload."""

    __tablename__ = "installment_history"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    installment_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("installments.id", ondelete="CASCADE"), nullable=False, index=True
    )
    upload_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("uploads.id", ondelete="CASCADE"), nullable=False, index=True
    )
    previous_status: Mapped[Optional[InstallmentStatus]] = mapped_column(
        Enum(InstallmentStatus, native_enum=False), nullable=True
    )
    new_status: Mapped[InstallmentStatus] = mapped_column(
        Enum(InstallmentStatus, native_enum=False), nullable=False
    )
    previous_received: Mapped[Optional[Decimal]] = mapped_column(Numeric(15, 2), nullable=True)
    new_received: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    installment: Mapped["Installment"] = relationship("Installment", back_populates="history")
    upload: Mapped["Upload"] = relationship("Upload", back_populates="installment_history")

    __table_args__ = (
        Index("ix_installment_history_installment_upload", "installment_id", "upload_id"),
    )

    def __repr__(self) -> str:
        return f"<InstallmentHistory(installment_id={self.installment_id}, upload_id={self.upload_id}, status={self.new_status})>"


class Upload(Base):
    """File upload tracking."""

    __tablename__ = "uploads"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    checksum: Mapped[str] = mapped_column(String(64), nullable=False, index=True)  # SHA256
    uploaded_by: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=False)
    upload_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    as_of_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    status: Mapped[UploadStatus] = mapped_column(
        Enum(UploadStatus, native_enum=False),
        default=UploadStatus.PENDING,
        nullable=False,
        index=True,
    )
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON summary

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Relationships
    uploader: Mapped["User"] = relationship("User", back_populates="uploads")
    installment_history: Mapped[list["InstallmentHistory"]] = relationship(
        "InstallmentHistory", back_populates="upload", lazy="dynamic"
    )
    closures: Mapped[list["ContractClosure"]] = relationship(
        "ContractClosure", back_populates="upload", lazy="dynamic"
    )

    __table_args__ = (
        UniqueConstraint("checksum", name="uq_upload_checksum"),
        Index("ix_uploads_uploader_time", "uploaded_by", "upload_time"),
    )

    def __repr__(self) -> str:
        return f"<Upload(id={self.id}, file_name='{self.file_name}', status={self.status})>"


class ContractClosure(Base):
    """Contract closure records."""

    __tablename__ = "contract_closures"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    contract_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("contracts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    upload_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("uploads.id", ondelete="SET NULL"), nullable=True
    )
    reason: Mapped[str] = mapped_column(String(200), nullable=False)
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    balance_at_closing: Mapped[Decimal] = mapped_column(Numeric(15, 2), nullable=False)
    closed_by: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=False)
    closed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    contract: Mapped["Contract"] = relationship("Contract", back_populates="closures")
    upload: Mapped[Optional["Upload"]] = relationship("Upload", back_populates="closures")
    closer: Mapped["User"] = relationship("User", foreign_keys=[closed_by])

    __table_args__ = (
        Index("ix_contract_closures_contract_closed", "contract_id", "closed_at"),
    )

    def __repr__(self) -> str:
        return f"<ContractClosure(contract_id={self.contract_id}, reason='{self.reason}')>"


class Contact(Base):
    """Contact information for customers."""

    __tablename__ = "contacts"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    cid: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    mobile: Mapped[Optional[str]] = mapped_column(String(20), nullable=True, index=True)
    source: Mapped[str] = mapped_column(String(50), nullable=False, default="manual")
    last_synced_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    history: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON history

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        Index("ix_contacts_email", "email"),
    )

    def __repr__(self) -> str:
        return f"<Contact(cid='{self.cid}', email='{self.email}')>"


class NotificationTemplate(Base):
    """Notification templates."""

    __tablename__ = "notification_templates"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    channel: Mapped[str] = mapped_column(String(20), nullable=False)  # email, sms, push
    subject: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    body_template: Mapped[str] = mapped_column(Text, nullable=False)
    variables: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON schema
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return f"<NotificationTemplate(name='{self.name}', channel='{self.channel}')>"


class Notification(Base):
    """Notifications sent to users/customers."""

    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    template_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("notification_templates.id", ondelete="SET NULL"), nullable=True
    )
    recipient_type: Mapped[str] = mapped_column(String(20), nullable=False)  # user, customer
    recipient_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    channel: Mapped[str] = mapped_column(String(20), nullable=False)
    subject: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False, index=True)
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    meta: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON metadata

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    template: Mapped[Optional["NotificationTemplate"]] = relationship("NotificationTemplate")

    __table_args__ = (
        Index("ix_notifications_recipient_status", "recipient_type", "recipient_id", "status"),
        Index("ix_notifications_created", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<Notification(id={self.id}, recipient={self.recipient_id}, status={self.status})>"


class User(Base):
    """System users."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    full_name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)
    is_superuser: Mapped[bool] = mapped_column(default=False, nullable=False)
    role: Mapped[str] = mapped_column(String(50), default="viewer", nullable=False)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    last_login: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    uploads: Mapped[list["Upload"]] = relationship("Upload", back_populates="uploader")
    closures: Mapped[list["ContractClosure"]] = relationship("ContractClosure", back_populates="closer")

    __table_args__ = (
        Index("ix_users_email_active", "email", "is_active"),
    )

    def __repr__(self) -> str:
        return f"<User(id={self.id}, username='{self.username}', role='{self.role}')>"


class AuditLog(Base):
    """Audit log for all important actions."""

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    action: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    entity_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    old_values: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON
    new_values: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON
    ip_address: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )

    __table_args__ = (
        Index("ix_audit_log_entity", "entity_type", "entity_id"),
        Index("ix_audit_log_user_action", "user_id", "action"),
    )

    def __repr__(self) -> str:
        return f"<AuditLog(action='{self.action}', entity={self.entity_type}:{self.entity_id})>"