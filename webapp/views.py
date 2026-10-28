"""Django presentation and HTTP layer over the preserved Workforce360 domain services.

The existing SQLAlchemy schema is intentionally retained in place so this web
layer can use the current local database and records without a lossy conversion.
"""
import json
from datetime import date
from functools import wraps
from pathlib import Path

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, InvalidHashError
from django.http import FileResponse, HttpResponse, JsonResponse
from django.middleware.csrf import get_token
from django.shortcuts import render
from django.views.decorators.http import require_GET, require_POST, require_http_methods
from sqlalchemy import func, select

from backend import db as legacy_db
from backend.config import settings as app_settings
from backend.models import Admin, Worker, Visitor, GateTransaction, CanteenTransaction, Sequence
from webapp.forms import WorkerRegistrationForm, VisitorRegistrationForm, WorkerStatusForm
from backend.services.identity import new_worker_id, encrypt_aadhaar
from backend.services.photos import MAX_BYTES, validate_photo
from backend.services import gate as gate_service, canteen as canteen_service
from backend.services.visitors import register_visitor, expire_stale_visitors, serialize_visitor
from backend.services.cards import card_pdf, CardAssetError
from backend.services.visitor_cards import visitor_card_pdf
from backend.services.timezone import today_local
from sqlalchemy import update

hasher = PasswordHasher()


def api_error(message, status=400):
    return JsonResponse({"detail": message}, status=status)


def parse_body(request):
    if request.content_type and "application/json" in request.content_type:
        try:
            return json.loads(request.body or b"{}")
        except (ValueError, UnicodeDecodeError):
            return None
    return request.POST


def signed_in(view):
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        user = request.session.get("operator")
        if not user:
            return api_error("Authentication required", 401)
        request.operator = user
        return view(request, *args, **kwargs)
    return wrapped


def roles(*allowed):
    def decorate(view):
        @wraps(view)
        @signed_in
        def wrapped(request, *args, **kwargs):
            if request.operator.get("role") not in allowed:
                return api_error("Access denied for this role", 403)
            return view(request, *args, **kwargs)
        return wrapped
    return decorate


def database():
    return legacy_db.SessionLocal()


def serialize_worker(worker):
    return {
        "worker_id": worker.worker_id, "worker_no": worker.worker_no,
        "name": worker.name, "contractor_name": worker.contractor_name,
        "joining_date": worker.joining_date.isoformat(), "contact_no": worker.contact_no,
        "emergency_contact": worker.emergency_contact,
        "aadhaar_masked": f"XXXX XXXX {worker.aadhaar_last4}",
        "photo_url": f"/api/workers/{worker.worker_id}/photo", "status": worker.status,
    }


def serialize_gate(row, name=None, photo_url=None):
    return {"id": row.id, "event_date": row.event_date.isoformat(),
            "scan_timestamp": row.scan_timestamp.isoformat() if row.scan_timestamp else None,
            "person_id": row.person_id, "person_type": row.person_type,
            "event_type": row.event_type, "barcode_scanned": row.barcode_scanned,
            "validation_result": row.validation_result, "rejection_reason": row.rejection_reason,
            "operator_id": row.operator_id, "name": name, "photo_url": photo_url}


def serialize_canteen(row, name=None, photo_url=None):
    return {"id": row.id, "person_id": row.worker_id, "worker_id": row.worker_id,
            "person_type": row.person_type, "business_date": row.business_date.isoformat(),
            "scan_timestamp": row.scan_timestamp.isoformat() if row.scan_timestamp else None,
            "gate_entry_id": row.gate_entry_id, "operator_id": row.operator_id,
            "scan_result": row.scan_result, "rejection_reason": row.rejection_reason,
            "name": name, "photo_url": photo_url}


