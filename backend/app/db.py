from collections.abc import Iterator

from sqlalchemy import inspect, text
from sqlmodel import Session, SQLModel, create_engine

from app.config import settings

_connect_args = (
    {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
)
engine = create_engine(settings.database_url, connect_args=_connect_args)


def init_db() -> None:
    from app.models import tables  # noqa: F401  (registers tables)

    SQLModel.metadata.create_all(engine)
    _migrate()


# create_all never alters existing tables, so older databases get the new columns here.
_NEW_COLUMNS: dict[str, list[tuple[str, str, str | None]]] = {
    "transaction": [("source_ref", "VARCHAR", None), ("created_by", "VARCHAR", "'owner'"),
                    ("corrects_id", "INTEGER", None)],
    "bill": [("source", "VARCHAR", "'manual'"), ("source_ref", "VARCHAR", None),
             ("created_by", "VARCHAR", "'owner'"), ("category", "VARCHAR", "'Other'"),
             ("note", "VARCHAR", "''")],
    "invoice": [("source", "VARCHAR", "'manual'"), ("source_ref", "VARCHAR", None),
                ("created_by", "VARCHAR", "'owner'")],
    "consentgrant": [("last_sync_at", "VARCHAR", None)],
}
# Old source names -> bank | file | manual. Run on every start; only touches old values.
_SOURCE_REMAP = {
    "transaction": {"mock_webank": "bank", "sandbox_payment": "bank", "csv": "file"},
    "bill": {"seed": "manual"},
    "invoice": {"seed": "manual"},
}


def _migrate() -> None:
    with engine.begin() as conn:
        inspector = inspect(conn)  # same connection, so it can't disturb the open transaction
        for table, columns in _NEW_COLUMNS.items():
            if not inspector.has_table(table):
                continue
            have = {c["name"] for c in inspector.get_columns(table)}
            for name, kind, default in columns:
                if name not in have:
                    ddl = f'ALTER TABLE "{table}" ADD COLUMN {name} {kind}'
                    conn.execute(text(ddl + (f" DEFAULT {default}" if default else "")))
        for table, mapping in _SOURCE_REMAP.items():
            if not inspector.has_table(table):
                continue
            for old, new in mapping.items():
                conn.execute(text(f'UPDATE "{table}" SET source = :new WHERE source = :old'),
                             {"new": new, "old": old})
            if table == "transaction":  # bank rows are written by the system, not the owner
                conn.execute(text("UPDATE \"transaction\" SET created_by = 'system' "
                                  "WHERE source = 'bank' AND created_by = 'owner'"))


def get_session() -> Iterator[Session]:
    with Session(engine) as session:
        yield session
