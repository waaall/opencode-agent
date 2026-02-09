from __future__ import annotations

from dataclasses import dataclass, field
import logging
from typing import Any, Dict, List, Sequence, Tuple

import numpy as np
import pandas as pd


@dataclass
class AnalysisOptions:
    """Runtime options controlling which analyses to execute."""

    datetime_columns: Sequence[str] = field(default_factory=list)
    preferred_numeric_columns: Sequence[str] = field(default_factory=list)
    groupby_columns: Sequence[str] = field(default_factory=list)
    categorical_top_n: int = 10
    time_frequency: str = "D"


@dataclass
class AnalysisResult:
    """Structured analysis output for downstream reporting and plotting."""

    dataframe: pd.DataFrame
    overview: Dict[str, Any]
    missing_summary: pd.DataFrame
    numeric_summary: pd.DataFrame
    categorical_summary: pd.DataFrame
    correlation_matrix: pd.DataFrame
    outlier_summary: pd.DataFrame
    groupby_summary: pd.DataFrame
    time_series_summary: pd.DataFrame
    markdown_summary: str


class DataAnalyzer:
    """Generic, reusable pandas-based analysis utilities."""

    def __init__(self, logger: logging.Logger | None = None) -> None:
        self.logger = logger or logging.getLogger("data-analysis")

    def run_full_analysis(self, dataframe: pd.DataFrame, options: AnalysisOptions) -> AnalysisResult:
        """Run the full analysis pipeline and return structured outputs."""
        cleaned_df, parsed_datetime_columns = self.prepare_dataframe(
            dataframe=dataframe,
            datetime_columns=options.datetime_columns,
        )
        numeric_columns = self.resolve_numeric_columns(
            dataframe=cleaned_df,
            preferred_columns=options.preferred_numeric_columns,
        )
        categorical_columns = self.resolve_categorical_columns(dataframe=cleaned_df)

        overview = self.build_overview(
            dataframe=cleaned_df,
            numeric_columns=numeric_columns,
            categorical_columns=categorical_columns,
            parsed_datetime_columns=parsed_datetime_columns,
        )
        missing_summary = self.analyze_missing_values(cleaned_df)
        numeric_summary = self.summarize_numeric(cleaned_df, numeric_columns)
        categorical_summary = self.summarize_categorical(
            dataframe=cleaned_df,
            categorical_columns=categorical_columns,
            top_n=options.categorical_top_n,
        )
        correlation_matrix = self.build_correlation_matrix(cleaned_df, numeric_columns)
        outlier_summary = self.detect_outliers_iqr(cleaned_df, numeric_columns)
        groupby_summary = self.group_aggregate(
            dataframe=cleaned_df,
            groupby_columns=options.groupby_columns,
            numeric_columns=numeric_columns,
        )
        time_series_summary = self.time_series_summary(
            dataframe=cleaned_df,
            datetime_columns=parsed_datetime_columns,
            numeric_columns=numeric_columns,
            frequency=options.time_frequency,
        )
        markdown_summary = self.build_markdown_summary(
            overview=overview,
            missing_summary=missing_summary,
            numeric_summary=numeric_summary,
            outlier_summary=outlier_summary,
            correlation_matrix=correlation_matrix,
            groupby_summary=groupby_summary,
            time_series_summary=time_series_summary,
        )

        return AnalysisResult(
            dataframe=cleaned_df,
            overview=overview,
            missing_summary=missing_summary,
            numeric_summary=numeric_summary,
            categorical_summary=categorical_summary,
            correlation_matrix=correlation_matrix,
            outlier_summary=outlier_summary,
            groupby_summary=groupby_summary,
            time_series_summary=time_series_summary,
            markdown_summary=markdown_summary,
        )

    def prepare_dataframe(
        self,
        dataframe: pd.DataFrame,
        datetime_columns: Sequence[str] | None = None,
    ) -> Tuple[pd.DataFrame, List[str]]:
        """Standardize dataframe, trim noise, and parse datetime columns."""
        if dataframe is None or dataframe.empty:
            return pd.DataFrame(), []

        cleaned = dataframe.copy()
        cleaned = cleaned.dropna(axis=0, how="all").dropna(axis=1, how="all")

        for column in cleaned.select_dtypes(include=["object"]).columns:
            cleaned[column] = cleaned[column].map(
                lambda value: value.strip() if isinstance(value, str) else value
            )

        explicit_datetime_columns = [col for col in (datetime_columns or []) if col in cleaned.columns]
        if explicit_datetime_columns:
            candidates = explicit_datetime_columns
            require_parse_ratio = 0.0
        else:
            candidates = [col for col in cleaned.columns if self.looks_like_datetime_column(col)]
            require_parse_ratio = 0.6

        parsed_columns: List[str] = []
        for column in candidates:
            parsed = pd.to_datetime(cleaned[column], errors="coerce")
            parse_ratio = parsed.notna().mean() if len(parsed) else 0.0
            if parse_ratio >= require_parse_ratio and parsed.notna().sum() > 0:
                cleaned[column] = parsed
                parsed_columns.append(column)
            else:
                self.logger.warning(
                    "Skip datetime conversion for column %s (parse ratio=%.2f)",
                    column,
                    parse_ratio,
                )

        self.logger.info(
            "Prepared dataframe: rows=%s, columns=%s, parsed_datetime=%s",
            len(cleaned),
            len(cleaned.columns),
            parsed_columns,
        )
        return cleaned, parsed_columns

    @staticmethod
    def looks_like_datetime_column(column_name: str) -> bool:
        key = str(column_name).lower()
        keywords = ("date", "time", "timestamp", "日期", "时间")
        return any(keyword in key for keyword in keywords)

    @staticmethod
    def resolve_numeric_columns(
        dataframe: pd.DataFrame,
        preferred_columns: Sequence[str] | None = None,
    ) -> List[str]:
        if dataframe.empty:
            return []
        if preferred_columns:
            selected = [column for column in preferred_columns if column in dataframe.columns]
            if selected:
                return selected
        return dataframe.select_dtypes(include=[np.number]).columns.tolist()

    @staticmethod
    def resolve_categorical_columns(dataframe: pd.DataFrame) -> List[str]:
        if dataframe.empty:
            return []
        object_columns = dataframe.select_dtypes(include=["object", "category"]).columns.tolist()
        return [column for column in object_columns if not column.startswith("__")]

    def build_overview(
        self,
        dataframe: pd.DataFrame,
        numeric_columns: Sequence[str],
        categorical_columns: Sequence[str],
        parsed_datetime_columns: Sequence[str],
    ) -> Dict[str, Any]:
        """Build high-level dataset overview."""
        if dataframe.empty:
            return {
                "rows": 0,
                "columns": 0,
                "missing_cells": 0,
                "missing_ratio": 0.0,
                "duplicate_rows": 0,
                "memory_mb": 0.0,
                "numeric_columns": [],
                "categorical_columns": [],
                "datetime_columns": [],
                "source_file_count": 0,
                "source_sheet_count": 0,
            }

        total_cells = int(dataframe.shape[0] * dataframe.shape[1]) or 1
        missing_cells = int(dataframe.isna().sum().sum())
        duplicate_rows = int(dataframe.duplicated().sum())
        memory_mb = float(dataframe.memory_usage(index=True, deep=True).sum() / (1024**2))

        source_file_count = (
            int(dataframe["__source_file"].nunique())
            if "__source_file" in dataframe.columns
            else 0
        )
        source_sheet_count = (
            int(dataframe["__source_sheet"].nunique())
            if "__source_sheet" in dataframe.columns
            else 0
        )

        return {
            "rows": int(dataframe.shape[0]),
            "columns": int(dataframe.shape[1]),
            "missing_cells": missing_cells,
            "missing_ratio": round(missing_cells / total_cells, 6),
            "duplicate_rows": duplicate_rows,
            "memory_mb": round(memory_mb, 3),
            "numeric_columns": list(numeric_columns),
            "categorical_columns": list(categorical_columns),
            "datetime_columns": list(parsed_datetime_columns),
            "source_file_count": source_file_count,
            "source_sheet_count": source_sheet_count,
        }

    @staticmethod
    def analyze_missing_values(dataframe: pd.DataFrame) -> pd.DataFrame:
        """Return missing-value summary per column."""
        columns = ["column", "missing_count", "missing_ratio"]
        if dataframe.empty:
            return pd.DataFrame(columns=columns)
        missing = dataframe.isna().sum().rename("missing_count").to_frame()
        missing["missing_ratio"] = (missing["missing_count"] / len(dataframe)).round(6)
        summary = (
            missing.reset_index()
            .rename(columns={"index": "column"})
            .sort_values(by=["missing_count", "column"], ascending=[False, True])
            .reset_index(drop=True)
        )
        return summary[columns]

    @staticmethod
    def summarize_numeric(dataframe: pd.DataFrame, numeric_columns: Sequence[str]) -> pd.DataFrame:
        """Generate robust numeric statistics."""
        columns = [
            "column",
            "count",
            "missing_count",
            "missing_ratio",
            "mean",
            "std",
            "min",
            "q1",
            "median",
            "q3",
            "max",
            "iqr",
            "cv",
        ]
        valid_columns = [column for column in numeric_columns if column in dataframe.columns]
        if not valid_columns:
            return pd.DataFrame(columns=columns)

        numeric_frame = dataframe[valid_columns].apply(pd.to_numeric, errors="coerce")
        describe_frame = numeric_frame.describe(percentiles=[0.25, 0.5, 0.75]).T
        describe_frame = describe_frame.rename(columns={"25%": "q1", "50%": "median", "75%": "q3"})
        describe_frame["missing_count"] = numeric_frame.isna().sum()
        describe_frame["missing_ratio"] = describe_frame["missing_count"] / len(dataframe)
        describe_frame["iqr"] = describe_frame["q3"] - describe_frame["q1"]
        describe_frame["cv"] = np.where(
            describe_frame["mean"] != 0,
            describe_frame["std"] / describe_frame["mean"],
            np.nan,
        )

        summary = describe_frame.reset_index().rename(columns={"index": "column"})
        summary = summary[columns].sort_values(by="column").reset_index(drop=True)
        return summary

    @staticmethod
    def summarize_categorical(
        dataframe: pd.DataFrame,
        categorical_columns: Sequence[str],
        top_n: int = 10,
    ) -> pd.DataFrame:
        """Summarize categorical columns and top values."""
        columns = [
            "column",
            "non_null_count",
            "missing_count",
            "unique_count",
            "top_values",
        ]
        rows: List[Dict[str, Any]] = []
        for column in categorical_columns:
            if column not in dataframe.columns:
                continue
            series = dataframe[column]
            non_null_count = int(series.notna().sum())
            missing_count = int(series.isna().sum())
            unique_count = int(series.nunique(dropna=True))
            if non_null_count == 0:
                top_values = ""
            else:
                counts = series.value_counts(dropna=True).head(max(top_n, 1))
                value_parts = [
                    f"{value}: {count} ({count / non_null_count:.1%})"
                    for value, count in counts.items()
                ]
                top_values = " | ".join(value_parts)

            rows.append(
                {
                    "column": column,
                    "non_null_count": non_null_count,
                    "missing_count": missing_count,
                    "unique_count": unique_count,
                    "top_values": top_values,
                }
            )

        if not rows:
            return pd.DataFrame(columns=columns)
        return pd.DataFrame(rows)[columns].sort_values(by="column").reset_index(drop=True)

    @staticmethod
    def build_correlation_matrix(
        dataframe: pd.DataFrame,
        numeric_columns: Sequence[str],
    ) -> pd.DataFrame:
        """Compute Pearson correlation matrix for numeric columns."""
        valid_columns = [column for column in numeric_columns if column in dataframe.columns]
        if len(valid_columns) < 2:
            return pd.DataFrame()
        corr = dataframe[valid_columns].corr(method="pearson", numeric_only=True)
        corr = corr.dropna(axis=0, how="all").dropna(axis=1, how="all")
        return corr

    @staticmethod
    def detect_outliers_iqr(
        dataframe: pd.DataFrame,
        numeric_columns: Sequence[str],
    ) -> pd.DataFrame:
        """Detect outliers using IQR rule for each numeric column."""
        columns = ["column", "lower_bound", "upper_bound", "outlier_count", "outlier_ratio"]
        rows: List[Dict[str, Any]] = []
        for column in numeric_columns:
            if column not in dataframe.columns:
                continue
            series = pd.to_numeric(dataframe[column], errors="coerce").dropna()
            if len(series) < 4:
                continue
            q1 = float(series.quantile(0.25))
            q3 = float(series.quantile(0.75))
            iqr = q3 - q1
            lower_bound = q1 - 1.5 * iqr
            upper_bound = q3 + 1.5 * iqr
            outlier_count = int(((series < lower_bound) | (series > upper_bound)).sum())
            rows.append(
                {
                    "column": column,
                    "lower_bound": lower_bound,
                    "upper_bound": upper_bound,
                    "outlier_count": outlier_count,
                    "outlier_ratio": outlier_count / len(series),
                }
            )
        if not rows:
            return pd.DataFrame(columns=columns)
        summary = pd.DataFrame(rows)[columns]
        return summary.sort_values(by="outlier_ratio", ascending=False).reset_index(drop=True)

    @staticmethod
    def group_aggregate(
        dataframe: pd.DataFrame,
        groupby_columns: Sequence[str],
        numeric_columns: Sequence[str],
    ) -> pd.DataFrame:
        """Aggregate dataset by selected dimensions."""
        valid_groupby = [column for column in groupby_columns if column in dataframe.columns]
        if dataframe.empty or not valid_groupby:
            return pd.DataFrame()

        grouped = dataframe.groupby(valid_groupby, dropna=False)
        result = grouped.size().rename("row_count").to_frame()
        for column in numeric_columns[:15]:
            if column not in dataframe.columns:
                continue
            result[f"{column}__mean"] = grouped[column].mean()
            result[f"{column}__median"] = grouped[column].median()
        result = result.reset_index().sort_values(by="row_count", ascending=False).reset_index(drop=True)
        return result

    @staticmethod
    def time_series_summary(
        dataframe: pd.DataFrame,
        datetime_columns: Sequence[str],
        numeric_columns: Sequence[str],
        frequency: str = "D",
    ) -> pd.DataFrame:
        """Aggregate row counts and numeric means over time."""
        if dataframe.empty:
            return pd.DataFrame()
        datetime_column = next(
            (
                column
                for column in datetime_columns
                if column in dataframe.columns and pd.api.types.is_datetime64_any_dtype(dataframe[column])
            ),
            None,
        )
        if datetime_column is None:
            return pd.DataFrame()

        frame = dataframe.copy()
        frame = frame.dropna(subset=[datetime_column])
        if frame.empty:
            return pd.DataFrame()

        frame["time_period"] = frame[datetime_column].dt.to_period(frequency).dt.to_timestamp()
        grouped = frame.groupby("time_period")

        result = grouped.size().rename("row_count").to_frame()
        for column in numeric_columns[:10]:
            if column not in frame.columns:
                continue
            result[f"{column}__mean"] = grouped[column].mean()
        result = result.reset_index().sort_values(by="time_period").reset_index(drop=True)
        result.insert(0, "datetime_column", datetime_column)
        return result

    def build_markdown_summary(
        self,
        overview: Dict[str, Any],
        missing_summary: pd.DataFrame,
        numeric_summary: pd.DataFrame,
        outlier_summary: pd.DataFrame,
        correlation_matrix: pd.DataFrame,
        groupby_summary: pd.DataFrame,
        time_series_summary: pd.DataFrame,
    ) -> str:
        """Generate a concise markdown report for human consumption."""
        lines: List[str] = [
            "# 数据分析总结",
            "",
            "## 数据规模与质量",
            f"- 行数: {overview.get('rows', 0)}",
            f"- 列数: {overview.get('columns', 0)}",
            f"- 缺失单元格: {overview.get('missing_cells', 0)} ({overview.get('missing_ratio', 0.0):.2%})",
            f"- 重复行: {overview.get('duplicate_rows', 0)}",
            f"- 数据内存占用: {overview.get('memory_mb', 0.0)} MB",
            f"- 来源文件数: {overview.get('source_file_count', 0)}",
            f"- 来源工作表数: {overview.get('source_sheet_count', 0)}",
            "",
            "## 字段结构",
            f"- 数值字段数: {len(overview.get('numeric_columns', []))}",
            f"- 分类型字段数: {len(overview.get('categorical_columns', []))}",
            f"- 时间字段: {', '.join(overview.get('datetime_columns', [])) or '无'}",
        ]

        top_missing = missing_summary[missing_summary["missing_count"] > 0].head(5)
        if not top_missing.empty:
            lines.extend(["", "## 缺失值最高字段（Top 5）"])
            for _, row in top_missing.iterrows():
                lines.append(
                    f"- {row['column']}: {int(row['missing_count'])} ({float(row['missing_ratio']):.2%})"
                )

        if not numeric_summary.empty:
            lines.extend(["", "## 数值字段说明"])
            lines.append(f"- 已生成 {len(numeric_summary)} 个字段的分布统计（均值、分位数、IQR、变异系数）。")

        top_outliers = outlier_summary[outlier_summary["outlier_count"] > 0].head(5)
        if not top_outliers.empty:
            lines.extend(["", "## 异常值字段（IQR，Top 5）"])
            for _, row in top_outliers.iterrows():
                lines.append(
                    f"- {row['column']}: {int(row['outlier_count'])} ({float(row['outlier_ratio']):.2%})"
                )

        pair = self.find_strongest_correlation_pair(correlation_matrix)
        if pair is not None:
            col_a, col_b, value = pair
            lines.extend(
                [
                    "",
                    "## 相关性提示",
                    f"- 最强相关字段对: `{col_a}` 与 `{col_b}`，相关系数 = {value:.4f}",
                ]
            )

        if not groupby_summary.empty:
            lines.extend(
                [
                    "",
                    "## 分组分析",
                    f"- 已按指定维度输出 {len(groupby_summary)} 组汇总结果。",
                ]
            )

        if not time_series_summary.empty:
            lines.extend(
                [
                    "",
                    "## 时间序列分析",
                    f"- 已按时间粒度汇总 {len(time_series_summary)} 个时间点。",
                ]
            )

        lines.extend(
            [
                "",
                "## 产物说明",
                "- 详细统计表已导出为 CSV。",
                "- 图表输出位于 `plots/` 目录。",
            ]
        )
        return "\n".join(lines) + "\n"

    @staticmethod
    def find_strongest_correlation_pair(correlation_matrix: pd.DataFrame) -> Tuple[str, str, float] | None:
        if correlation_matrix.empty or len(correlation_matrix.columns) < 2:
            return None
        best_pair: Tuple[str, str, float] | None = None
        columns = list(correlation_matrix.columns)
        for i in range(len(columns)):
            for j in range(i + 1, len(columns)):
                value = correlation_matrix.iloc[i, j]
                if pd.isna(value):
                    continue
                if best_pair is None or abs(value) > abs(best_pair[2]):
                    best_pair = (columns[i], columns[j], float(value))
        return best_pair