def _resolve_person_details(db, rows_with_person_id, id_attr="person_id"):
    """Look up name and photo_url for a list of transaction rows."""
    ids = {getattr(r, id_attr) for r in rows_with_person_id}
    person_map = {}
    if ids:
        workers = db.scalars(select(Worker).where(Worker.worker_id.in_(ids))).all()
        for w in workers:
            person_map[w.worker_id] = (w.name, f"/api/workers/{w.worker_id}/photo")
        visitor_ids = ids - set(person_map.keys())
        if visitor_ids:
            visitors_found = db.scalars(select(Visitor).where(Visitor.visitor_id.in_(visitor_ids))).all()
            for v in visitors_found:
                photo = f"/api/visitors/{v.visitor_id}/photo" if v.photo_path else None
                person_map[v.visitor_id] = (v.name, photo)
    return person_map


def valid_photo(upload, required=False):
    if not upload:
        if required:
            raise ValueError("Photo is required")
        return None
    if upload.size > MAX_BYTES:
        raise ValueError("Photo must be 200 KB or smaller")
    return validate_photo(upload.read(MAX_BYTES + 1), required=required)


def home(request):
    if request.session.get("operator"):
        context = {"operator": request.session["operator"], "csrf_token": get_token(request)}
        return render(request, "webapp/index.html", context)
    return render(request, "webapp/login.html", {"csrf_token": get_token(request)})


@require_GET
def health(request):
    db = database()
    try:
        db.execute(select(1))
        return JsonResponse({"status": "ok"})
    finally:
        db.close()


@require_POST
def login_view(request):
    body = parse_body(request)
    if not isinstance(body, dict):
        return api_error("Invalid login request", 422)
    username = str(body.get("username", "")).strip()
    password = str(body.get("password", ""))
    if not username or len(username) > 80 or not password or len(password) > 200:
        return api_error("Invalid username or password", 401)
    db = database()
    try:
        admin = db.scalar(select(Admin).where(Admin.username == username))
        if not admin:
            try:
                hasher.verify(hasher.hash("invalid-account-placeholder"), password)
            except Exception:
                pass
            return api_error("Invalid username or password", 401)
        try:
            hasher.verify(admin.password_hash, password)
        except (VerifyMismatchError, InvalidHashError):
            return api_error("Invalid username or password", 401)
        if hasher.check_needs_rehash(admin.password_hash):
            admin.password_hash = hasher.hash(password)
            db.commit()
        request.session.cycle_key()
        request.session["operator"] = {"id": admin.id, "username": admin.username, "role": getattr(admin, "role", "ADMIN")}
        token = get_token(request)
        return JsonResponse({**request.session["operator"], "csrf_token": token})
    finally:
        db.close()


@require_GET
@signed_in
def me(request):
    return JsonResponse({**request.operator, "csrf_token": get_token(request)})


@require_POST
@signed_in
def logout_view(request):
    request.session.flush()
    return JsonResponse({"status": "ok"})


@require_GET
@roles("ADMIN", "GATE", "CANTEEN")
def summary(request):
    db = database()
    try:
        total = db.scalar(select(func.count()).select_from(Worker)) or 0
        active = db.scalar(select(func.count()).select_from(Worker).where(Worker.status == "Active")) or 0
        return JsonResponse({"total": total, "active": active, "inactive": total - active})
    finally:
        db.close()


