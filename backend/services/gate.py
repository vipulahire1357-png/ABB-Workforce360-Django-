"""Gate entry/exit state machine and scan processing."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models import Worker, Visitor, GateTransaction
from backend.services.timezone import site_tz, now_local

MIN_MINUTES = 10  # Minimum time between ENTRY and EXIT


@dataclass
class ScanResult:
    accepted: bool
    event_type: str | None = None
    reason: str = ""
    person: dict[str, Any] | None = None
    entry_time: str | None = None
    remaining_seconds: int | None = None
    transaction_id: int | None = None


def _person_worker(w: Worker) -> dict:
    return {
        "person_type": "WORKER", "person_id": w.worker_id, "name": w.name,
        "detail": w.contractor_name, "worker_no": w.worker_no,
        "photo_url": f"/api/workers/{w.worker_id}/photo", "status": w.status,
    }


def _person_visitor(v: Visitor) -> dict:
    return {
        "person_type": "VISITOR", "person_id": v.visitor_id, "name": v.name,
        "detail": v.company_name, "visitor_no": v.visitor_no,
        "photo_url": f"/api/visitors/{v.visitor_id}/photo" if v.photo_path else None,
        "status": v.status,
    }


def _today_accepted(db: Session, person_id: str, event_date):
    """Return today's ACCEPTED gate transactions for a person, ordered by time."""
    return list(db.scalars(
        select(GateTransaction).where(
            GateTransaction.person_id == person_id,
            GateTransaction.event_date == event_date,
            GateTransaction.validation_result == "ACCEPTED",
        ).order_by(GateTransaction.scan_timestamp.asc())
    ))


def _record(db, *, event_date, scan_ts, person_id, person_type, event_type,
            barcode, result, reason=None, operator_id=None):
    txn = GateTransaction(
        event_date=event_date, scan_timestamp=scan_ts, person_id=person_id,
        person_type=person_type, event_type=event_type, barcode_scanned=barcode,
        validation_result=result, rejection_reason=reason, operator_id=operator_id,
    )
    db.add(txn)
    db.flush()
    return txn


def _state_machine(db, person_id, person_type, person, barcode,
                   scan_ts, event_date, operator_id) -> ScanResult:
    """Core ENTRY/EXIT state machine applied identically to workers and visitors."""
    accepted = _today_accepted(db, person_id, event_date)
    entries = [t for t in accepted if t.event_type == "ENTRY"]
    exits = [t for t in accepted if t.event_type == "EXIT"]

    # Already completed ENTRY+EXIT pair today
    if exits:
        _record(db, event_date=event_date, scan_ts=scan_ts, person_id=person_id,
                person_type=person_type, event_type="ENTRY", barcode=barcode,
                result="REJECTED", reason="ALREADY_COMPLETED", operator_id=operator_id)
        et = entries[0].scan_timestamp.isoformat() if entries else None
        return ScanResult(False, None, "ALREADY_COMPLETED", person, et)

    # First scan today — ENTRY
    if not entries:
        txn = _record(db, event_date=event_date, scan_ts=scan_ts, person_id=person_id,
                      person_type=person_type, event_type="ENTRY", barcode=barcode,
                      result="ACCEPTED", operator_id=operator_id)
        return ScanResult(True, "ENTRY", "ENTRY_ACCEPTED", person,
                          scan_ts.isoformat(), transaction_id=txn.id)

    # Has ENTRY, no EXIT — check 10-minute rule using server timestamps
    entry_ts = entries[0].scan_timestamp
    if entry_ts.tzinfo is None:
        entry_ts = entry_ts.replace(tzinfo=site_tz())
    elapsed = (scan_ts - entry_ts).total_seconds() / 60.0

    if elapsed < MIN_MINUTES:
        remaining = max(0, int((MIN_MINUTES - elapsed) * 60))
        _record(db, event_date=event_date, scan_ts=scan_ts, person_id=person_id,
                person_type=person_type, event_type="EXIT", barcode=barcode,
                result="REJECTED", reason="NOT_YET_ELIGIBLE", operator_id=operator_id)
        return ScanResult(False, "EXIT", "NOT_YET_ELIGIBLE", person,
                          entries[0].scan_timestamp.isoformat(), remaining)

    # EXIT accepted
    txn = _record(db, event_date=event_date, scan_ts=scan_ts, person_id=person_id,
                  person_type=person_type, event_type="EXIT", barcode=barcode,
                  result="ACCEPTED", operator_id=operator_id)
    return ScanResult(True, "EXIT", "EXIT_ACCEPTED", person,
                      entries[0].scan_timestamp.isoformat(), transaction_id=txn.id)


def process_scan(db: Session, barcode: str, operator_id: int | None) -> ScanResult:
    """Process a gate barcode scan: resolve person, validate, and apply state machine."""
    barcode = barcode.strip().upper()
    if not barcode:
        return ScanResult(False, None, "INVALID_ID")

    scan_ts = now_local()
    event_date = scan_ts.date()

    # --- Try worker ---
    worker = db.scalar(select(Worker).where(Worker.worker_id == barcode))
    if worker:
        person = _person_worker(worker)
        if worker.status != "Active":
            _record(db, event_date=event_date, scan_ts=scan_ts, person_id=worker.worker_id,
                    person_type="WORKER", event_type="ENTRY", barcode=barcode,
                    result="REJECTED", reason="WORKER_INACTIVE", operator_id=operator_id)
            return ScanResult(False, None, "WORKER_INACTIVE", person)
        return _state_machine(db, worker.worker_id, "WORKER", person,
                              barcode, scan_ts, event_date, operator_id)

    # --- Try visitor ---
    visitor = db.scalar(select(Visitor).where(Visitor.visitor_id == barcode))
    if visitor:
        person = _person_visitor(visitor)
        if visitor.status != "Active":
            _record(db, event_date=event_date, scan_ts=scan_ts, person_id=visitor.visitor_id,
                    person_type="VISITOR", event_type="ENTRY", barcode=barcode,
                    result="REJECTED", reason="VISITOR_INACTIVE", operator_id=operator_id)
            return ScanResult(False, None, "VISITOR_INACTIVE", person)
        # Check expiration
        exp = visitor.expiration_timestamp
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=site_tz())
        if scan_ts > exp:
            visitor.status = "Inactive"
            _record(db, event_date=event_date, scan_ts=scan_ts, person_id=visitor.visitor_id,
                    person_type="VISITOR", event_type="ENTRY", barcode=barcode,
                    result="REJECTED", reason="VISITOR_EXPIRED", operator_id=operator_id)
            person["status"] = "Inactive"
            return ScanResult(False, None, "VISITOR_EXPIRED", person)
        return _state_machine(db, visitor.visitor_id, "VISITOR", person,
                              barcode, scan_ts, event_date, operator_id)

    # --- Unknown ID ---
    _record(db, event_date=event_date, scan_ts=scan_ts, person_id=barcode,
            person_type="UNKNOWN", event_type="ENTRY", barcode=barcode,
            result="REJECTED", reason="INVALID_ID", operator_id=operator_id)
    return ScanResult(False, None, "INVALID_ID")

