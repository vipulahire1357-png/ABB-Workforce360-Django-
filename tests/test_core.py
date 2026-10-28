from datetime import date
from pathlib import Path
from types import SimpleNamespace
from pypdf import PdfReader
from backend.schemas import WorkerCreate, StatusUpdate
from backend.services import cards

def test_registration_validation_normalizes_fields():
    w = WorkerCreate(name="  Ada   Worker ", contractor_name=" North   Works ", joining_date=date(2026,1,2), contact_no="+91 98765-43210", emergency_contact="9876543211", aadhaar_no="1234 5678 9012")
    assert w.name == "Ada Worker"
    assert w.contact_no == "919876543210"
    assert w.aadhaar_no == "123456789012"

def test_reject_invalid_aadhaar_and_phone():
    import pytest
    with pytest.raises(ValueError): WorkerCreate(name="A", contractor_name="C", joining_date=date.today(), contact_no="123", emergency_contact="9876543210", aadhaar_no="123")

def test_worker_id_hmac_is_stable_and_does_not_include_aadhaar(monkeypatch):
    from backend.services import identity
    monkeypatch.setattr(identity.settings,"worker_id_secret","k"*40)
    first=identity.new_worker_id("ABB-P3-W-1","123456789012")
    assert first==identity.new_worker_id("ABB-P3-W-1","123456789012")
    assert first!=identity.new_worker_id("ABB-P3-W-2","123456789012")
    assert "123456789012" not in first and first.startswith("WIR-")

def test_status_is_limited_to_supported_values():
    import pytest
    assert StatusUpdate(status="Inactive").status == "Inactive"
    with pytest.raises(ValueError): StatusUpdate(status="Deleted")

def test_photo_validation_accepts_exact_200_kb_and_rejects_over_limit():
    import io, pytest
    from PIL import Image
    from backend.services.photos import validate_photo, MAX_BYTES
    buf=io.BytesIO(); Image.new("RGB",(140,180),(120,80,60)).save(buf,format="JPEG")
    exact=buf.getvalue()+b"\0"*(MAX_BYTES-len(buf.getvalue()))
    accepted=validate_photo(exact)
    assert len(accepted)==MAX_BYTES
    with pytest.raises(ValueError, match="200 KB"):
        validate_photo(exact+b"\0")

def test_id_card_is_two_vertical_cr80_pages_and_has_expected_text(monkeypatch, tmp_path):
    # Make generated test asset and photo without embedding any personal data.
    from PIL import Image
    logo=tmp_path/"logo.png"; Image.new("RGB",(200,70),(230,0,0)).save(logo)
    photo=tmp_path/"WIR-test.jpg"; Image.new("RGB",(300,400),(100,120,140)).save(photo,format="JPEG")
    monkeypatch.setattr(cards.settings,"logo_path",logo); monkeypatch.setattr(cards.settings,"upload_dir",tmp_path)
    w=SimpleNamespace(worker_id="WIR-0123456789ABCDEF0123",worker_no="ABB-P3-W-1",name="Test Worker",contractor_name="Test Contractor",joining_date=date(2026,1,2),contact_no="9876543210",emergency_contact="9876543211",photo_path=photo.name)
    reader=PdfReader(__import__('io').BytesIO(cards.card_pdf(w)))
    assert len(reader.pages)==2
    for page in reader.pages:
        assert abs(float(page.mediabox.width)-54*72/25.4)<0.1
        assert abs(float(page.mediabox.height)-86*72/25.4)<0.1
    front=reader.pages[0].extract_text(); back=reader.pages[1].extract_text()
    assert "TEST WORKER" in front and "Test Contractor" in front
    assert "Name" not in front and "CONTRACTOR" not in front
    assert "WORKER ID:" not in front and "ABB PLANT:" not in front
    assert w.worker_id in front and w.worker_no not in front
    assert w.worker_no in back and w.worker_id in back and "02/01/2026" in back and "+91 98765 43211" in back
    assert "Aadhaar" not in front+back

def test_card_handles_long_names_without_dropping_text(monkeypatch, tmp_path):
    from PIL import Image
    logo=tmp_path/"logo.png"; Image.new("RGB",(200,70),(230,0,0)).save(logo)
    photo=tmp_path/"worker.jpg"; Image.new("RGB",(300,400),(100,120,140)).save(photo,format="JPEG")
    monkeypatch.setattr(cards.settings,"logo_path",logo); monkeypatch.setattr(cards.settings,"upload_dir",tmp_path)
    name="A Long Worker Name With Several Words To Verify Wrapping Across The Card Width"
    contractor="A Contractor Organization With A Long Registered Company Name"
    w=SimpleNamespace(worker_id="WIR-0123456789ABCDEF0123",worker_no="ABB-P3-W-101",name=name,contractor_name=contractor,joining_date=date(2026,1,2),contact_no="1234567890123456",emergency_contact="9876543210987654",photo_path=photo.name)
    reader=PdfReader(__import__('io').BytesIO(cards.card_pdf(w)))
    front=reader.pages[0].extract_text()
    back=reader.pages[1].extract_text()
    assert all(word.upper() in front for word in name.split())
    assert all(word in front for word in contractor.split())
    assert "1234567890123456" in back and "9876543210987654" in back

