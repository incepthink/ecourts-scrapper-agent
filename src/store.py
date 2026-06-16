"""SQLAlchemy models + session helpers (SQLite by default, MySQL-ready).

Schema:
  advocates          one row per distinct advocate name (normalized)
  cases              one row per CNR (the eCourts unique case id)
  case_advocates     many-to-many: a case lists several advocates
  orders             final orders / judgements per case (+ downloaded PDF path)
  seed_names         crawl queue of advocate names to search (self-expanding)
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
    create_engine,
    func,
    select,
)
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
    relationship,
    sessionmaker,
)

import config


def normalize_name(name: str) -> str:
    """Uppercase + collapse whitespace + drop punctuation, for de-duping advocates."""
    n = re.sub(r"[^A-Za-z ]", " ", name or "")
    n = re.sub(r"\s+", " ", n).strip().upper()
    return n


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Advocate(Base):
    __tablename__ = "advocates"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    name_norm: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    cases: Mapped[list["CaseAdvocate"]] = relationship(back_populates="advocate")


class Case(Base):
    __tablename__ = "cases"
    id: Mapped[int] = mapped_column(primary_key=True)
    cnr: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    internal_case_no: Mapped[str] = mapped_column(String(32), default="")
    court_code: Mapped[str] = mapped_column(String(16), default="")
    establishment: Mapped[str] = mapped_column(String(255), default="")
    case_number_full: Mapped[str] = mapped_column(String(255), default="")
    case_type: Mapped[str] = mapped_column(String(255), default="")
    registration_number: Mapped[str] = mapped_column(String(64), default="")
    year: Mapped[str] = mapped_column(String(8), default="")
    petitioner: Mapped[str] = mapped_column(Text, default="")
    respondent: Mapped[str] = mapped_column(Text, default="")
    # populated from case history:
    case_status: Mapped[str] = mapped_column(String(128), default="")
    nature_of_disposal: Mapped[str] = mapped_column(String(255), default="")  # win/loss signal
    decision_date: Mapped[str] = mapped_column(String(64), default="")
    filing_date: Mapped[str] = mapped_column(String(64), default="")
    judge: Mapped[str] = mapped_column(String(255), default="")
    history_fetched: Mapped[bool] = mapped_column(Boolean, default=False)
    state_code: Mapped[str] = mapped_column(String(8), default="")
    dist_code: Mapped[str] = mapped_column(String(8), default="")
    complex_code: Mapped[str] = mapped_column(String(16), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    advocates: Mapped[list["CaseAdvocate"]] = relationship(back_populates="case")
    orders: Mapped[list["Order"]] = relationship(back_populates="case")


class CaseAdvocate(Base):
    __tablename__ = "case_advocates"
    __table_args__ = (UniqueConstraint("case_id", "advocate_id", name="uq_case_adv"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("cases.id"), index=True)
    advocate_id: Mapped[int] = mapped_column(ForeignKey("advocates.id"), index=True)
    case: Mapped["Case"] = relationship(back_populates="advocates")
    advocate: Mapped["Advocate"] = relationship(back_populates="cases")


class Order(Base):
    __tablename__ = "orders"
    __table_args__ = (UniqueConstraint("case_id", "order_number", name="uq_case_order"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("cases.id"), index=True)
    order_number: Mapped[str] = mapped_column(String(16), default="")
    order_date: Mapped[str] = mapped_column(String(64), default="")
    label: Mapped[str] = mapped_column(Text, default="")
    downloaded: Mapped[bool] = mapped_column(Boolean, default=False)
    pdf_local_path: Mapped[str] = mapped_column(Text, default="")
    sha256: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    case: Mapped["Case"] = relationship(back_populates="orders")


class SeedName(Base):
    __tablename__ = "seed_names"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    name_norm: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)  # pending|done|error
    source: Mapped[str] = mapped_column(String(64), default="manual")
    note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


_engine = create_engine(config.DB_URL, future=True)
Session = sessionmaker(bind=_engine, future=True)


def init_db() -> None:
    Base.metadata.create_all(_engine)


# ---- upsert helpers -------------------------------------------------------


def get_or_create_advocate(session, name: str) -> Advocate:
    norm = normalize_name(name)
    adv = session.scalar(select(Advocate).where(Advocate.name_norm == norm))
    if adv is None:
        adv = Advocate(name=name.strip(), name_norm=norm)
        session.add(adv)
        session.flush()
    return adv


def enqueue_seed(session, name: str, source: str = "harvest") -> bool:
    """Add a name to the crawl queue if not present. Returns True if newly added."""
    norm = normalize_name(name)
    if not norm:
        return False
    exists = session.scalar(select(SeedName.id).where(SeedName.name_norm == norm))
    if exists:
        return False
    session.add(SeedName(name=name.strip(), name_norm=norm, source=source))
    return True


def stats(session) -> dict:
    return {
        "advocates": session.scalar(select(func.count()).select_from(Advocate)),
        "cases": session.scalar(select(func.count()).select_from(Case)),
        "orders": session.scalar(select(func.count()).select_from(Order)),
        "orders_downloaded": session.scalar(
            select(func.count()).select_from(Order).where(Order.downloaded.is_(True))
        ),
        "seed_pending": session.scalar(
            select(func.count()).select_from(SeedName).where(SeedName.status == "pending")
        ),
        "seed_done": session.scalar(
            select(func.count()).select_from(SeedName).where(SeedName.status == "done")
        ),
    }
