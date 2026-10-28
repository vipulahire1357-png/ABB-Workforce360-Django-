from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from backend.config import settings

connect_args = {"check_same_thread": False, "timeout": 30} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, connect_args=connect_args, pool_pre_ping=True)
if settings.database_url.startswith("sqlite"):
    @event.listens_for(engine, "connect")
    def sqlite_pragmas(conn, _):
        cur = conn.cursor(); cur.execute("PRAGMA foreign_keys=ON"); cur.execute("PRAGMA journal_mode=WAL"); cur.execute("PRAGMA busy_timeout=30000"); cur.close()
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
class Base(DeclarativeBase): pass

def init_db():
    from backend import models
    if settings.database_url.startswith("sqlite:///"):
        from pathlib import Path
        Path(settings.database_url.removeprefix("sqlite:///")).parent.mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(bind=engine)
    if settings.database_url.startswith("sqlite"):
        with engine.connect() as conn:
            cols = [r[1] for r in conn.exec_driver_sql("PRAGMA table_info(admins)").fetchall()]
            if cols and "role" not in cols:
                conn.exec_driver_sql("ALTER TABLE admins ADD COLUMN role VARCHAR(20) NOT NULL DEFAULT 'ADMIN'")
                conn.commit()
            canteen_cols = [r[1] for r in conn.exec_driver_sql("PRAGMA table_info(canteen_transactions)").fetchall()]
            if canteen_cols:
                if "person_type" not in canteen_cols:
                    conn.exec_driver_sql("ALTER TABLE canteen_transactions ADD COLUMN person_type VARCHAR(10) NOT NULL DEFAULT 'WORKER'")
                conn.exec_driver_sql(
                    "UPDATE canteen_transactions SET person_type = 'VISITOR' "
                    "WHERE person_type != 'VISITOR' "
                    "AND worker_id IN (SELECT visitor_id FROM visitors)"
                )
                conn.commit()

def get_db():
    db = SessionLocal()
    try: yield db
    finally: db.close()

