from datetime import datetime
from sqlalchemy import JSON, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from src.config.database import Base
from src.constants.enums import PackState, ShipState
from src.utils.time import now

class ListVersion(Base):
    __tablename__ = 'list_versions'

    id: Mapped[int] = mapped_column(primary_key=True)
    version: Mapped[int] = mapped_column(unique=True)
    run_id: Mapped[int] = mapped_column(ForeignKey('runs.id'), unique=True)
    entry_count: Mapped[int]
    fingerprint: Mapped[str] = mapped_column(String(64))
    entries: Mapped[list] = mapped_column(JSON)
    author: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(default=now)

class SiteState(Base):
    __tablename__ = 'site_states'

    site: Mapped[str] = mapped_column(String(100), primary_key=True)
    baseline: Mapped[int] = mapped_column(default=0)
    updated_at: Mapped[datetime] = mapped_column(default=now, onupdate=now)

class Shipment(Base):
    __tablename__ = 'shipments'

    id: Mapped[int] = mapped_column(primary_key=True)
    site: Mapped[str] = mapped_column(String(100), index=True)
    from_version: Mapped[int]
    to_version: Mapped[int]
    state: Mapped[str] = mapped_column(String(20), default=ShipState.OPEN, index=True)
    package_count: Mapped[int]
    created_at: Mapped[datetime] = mapped_column(default=now)
    completed_at: Mapped[datetime | None]

class Package(Base):
    __tablename__ = 'packages'
    __table_args__ = (UniqueConstraint('shipment_id', 'seq'),)

    id: Mapped[int] = mapped_column(primary_key=True)
    shipment_id: Mapped[int] = mapped_column(ForeignKey('shipments.id'), index=True)
    seq: Mapped[int]
    item_count: Mapped[int]
    fingerprint: Mapped[str] = mapped_column(String(64))
    summary: Mapped[dict] = mapped_column(JSON)
    items: Mapped[list] = mapped_column(JSON)
    state: Mapped[str] = mapped_column(String(20), default=PackState.PENDING, index=True)
    receipt: Mapped[str | None] = mapped_column(String(64))
    acked_by: Mapped[str | None] = mapped_column(String(64))
    acked_at: Mapped[datetime | None]
