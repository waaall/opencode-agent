"""数据库会话管理：初始化引擎、建表并提供会话工厂。"""

from __future__ import annotations

import logging
import time

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings
from app.infra.db.models import Base

settings = get_settings()
logger = logging.getLogger(__name__)

engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,
    future=True,
)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False, expire_on_commit=False, class_=Session)


def init_db() -> None:
    """初始化数据库表结构。"""
    started = time.perf_counter()
    logger.info("db init started", extra={"event": "db.init.started", "external_service": "database", "op": "create_all"})
    try:
        Base.metadata.create_all(bind=engine)
    except Exception as exc:
        duration_ms = round((time.perf_counter() - started) * 1000, 2)
        logger.exception(
            "db init failed",
            extra={
                "event": "db.init.failed",
                "external_service": "database",
                "op": "create_all",
                "duration_ms": duration_ms,
                "error_type": type(exc).__name__,
                "error": str(exc),
            },
        )
        raise
    duration_ms = round((time.perf_counter() - started) * 1000, 2)
    logger.info(
        "db init succeeded",
        extra={
            "event": "db.init.succeeded",
            "external_service": "database",
            "op": "create_all",
            "duration_ms": duration_ms,
        },
    )


def get_db_session() -> Session:
    """生成数据库会话并在结束后自动关闭。"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