def test_missing_photo_is_a_controlled_card_asset_error(monkeypatch, tmp_path):
    import pytest
    from backend.services.cards import CardAssetError
    from PIL import Image
    logo=tmp_path/"logo.png"; Image.new("RGB",(200,70),(230,0,0)).save(logo)
    monkeypatch.setattr(cards.settings,"logo_path",logo); monkeypatch.setattr(cards.settings,"upload_dir",tmp_path)
    w=SimpleNamespace(worker_id="WIR-TEST",worker_no="ABB-P3-W-1",name="Test",contractor_name="Test",joining_date=date(2026,1,2),contact_no="9876543210",emergency_contact="9876543211",photo_path="missing.jpg")
    with pytest.raises(CardAssetError): cards.card_pdf(w)
    (tmp_path/"missing.jpg").write_bytes(b"not an image")
    with pytest.raises(CardAssetError): cards.card_pdf(w)

def test_missing_official_logo_is_a_controlled_card_asset_error(monkeypatch, tmp_path):
    import pytest
    from backend.services.cards import CardAssetError
    monkeypatch.setattr(cards.settings,"logo_path",tmp_path/"missing.svg")
    w=SimpleNamespace(worker_id="WIR-TEST",worker_no="ABB-P3-W-1",name="Test",contractor_name="Test",joining_date=date(2026,1,2),contact_no="9876543210",emergency_contact="9876543211",photo_path="missing.jpg")
    with pytest.raises(CardAssetError): cards.card_pdf(w)

def test_code128_barcode_decodes_to_exact_worker_id():
    import zxingcpp
    from PIL import Image, ImageDraw
    from reportlab.graphics.barcode import code128
    value="WIR-0123456789ABCDEF0123"
    barcode=code128.Code128(value,barHeight=70,barWidth=1.3,humanReadable=False,quiet=True)
    barcode._calculate()
    module_px,quiet_modules,height=4,60,160
    quiet=quiet_modules*module_px
    units=sum(ord(char.upper())-ord("A")+1 for char in barcode.decomposed)
    image=Image.new("RGB",(units*module_px+2*quiet,height),"white")
    draw=ImageDraw.Draw(image); x=quiet
    for char in barcode.decomposed:
        width=(ord(char.upper())-ord("A")+1)*module_px
        if char.isupper(): draw.rectangle((x,0,x+width-1,height-1),fill="black")
        x+=width
    decoded=zxingcpp.read_barcode(image)
    assert decoded is not None and str(decoded.format)=="Code 128"
    assert decoded.text==value

def test_canteen_schema_migration_preserves_worker_transactions():
    from sqlalchemy import create_engine
    from backend import db as dbmod

    old_engine = dbmod.engine
    legacy_engine = create_engine("sqlite://")
    dbmod.engine = legacy_engine
    try:
        with legacy_engine.begin() as conn:
            conn.exec_driver_sql(
                "CREATE TABLE canteen_transactions ("
                "id INTEGER PRIMARY KEY, worker_id VARCHAR(40) NOT NULL, "
                "business_date DATE NOT NULL, scan_timestamp DATETIME NOT NULL, "
                "gate_entry_id INTEGER, operator_id INTEGER, "
                "scan_result VARCHAR(10) NOT NULL, rejection_reason VARCHAR(60))"
            )
            conn.exec_driver_sql("CREATE TABLE visitors (visitor_id VARCHAR(40) PRIMARY KEY)")
            conn.exec_driver_sql("INSERT INTO visitors (visitor_id) VALUES ('VIS-LEGACY')")
            conn.exec_driver_sql(
                "INSERT INTO canteen_transactions "
                "(id, worker_id, business_date, scan_timestamp, scan_result) "
                "VALUES (1, 'WIR-LEGACY', '2026-01-01', '2026-01-01 08:00:00', 'ACCEPTED')"
            )
            conn.exec_driver_sql(
                "INSERT INTO canteen_transactions "
                "(id, worker_id, business_date, scan_timestamp, scan_result) "
                "VALUES (2, 'VIS-LEGACY', '2026-01-01', '2026-01-01 08:01:00', 'REJECTED')"
            )

        dbmod.init_db()

        with legacy_engine.connect() as conn:
            columns = {row[1] for row in conn.exec_driver_sql("PRAGMA table_info(canteen_transactions)")}
            row = conn.exec_driver_sql(
                "SELECT worker_id, person_type FROM canteen_transactions WHERE id = 1"
            ).one()
            visitor_row = conn.exec_driver_sql(
                "SELECT worker_id, person_type FROM canteen_transactions WHERE id = 2"
            ).one()
        assert "person_type" in columns
        assert row == ("WIR-LEGACY", "WORKER")
        assert visitor_row == ("VIS-LEGACY", "VISITOR")

        with legacy_engine.begin() as conn:
            conn.exec_driver_sql("UPDATE canteen_transactions SET person_type = 'WORKER' WHERE id = 2")
        dbmod.init_db()
        with legacy_engine.connect() as conn:
            visitor_row = conn.exec_driver_sql(
                "SELECT worker_id, person_type FROM canteen_transactions WHERE id = 2"
            ).one()
        assert visitor_row == ("VIS-LEGACY", "VISITOR")
    finally:
        legacy_engine.dispose()
        dbmod.engine = old_engine
