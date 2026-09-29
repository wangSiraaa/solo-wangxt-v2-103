"""数据库层：SQLAlchemy 2.x。

生产/演示部署使用 PostgreSQL（见 deploy/docker-compose.yml 与
deploy/initdb/01_init.sql）；本地无数据库或跑测试时回退 SQLite，
种子数据完全一致，保证算法验证不依赖外部服务。
"""

from __future__ import annotations

import os
from typing import Optional

from sqlalchemy import (
    Boolean,
    Column,
    ForeignKeyConstraint,
    Integer,
    String,
    create_engine,
)
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

DEFAULT_PG_URL = "postgresql+psycopg2://isolation:isolation@localhost:5432/isolation"


def database_url() -> str:
    url = os.environ.get("DATABASE_URL", DEFAULT_PG_URL)
    if os.environ.get("USE_SQLITE") == "1":
        url = "sqlite:///./isolation_demo.db"
    return url


class Base(DeclarativeBase):
    pass


class NodeRow(Base):
    __tablename__ = "nodes"
    network_id = Column(String(64), primary_key=True)
    node_id = Column(String(64), primary_key=True)
    label = Column(String(256), nullable=False)
    kind = Column(String(32), nullable=False)  # source/junction/equipment/supply/sink
    pos_x = Column(Integer, default=0)
    pos_y = Column(Integer, default=0)


class SegmentRow(Base):
    __tablename__ = "segments"
    network_id = Column(String(64), primary_key=True)
    segment_id = Column(String(64), primary_key=True)
    source_id = Column(String(64), nullable=False)
    target_id = Column(String(64), nullable=False)
    kind = Column(String(32), nullable=False)  # main/bypass/branch/outlet
    label = Column(String(256), nullable=False, default="")


class ValveRow(Base):
    __tablename__ = "valves"
    network_id = Column(String(64), primary_key=True)
    valve_id = Column(String(64), primary_key=True)
    segment_id = Column(String(64), nullable=False)
    label = Column(String(256), nullable=False)
    is_open = Column(Boolean, nullable=False, default=True)
    is_locked = Column(Boolean, nullable=False, default=False)


class ScenarioRow(Base):
    __tablename__ = "scenarios"
    network_id = Column(String(64), primary_key=True)
    scenario_id = Column(String(64), primary_key=True)
    name = Column(String(256), nullable=False)
    target_id = Column(String(64), nullable=False)


class RequiredSupplyRow(Base):
    __tablename__ = "scenario_required_supplies"
    network_id = Column(String(64), primary_key=True)
    scenario_id = Column(String(64), primary_key=True)
    node_id = Column(String(64), primary_key=True)

    __table_args__ = (
        ForeignKeyConstraint(
            ["network_id", "scenario_id"],
            ["scenarios.network_id", "scenarios.scenario_id"],
        ),
    )


_engine = None
_SessionLocal: Optional[sessionmaker] = None


def init_engine(url: Optional[str] = None):
    global _engine, _SessionLocal
    _engine = create_engine(
        url or database_url(),
        echo=False,
        future=True,
    )
    _SessionLocal = sessionmaker(bind=_engine, future=True, expire_on_commit=False)
    return _engine


def get_engine():
    if _engine is None:
        init_engine()
    return _engine


def create_all():
    Base.metadata.create_all(get_engine())


def session_scope() -> Session:
    if _SessionLocal is None:
        init_engine()
    assert _SessionLocal is not None
    return _SessionLocal()
