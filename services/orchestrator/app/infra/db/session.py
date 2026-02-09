"""数据库会话管理：初始化引擎、建表并提供会话工厂。"""

from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings
from app.infra.db.models import Base

settings = get_settings()

engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    future=True,
)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False, expire_on_commit=False, class_=Session)


def init_db() -> None:
    """初始化数据库表结构。"""
    Base.metadata.create_all(bind=engine)


def get_db_session() -> Session:
    """生成数据库会话并在结束后自动关闭。"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
