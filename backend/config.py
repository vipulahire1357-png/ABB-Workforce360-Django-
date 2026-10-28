from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[1]

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="WIR_", env_file=".env", extra="ignore")
    database_url: str = f"sqlite:///{ROOT / 'data' / 'wir.sqlite3'}"
    upload_dir: Path = ROOT / "data" / "uploads" / "workers"
    visitor_upload_dir: Path = ROOT / "data" / "uploads" / "visitors"
    logo_path: Path = ROOT / "assets" / "abb-logo.svg"
    font_dir: Path | None = None
    session_secret: str = ""
    worker_id_secret: str = ""
    visitor_id_secret: str = ""
    aadhaar_encryption_key: str = ""
    site_timezone: str = "Asia/Kolkata"
    cookie_secure: bool = False

    def validate_secrets(self):
        for label, value in (("WIR_SESSION_SECRET", self.session_secret), ("WIR_WORKER_ID_SECRET", self.worker_id_secret)):
            if len(value.encode()) < 32 or value.startswith("replace-"):
                raise RuntimeError(f"{label} must be configured with at least 32 random bytes")
        if self.aadhaar_encryption_key:
            from cryptography.fernet import Fernet
            try: Fernet(self.aadhaar_encryption_key.encode())
            except Exception as exc: raise RuntimeError("WIR_AADHAAR_ENCRYPTION_KEY must be a valid Fernet key") from exc

settings = Settings()