@require_http_methods(["GET", "POST"])
@roles("ADMIN", "GATE", "CANTEEN")
def workers(request):
    db = database()
    try:
        if request.method == "POST":
            form = WorkerRegistrationForm(data=request.POST, files=request.FILES)
            if not form.is_valid():
                return api_error("Invalid registration details", 422)
            values = form.domain_value
            try:
                photo = valid_photo(form.cleaned_data.get("photo"), required=True)
            except ValueError as error:
                return api_error(str(error), 422)
            if not app_settings.aadhaar_encryption_key:
                return api_error("Aadhaar encryption is not configured", 503)
            if not app_settings.worker_id_secret:
                return api_error("Worker ID generation is not configured", 503)
            saved = None
            try:
                db.rollback()
                db.execute(__import__("sqlalchemy").text("BEGIN IMMEDIATE"))
                db.execute(Sequence.__table__.insert().prefix_with("OR IGNORE").values(name="worker_no", value=0))
                number = db.execute(update(Sequence).where(Sequence.name == "worker_no").values(value=Sequence.value + 1).returning(Sequence.value)).scalar_one()
                worker_no = f"ABB-P3-W-{number}"
                worker_id = new_worker_id(worker_no, values.aadhaar_no)
                app_settings.upload_dir.mkdir(parents=True, exist_ok=True)
                saved = app_settings.upload_dir / f"{worker_id}.jpg"
                saved.write_bytes(photo)
                worker = Worker(worker_no=worker_no, worker_id=worker_id, name=values.name,
                    contractor_name=values.contractor_name, joining_date=values.joining_date,
                    contact_no=values.contact_no, emergency_contact=values.emergency_contact,
                    aadhaar_encrypted=encrypt_aadhaar(values.aadhaar_no), aadhaar_last4=values.aadhaar_no[-4:],
                    photo_path=saved.name, status="Active")
                db.add(worker); db.flush(); db.commit()
                return JsonResponse(serialize_worker(worker), status=201)
            except Exception:
                db.rollback()
                if saved:
                    saved.unlink(missing_ok=True)
                return api_error("Registration could not be completed", 409)
        page = max(1, int(request.GET.get("page", 1)))
        page_size = min(100, max(1, int(request.GET.get("page_size", 25))))
        sort = request.GET.get("sort", "worker_no")
        direction = request.GET.get("direction", "asc")
        fields = {"worker_no": Worker.worker_no, "name": Worker.name, "joining_date": Worker.joining_date, "status": Worker.status}
        field = fields.get(sort, Worker.worker_no)
        stmt = select(Worker)
        name = request.GET.get("name", "")[:100]
        if name:
            stmt = stmt.where(Worker.name.ilike(f"%{name}%"))
        total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        order = field.desc() if direction == "desc" else field.asc()
        rows = db.scalars(stmt.order_by(order).offset((page - 1) * page_size).limit(page_size)).all()
        counts = {status: db.scalar(select(func.count()).select_from(Worker).where(Worker.status == status)) or 0 for status in ("Active", "Inactive")}
        return JsonResponse({"items": [serialize_worker(w) for w in rows], "page": page, "page_size": page_size,
            "total": total, "active": counts["Active"], "inactive": counts["Inactive"]})
    except ValueError:
        return api_error("Invalid pagination", 422)
    finally:
        db.close()


@require_GET
@roles("ADMIN", "GATE", "CANTEEN")
def worker_search(request):
    query = request.GET.get("q", "").strip()[:80]
    db = database()
    try:
        rows = db.scalars(select(Worker).where(Worker.name.ilike(f"%{query}%")).order_by(Worker.name).limit(20)).all() if query else []
        return JsonResponse([{"worker_id": w.worker_id, "name": w.name, "worker_no": w.worker_no} for w in rows], safe=False)
    finally:
        db.close()


def find_worker(db, worker_id):
    return db.scalar(select(Worker).where(Worker.worker_id == worker_id))


@require_GET
@roles("ADMIN", "GATE", "CANTEEN")
def worker_detail(request, worker_id):
    db = database()
    try:
        worker = find_worker(db, worker_id)
        return JsonResponse(serialize_worker(worker)) if worker else api_error("Worker not found", 404)
    finally:
        db.close()


@require_http_methods(["POST", "PATCH"])
@roles("ADMIN", "GATE", "CANTEEN")
def worker_status(request, worker_id):
    body = parse_body(request) or {}
    form = WorkerStatusForm(data=body)
    if not form.is_valid():
        return api_error("Status must be Active or Inactive", 422)
    status = form.cleaned_data["status"]
    db = database()
    try:
        worker = find_worker(db, worker_id)
        if not worker:
            return api_error("Worker not found", 404)
        worker.status = status; db.commit()
        return JsonResponse(serialize_worker(worker))
    finally:
        db.close()


