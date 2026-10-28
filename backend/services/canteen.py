"""Canteen scan validation — one successful meal per eligible person per business day."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models import Worker, Visitor, GateTransaction, CanteenTransaction
from backend.services.timezone import now_local, site_tz


@dataclass
class CanteenResult:
    accepted: bool
    reason: str = ""
    person: dict[str, Any] | None = None
    gate_entry_time: str | None = None
    transaction_id: int | None = None


def _person_worker(w: Worker) -> dict:
    return {
        "person_type": "WORKER", "person_id": w.worker_id, "name": w.name,
        "worker_no": w.worker_no, "detail": w.contractor_name,
        "photo_url": f"/api/workers/{w.worker_id}/photo",
    }


def _person_visitor(v: Visitor) -> dict:
    return {
        "person_type": "VISITOR", "person_id": v.visitor_id, "name": v.name,
        "visitor_no": v.visitor_no, "detail": v.company_name,
        "photo_url": f"/api/visitors/{v.visitor_id}/photo" if v.photo_path else None,
    }


def _record(db, person_id, person_type, business_date, scan_ts, gate_entry_id,
            operator_id, result, reason):
    txn = CanteenTransaction(
        worker_id=person_id, person_type=person_type, business_date=business_date,
        scan_timestamp=scan_ts, gate_entry_id=gate_entry_id,
        operator_id=operator_id, scan_result=result,
        rejection_reason=reason,
    )
    db.add(txn)
    db.flush()
    return txn


def process_scan(db: Session, barcode: str, operator_id: int | None) -> CanteenResult:
    """Process a canteen scan for an active worker or visitor with today's gate entry."""
    barcode = barcode.strip().upper()
    if not barcode:
        return CanteenResult(False, "INVALID_ID")

    scan_ts = now_local()
    business_date = scan_ts.date()

    # Resolve worker first, then visitor. IDs are case-insensitive to accommodate scanner case settings.
    worker = db.scalar(select(Worker).where(Worker.worker_id == barcode))
    if worker:
        person_id, person_type = worker.worker_id, "WORKER"
        person = _person_worker(worker)
        eligible = worker.status == "Active"
        if not eligible:
            _record(db, person_id, person_type, business_date, scan_ts, None, operator_id,
                    "REJECTED", "WORKER_NOT_ELIGIBLE")
            return CanteenResult(False, "WORKER_NOT_ELIGIBLE", person)
    else:
        visitor = db.scalar(select(Visitor).where(Visitor.visitor_id == barcode))
        if not visitor:
            _record(db, barcode, "UNKNOWN", business_date, scan_ts, None, operator_id,
                    "REJECTED", "PERSON_NOT_FOUND")
            return CanteenResult(False, "PERSON_NOT_FOUND")

        person_id, person_type = visitor.visitor_id, "VISITOR"
        person = _person_visitor(visitor)
        exp = visitor.expiration_timestamp
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=site_tz())
        if visitor.status != "Active" or scan_ts > exp:
            if scan_ts > exp:
                visitor.status = "Inactive"
            _record(db, person_id, person_type, business_date, scan_ts, None, operator_id,
                    "REJECTED", "VISITOR_NOT_ELIGIBLE")
            return CanteenResult(False, "VISITOR_NOT_ELIGIBLE", person)

    # Check for qualifying gate ENTRY today (ACCEPTED entries only)
    gate_entry = db.scalar(
        select(GateTransaction).where(
            GateTransaction.person_id == person_id,
            GateTransaction.event_date == business_date,
            GateTransaction.event_type == "ENTRY",
            GateTransaction.validation_result == "ACCEPTED",
        ).order_by(GateTransaction.scan_timestamp.asc()).limit(1)
    )
    if not gate_entry:
        _record(db, person_id, person_type, business_date, scan_ts, None, operator_id,
                "REJECTED", "NO_GATE_ENTRY")
        return CanteenResult(False, "NO_GATE_ENTRY", person)

    # Check for existing successful canteen scan today
    existing = db.scalar(
        select(CanteenTransaction).where(
            CanteenTransaction.worker_id == person_id,
            CanteenTransaction.business_date == business_date,
            CanteenTransaction.scan_result == "ACCEPTED",
        )
    )
    if existing:
        _record(db, person_id, person_type, business_date, scan_ts, gate_entry.id,
                operator_id, "REJECTED", "ALREADY_SCANNED")
        return CanteenResult(False, "ALREADY_SCANNED", person,
                             gate_entry.scan_timestamp.isoformat())

    # Accept
    txn = _record(db, person_id, person_type, business_date, scan_ts, gate_entry.id,
                  operator_id, "ACCEPTED", None)
    return CanteenResult(True, "CANTEEN_SCAN_ACCEPTED", person,
                         gate_entry.scan_timestamp.isoformat(), txn.id)

