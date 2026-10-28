from datetime import date, datetime, timezone
from sqlalchemy import String, Integer, Date, DateTime, ForeignKey, CheckConstraint, Index
from sqlalchemy.orm import Mapped, mapped_column
from backend.db import Base

def utcnow(): return datetime.now(timezone.utc)

class Worker(Base):
    __tablename__ = "workers"
    __table_args__ = (CheckConstraint("status IN ('Active','Inactive')", name="ck_worker_status"), Index("ix_workers_name", "name"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    worker_no: Mapped[str] = mapped_column(String(40), unique=True, nullable=False, index=True)
    worker_id: Mapped[str] = mapped_column(String(40), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    contractor_name: Mapped[str] = mapped_column(String(120), nullable=False)
    joining_date: Mapped[date] = mapped_column(Date, nullable=False)
    contact_no: Mapped[str] = mapped_column(String(16), nullable=False)
    emergency_contact: Mapped[str] = mapped_column(String(16), nullable=False)
    aadhaar_encrypted: Mapped[str | None] = mapped_column(String(512))
    aadhaar_last4: Mapped[str] = mapped_column(String(4), nullable=False)
    photo_path: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(8), nullable=False, default="Active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

class Sequence(Base):
    __tablename__ = "sequences"
    name: Mapped[str] = mapped_column(String(40), primary_key=True)
    value: Mapped[int] = mapped_column(Integer, nullable=False)

class Admin(Base):
    __tablename__ = "admins"
    __table_args__ = (CheckConstraint("role IN ('ADMIN', 'GATE', 'CANTEEN')", name="ck_admin_role"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False, default="ADMIN")


class Visitor(Base):
    __tablename__ = "visitors"
    __table_args__ = (
        CheckConstraint("status IN ('Active','Inactive')", name="ck_visitor_status"),
        Index("ix_visitors_name", "name"),
        Index("ix_visitors_status", "status"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    visitor_no: Mapped[str] = mapped_column(String(40), unique=True, nullable=False, index=True)
    visitor_id: Mapped[str] = mapped_column(String(40), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    company_name: Mapped[str] = mapped_column(String(120), nullable=False)
    location: Mapped[str] = mapped_column(String(120), nullable=False)
    host: Mapped[str] = mapped_column(String(120), nullable=False)
    purpose: Mapped[str] = mapped_column(String(255), nullable=False)
    contact_no: Mapped[str] = mapped_column(String(16), nullable=False)
    aadhaar_encrypted: Mapped[str | None] = mapped_column(String(512), nullable=True)
    aadhaar_last4: Mapped[str] = mapped_column(String(4), nullable=False)
    photo_path: Mapped[str | None] = mapped_column(String(255), nullable=True)
    registration_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expiration_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(10), nullable=False, default="Active")
    created_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("admins.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class GateTransaction(Base):
    __tablename__ = "gate_transactions"
    __table_args__ = (
        Index("ix_gate_person_date", "person_id", "event_date"),
        Index("ix_gate_event_date", "event_date"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    scan_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    person_id: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    person_type: Mapped[str] = mapped_column(String(10), nullable=False)  # WORKER, VISITOR
    event_type: Mapped[str | None] = mapped_column(String(10), nullable=True)  # ENTRY, EXIT
    barcode_scanned: Mapped[str] = mapped_column(String(120), nullable=False)
    validation_result: Mapped[str] = mapped_column(String(10), nullable=False)  # ACCEPTED, REJECTED
    rejection_reason: Mapped[str | None] = mapped_column(String(60), nullable=True)
    operator_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("admins.id"), nullable=True)


class CanteenTransaction(Base):
    __tablename__ = "canteen_transactions"
    __table_args__ = (
        Index("ix_canteen_worker_date", "worker_id", "business_date"),
        Index("ix_canteen_business_date", "business_date"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # Legacy column name retained for existing SQLite databases; it stores either a worker or visitor ID.
    worker_id: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    person_type: Mapped[str] = mapped_column(String(10), nullable=False, default="WORKER")
    business_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    scan_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    gate_entry_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("gate_transactions.id"), nullable=True)
    operator_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("admins.id"), nullable=True)
    scan_result: Mapped[str] = mapped_column(String(10), nullable=False)  # ACCEPTED, REJECTED
    rejection_reason: Mapped[str | None] = mapped_column(String(60), nullable=True)


