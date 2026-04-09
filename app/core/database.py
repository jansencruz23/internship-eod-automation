from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker, DeclarativeBase

from app.core.config import get_settings


engine = create_engine(
    get_settings().DATABASE_URL,
    connect_args={"check_same_thread": False},
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    """FastAPI dependency that yields a database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _run_migrations():
    """Add new columns to existing tables without deleting the database."""
    insp = inspect(engine)

    if "app_settings" not in insp.get_table_names():
        return  # Table will be created by create_all

    columns = [c["name"] for c in insp.get_columns("app_settings")]
    if "auto_post_internity_enabled" not in columns:
        with engine.begin() as conn:
            conn.execute(
                text(
                    "ALTER TABLE app_settings "
                    "ADD COLUMN auto_post_internity_enabled BOOLEAN DEFAULT 0"
                )
            )
        print("[DB] Added auto_post_internity_enabled column to app_settings.")

    if "teams_sentence_count" not in columns:
        with engine.begin() as conn:
            conn.execute(
                text(
                    "ALTER TABLE app_settings "
                    "ADD COLUMN teams_sentence_count INTEGER DEFAULT 5"
                )
            )
        print("[DB] Added teams_sentence_count column to app_settings.")


def init_db():
    """Create all tables."""
    import app.models.activity  # noqa: F401
    import app.models.report  # noqa: F401
    import app.models.settings  # noqa: F401

    Base.metadata.create_all(bind=engine)
    _run_migrations()
