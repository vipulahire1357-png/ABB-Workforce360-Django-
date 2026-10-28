"""Django adapter tests use an isolated in-memory domain database."""
import json
import unittest
from datetime import timedelta
from unittest.mock import patch
import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "workforce360.settings")
import django
django.setup()

from argon2 import PasswordHasher
from django.test import Client, SimpleTestCase, override_settings
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from backend import db as dbmod
from backend.models import Base, Admin, Worker, Visitor, GateTransaction, CanteenTransaction, Sequence
from backend.services.identity import new_worker_id, encrypt_aadhaar
from backend.services.timezone import now_local
from datetime import date


@override_settings(SESSION_ENGINE="django.contrib.sessions.backends.signed_cookies",
                   ALLOWED_HOSTS=["testserver", "127.0.0.1", "localhost"])
class DjangoWebAdapterTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.old_engine = dbmod.engine
        cls.test_engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        dbmod.engine = cls.test_engine
        dbmod.SessionLocal.configure(bind=cls.test_engine)
        Base.metadata.create_all(cls.test_engine)

    @classmethod
    def tearDownClass(cls):
        cls.test_engine.dispose()
        dbmod.engine = cls.old_engine
        dbmod.SessionLocal.configure(bind=cls.old_engine)
        super().tearDownClass()

    def setUp(self):
        self.client = Client(enforce_csrf_checks=True)
        with dbmod.SessionLocal() as db:
            db.query(Admin).delete()
            db.query(Worker).delete()
            db.query(Visitor).delete(); db.query(GateTransaction).delete(); db.query(CanteenTransaction).delete(); db.query(Sequence).delete()
            db.add(Admin(username="test-admin", password_hash=PasswordHasher().hash("test-password-long"), role="ADMIN"))
            db.add(Admin(username="gate-user", password_hash=PasswordHasher().hash("gate-password-long"), role="GATE"))
            db.add(Admin(username="canteen-user", password_hash=PasswordHasher().hash("canteen-password-long"), role="CANTEEN"))
            db.commit()

    def csrf_token(self):
        self.client.get("/")
        return self.client.cookies["csrftoken"].value

    def login(self, username="test-admin", password="test-password-long"):
        token = self.csrf_token()
        return self.client.post("/api/auth/login", data=json.dumps({"username": username, "password": password}),
            content_type="application/json", HTTP_X_CSRFTOKEN=token)

    def test_login_session_and_role_protected_dashboard(self):
        response = self.login()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["role"], "ADMIN")
        self.assertEqual(self.client.get("/api/summary").status_code, 200)

    def test_csrf_and_role_checks_are_enforced(self):
        self.client.get("/")
        denied = self.client.post("/api/auth/login", data=json.dumps({"username": "test-admin", "password": "bad"}), content_type="application/json")
        self.assertEqual(denied.status_code, 403)
        self.login("gate-user", "gate-password-long")
        self.assertEqual(self.client.get("/api/canteen/transactions").status_code, 403)
        self.assertEqual(self.client.get("/api/gate/transactions").status_code, 200)

    def add_worker(self, status="Active"):
        app_settings = __import__("backend.config", fromlist=["settings"]).settings
        original = app_settings.aadhaar_encryption_key
        from cryptography.fernet import Fernet
        app_settings.aadhaar_encryption_key = Fernet.generate_key().decode()
        try:
            with dbmod.SessionLocal() as db:
                worker = Worker(worker_no="ABB-P3-W-1", worker_id="WIR-TEST00000000000001", name="Test Worker",
                    contractor_name="Test Contractor", joining_date=date(2026,1,2), contact_no="9876543210",
                    emergency_contact="9876543211", aadhaar_encrypted=encrypt_aadhaar("123456789012"),
                    aadhaar_last4="9012", photo_path="missing.jpg", status=status)
                db.add(worker); db.commit()
        finally:
            app_settings.aadhaar_encryption_key = original
        return "WIR-TEST00000000000001"

    def test_gate_canteen_state_rules_and_ten_minute_interval(self):
        worker_id = self.add_worker()
        self.login("gate-user", "gate-password-long")
        first = self.client.post("/api/gate/scan", data=json.dumps({"barcode":worker_id}), content_type="application/json", HTTP_X_CSRFTOKEN=self.client.cookies["csrftoken"].value)
        self.assertEqual(first.status_code,200); self.assertTrue(first.json()["accepted"]); self.assertEqual(first.json()["event_type"],"ENTRY")
        immediate = self.client.post("/api/gate/scan", data=json.dumps({"barcode":worker_id}), content_type="application/json", HTTP_X_CSRFTOKEN=self.client.cookies["csrftoken"].value)
        self.assertFalse(immediate.json()["accepted"]); self.assertEqual(immediate.json()["reason"],"NOT_YET_ELIGIBLE")
        self.login("canteen-user", "canteen-password-long")
        meal = self.client.post("/api/canteen/scan", data=json.dumps({"barcode":worker_id}), content_type="application/json", HTTP_X_CSRFTOKEN=self.client.cookies["csrftoken"].value)
        self.assertTrue(meal.json()["accepted"])
        duplicate = self.client.post("/api/canteen/scan", data=json.dumps({"barcode":worker_id}), content_type="application/json", HTTP_X_CSRFTOKEN=self.client.cookies["csrftoken"].value)
        self.assertFalse(duplicate.json()["accepted"]); self.assertEqual(duplicate.json()["reason"],"ALREADY_SCANNED")
        self.login("gate-user", "gate-password-long")
        later = now_local() + timedelta(minutes=11)
        with patch("backend.services.gate.now_local", return_value=later):
            exit_result = self.client.post("/api/gate/scan", data=json.dumps({"barcode":worker_id}), content_type="application/json", HTTP_X_CSRFTOKEN=self.client.cookies["csrftoken"].value)
        self.assertTrue(exit_result.json()["accepted"]); self.assertEqual(exit_result.json()["event_type"],"EXIT")

    def test_inactive_worker_and_unknown_identity_are_rejected_and_audited(self):
        inactive_id = self.add_worker("Inactive")
        self.login("gate-user", "gate-password-long")
        for barcode, reason in [(inactive_id,"WORKER_INACTIVE"),("WIR-NOTFOUND","INVALID_ID")]:
            response = self.client.post("/api/gate/scan", data=json.dumps({"barcode":barcode}), content_type="application/json", HTTP_X_CSRFTOKEN=self.client.cookies["csrftoken"].value)
            self.assertFalse(response.json()["accepted"]); self.assertEqual(response.json()["reason"],reason)
        with dbmod.SessionLocal() as db:
            self.assertEqual(db.query(GateTransaction).filter_by(validation_result="REJECTED").count(),2)

    def test_concurrent_gate_scans_are_serialized_by_sqlite(self):
        from concurrent.futures import ThreadPoolExecutor
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from threading import Barrier
        with TemporaryDirectory() as folder:
            engine=create_engine(f"sqlite:///{Path(folder, 'concurrent.sqlite3').as_posix()}",
                connect_args={"check_same_thread":False,"timeout":30})
            Base.metadata.create_all(engine)
            old_engine=dbmod.engine
            dbmod.engine=engine; dbmod.SessionLocal.configure(bind=engine)
            worker_id="WIR-CONCURRENT00000001"
            with dbmod.SessionLocal() as db:
                db.add(Worker(worker_no="ABB-P3-W-1", worker_id=worker_id, name="Concurrent Worker",
                    contractor_name="Test Contractor", joining_date=date(2026,1,2), contact_no="9876543210",
                    emergency_contact="9876543211", aadhaar_last4="9012", photo_path="missing.jpg", status="Active"))
                db.commit()
            barrier=Barrier(2)
            def scan_once():
                client=Client(enforce_csrf_checks=False)
                session=client.session; session["operator"]={"id":1,"username":"gate-user","role":"GATE"}; session.save()
                client.cookies["sessionid"]=session.session_key
                barrier.wait()
                response=client.post("/api/gate/scan", data=json.dumps({"barcode":worker_id}), content_type="application/json")
                return response.status_code,response.json()
            try:
                with ThreadPoolExecutor(max_workers=2) as pool:
                    results=list(pool.map(lambda _: scan_once(), range(2)))
                self.assertEqual([r[0] for r in results],[200,200])
                self.assertEqual(sorted(r[1]["accepted"] for r in results),[False,True])
                with dbmod.SessionLocal() as db:
                    self.assertEqual(db.query(GateTransaction).filter_by(validation_result="ACCEPTED").count(),1)
                    self.assertEqual(db.query(GateTransaction).filter_by(validation_result="REJECTED").count(),1)
            finally:
                engine.dispose(); dbmod.engine=old_engine; dbmod.SessionLocal.configure(bind=old_engine)

    def test_visitor_registration_expiry_and_gate_rejection(self):
        from backend.config import settings as app_settings
        from cryptography.fernet import Fernet
        original = app_settings.aadhaar_encryption_key
        app_settings.aadhaar_encryption_key = Fernet.generate_key().decode()
        try:
            self.login("gate-user", "gate-password-long")
            response = self.client.post("/api/visitors", data={"name":"Guest Person","company_name":"Example Co",
                "location":"Vadodara","host":"Host Employee","purpose":"Meeting","contact_no":"9876543210",
                "aadhaar_no":"123456789012"}, HTTP_X_CSRFTOKEN=self.client.cookies["csrftoken"].value)
            self.assertEqual(response.status_code,201,response.content)
            visitor_id=response.json()["visitor_id"]
            visitor_card=self.client.get(f"/api/visitors/{visitor_id}/id-card")
            self.assertEqual(visitor_card.status_code,200,visitor_card.content[:200])
            from pypdf import PdfReader
            self.assertEqual(len(PdfReader(__import__("io").BytesIO(visitor_card.content)).pages),2)
            entry=self.client.post("/api/gate/scan", data=json.dumps({"barcode":visitor_id}), content_type="application/json", HTTP_X_CSRFTOKEN=self.client.cookies["csrftoken"].value)
            self.assertTrue(entry.json()["accepted"])
            self.login("canteen-user", "canteen-password-long")
            meal=self.client.post("/api/canteen/scan", data=json.dumps({"barcode":visitor_id}), content_type="application/json", HTTP_X_CSRFTOKEN=self.client.cookies["csrftoken"].value)
            self.assertTrue(meal.json()["accepted"])
            duplicate=self.client.post("/api/canteen/scan", data=json.dumps({"barcode":visitor_id}), content_type="application/json", HTTP_X_CSRFTOKEN=self.client.cookies["csrftoken"].value)
            self.assertFalse(duplicate.json()["accepted"]); self.assertEqual(duplicate.json()["reason"],"ALREADY_SCANNED")
            self.login("gate-user", "gate-password-long")
            with dbmod.SessionLocal() as db:
                visitor=db.query(Visitor).filter_by(visitor_id=visitor_id).one()
                self.assertEqual(visitor.status,"Active")
                visitor.expiration_timestamp=now_local()-timedelta(seconds=1); db.commit()
            scan=self.client.post("/api/gate/scan", data=json.dumps({"barcode":visitor_id}), content_type="application/json", HTTP_X_CSRFTOKEN=self.client.cookies["csrftoken"].value)
            self.assertFalse(scan.json()["accepted"]); self.assertEqual(scan.json()["reason"],"VISITOR_EXPIRED")
            with dbmod.SessionLocal() as db:
                self.assertEqual(db.query(Visitor).filter_by(visitor_id=visitor_id).one().status,"Inactive")
        finally:
            app_settings.aadhaar_encryption_key=original

    def test_templates_render_django_and_unauthenticated_apis_reject(self):
        page = self.client.get("/")
        self.assertContains(page, "ABB Workforce360")
        self.assertContains(page, "name=\"username\"")
        self.assertEqual(self.client.get("/api/workers").status_code, 401)

    def test_development_server_is_loopback_only_and_accepts_an_alternate_port(self):
        from django.core.management.base import CommandError
        from webapp.management.commands.runserver import local_addrport
        self.assertEqual(local_addrport(None), "127.0.0.1:8000")
        self.assertEqual(local_addrport("8010"), "127.0.0.1:8010")
        self.assertEqual(local_addrport("localhost:8123"), "127.0.0.1:8123")
        with self.assertRaises(CommandError):
            local_addrport("0.0.0.0:8000")

    def test_worker_registration_uses_existing_identifier_and_storage_rules(self):
        from django.test import override_settings as settings_override
        from backend.config import settings as app_settings
        from cryptography.fernet import Fernet
        from PIL import Image
        import io, tempfile
        response = self.login()
        token = response.json()["csrf_token"]
        original_key, original_secret, original_upload = app_settings.aadhaar_encryption_key, app_settings.worker_id_secret, app_settings.upload_dir
        tmp = tempfile.TemporaryDirectory()
        app_settings.aadhaar_encryption_key = Fernet.generate_key().decode()
        app_settings.worker_id_secret = "w" * 40
        app_settings.upload_dir = __import__("pathlib").Path(tmp.name)
        buffer = io.BytesIO(); Image.new("RGB", (100, 140), (70, 90, 110)).save(buffer, "JPEG")
        try:
            response = self.client.post("/api/workers", data={"name":"Test Worker", "contractor_name":"Test Contractor",
                "joining_date":"2026-01-02", "contact_no":"9876543210", "emergency_contact":"9876543211",
                "aadhaar_no":"123456789012", "photo":__import__("django.core.files.uploadedfile", fromlist=["SimpleUploadedFile"]).SimpleUploadedFile("photo.jpg", buffer.getvalue(), content_type="image/jpeg")},
                HTTP_X_CSRFTOKEN=token)
            self.assertEqual(response.status_code, 201, response.content)
            record = response.json()
            self.assertEqual(record["worker_no"], "ABB-P3-W-1")
            self.assertEqual(record["aadhaar_masked"], "XXXX XXXX 9012")
            self.assertTrue((app_settings.upload_dir / f"{record['worker_id']}.jpg").exists())
            card=self.client.get(f"/api/workers/{record['worker_id']}/id-card")
            self.assertEqual(card.status_code,200,card.content[:200])
            from pypdf import PdfReader
            self.assertEqual(len(PdfReader(__import__("io").BytesIO(card.content)).pages),2)
            changed=self.client.patch(f"/api/workers/{record['worker_id']}/status",data=json.dumps({"status":"Inactive"}),
                content_type="application/json",HTTP_X_CSRFTOKEN=token)
            self.assertEqual(changed.status_code,200); self.assertEqual(changed.json()["status"],"Inactive")
        finally:
            app_settings.aadhaar_encryption_key, app_settings.worker_id_secret, app_settings.upload_dir = original_key, original_secret, original_upload
            tmp.cleanup()
