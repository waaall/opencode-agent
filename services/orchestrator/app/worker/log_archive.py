"""日志归档任务：热层清理、冷层切片上传与抽样恢复校验。"""

from __future__ import annotations

import gzip
import hashlib
import json
import logging
import tempfile
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from app.config import Settings

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class ArchiveObject:
    """单个归档切片对象描述。"""

    local_path: Path
    key: str
    level: str
    hour: int
    line_count: int
    size_bytes: int
    sha256: str
    first_ts: str | None
    last_ts: str | None


def _parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            chunk = f.read(64 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _iter_target_records(log_root: Path, target_date: date) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for file_path in sorted(log_root.rglob("orchestrator.jsonl*")):
        if not file_path.is_file():
            continue
        with file_path.open("r", encoding="utf-8", errors="replace") as f:
            for line in f:
                text = line.strip()
                if not text:
                    continue
                try:
                    payload = json.loads(text)
                except json.JSONDecodeError:
                    logger.debug(
                        "invalid json line skipped",
                        extra={
                            "event": "log.archive.record.invalid.debug",
                            "payload_preview": {"file": str(file_path)},
                        },
                    )
                    continue
                parsed_ts = _parse_timestamp(payload.get("ts"))
                if parsed_ts is None or parsed_ts.date() != target_date:
                    continue
                records.append(
                    {
                        "line": text,
                        "ts": parsed_ts.isoformat().replace("+00:00", "Z"),
                        "hour": parsed_ts.hour,
                        "level": str(payload.get("level", "INFO")).upper(),
                    }
                )
    return records


def _build_archive_objects(
    *,
    records: list[dict[str, Any]],
    prefix: str,
    target_date: date,
    output_dir: Path,
    max_lines_per_part: int = 5000,
) -> list[ArchiveObject]:
    grouped: dict[tuple[int, str], list[dict[str, Any]]] = {}
    for item in records:
        key = (int(item["hour"]), str(item["level"]))
        grouped.setdefault(key, []).append(item)

    objects: list[ArchiveObject] = []
    for (hour, level), group_items in sorted(grouped.items(), key=lambda x: x[0]):
        group_items.sort(key=lambda item: item["ts"])
        part = 1
        for start in range(0, len(group_items), max_lines_per_part):
            chunk = group_items[start : start + max_lines_per_part]
            object_key = (
                f"{prefix}/dt={target_date.isoformat()}/hour={hour:02d}/level={level}/part-{part:04d}.jsonl.gz"
            )
            local_path = output_dir / object_key
            local_path.parent.mkdir(parents=True, exist_ok=True)
            with gzip.open(local_path, "wt", encoding="utf-8") as gz:
                for row in chunk:
                    gz.write(row["line"])
                    gz.write("\n")
            objects.append(
                ArchiveObject(
                    local_path=local_path,
                    key=object_key,
                    level=level,
                    hour=hour,
                    line_count=len(chunk),
                    size_bytes=local_path.stat().st_size,
                    sha256=_sha256_file(local_path),
                    first_ts=chunk[0]["ts"] if chunk else None,
                    last_ts=chunk[-1]["ts"] if chunk else None,
                )
            )
            part += 1
    return objects


def _build_s3_client(settings: Settings) -> Any:
    try:
        import boto3
    except ModuleNotFoundError as exc:
        raise RuntimeError("boto3 is required for log archive upload") from exc
    kwargs: dict[str, Any] = {"region_name": settings.log_archive_region}
    if settings.log_archive_s3_endpoint:
        kwargs["endpoint_url"] = settings.log_archive_s3_endpoint
    return boto3.client("s3", **kwargs)


def _cleanup_hot_logs(log_root: Path, *, now: datetime, retention_days: int) -> int:
    cutoff = now - timedelta(days=retention_days)
    removed = 0
    for file_path in log_root.rglob("orchestrator.jsonl*"):
        if not file_path.is_file():
            continue
        modified = datetime.fromtimestamp(file_path.stat().st_mtime, tz=timezone.utc)
        if modified >= cutoff:
            continue
        try:
            file_path.unlink()
            removed += 1
        except FileNotFoundError:
            continue
    return removed


def _verify_restore_sample(s3_client: Any, *, bucket: str, key: str) -> bool:
    response = s3_client.get_object(Bucket=bucket, Key=key)
    body = response["Body"].read()
    restored = gzip.decompress(body).decode("utf-8")
    first_line = restored.splitlines()[0] if restored.splitlines() else ""
    if first_line:
        json.loads(first_line)
    return True


def archive_logs_once(
    *,
    settings: Settings,
    target_date: date | None = None,
    now: datetime | None = None,
    s3_client: Any | None = None,
) -> dict[str, Any]:
    """执行一次日志归档：切片、上传、热层清理与抽样恢复。"""
    now_utc = now or datetime.now(timezone.utc)
    if now_utc.tzinfo is None:
        now_utc = now_utc.replace(tzinfo=timezone.utc)
    archive_date = target_date or (now_utc.date() - timedelta(days=1))
    summary: dict[str, Any] = {
        "target_date": archive_date.isoformat(),
        "archived_files": 0,
        "archived_lines": 0,
        "manifest_key": None,
        "restore_sample_verified": False,
        "hot_deleted_files": 0,
    }
    if not settings.log_archive_enabled:
        logger.info("log archive disabled", extra={"event": "log.archive.skipped", "payload_preview": summary})
        return summary
    if not settings.log_archive_bucket:
        logger.error(
            "log archive bucket missing",
            extra={
                "event": "log.archive.failed",
                "error_type": "ConfigurationError",
                "error": "log_archive_bucket is required when LOG_ARCHIVE_ENABLED=true",
            },
        )
        return summary

    log_root = settings.log_dir
    if not log_root.is_absolute():
        log_root = (Path.cwd() / log_root).resolve()
    if not log_root.exists():
        logger.info("log root does not exist", extra={"event": "log.archive.skipped", "payload_preview": summary})
        return summary

    logger.info(
        "log archive started",
        extra={
            "event": "log.archive.started",
            "external_service": "s3",
            "op": "archive",
            "payload_preview": {"target_date": archive_date.isoformat()},
        },
    )
    records = _iter_target_records(log_root, archive_date)
    if not records:
        logger.info(
            "no records for archive date",
            extra={"event": "log.archive.skipped", "payload_preview": {"target_date": archive_date.isoformat()}},
        )
        summary["hot_deleted_files"] = _cleanup_hot_logs(
            log_root, now=now_utc, retention_days=settings.log_hot_retention_days
        )
        return summary

    with tempfile.TemporaryDirectory(prefix="orchestrator-log-archive-") as temp_dir:
        objects = _build_archive_objects(
            records=records,
            prefix=settings.log_archive_prefix.strip("/"),
            target_date=archive_date,
            output_dir=Path(temp_dir),
        )
        if not objects:
            summary["hot_deleted_files"] = _cleanup_hot_logs(
                log_root, now=now_utc, retention_days=settings.log_hot_retention_days
            )
            return summary

        client = s3_client or _build_s3_client(settings)
        for obj in objects:
            client.upload_file(str(obj.local_path), settings.log_archive_bucket, obj.key)

        manifest_key = f"{settings.log_archive_prefix.strip('/')}/dt={archive_date.isoformat()}/manifest.json"
        manifest = {
            "service": "opencode-orchestrator",
            "target_date": archive_date.isoformat(),
            "generated_at": now_utc.isoformat().replace("+00:00", "Z"),
            "cold_retention_days": settings.log_cold_retention_days,
            "files": [
                {
                    "key": item.key,
                    "level": item.level,
                    "hour": item.hour,
                    "line_count": item.line_count,
                    "size_bytes": item.size_bytes,
                    "sha256": item.sha256,
                    "first_ts": item.first_ts,
                    "last_ts": item.last_ts,
                }
                for item in objects
            ],
        }
        client.put_object(
            Bucket=settings.log_archive_bucket,
            Key=manifest_key,
            Body=(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode("utf-8"),
            ContentType="application/json",
        )

        summary["archived_files"] = len(objects)
        summary["archived_lines"] = sum(item.line_count for item in objects)
        summary["manifest_key"] = manifest_key

        if now_utc.weekday() == 0 and objects:
            try:
                summary["restore_sample_verified"] = _verify_restore_sample(
                    client,
                    bucket=settings.log_archive_bucket,
                    key=objects[0].key,
                )
                logger.info(
                    "log archive restore sample verified",
                    extra={
                        "event": "log.archive.restore_sample.succeeded",
                        "external_service": "s3",
                        "op": "restore-sample",
                        "payload_preview": {"key": objects[0].key},
                    },
                )
            except Exception as exc:
                logger.error(
                    "log archive restore sample failed",
                    extra={
                        "event": "log.archive.restore_sample.failed",
                        "external_service": "s3",
                        "op": "restore-sample",
                        "error_type": type(exc).__name__,
                        "error": str(exc),
                    },
                )

    summary["hot_deleted_files"] = _cleanup_hot_logs(log_root, now=now_utc, retention_days=settings.log_hot_retention_days)
    logger.info("log archive completed", extra={"event": "log.archive.succeeded", "payload_preview": summary})
    return summary
