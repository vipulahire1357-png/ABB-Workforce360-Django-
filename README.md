# ABB Workforce360

ABB Workforce360 manages worker identity registration, visitor passes, gate entry and exit, canteen meal scans, administrator access, and two-sided CR80 identity cards for ABB Plant 3.

The local application is served by Django templates and static HTML/CSS with small browser-native JavaScript helpers. The existing SQLAlchemy domain services and SQLite schema remain in place behind Django so existing records, identifiers, scan history, and card rules can be reused without a lossy database conversion. Docker, production deployment, and multi-laptop networking are intentionally not implemented.

## Prerequisites

- Python 3.11 or newer
- Git
- PowerShell on Windows, or a shell with Python virtual environment support

Node.js, npm, React, TypeScript, and Vite are not required to run or test the application.

## Set up locally

From the repository root in PowerShell:

```powershell
Copy-Item .env.example .env
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

On macOS/Linux, activate with `source .venv/bin/activate` after creating the environment with `python3 -m venv .venv`.

### Environment and existing data

The app reads `WIR_*` values from `.env`. For a fresh installation, copy the template and set unique values for `WIR_SESSION_SECRET` and `WIR_WORKER_ID_SECRET` (each at least 32 random bytes). Django derives its session and CSRF signing from the session secret. Set `WIR_AADHAAR_ENCRYPTION_KEY` to a Fernet key before registering records that contain Aadhaar data. Generate one with:

```powershell
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

For an existing installation, keep its `.env` and all existing key values. Do not regenerate the worker ID or Aadhaar encryption keys: saved identifiers and encrypted values depend on them. Never commit `.env` or share its contents.

`WIR_DATABASE_URL` selects the SQLite database. The existing default is `data/wir.sqlite3`. `WIR_UPLOAD_DIR` selects worker photo storage and `WIR_VISITOR_UPLOAD_DIR` selects visitor photo storage. Paths may be relative to the repository root or absolute. Do not put the database or uploads in a temporary directory.

The Django adapter continues to use the existing SQLite tables. It does not import records into a new Django schema or reset the database. Startup creates any missing legacy tables and runs only the existing additive SQLite compatibility updates. Django's own optional framework migrations add framework tables; they do not replace workforce tables.

No workforce data migration is needed for this change. For Django framework tables only, run `python manage.py migrate`; it creates framework-owned tables and leaves the existing worker, visitor, admin, gate, canteen, and sequence tables intact. Do not use `flush`, delete the SQLite file, or run a database reset to set up the app. Normal local startup does not require this command because signed-cookie sessions are used.

## Create an administrator

Existing installations keep their current administrator accounts. To create an additional account, run:

```powershell
python -m backend.create_admin
```

The command asks for a username, role (`ADMIN`, `GATE`, or `CANTEEN`), and a password of at least 14 characters. Do not create a replacement admin as part of normal startup.

## Start on localhost

```powershell
python manage.py runserver
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000). The development command binds only to loopback. If port 8000 is occupied, pass a loopback port such as `python manage.py runserver 127.0.0.1:8010` and open `http://127.0.0.1:8010`. This is not a production server.

## Application workflows

- **Worker registration and management:** register a worker with a validated JPG photo, search the directory, update active status, and download a two-sided CR80 PDF identity card. Worker IDs and worker numbers use the existing generation rules.
- **Gate operations:** scan or type a barcode into the gate input. USB barcode scanners that send keystrokes and Enter are supported. Server-side checks enforce worker/visitor status, daily state transitions, duplicate prevention, and the established 10-minute entry-to-exit interval. Accepted and rejected scans are audited.
- **Visitor passes:** register a visitor, optionally capture or upload a JPG photo, review active/expired passes, and download the visitor PDF. Passes expire at 23:59:59 in the configured site timezone on the registration date.
- **Canteen:** scan an eligible worker or visitor after an accepted gate entry. The server enforces one successful meal scan per person per business day and records rejected attempts.
- **Dashboard and reports:** administrator counts come from the database; gate and canteen histories can be refreshed and filtered by date/result.
- **Photographs:** the browser camera helper and file upload validate JPEG format, dimensions, and a 200 KB limit. Photos are saved in persistent configurable storage, not inside a temporary runtime folder.

Passwords are stored as Argon2 hashes. Aadhaar values are encrypted at rest and only the last four digits are returned in lists. State-changing requests use Django CSRF protection and authenticated role checks.

## Database and file backups

Stop the local app before copying the SQLite database and its upload folders. Keep the database and photos together. Preserve `.env` with the backup in a restricted location because its secrets are needed to retain existing IDs and encrypted fields. Never put real records, photos, or secrets in Git.

The removed portable package used a separate database that contained no worker, visitor, gate, or canteen records or photos, but it did contain one separate administrator account. That account was not transferred to the primary database. Recreate it with `python -m backend.create_admin` if it was needed.

## Tests and checks

```powershell
python -m pip install -r requirements-test.txt
python manage.py check
python manage.py test tests.test_django_web --verbosity 2
python -m pytest -q --basetemp=.pytest-work
```

Tests use isolated in-memory databases or test fixtures; they do not run against the live workforce database.

## Project structure

- `workforce360/` — Django settings, URLs, and WSGI entry point
- `webapp/` — Django views, server-rendered templates, static CSS/JavaScript, and local runserver validation
- `backend/services/` — retained identity, photo, visitor, gate, canteen, timezone, and PDF business logic
- `backend/models.py`, `backend/db.py` — retained SQLAlchemy definitions for the existing SQLite schema
- `data/` — ignored local SQLite database, uploads, and runtime state
- `tests/` — Django adapter tests and existing business-rule regression tests

## Legacy components retired

The React/Vite frontend, npm manifests, Windows portable package, portable build workflow, and laptop/LAN launcher path have been removed. The application starts with Django and a Python environment only. No Docker or deployment configuration is part of this project phase.

## Troubleshooting

- **Startup reports invalid secrets:** restore the existing `.env` values or configure the required secrets before starting.
- **Aadhaar registration is unavailable:** set a valid Fernet value in `WIR_AADHAAR_ENCRYPTION_KEY`; for existing data, use the original value.
- **Photo rejected:** choose a JPEG smaller than or equal to 200 KB with supported dimensions.
- **A stored photo is missing:** confirm the configured upload path and restore the photo backup; the database record is not deleted when a file is missing.
- **Identity card cannot be generated:** confirm the ABB logo asset and referenced worker/visitor photo exist.
- **Port 8000 is occupied:** choose an unused loopback port, for example `python manage.py runserver 127.0.0.1:8010`. The application does not discover or expose a laptop on the LAN.
