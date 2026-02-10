"""
面向异构表格数据的稳健日期时间解析工具。

本模块有两个用途：
1. 提供可复用的 `DateTimeParser`，便于在数据处理流水线中集成。
2. 提供轻量 CLI，用于独立验证日期时间解析效果。
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
import logging
from pathlib import Path
import re
from typing import Dict, Sequence

import pandas as pd

from data_loader import DataLoader


@dataclass
class DateTimeParseResult:
    """单个 Series 解析为 datetime 后的结果摘要。"""

    column: str
    parsed: pd.Series
    parsed_count: int
    total_count: int
    parse_ratio: float
    strategy_counts: Dict[str, int] = field(default_factory=dict)


class DateTimeParser:
    """针对真实世界混合格式的多策略日期时间解析器。"""

    NULL_TEXTS = {
        "",
        "nan",
        "nat",
        "none",
        "null",
        "na",
        "n/a",
        "-",
        "--",
        "无",
        "空",
    }

    DATETIME_NAME_KEYWORDS = (
        "date",
        "time",
        "timestamp",
        "datetime",
        "日期",
        "时间",
        "时刻",
        "时间戳",
        "起始",
        "开始",
        "结束",
    )

    # 先尝试高确定性的常见格式，再回退到通用推断解析。
    COMMON_FORMATS = (
        "%Y-%m-%d %H:%M:%S",
        "%Y/%m/%d %H:%M:%S",
        "%Y.%m.%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y/%m/%d %H:%M",
        "%Y.%m.%d %H:%M",
        "%Y-%m-%d",
        "%Y/%m/%d",
        "%Y.%m.%d",
        "%Y%m%d%H%M%S",
        "%Y%m%d%H%M",
        "%Y%m%d",
        "%d-%m-%Y %H:%M:%S",
        "%d/%m/%Y %H:%M:%S",
        "%d-%m-%Y %H:%M",
        "%d/%m/%Y %H:%M",
        "%d-%m-%Y",
        "%d/%m/%Y",
        "%m/%d/%Y %H:%M:%S",
        "%m/%d/%Y %H:%M",
        "%m/%d/%Y",
        "%H:%M:%S",
        "%H:%M",
    )

    EPOCH_UNIT_BOUNDS = {
        # 使用合理时间范围，降低普通数字被误判为时间戳的概率。
        "s": (946684800, 4102444800),  # 2000-01-01 到 2100-01-01
        "ms": (946684800000, 4102444800000),
        "us": (946684800000000, 4102444800000000),
        "ns": (946684800000000000, 4102444800000000000),
    }

    _FULL_WIDTH_TRANSLATION = str.maketrans(
        {
            "：": ":",
            "／": "/",
            "－": "-",
            "．": ".",
            "，": ",",
            "　": " ",
        }
    )

    def __init__(
        self,
        logger: logging.Logger | None = None,
        min_valid_datetime: str = "1970-01-01",
        max_valid_datetime: str = "2100-12-31 23:59:59",
    ) -> None:
        self.logger = logger or logging.getLogger("data-analysis")
        self.min_valid_datetime = pd.Timestamp(min_valid_datetime)
        self.max_valid_datetime = pd.Timestamp(max_valid_datetime)

    @classmethod
    def looks_like_datetime_name(cls, column_name: str) -> bool:
        """基于列名关键字判断该列是否“像”日期时间列。"""
        key = str(column_name).strip().lower()
        return any(keyword in key for keyword in cls.DATETIME_NAME_KEYWORDS)

    def parse_series(
        self,
        series: pd.Series,
        column_name: str = "",
        enforce_valid_range: bool = True,
    ) -> DateTimeParseResult:
        """使用分层回退策略将 Series 解析为 datetime。"""
        if series is None:
            empty = pd.Series(dtype="datetime64[ns]")
            return DateTimeParseResult(
                column=column_name,
                parsed=empty,
                parsed_count=0,
                total_count=0,
                parse_ratio=0.0,
                strategy_counts={},
            )

        total_count = int(len(series))
        if total_count == 0:
            empty = pd.Series(index=series.index, dtype="datetime64[ns]")
            return DateTimeParseResult(
                column=column_name,
                parsed=empty,
                parsed_count=0,
                total_count=0,
                parse_ratio=0.0,
                strategy_counts={},
            )

        # 保持原索引不变，逐步填充解析结果。
        parsed = pd.Series(pd.NaT, index=series.index, dtype="datetime64[ns]")
        strategy_counts: Dict[str, int] = {}

        if pd.api.types.is_datetime64_any_dtype(series):
            already = pd.to_datetime(series, errors="coerce")
            parsed = self._merge_parsed(parsed, already, strategy_counts, "already_datetime")
            return self._build_result(column_name, parsed, total_count, strategy_counts)

        # 先处理数值形态日期：Excel 序列号与各粒度 Unix 时间戳。
        numeric_values = pd.to_numeric(series, errors="coerce")
        parsed = self._merge_parsed(
            parsed,
            self._parse_excel_serial(numeric_values),
            strategy_counts,
            "excel_serial",
        )
        for unit in ("s", "ms", "us", "ns"):
            parsed = self._merge_parsed(
                parsed,
                self._parse_epoch(numeric_values, unit),
                strategy_counts,
                f"epoch_{unit}",
            )

        # 再处理文本形态日期：先做规整，再按紧凑数字/年月/常见格式依次匹配。
        normalized_text = series.map(self._normalize_datetime_text)
        parsed = self._merge_parsed(
            parsed,
            self._parse_compact_digit_datetime(normalized_text),
            strategy_counts,
            "compact_digits",
        )
        parsed = self._merge_parsed(
            parsed,
            self._parse_year_or_year_month(normalized_text),
            strategy_counts,
            "year_or_year_month",
        )

        for date_format in self.COMMON_FORMATS:
            parsed = self._merge_parsed(
                parsed,
                pd.to_datetime(normalized_text, format=date_format, errors="coerce"),
                strategy_counts,
                f"format:{date_format}",
            )

        # 长尾场景回退：先解析带时区文本，再分别用默认顺序与 dayfirst 推断。
        timezone_text = normalized_text.where(
            normalized_text.str.contains(r"(?:Z|[+-]\d{2}:?\d{2})$", na=False)
        )
        if timezone_text.notna().any():
            tz_candidate = pd.to_datetime(timezone_text, errors="coerce", utc=True)
            tz_candidate = tz_candidate.dt.tz_convert(None)
            parsed = self._merge_parsed(parsed, tz_candidate, strategy_counts, "generic_tz")

        unresolved = normalized_text.where(parsed.isna())
        parsed = self._merge_parsed(
            parsed,
            pd.to_datetime(unresolved, errors="coerce"),
            strategy_counts,
            "generic",
        )
        unresolved = normalized_text.where(parsed.isna())
        parsed = self._merge_parsed(
            parsed,
            pd.to_datetime(unresolved, errors="coerce", dayfirst=True),
            strategy_counts,
            "generic_dayfirst",
        )

        if enforce_valid_range:
            parsed = self._clip_out_of_range(parsed, strategy_counts)

        return self._build_result(column_name, parsed, total_count, strategy_counts)

    def parse_dataframe_columns(
        self,
        dataframe: pd.DataFrame,
        columns: Sequence[str],
        parse_ratio_threshold: float = 0.6,
    ) -> tuple[pd.DataFrame, list[str], Dict[str, DateTimeParseResult]]:
        """解析指定 DataFrame 列，并返回解析后的数据与报告。"""
        parsed_columns: list[str] = []
        parse_reports: Dict[str, DateTimeParseResult] = {}
        output = dataframe.copy()

        for column in columns:
            if column not in output.columns:
                continue
            result = self.parse_series(output[column], column_name=column)
            parse_reports[column] = result
            if result.parsed_count > 0 and result.parse_ratio >= parse_ratio_threshold:
                output[column] = result.parsed
                parsed_columns.append(column)
        return output, parsed_columns, parse_reports

    def _parse_excel_serial(self, numeric_values: pd.Series) -> pd.Series:
        """
        解析 Excel 序列日期（按“天”存储的数字）。

        现代年份常见序列值大约在 2 万到 8 万之间。
        """
        mask = numeric_values.between(20_000, 80_000, inclusive="both")
        candidate = pd.Series(pd.NaT, index=numeric_values.index, dtype="datetime64[ns]")
        if not mask.any():
            return candidate
        candidate.loc[mask] = pd.to_datetime(
            numeric_values.loc[mask],
            unit="D",
            origin="1899-12-30",
            errors="coerce",
        )
        return candidate

    def _parse_epoch(self, numeric_values: pd.Series, unit: str) -> pd.Series:
        """按单位解析 Unix 时间戳，并应用合理区间过滤。"""
        bounds = self.EPOCH_UNIT_BOUNDS.get(unit)
        candidate = pd.Series(pd.NaT, index=numeric_values.index, dtype="datetime64[ns]")
        if bounds is None:
            return candidate
        lower_bound, upper_bound = bounds
        mask = numeric_values.between(lower_bound, upper_bound, inclusive="both")
        if not mask.any():
            return candidate
        candidate.loc[mask] = pd.to_datetime(
            numeric_values.loc[mask],
            unit=unit,
            errors="coerce",
        )
        return candidate

    def _parse_compact_digit_datetime(self, text_values: pd.Series) -> pd.Series:
        """解析纯数字紧凑时间串，例如 `20260125000055`。"""
        candidate = pd.Series(pd.NaT, index=text_values.index, dtype="datetime64[ns]")

        mask_14 = candidate.isna() & text_values.str.fullmatch(r"\d{14}", na=False)
        if mask_14.any():
            candidate.loc[mask_14] = pd.to_datetime(
                text_values.loc[mask_14],
                format="%Y%m%d%H%M%S",
                errors="coerce",
            )

        mask_12 = candidate.isna() & text_values.str.fullmatch(r"\d{12}", na=False)
        if mask_12.any():
            candidate.loc[mask_12] = pd.to_datetime(
                text_values.loc[mask_12],
                format="%Y%m%d%H%M",
                errors="coerce",
            )

        mask_8 = candidate.isna() & text_values.str.fullmatch(r"\d{8}", na=False)
        if mask_8.any():
            candidate.loc[mask_8] = pd.to_datetime(
                text_values.loc[mask_8],
                format="%Y%m%d",
                errors="coerce",
            )
        return candidate

    @staticmethod
    def _parse_year_or_year_month(text_values: pd.Series) -> pd.Series:
        """处理宽松的“年”或“年月”值，例如 `2026.0000`、`2026-01`。"""
        candidate = pd.Series(pd.NaT, index=text_values.index, dtype="datetime64[ns]")

        year_mask = text_values.str.fullmatch(r"\d{4}(?:\.0+)?", na=False)
        if year_mask.any():
            normalized_year = text_values.loc[year_mask].str.extract(r"(\d{4})")[0]
            candidate.loc[year_mask] = pd.to_datetime(
                normalized_year,
                format="%Y",
                errors="coerce",
            )

        year_month_mask = candidate.isna() & text_values.str.fullmatch(
            r"\d{4}[-/.]\d{1,2}",
            na=False,
        )
        if year_month_mask.any():
            year_month = (
                text_values.loc[year_month_mask]
                .str.replace("/", "-", regex=False)
                .str.replace(".", "-", regex=False)
            )
            candidate.loc[year_month_mask] = pd.to_datetime(
                year_month + "-01",
                format="%Y-%m-%d",
                errors="coerce",
            )
        return candidate

    def _clip_out_of_range(self, parsed: pd.Series, strategy_counts: Dict[str, int]) -> pd.Series:
        """将超出有效时间范围的解析结果置为 NaT。"""
        mask = parsed.notna() & (
            (parsed < self.min_valid_datetime) | (parsed > self.max_valid_datetime)
        )
        clipped_count = int(mask.sum())
        if clipped_count:
            parsed = parsed.copy()
            parsed.loc[mask] = pd.NaT
            strategy_counts["out_of_range_clipped"] = clipped_count
        return parsed

    @staticmethod
    def _merge_parsed(
        base: pd.Series,
        candidate: pd.Series,
        strategy_counts: Dict[str, int],
        strategy_name: str,
    ) -> pd.Series:
        """仅填充未解析位置，并统计当前策略贡献数量。"""
        candidate = DateTimeParser._force_naive_datetime(candidate)
        fill_mask = base.isna() & candidate.notna()
        fill_count = int(fill_mask.sum())
        if fill_count:
            base = base.copy()
            base.loc[fill_mask] = candidate.loc[fill_mask]
            strategy_counts[strategy_name] = strategy_counts.get(strategy_name, 0) + fill_count
        return base

    @classmethod
    def _normalize_datetime_text(cls, raw_value: object) -> str | None:
        """
        将噪声较多的时间文本规整为易解析字符串。

        处理内容包括：
        - 全角标点；
        - 中文年月日时分秒等单位；
        - 重复空白与重复分隔符。
        """
        if pd.isna(raw_value):
            return None
        text = str(raw_value).strip()
        if not text:
            return None

        lowered = text.lower()
        if lowered in cls.NULL_TEXTS:
            return None

        text = text.translate(cls._FULL_WIDTH_TRANSLATION)
        text = text.replace("年", "-").replace("月", "-").replace("日", " ")
        text = text.replace("号", " ")
        text = text.replace("时", ":").replace("点", ":").replace("分", ":").replace("秒", "")
        text = text.replace("T", " ").replace("t", " ")
        text = text.replace("，", ",")
        text = text.strip(" ,;")

        # 清理重复分隔符与多余空格，降低通用解析失败率。
        text = re.sub(r"[:]{2,}", ":", text)
        text = re.sub(r"[ ]{2,}", " ", text)
        text = re.sub(r"[-]{2,}", "-", text)
        text = re.sub(r"/{2,}", "/", text)
        text = re.sub(r"[.]{2,}", ".", text)
        text = text.strip()
        text = text.rstrip(":")
        return text or None

    @staticmethod
    def _force_naive_datetime(values: pd.Series) -> pd.Series:
        """
        将候选结果统一为不带时区的 `datetime64[ns]`。

        这样可避免源数据含时区偏移时，后续比较和统计出现类型不一致。
        """
        if values.empty:
            return values.astype("datetime64[ns]")

        if pd.api.types.is_datetime64_any_dtype(values):
            if getattr(values.dtype, "tz", None) is None:
                return pd.to_datetime(values, errors="coerce")
            return values.dt.tz_localize(None)

        normalized = values.map(DateTimeParser._coerce_single_naive_timestamp)
        return pd.to_datetime(normalized, errors="coerce")

    @staticmethod
    def _coerce_single_naive_timestamp(value: object) -> pd.Timestamp | pd.NaT:
        """将单值转为无时区 Timestamp；失败时返回 NaT。"""
        if pd.isna(value):
            return pd.NaT
        try:
            timestamp = pd.Timestamp(value)
        except Exception:  # pylint: disable=broad-except
            return pd.NaT
        if timestamp.tzinfo is not None:
            return timestamp.tz_localize(None)
        return timestamp

    @staticmethod
    def _build_result(
        column: str,
        parsed: pd.Series,
        total_count: int,
        strategy_counts: Dict[str, int],
    ) -> DateTimeParseResult:
        parsed_count = int(parsed.notna().sum())
        parse_ratio = float(parsed_count / total_count) if total_count else 0.0
        return DateTimeParseResult(
            column=column,
            parsed=parsed,
            parsed_count=parsed_count,
            total_count=total_count,
            parse_ratio=parse_ratio,
            strategy_counts=strategy_counts,
        )


def _parse_column_args(values: Sequence[str] | None) -> list[str]:
    """解析 `--column` 参数，支持重复传参与逗号分隔混用。"""
    if not values:
        return []
    parsed: list[str] = []
    for raw in values:
        parsed.extend([item.strip() for item in str(raw).split(",") if item.strip()])
    return parsed


def run_cli(
    *,
    input_path: str,
    columns: Sequence[str],
    sheet_name: str = "first",
    output_path: str | None = None,
    recursive: bool = False,
) -> int:
    """CLI 入口：解析日期时间列，并可选导出预览 CSV。"""
    logger = logging.getLogger("datetime-parser")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    logger.addHandler(logging.StreamHandler())

    loader = DataLoader(logger=logger)
    datasets = loader.load_path(input_path=input_path, recursive=recursive, sheet_name=sheet_name)
    if not datasets:
        logger.error("No dataset loaded from: %s", input_path)
        return 1

    frame = datasets[0].dataframe.copy()
    parser = DateTimeParser(logger=logger)
    target_columns = list(columns) if columns else [
        column for column in frame.columns if DateTimeParser.looks_like_datetime_name(column)
    ]
    if not target_columns:
        logger.warning("No candidate datetime columns found.")
        return 0

    for column in target_columns:
        if column not in frame.columns:
            logger.warning("Skip missing column: %s", column)
            continue
        result = parser.parse_series(frame[column], column_name=column)
        logger.info(
            "%s parse_ratio=%.2f (%s/%s), strategies=%s",
            column,
            result.parse_ratio,
            result.parsed_count,
            result.total_count,
            result.strategy_counts,
        )
        frame[column] = result.parsed

    if output_path:
        destination = Path(output_path).expanduser().resolve()
        destination.parent.mkdir(parents=True, exist_ok=True)
        frame.to_csv(destination, index=False, encoding="utf-8-sig")
        logger.info("Saved parsed preview: %s", destination)
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    arg_parser = argparse.ArgumentParser(description="Standalone datetime parser")
    arg_parser.add_argument("--input_path", type=str, required=True, help="Input file or directory path")
    arg_parser.add_argument(
        "--column",
        action="append",
        help="Datetime column name (repeatable, supports comma-separated values)",
    )
    arg_parser.add_argument(
        "--sheet_name",
        type=str,
        default="first",
        help="Excel sheet selector: first/all/<name>/<index>",
    )
    arg_parser.add_argument("--recursive", action="store_true", help="Recursively scan input directory")
    arg_parser.add_argument("--output_path", type=str, help="Optional CSV output path")
    args = arg_parser.parse_args(argv)

    return run_cli(
        input_path=args.input_path,
        columns=_parse_column_args(args.column),
        sheet_name=args.sheet_name,
        output_path=args.output_path,
        recursive=bool(args.recursive),
    )


if __name__ == "__main__":
    raise SystemExit(main())
