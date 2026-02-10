"""
通用数据分析器（pandas 版）

职责：
1. 对输入 DataFrame 做基础清洗（去空行列、字符串去空格、时间列解析）。
2. 产出结构化统计结果（概览、缺失值、数值分布、相关性、异常值、分组、时序）。
3. 生成一份面向人的 Markdown 摘要，方便在报告中直接引用。

设计取向：
- 所有分析方法都尽量“空数据可安全返回”，减少调用方的分支判断。
- 输出以 DataFrame/Dict 为主，便于后续导出 CSV、画图或二次加工。
"""

from __future__ import annotations

from dataclasses import dataclass, field
import logging
from typing import Any, Dict, List, Sequence, Tuple

import numpy as np
import pandas as pd

from datetime_parser import DateTimeParser


@dataclass
class AnalysisOptions:
    """分析运行选项。"""

    # 明确指定要解析为时间的字段名；为空时按字段名关键词自动猜测。
    datetime_columns: Sequence[str] = field(default_factory=list)
    # 优先作为数值分析对象的字段；为空时自动选取全部数值型字段。
    preferred_numeric_columns: Sequence[str] = field(default_factory=list)
    # 需要做分组汇总的维度字段。
    groupby_columns: Sequence[str] = field(default_factory=list)
    # 时间序列聚合粒度（如 D/W/M）。
    time_frequency: str = "D"


@dataclass
class AnalysisResult:
    """完整分析结果容器。"""

    # 清洗后的数据（作为后续导出和绘图的统一输入）。
    dataframe: pd.DataFrame
    # 数据概览指标（行列数、缺失率、重复行、内存占用等）。
    overview: Dict[str, Any]
    # 各字段缺失值统计。
    missing_summary: pd.DataFrame
    # 数值字段统计表（均值/分位数/IQR/CV 等）。
    numeric_summary: pd.DataFrame
    # Pearson 相关系数矩阵。
    correlation_matrix: pd.DataFrame
    # IQR 规则异常值统计。
    outlier_summary: pd.DataFrame
    # 分组聚合统计。
    groupby_summary: pd.DataFrame
    # 时间粒度聚合统计。
    time_series_summary: pd.DataFrame
    # 面向阅读的 Markdown 摘要。
    markdown_summary: str


