"""
通用数据分析器(pandas 版)

职责：
1. 对输入 DataFrame 做基础清洗(去空行列、字符串去空格、时间列解析)。
2. 产出结构化统计结果(概览、缺失值、数值分布、相关性、异常值、分组、时序)。

设计取向：
- 所有分析方法都尽量“空数据可安全返回”, 减少调用方的分支判断。
- 输出以 DataFrame/Dict 为主, 便于后续导出 CSV、画图或二次加工。
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
    # 时间序列聚合粒度：支持 auto/H/D(auto 会在 H 与 D 间自动决策)。
    time_frequency: str = "auto"


@dataclass
class AnalysisResult:
    """完整分析结果容器。"""

    # 清洗后的数据(作为后续导出和绘图的统一输入)。
    dataframe: pd.DataFrame
    # 数据概览指标(行列数、缺失率、重复行、内存占用等)。
    overview: Dict[str, Any]
    # 各字段缺失值统计。
    missing_summary: pd.DataFrame
    # 数值字段统计表(均值/分位数/IQR/CV 等)。
    numeric_summary: pd.DataFrame
    # Pearson 相关系数矩阵。
    correlation_matrix: pd.DataFrame
    # IQR 规则异常值统计。
    outlier_summary: pd.DataFrame
    # 分组聚合统计。
    groupby_summary: pd.DataFrame
    # 时间粒度聚合统计。
    time_series_summary: pd.DataFrame


class DataAnalyzer:
    """基于 pandas 的可复用分析器。"""

    def __init__(self, logger: logging.Logger | None = None) -> None:
        # 注入 logger 便于在批处理场景统一接入日志系统；
        # 未传入时使用本模块默认命名 logger。
        self.logger = logger or logging.getLogger("data-analysis")
        self.datetime_parser = DateTimeParser(logger=self.logger)

    def run_full_analysis(self, dataframe: pd.DataFrame, options: AnalysisOptions) -> AnalysisResult:
        """
        执行完整分析流水线, 并返回结构化结果。

        流程顺序固定：
        1) 清洗与时间解析
        2) 字段类型决策(数值/分类)
        3) 多维统计计算
        """
        # 先统一数据质量, 再做后续统计, 避免重复在各函数里做防御性处理。
        cleaned_df, parsed_datetime_columns = self.prepare_dataframe(
            dataframe=dataframe,
            datetime_columns=options.datetime_columns,
        )
        # 数值字段优先尊重用户传入偏好；否则自动推断。
        numeric_columns = self.resolve_numeric_columns(
            dataframe=cleaned_df,
            preferred_columns=options.preferred_numeric_columns,
        )
        # 分类字段只在 object/category 中选取, 并排除内部元字段(双下划线)。
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
        # 记录时间粒度“请求值/实际值/判定依据”, 用于报告说明与问题排查。
        overview["time_frequency_requested"] = str(
            time_series_summary.attrs.get(
                "requested_frequency",
                self.normalize_time_frequency(options.time_frequency),
            )
        )
        overview["time_frequency_resolved"] = str(
            time_series_summary.attrs.get(
                "resolved_frequency",
                overview["time_frequency_requested"],
            )
        )
        overview["time_frequency_reason"] = str(
            time_series_summary.attrs.get("frequency_reason", "")
        )

        # 返回一个统一结果对象, 方便上层按需选择消费字段。
        return AnalysisResult(
            dataframe=cleaned_df,
            overview=overview,
            missing_summary=missing_summary,
            numeric_summary=numeric_summary,
            correlation_matrix=correlation_matrix,
            outlier_summary=outlier_summary,
            groupby_summary=groupby_summary,
            time_series_summary=time_series_summary,
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
        # 空输入直接返回空表, 避免后续函数大量 if 判断。
        if dataframe is None or dataframe.empty:
            return pd.DataFrame(), []

        # 深拷贝一份, 避免就地修改调用方传入对象。
        cleaned = dataframe.copy()
        # 删除整行/整列全空的数据块, 降低统计噪声。
        cleaned = cleaned.dropna(axis=0, how="all").dropna(axis=1, how="all")

        # object 列做字符串 trim, 减少 "A" 与 " A " 被误判为不同值。
        for column in cleaned.select_dtypes(include=["object"]).columns:
            cleaned[column] = cleaned[column].map(
                lambda value: value.strip() if isinstance(value, str) else value
            )

        # 时间列决策策略：
        # - 用户显式指定：强制尝试, 解析率阈值放宽到 0(只要有可解析值即可)
        # - 未指定：按字段名关键词猜测, 要求解析率 >= 60%
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
                # 跳过时记录告警, 方便排查字段命名误判或脏数据问题。
                self.logger.warning(
                    "Skip datetime conversion for column %s (parse ratio=%.2f, parsed=%s/%s, strategies=%s)",
                    column,
                    parse_ratio,
                    result.parsed_count,
                    result.total_count,
                    result.strategy_counts,
                )

        # 记录清洗后的关键规模信息, 便于调试链路观察。
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
        1. 有 preferred 且命中字段时, 优先使用命中集合；
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

        仅选择 object/category, 且排除以 `__` 开头的内部元字段。
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
        - memory_mb: pandas 深度内存估算(含对象列内容)
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

        # 兜底为 1, 避免空表场景出现除零错误。
        total_cells = int(dataframe.shape[0] * dataframe.shape[1]) or 1
        missing_cells = int(dataframe.isna().sum().sum())
        duplicate_rows = int(dataframe.duplicated().sum())
        memory_mb = float(dataframe.memory_usage(index=True, deep=True).sum() / (1024**2))

        # 若上游合并数据时注入了来源元字段, 这里额外统计来源覆盖情况。
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
        """按列统计缺失数量和缺失率, 并按缺失数量降序输出。"""
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
        输出指标包含：
        - count/min/max/mean/std(来自 describe)
        - q1/median/q3(四分位)
        - missing_count/missing_ratio
        - iqr(四分位距)
        - cv(变异系数 = std / mean, mean=0 时置为 NaN)
        """
        columns = ["column", "count", "missing_count",
                   "missing_ratio", "mean", "std", "min",
                   "q1", "median", "q3", "max", "iqr", "cv"]
        valid_columns = [column for column in numeric_columns if column in dataframe.columns]
        if not valid_columns:
            return pd.DataFrame(columns=columns)

        # 统一转 numeric：非法值强制为 NaN, 确保统计过程不抛错。
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
        仅当有效数值字段 >= 2 时才有意义, 否则返回空表。
        """
        valid_columns = [column for column in numeric_columns if column in dataframe.columns]
        if len(valid_columns) < 2:
            return pd.DataFrame()
        corr = dataframe[valid_columns].corr(method="pearson", numeric_only=True)
        # 去掉全空行列, 避免输出中出现无信息矩阵边缘。
        corr = corr.dropna(axis=0, how="all").dropna(axis=1, how="all")
        return corr

    @staticmethod
    def detect_outliers_iqr(
        dataframe: pd.DataFrame,
        numeric_columns: Sequence[str],
    ) -> pd.DataFrame:
        """
        使用 IQR 规则检测异常值。判定阈值：
        - lower = Q1 - 1.5 * IQR
        - upper = Q3 + 1.5 * IQR
        """
        columns = ["column", "lower_bound", "upper_bound", "outlier_count", "outlier_ratio"]
        rows: List[Dict[str, Any]] = []
        for column in numeric_columns:
            if column not in dataframe.columns:
                continue
            series = pd.to_numeric(dataframe[column], errors="coerce").dropna()
            # 样本太少(<4)时四分位统计稳定性较差, 直接跳过。
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
        - 每个数值字段(最多前 15 个)的均值与中位数
        """
        valid_groupby = [column for column in groupby_columns if column in dataframe.columns]
        if dataframe.empty or not valid_groupby:
            return pd.DataFrame()

        # dropna=False 保留分组维度为空的记录, 避免样本被静默丢失。
        grouped = dataframe.groupby(valid_groupby, dropna=False)
        result = grouped.size().rename("row_count").to_frame()
        # 列数做上限限制, 防止宽表下聚合输出爆炸。
        for column in numeric_columns[:15]:
            if column not in dataframe.columns:
                continue
            result[f"{column}__mean"] = grouped[column].mean()
            result[f"{column}__median"] = grouped[column].median()
        result = result.reset_index().sort_values(by="row_count", ascending=False).reset_index(drop=True)
        return result

    @staticmethod
    def normalize_time_frequency(frequency: str | None) -> str:
        """规范化时间频率字符串(大小写、空值)。"""
        normalized = str(frequency or "auto").strip().upper()
        return normalized or "AUTO"

    @staticmethod
    def to_pandas_frequency(frequency: str) -> str:
        """
        把业务侧频率标识转换为 pandas 频率字符串。

        说明：
        - pandas 新版本建议使用小写 `h`, 这里做兼容映射；
        - 其他频率保持原值, 交给 pandas 自身校验。
        """
        normalized = DataAnalyzer.normalize_time_frequency(frequency)
        if normalized == "H":
            return "h"
        return normalized

    @staticmethod
    def has_subdaily_information(datetime_series: pd.Series) -> bool:
        """判断时间序列里是否存在小时级及以下的信息。"""
        series = datetime_series.dropna()
        if series.empty:
            return False
        # 只要有任意一条记录带有非 00:00:00 的时间信息, 就认为具备小时粒度意义。
        return bool(
            (
                (series.dt.hour != 0)
                | (series.dt.minute != 0)
                | (series.dt.second != 0)
                | (series.dt.microsecond != 0)
                | (series.dt.nanosecond != 0)
            ).any()
        )

    @staticmethod
    def build_frequency_metrics(datetime_series: pd.Series, frequency: str) -> Dict[str, float]:
        """
        计算候选频率的关键指标。

        指标解释：
        - non_empty_bins: 实际出现数据的桶数量
        - total_bins: 覆盖时间范围内理论桶数量
        - occupancy: 非空桶占比
        - points_per_bin: 单桶平均样本量(信息密度)
        """
        series = datetime_series.dropna().sort_values()
        if series.empty:
            return {
                "non_empty_bins": 0.0,
                "total_bins": 0.0,
                "occupancy": 0.0,
                "points_per_bin": 0.0,
            }
        pandas_frequency = DataAnalyzer.to_pandas_frequency(frequency)
        period_index = series.dt.to_period(pandas_frequency)
        non_empty_bins = int(period_index.nunique())
        start_period = period_index.min()
        end_period = period_index.max()
        total_bins = (
            int(len(pd.period_range(start=start_period, end=end_period, freq=pandas_frequency)))
            if non_empty_bins > 0
            else 0
        )
        occupancy = non_empty_bins / max(total_bins, 1)
        points_per_bin = len(series) / max(non_empty_bins, 1)
        return {
            "non_empty_bins": float(non_empty_bins),
            "total_bins": float(total_bins),
            "occupancy": float(occupancy),
            "points_per_bin": float(points_per_bin),
        }

    @staticmethod
    def score_frequency_candidate(
        *,
        metrics: Dict[str, float],
        min_bins: int,
        max_bins: int,
        occupancy_target: float,
        density_target: float,
    ) -> float:
        """根据时间跨度覆盖与信息密度综合给候选频率打分。"""
        non_empty_bins = float(metrics.get("non_empty_bins", 0.0))
        occupancy = float(metrics.get("occupancy", 0.0))
        points_per_bin = float(metrics.get("points_per_bin", 0.0))

        # bin_score 追求“点数适中”：太少看不出趋势, 太多噪声大且可读性差。
        if non_empty_bins <= 0:
            bin_score = 0.0
        elif non_empty_bins < min_bins:
            bin_score = non_empty_bins / float(max(min_bins, 1))
        elif non_empty_bins <= max_bins:
            bin_score = 1.0
        else:
            bin_score = max(0.0, max_bins / non_empty_bins)

        # occupancy_score 衡量时间跨度覆盖率；density_score 衡量每个桶的信息量。
        occupancy_score = min(1.0, occupancy / max(occupancy_target, 1e-6))
        density_score = min(1.0, points_per_bin / max(density_target, 1e-6))
        return 0.5 * bin_score + 0.3 * occupancy_score + 0.2 * density_score

    @staticmethod
    def format_frequency_metrics(metrics: Dict[str, float]) -> str:
        """把频率指标压缩为可读字符串, 便于记录到日志和摘要里。"""
        return (
            f"bins={int(metrics.get('non_empty_bins', 0.0))}/{int(metrics.get('total_bins', 0.0))}, "
            f"occupancy={float(metrics.get('occupancy', 0.0)):.2%}, "
            f"density={float(metrics.get('points_per_bin', 0.0)):.2f}"
        )

    def resolve_time_frequency(
        self,
        datetime_series: pd.Series,
        requested_frequency: str | None,
    ) -> Tuple[str, str]:
        """
        解析最终时间频率。

        规则：
        - 手动指定 H/D/W/M 时直接使用；
        - AUTO 模式下, 仅在 H 与 D 间选择；
        - 选择依据综合考虑时间跨度、桶覆盖率、样本密度与时间精度。
        """
        requested = self.normalize_time_frequency(requested_frequency)
        manual_supported = {"H", "D", "W", "M"}
        if requested in manual_supported:
            return requested, f"manual:{requested}"
        if requested != "AUTO":
            self.logger.warning(
                "Unsupported time_frequency=%s. Fallback to AUTO strategy (H/D).",
                requested,
            )

        series = datetime_series.dropna().sort_values()
        if series.empty:
            return "D", "auto:no_valid_datetime_value"

        span_hours = float((series.max() - series.min()).total_seconds() / 3600.0)
        has_subdaily = self.has_subdaily_information(series)
        h_metrics = self.build_frequency_metrics(series, frequency="H")
        d_metrics = self.build_frequency_metrics(series, frequency="D")
        h_info = self.format_frequency_metrics(h_metrics)
        d_info = self.format_frequency_metrics(d_metrics)

        # 没有小时信息时, 小时粒度只会产生伪细化, 直接回退到天粒度。
        if not has_subdaily:
            return (
                "D",
                f"auto:no_subdaily_info, span_hours={span_hours:.2f}, H[{h_info}], D[{d_info}]",
            )

        # 短跨度且小时桶有足够覆盖时, 优先保留小时级变化。
        if span_hours <= 48.0 and h_metrics["non_empty_bins"] >= 3 and h_metrics["occupancy"] >= 0.10:
            return (
                "H",
                f"auto:short_span_dense_hourly, span_hours={span_hours:.2f}, H[{h_info}], D[{d_info}]",
            )

        # 长跨度下若小时桶过于稀疏, 优先按天聚合, 减少噪声和空档。
        if h_metrics["total_bins"] >= 24.0 * 45.0 and h_metrics["occupancy"] < 0.05:
            return (
                "D",
                f"auto:long_span_sparse_hourly, span_hours={span_hours:.2f}, H[{h_info}], D[{d_info}]",
            )

        h_score = self.score_frequency_candidate(
            metrics=h_metrics,
            min_bins=6,
            max_bins=240,
            occupancy_target=0.20,
            density_target=2.0,
        )
        d_score = self.score_frequency_candidate(metrics=d_metrics, min_bins=4, max_bins=120,
                                                 occupancy_target=0.30, density_target=3.0)

        # 分数接近时, 若小时粒度至少有 2 个有效桶, 倾向保留更细粒度信息。
        if abs(h_score - d_score) < 0.03 and h_metrics["non_empty_bins"] >= 2:
            resolved = "H"
        else:
            resolved = "H" if h_score >= d_score else "D"
        reason = (
            f"auto:score(H={h_score:.3f}, D={d_score:.3f}), span_hours={span_hours:.2f}, "
            f"H[{h_info}], D[{d_info}]"
        )
        return resolved, reason

    def time_series_summary(
        self,
        dataframe: pd.DataFrame,
        datetime_columns: Sequence[str],
        numeric_columns: Sequence[str],
        frequency: str = "auto",
    ) -> pd.DataFrame:
        """
        按时间粒度汇总行数、数值均值与标准差。

        规则：
        - 仅使用第一个可用且 dtype 为 datetime 的时间列；
        - frequency=auto 时, 会在 H 与 D 间自动选择；
        - 生成 `time_period` 作为聚合键；
        - 每个数值字段最多聚合前 10 个, 控制输出体积。
        """
        requested_frequency = self.normalize_time_frequency(frequency)

        # 统一封装空结果, 确保调用方也能拿到频率解析元信息。
        def empty_summary(reason: str, resolved_frequency: str = "D", datetime_column_name: str = "") -> pd.DataFrame:
            empty = pd.DataFrame()
            empty.attrs["datetime_column"] = datetime_column_name
            empty.attrs["requested_frequency"] = requested_frequency
            empty.attrs["resolved_frequency"] = resolved_frequency
            empty.attrs["frequency_reason"] = reason
            return empty

        if dataframe.empty:
            return empty_summary(reason="empty_dataframe", resolved_frequency=requested_frequency)
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
            return empty_summary(reason="no_datetime_column")

        frame = dataframe.copy()
        # 时间为空的记录无法参与时序聚合, 先过滤。
        frame = frame.dropna(subset=[datetime_column])
        if frame.empty:
            return empty_summary(reason="all_datetime_null", datetime_column_name=datetime_column)

        resolved_frequency, frequency_reason = self.resolve_time_frequency(
            datetime_series=frame[datetime_column],
            requested_frequency=requested_frequency,
        )
        self.logger.info(
            "Resolved time frequency: requested=%s, resolved=%s, reason=%s",
            requested_frequency,
            resolved_frequency,
            frequency_reason,
        )

        # to_period(frequency) 先落到周期, 再转 timestamp 便于下游可视化与导出。
        pandas_frequency = self.to_pandas_frequency(resolved_frequency)
        try:
            frame["time_period"] = frame[datetime_column].dt.to_period(pandas_frequency).dt.to_timestamp()
        except Exception as exc:
            self.logger.warning(
                "Failed to apply frequency=%s (%s), fallback to D.",
                resolved_frequency,
                exc,
            )
            resolved_frequency = "D"
            frequency_reason = (
                f"{frequency_reason}; fallback_to_D_due_to_error={type(exc).__name__}"
            )
            frame["time_period"] = frame[datetime_column].dt.to_period("D").dt.to_timestamp()
        grouped = frame.groupby("time_period")

        result = grouped.size().rename("row_count").to_frame()
        for column in numeric_columns[:10]:
            if column not in frame.columns:
                continue
            result[f"{column}__mean"] = grouped[column].mean()
            result[f"{column}__std"] = grouped[column].std()
        result = result.reset_index().sort_values(by="time_period").reset_index(drop=True)
        result.insert(0, "datetime_column", datetime_column)
        result.attrs["datetime_column"] = datetime_column
        result.attrs["requested_frequency"] = requested_frequency
        result.attrs["resolved_frequency"] = resolved_frequency
        result.attrs["frequency_reason"] = frequency_reason
        return result