@require_GET
@roles("ADMIN", "GATE", "CANTEEN")
def worker_photo(request, worker_id):
    db = database()
    try:
        worker = find_worker(db, worker_id)
        path = app_settings.upload_dir / Path(worker.photo_path).name if worker else None
        if not path or not path.is_file():
            return api_error("Photo not found", 404)
        return FileResponse(path.open("rb"), content_type="image/jpeg", headers={"Cache-Control": "private, no-store"})
    finally:
        db.close()


@require_GET
@roles("ADMIN", "GATE", "CANTEEN")
def worker_card(request, worker_id):
    db = database()
    try:
        worker = find_worker(db, worker_id)
        if not worker:
            return api_error("Worker not found", 404)
        try:
            pdf = card_pdf(worker)
        except CardAssetError:
            return api_error("ID card cannot be generated because a required image asset is missing or invalid", 503)
        response = HttpResponse(pdf, content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="{worker.worker_no}.pdf"'
        response["Cache-Control"] = "private, no-store"
        return response
    finally:
        db.close()


@require_POST
@roles("ADMIN", "GATE")
def gate_scan(request):
    body = parse_body(request) or {}
    barcode = str(body.get("barcode", "")).strip()
    if not barcode or len(barcode) > 120:
        return api_error("Invalid barcode", 422)
    db = database()
    try:
        db.execute(__import__("sqlalchemy").text("BEGIN IMMEDIATE"))
        result = gate_service.process_scan(db, barcode, request.operator["id"])
        db.commit()
        return JsonResponse({"accepted": result.accepted, "event_type": result.event_type, "reason": result.reason,
            "person": result.person, "entry_time": result.entry_time, "remaining_seconds": result.remaining_seconds,
            "transaction_id": result.transaction_id})
    except Exception:
        db.rollback()
        return api_error("Gate scan could not be completed", 409)
    finally:
        db.close()


@require_GET
@roles("ADMIN", "GATE")
def gate_history(request):
    db = database()
    try:
        page = max(1, int(request.GET.get("page", 1))); size = min(100, max(1, int(request.GET.get("page_size", 25))))
        stmt = select(GateTransaction)
        if request.GET.get("event_date"):
            stmt = stmt.where(GateTransaction.event_date == date.fromisoformat(request.GET["event_date"]))
        if request.GET.get("person_type"):
            stmt = stmt.where(GateTransaction.person_type == request.GET["person_type"].upper())
        if request.GET.get("person_id"):
            stmt = stmt.where(GateTransaction.person_id == request.GET["person_id"])
        if request.GET.get("result"):
            stmt = stmt.where(GateTransaction.validation_result == request.GET["result"].upper())
        total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        rows = db.scalars(stmt.order_by(GateTransaction.scan_timestamp.desc()).offset((page - 1) * size).limit(size)).all()
        pmap = _resolve_person_details(db, rows, "person_id")
        items = [serialize_gate(r, *pmap.get(r.person_id, (None, None))) for r in rows]
        return JsonResponse({"items": items, "page": page, "page_size": size, "total": total})
    except ValueError:
        return api_error("Invalid filter", 422)
    finally:
        db.close()


@require_GET
@roles("ADMIN", "GATE")
def gate_report(request):
    db = database()
    try:
        target = date.fromisoformat(request.GET["report_date"]) if request.GET.get("report_date") else today_local()
        rows = list(db.scalars(select(GateTransaction).where(GateTransaction.event_date == target).order_by(GateTransaction.scan_timestamp.asc())))
        accepted = [row for row in rows if row.validation_result == "ACCEPTED"]
        latest_worker_events = {}
        worker_events = db.execute(
            select(GateTransaction.person_id, GateTransaction.event_type)
            .where(
                GateTransaction.person_type == "WORKER",
                GateTransaction.validation_result == "ACCEPTED",
                GateTransaction.event_type.in_(("ENTRY", "EXIT")),
            )
            .order_by(GateTransaction.scan_timestamp.desc(), GateTransaction.id.desc())
        )
        for person_id, event_type in worker_events:
            latest_worker_events.setdefault(person_id, event_type)
        return JsonResponse({"date": target.isoformat(), "total_transactions": len(rows),
            "accepted_entries": sum(row.event_type == "ENTRY" for row in accepted),
            "accepted_exits": sum(row.event_type == "EXIT" for row in accepted),
            "estimated_workers_inside": sum(event_type == "ENTRY" for event_type in latest_worker_events.values()),
            "rejected": sum(row.validation_result == "REJECTED" for row in rows),
            "unique_persons": len({row.person_id for row in accepted}),
            "transactions": [serialize_gate(row) for row in rows]})
    except ValueError:
        return api_error("Invalid report date", 422)
    finally:
        db.close()


@require_http_methods(["GET", "POST"])
@roles("ADMIN", "GATE")
def visitors(request):
    db = database()
    try:
        if request.method == "POST":
            form = VisitorRegistrationForm(data=request.POST, files=request.FILES)
            if not form.is_valid():
                return api_error("Invalid visitor details", 422)
            values = form.domain_value
            try:
                photo = valid_photo(form.cleaned_data.get("photo"))
            except ValueError as error:
                return api_error(str(error), 422)
            if not app_settings.aadhaar_encryption_key:
                return api_error("Aadhaar encryption is not configured", 503)
            saved = None
            try:
                db.execute(__import__("sqlalchemy").text("BEGIN IMMEDIATE"))
                visitor = register_visitor(db, name=values.name, company_name=values.company_name, location=values.location,
                    host=values.host, purpose=values.purpose, contact_no=values.contact_no, aadhaar_no=values.aadhaar_no,
                    photo_path=None, operator_id=request.operator["id"])
                if photo:
                    app_settings.visitor_upload_dir.mkdir(parents=True, exist_ok=True)
                    saved = app_settings.visitor_upload_dir / f"{visitor.visitor_id}.jpg"
                    saved.write_bytes(photo); visitor.photo_path = saved.name; db.flush()
                db.commit()
                return JsonResponse(serialize_visitor(visitor), status=201)
            except Exception:
                db.rollback()
                if saved:
                    saved.unlink(missing_ok=True)
                return api_error("Registration could not be completed", 409)
        page = max(1, int(request.GET.get("page", 1))); size = min(100, max(1, int(request.GET.get("page_size", 25))))
        expire_stale_visitors(db)
        stmt = select(Visitor)
        if request.GET.get("name"):
            stmt = stmt.where(Visitor.name.ilike(f"%{request.GET['name'][:100]}%"))
        if request.GET.get("status"):
            stmt = stmt.where(Visitor.status == request.GET["status"])
        total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        rows = db.scalars(stmt.order_by(Visitor.id.desc()).offset((page - 1) * size).limit(size)).all()
        active = db.scalar(select(func.count()).select_from(Visitor).where(Visitor.status == "Active")) or 0
        inactive = db.scalar(select(func.count()).select_from(Visitor).where(Visitor.status == "Inactive")) or 0
        return JsonResponse({"items": [serialize_visitor(v) for v in rows], "page": page, "page_size": size,
            "total": total, "active": active, "inactive": inactive})
    except ValueError:
        return api_error("Invalid pagination", 422)
    finally:
        db.close()


@require_GET
@roles("ADMIN", "GATE")
def visitor_detail(request, visitor_id):
    db = database()
    try:
        visitor = db.scalar(select(Visitor).where(Visitor.visitor_id == visitor_id))
        return JsonResponse(serialize_visitor(visitor)) if visitor else api_error("Visitor not found", 404)
    finally:
        db.close()


@require_GET
@roles("ADMIN", "GATE")
def visitor_photo(request, visitor_id):
    db = database()
    try:
        visitor = db.scalar(select(Visitor).where(Visitor.visitor_id == visitor_id))
        path = app_settings.visitor_upload_dir / Path(visitor.photo_path).name if visitor and visitor.photo_path else None
        if not path or not path.is_file():
            return api_error("Photo not found", 404)
        return FileResponse(path.open("rb"), content_type="image/jpeg", headers={"Cache-Control": "private, no-store"})
    finally:
        db.close()


@require_GET
@roles("ADMIN", "GATE")
def visitor_card(request, visitor_id):
    db = database()
    try:
        visitor = db.scalar(select(Visitor).where(Visitor.visitor_id == visitor_id))
        if not visitor:
            return api_error("Visitor not found", 404)
        try:
            pdf = visitor_card_pdf(visitor)
        except CardAssetError:
            return api_error("ID card cannot be generated because a required asset is missing", 503)
        response = HttpResponse(pdf, content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="{visitor.visitor_no}.pdf"'
        response["Cache-Control"] = "private, no-store"
        return response
    finally:
        db.close()


@require_POST
@roles("ADMIN", "CANTEEN")
def canteen_scan(request):
    body = parse_body(request) or {}; barcode = str(body.get("barcode", "")).strip()
    if not barcode or len(barcode) > 120:
        return api_error("Invalid barcode", 422)
    db = database()
    try:
        db.execute(__import__("sqlalchemy").text("BEGIN IMMEDIATE"))
        result = canteen_service.process_scan(db, barcode, request.operator["id"]); db.commit()
        return JsonResponse({"accepted": result.accepted, "reason": result.reason, "person": result.person,
            "gate_entry_time": result.gate_entry_time, "transaction_id": result.transaction_id})
    except Exception:
        db.rollback(); return api_error("Canteen scan could not be completed", 409)
    finally:
        db.close()


@require_GET
@roles("ADMIN", "CANTEEN")
def canteen_history(request):
    db = database()
    try:
        page = max(1, int(request.GET.get("page", 1))); size = min(100, max(1, int(request.GET.get("page_size", 25))))
        stmt = select(CanteenTransaction)
        if request.GET.get("business_date"):
            stmt = stmt.where(CanteenTransaction.business_date == date.fromisoformat(request.GET["business_date"]))
        person_id = request.GET.get("person_id") or request.GET.get("worker_id")
        if person_id:
            stmt = stmt.where(CanteenTransaction.worker_id == person_id.strip().upper())
        if request.GET.get("result"):
            stmt = stmt.where(CanteenTransaction.scan_result == request.GET["result"].upper())
        total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        rows = db.scalars(stmt.order_by(CanteenTransaction.scan_timestamp.desc()).offset((page - 1) * size).limit(size)).all()
        pmap = _resolve_person_details(db, rows, "worker_id")
        items = [serialize_canteen(r, *pmap.get(r.worker_id, (None, None))) for r in rows]
        return JsonResponse({"items": items, "page": page, "page_size": size, "total": total})
    except ValueError:
        return api_error("Invalid filter", 422)
    finally:
        db.close()


@require_GET
@roles("ADMIN", "CANTEEN")
def canteen_report(request):
    db = database()
    try:
        target = date.fromisoformat(request.GET["report_date"]) if request.GET.get("report_date") else today_local()
        rows = list(db.scalars(select(CanteenTransaction).where(CanteenTransaction.business_date == target).order_by(CanteenTransaction.scan_timestamp.asc())))
        accepted = [r for r in rows if r.scan_result == "ACCEPTED"]
        rejected = [r for r in rows if r.scan_result == "REJECTED"]
        return JsonResponse({"date": target.isoformat(), "total_scans": len(rows), "successful_scans": len(accepted),
            "unique_people": len({r.worker_id for r in accepted}), "unique_workers": len({r.worker_id for r in accepted if r.person_type == "WORKER"}),
            "unique_visitors": len({r.worker_id for r in accepted if r.person_type == "VISITOR"}), "rejected_scans": len(rejected),
            "duplicate_attempts": sum(r.rejection_reason == "ALREADY_SCANNED" for r in rejected),
            "no_gate_entry": sum(r.rejection_reason == "NO_GATE_ENTRY" for r in rejected),
            "transactions": [serialize_canteen(r) for r in rows]})
    except ValueError:
        return api_error("Invalid report date", 422)
    finally:
        db.close()
