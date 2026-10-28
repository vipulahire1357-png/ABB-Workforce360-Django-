"""Visitor registration and lifecycle management."""

from __future__ import annotations

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from backend.models import Visitor, Sequence
from backend.services.identity import new_visitor_id, encrypt_aadhaar
from backend.services.timezone import site_tz, now_local


def register_visitor(db: Session, *, name: str, company_name: str, location: str,
                     host: str, purpose: str, contact_no: str, aadhaar_no: str,
                     photo_path: str | None, operator_id: int | None) -> Visitor:
    """Create a new visitor with atomic number allocation.

    The registration expires at 23:59:59 on the registration date (site timezone).
    """
    now = now_local()
    expiration = now.replace(hour=23, minute=59, second=59, microsecond=999999)

    # Atomic visitor number allocation — same SQLite UPDATE pattern as workers
    db.execute(
        Sequence.__table__.insert().prefix_with("OR IGNORE")
        .values(name="visitor_no", value=0)
    )
    seq = db.execute(
        update(Sequence).where(Sequence.name == "visitor_no")
        .values(value=Sequence.value + 1)
        .returning(Sequence.value)
    ).scalar_one()

    visitor_no = f"ABB-P3-V-{seq}"
    visitor_id = new_visitor_id(visitor_no, aadhaar_no)

    visitor = Visitor(
        visitor_no=visitor_no,
        visitor_id=visitor_id,
        name=name,
        company_name=company_name,
        location=location,
        host=host,
        purpose=purpose,
        contact_no=contact_no,
        aadhaar_encrypted=encrypt_aadhaar(aadhaar_no),
        aadhaar_last4=aadhaar_no[-4:],
        photo_path=photo_path,
        registration_timestamp=now,
        expiration_timestamp=expiration,
        status="Active",
        created_by=operator_id,
    )
    db.add(visitor)
    db.flush()
    return visitor


def expire_stale_visitors(db: Session) -> int:
    """Mark expired visitors as Inactive. Returns count updated."""
    now = now_local()
    result = db.execute(
        update(Visitor)
        .where(Visitor.status == "Active", Visitor.expiration_timestamp < now)
        .values(status="Inactive")
    )
    db.commit()
    return result.rowcount


def is_visitor_valid(visitor: Visitor) -> bool:
    """Check if a visitor registration is currently valid."""
    if visitor.status != "Active":
        return False
    now = now_local()
    exp = visitor.expiration_timestamp
    if exp.tzinfo is None:
        exp = exp.replace(tzinfo=site_tz())
    return now <= exp


def serialize_visitor(v: Visitor) -> dict:
    """Safe serialization of a visitor record — Aadhaar masked."""
    return {
        "visitor_id": v.visitor_id,
        "visitor_no": v.visitor_no,
        "name": v.name,
        "company_name": v.company_name,
        "location": v.location,
        "host": v.host,
        "purpose": v.purpose,
        "contact_no": v.contact_no,
        "aadhaar_masked": f"XXXX XXXX {v.aadhaar_last4}",
        "photo_url": f"/api/visitors/{v.visitor_id}/photo" if v.photo_path else None,
        "registration_timestamp": v.registration_timestamp.isoformat() if v.registration_timestamp else None,
        "expiration_timestamp": v.expiration_timestamp.isoformat() if v.expiration_timestamp else None,
        "status": v.status,
    }
