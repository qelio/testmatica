from sqlalchemy import (
    Column,
    DateTime,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB


def messaging_tables(metadata: MetaData) -> tuple[Table, Table]:
    """Служебные таблицы outbox и inbox. Каждый сервис регистрирует их в своей metadata,
    чтобы Alembic создал их в его базе."""
    outbox = Table(
        "outbox",
        metadata,
        Column("id", Uuid, primary_key=True),
        Column("exchange", String(100), nullable=False),
        Column("routing_key", String(200), nullable=False),
        Column("payload", JSONB, nullable=False),
        Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
        Column("published_at", DateTime(timezone=True)),
        Index(
            "ix_outbox_unpublished",
            "created_at",
            postgresql_where=text("published_at IS NULL"),
        ),
    )
    inbox = Table(
        "inbox",
        metadata,
        Column("event_id", Uuid, primary_key=True),
        Column("consumer", String(100), primary_key=True),
        Column("processed_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    )
    return outbox, inbox