class DataAnalyzer:
    """基于 pandas 的可复用分析器。"""

    def __init__(self, logger: logging.Logger | None = None) -> None:
        # 注入 logger 便于在批处理场景统一接入日志系统；
        # 未传入时使用本模块默认命名 logger。
        self.logger = logger or logging.getLogger("data-analysis")
        self.datetime_parser = DateTimeParser(logger=self.logger)

    def run_full_analysis(self, dataframe: pd.DataFrame, options: AnalysisOptions) -> AnalysisResult:
        """
        执行完整分析流水线，并返回结构化结果。

        流程顺序固定：
        1) 清洗与时间解析
        2) 字段类型决策（数值/分类）
        3) 多维统计计算
        4) 组装 Markdown 摘要
        """
        # 先统一数据质量，再做后续统计，避免重复在各函数里做防御性处理。
        cleaned_df, parsed_datetime_columns = self.prepare_dataframe(
            dataframe=dataframe,
            datetime_columns=options.datetime_columns,
        )
        # 数值字段优先尊重用户传入偏好；否则自动推断。
        numeric_columns = self.resolve_numeric_columns(
            dataframe=cleaned_df,
            preferred_columns=options.preferred_numeric_columns,
        )
        # 分类字段只在 object/category 中选取，并排除内部元字段（双下划线）。
        categorical_columns = self.resolve_categorical_columns(dataframe=cleaned_df)

        # 概览类指标
        overview = self.build_overview(
            dataframe=cleaned_df,
            numeric_columns=numeric_columns,
            categorical_columns=categorical_columns,
            parsed_datetime_columns=parsed_datetime_columns,
        )
        # 明细统计
        missing_summary = self.analyze_missing_values(cleaned_df)
        numeric_summary = self.summarize_numeric(cleaned_df, numeric_columns)
        # 关系分析
        correlation_matrix = self.build_correlation_matrix(cleaned_df, numeric_columns)
        outlier_summary = self.detect_outliers_iqr(cleaned_df, numeric_columns)
        # 维度与时序分析
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
        # 汇总为可读报告文本（用于终端展示或写入 md 文件）
        markdown_summary = self.build_markdown_summary(
            overview=overview,
            missing_summary=missing_summary,
            numeric_summary=numeric_summary,
            outlier_summary=outlier_summary,
            correlation_matrix=correlation_matrix,
            groupby_summary=groupby_summary,
            time_series_summary=time_series_summary,
        )

        # 返回一个统一结果对象，方便上层按需选择消费字段。
        return AnalysisResult(
            dataframe=cleaned_df,
            overview=overview,
            missing_summary=missing_summary,
            numeric_summary=numeric_summary,
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
        """
        标准化 DataFrame、去除明显噪声并解析时间列。

        返回：
        - cleaned: 清洗后的 DataFrame
        - parsed_columns: 成功解析为 datetime 的字段名列表
        """
        # 空输入直接返回空表，避免后续函数大量 if 判断。
        if dataframe is None or dataframe.empty:
            return pd.DataFrame(), []

        # 深拷贝一份，避免就地修改调用方传入对象。
        cleaned = dataframe.copy()
        # 删除整行/整列全空的数据块，降低统计噪声。
        cleaned = cleaned.dropna(axis=0, how="all").dropna(axis=1, how="all")

        # object 列做字符串 trim，减少 "A" 与 " A " 被误判为不同值。
        for column in cleaned.select_dtypes(include=["object"]).columns:
            cleaned[column] = cleaned[column].map(
                lambda value: value.strip() if isinstance(value, str) else value
            )

        # 时间列决策策略：
        # - 用户显式指定：强制尝试，解析率阈值放宽到 0（只要有可解析值即可）
        # - 未指定：按字段名关键词猜测，要求解析率 >= 60%
        explicit_datetime_columns = [col for col in (datetime_columns or []) if col in cleaned.columns]
        if explicit_datetime_columns:
            candidates = explicit_datetime_columns
            require_parse_ratio = 0.0
        else:
            candidates = [col for col in cleaned.columns if self.looks_like_datetime_column(col)]
            require_parse_ratio = 0.6

        parsed_columns: List[str] = []
        for column in candidates:
            result = self.datetime_parser.parse_series(cleaned[column], column_name=column)
            parse_ratio = result.parse_ratio
            # 只有解析率达标且至少有 1 个有效日期时才替换原列。
            if parse_ratio >= require_parse_ratio and result.parsed_count > 0:
                cleaned[column] = result.parsed
                parsed_columns.append(column)
                self.logger.info(
                    "Datetime conversion succeeded for %s (ratio=%.2f, parsed=%s/%s, strategies=%s)",
                    column,
                    parse_ratio,
                    result.parsed_count,
                    result.total_count,
                    result.strategy_counts,
                )
            else:
                # 跳过时记录告警，方便排查字段命名误判或脏数据问题。
                self.logger.warning(
                    "Skip datetime conversion for column %s (parse ratio=%.2f, parsed=%s/%s, strategies=%s)",
                    column,
                    parse_ratio,
                    result.parsed_count,
                    result.total_count,
                    result.strategy_counts,
                )

        # 记录清洗后的关键规模信息，便于调试链路观察。
        self.logger.info(
            "Prepared dataframe: rows=%s, columns=%s, parsed_datetime=%s",
            len(cleaned),
            len(cleaned.columns),
            parsed_columns,
        )
        return cleaned, parsed_columns

    @staticmethod
    def looks_like_datetime_column(column_name: str) -> bool:
        """通过字段名关键词做时间列启发式识别。"""
        return DateTimeParser.looks_like_datetime_name(column_name)

    @staticmethod
    def resolve_numeric_columns(
        dataframe: pd.DataFrame,
        preferred_columns: Sequence[str] | None = None,
    ) -> List[str]:
        """
        决定要参与数值分析的字段。

        规则：
        1. 有 preferred 且命中字段时，优先使用命中集合；
        2. 否则回退到所有数值 dtype 字段。
        """
        if dataframe.empty:
            return []
        if preferred_columns:
            selected = [column for column in preferred_columns if column in dataframe.columns]
            if selected:
                return selected
        return dataframe.select_dtypes(include=[np.number]).columns.tolist()

    @staticmethod
    def resolve_categorical_columns(dataframe: pd.DataFrame) -> List[str]:
        """
        决定分类字段集合。

        仅选择 object/category，且排除以 `__` 开头的内部元字段。
        """
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
        """
        生成数据集总览信息。

        指标口径：
        - missing_ratio: 缺失单元格 / 总单元格
        - duplicate_rows: 完全重复行数量
        - memory_mb: pandas 深度内存估算（含对象列内容）
        """
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

        # 兜底为 1，避免空表场景出现除零错误。
        total_cells = int(dataframe.shape[0] * dataframe.shape[1]) or 1
        missing_cells = int(dataframe.isna().sum().sum())
        duplicate_rows = int(dataframe.duplicated().sum())
        memory_mb = float(dataframe.memory_usage(index=True, deep=True).sum() / (1024**2))

        # 若上游合并数据时注入了来源元字段，这里额外统计来源覆盖情况。
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
        """按列统计缺失数量和缺失率，并按缺失数量降序输出。"""
        columns = ["column", "missing_count", "missing_ratio"]
        if dataframe.empty:
            return pd.DataFrame(columns=columns)
        # isna().sum() 会逐列统计缺失值个数。
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
        """
        生成数值字段统计摘要。

        输出指标包含：
        - count/min/max/mean/std（来自 describe）
        - q1/median/q3（四分位）
        - missing_count/missing_ratio
        - iqr（四分位距）
        - cv（变异系数 = std / mean，mean=0 时置为 NaN）
        """
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

        # 统一转 numeric：非法值强制为 NaN，确保统计过程不抛错。
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
    def build_correlation_matrix(
        dataframe: pd.DataFrame,
        numeric_columns: Sequence[str],
    ) -> pd.DataFrame:
        """
        计算数值字段 Pearson 相关矩阵。

        仅当有效数值字段 >= 2 时才有意义，否则返回空表。
        """
        valid_columns = [column for column in numeric_columns if column in dataframe.columns]
        if len(valid_columns) < 2:
            return pd.DataFrame()
        corr = dataframe[valid_columns].corr(method="pearson", numeric_only=True)
        # 去掉全空行列，避免输出中出现无信息矩阵边缘。
        corr = corr.dropna(axis=0, how="all").dropna(axis=1, how="all")
        return corr

    @staticmethod
    def detect_outliers_iqr(
        dataframe: pd.DataFrame,
        numeric_columns: Sequence[str],
    ) -> pd.DataFrame:
        """
        使用 IQR 规则检测异常值。

        判定阈值：
        - lower = Q1 - 1.5 * IQR
        - upper = Q3 + 1.5 * IQR
        """
        columns = ["column", "lower_bound", "upper_bound", "outlier_count", "outlier_ratio"]
        rows: List[Dict[str, Any]] = []
        for column in numeric_columns:
            if column not in dataframe.columns:
                continue
            series = pd.to_numeric(dataframe[column], errors="coerce").dropna()
            # 样本太少（<4）时四分位统计稳定性较差，直接跳过。
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
        """
        按指定维度做分组聚合。

        输出包含：
        - row_count：每组样本量
        - 每个数值字段（最多前 15 个）的均值与中位数
        """
        valid_groupby = [column for column in groupby_columns if column in dataframe.columns]
        if dataframe.empty or not valid_groupby:
            return pd.DataFrame()

        # dropna=False 保留分组维度为空的记录，避免样本被静默丢失。
        grouped = dataframe.groupby(valid_groupby, dropna=False)
        result = grouped.size().rename("row_count").to_frame()
        # 列数做上限限制，防止宽表下聚合输出爆炸。
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
        """
        按时间粒度汇总行数、数值均值与标准差。

        规则：
        - 仅使用第一个可用且 dtype 为 datetime 的时间列；
        - 生成 `time_period` 作为聚合键；
        - 每个数值字段最多聚合前 10 个，控制输出体积。
        """
        if dataframe.empty:
            return pd.DataFrame()
        # 从候选时间列中选第一个真正 datetime 类型的字段。
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
        # 时间为空的记录无法参与时序聚合，先过滤。
        frame = frame.dropna(subset=[datetime_column])
        if frame.empty:
            return pd.DataFrame()

        # to_period(frequency) 先落到周期，再转 timestamp 便于下游可视化与导出。
        frame["time_period"] = frame[datetime_column].dt.to_period(frequency).dt.to_timestamp()
        grouped = frame.groupby("time_period")

        result = grouped.size().rename("row_count").to_frame()
        for column in numeric_columns[:10]:
            if column not in frame.columns:
                continue
            result[f"{column}__mean"] = grouped[column].mean()
            result[f"{column}__std"] = grouped[column].std()
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
        """
        生成面向阅读的 Markdown 摘要。

        约束：
        - 文本尽量短，展示关键指标和 Top 信息；
        - 详细明细交给 CSV/图表，不在摘要里展开。
        """
        # 先构建固定信息段落：规模、质量、字段结构。
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

        # 缺失值 Top 5
        top_missing = missing_summary[missing_summary["missing_count"] > 0].head(5)
        if not top_missing.empty:
            lines.extend(["", "## 缺失值最高字段（Top 5）"])
            for _, row in top_missing.iterrows():
                lines.append(
                    f"- {row['column']}: {int(row['missing_count'])} ({float(row['missing_ratio']):.2%})"
                )

        # 数值统计只给出“已生成”的提示，细节由统计表承载。
        if not numeric_summary.empty:
            lines.extend(["", "## 数值字段说明"])
            lines.append(f"- 已生成 {len(numeric_summary)} 个字段的分布统计（均值、分位数、IQR、变异系数）。")

        # 异常值 Top 5
        top_outliers = outlier_summary[outlier_summary["outlier_count"] > 0].head(5)
        if not top_outliers.empty:
            lines.extend(["", "## 异常值字段（IQR，Top 5）"])
            for _, row in top_outliers.iterrows():
                lines.append(
                    f"- {row['column']}: {int(row['outlier_count'])} ({float(row['outlier_ratio']):.2%})"
                )

        # 相关性只突出最强的一对，避免摘要过载。
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

        # 分组/时序仅报告“已输出多少组（点）”，详情看数据表。
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

        # 结尾说明结果产物位置，方便调用方对接后续流程。
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
        """
        在相关矩阵中找到绝对值最大的非对角相关系数对。

        返回 (列A, 列B, 系数)；若矩阵无效则返回 None。
        """
        if correlation_matrix.empty or len(correlation_matrix.columns) < 2:
            return None
        best_pair: Tuple[str, str, float] | None = None
        columns = list(correlation_matrix.columns)
        # 只遍历上三角 (i < j)，避免重复比较对称位置。
        for i in range(len(columns)):
            for j in range(i + 1, len(columns)):
                value = correlation_matrix.iloc[i, j]
                if pd.isna(value):
                    continue
                if best_pair is None or abs(value) > abs(best_pair[2]):
                    best_pair = (columns[i], columns[j], float(value))
        return best_pair
