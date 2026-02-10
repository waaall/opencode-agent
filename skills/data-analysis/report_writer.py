from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, Sequence

import numpy as np
import pandas as pd

from analyzer import AnalysisResult


class ReportWriter:
    """Persist analysis outputs to files with a consistent structure."""

    def __init__(self, output_dir: str | Path, logger: logging.Logger | None = None) -> None:
        self.logger = logger or logging.getLogger("data-analysis")
        self.output_dir = Path(output_dir).expanduser().resolve()
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def write_full_report(self, result: AnalysisResult, chart_files: Sequence[str]) -> None:
        self.write_dataframe(result.dataframe, "processed_data.csv")
        self.write_dataframe(result.missing_summary, "missing_summary.csv")
        self.write_dataframe(result.numeric_summary, "numeric_summary.csv")
        self.write_dataframe(result.correlation_matrix, "correlation_matrix.csv")
        self.write_dataframe(result.outlier_summary, "outlier_summary.csv")
        self.write_dataframe(result.groupby_summary, "groupby_summary.csv")
        self.write_dataframe(result.time_series_summary, "time_series_summary.csv")

        markdown_summary = self.build_markdown_summary(
            overview=result.overview,
            missing_summary=result.missing_summary,
            numeric_summary=result.numeric_summary,
            outlier_summary=result.outlier_summary,
            correlation_matrix=result.correlation_matrix,
            groupby_summary=result.groupby_summary,
            time_series_summary=result.time_series_summary,
            chart_files=chart_files,
        )
        self.write_markdown(markdown_summary, "summary.md")

        report_meta = {
            "overview": result.overview,
            "files": {
                "processed_data": "processed_data.csv",
                "missing_summary": "missing_summary.csv",
                "numeric_summary": "numeric_summary.csv",
                "correlation_matrix": "correlation_matrix.csv",
                "outlier_summary": "outlier_summary.csv",
                "groupby_summary": "groupby_summary.csv",
                "time_series_summary": "time_series_summary.csv",
                "summary_markdown": "summary.md",
            },
            "generated_charts": list(chart_files),
        }
        self.write_json(report_meta, "analysis_bundle.json")

    def write_dataframe(self, dataframe: pd.DataFrame, filename: str) -> str:
        output_path = self.output_dir / filename
        if dataframe is None:
            dataframe = pd.DataFrame()
        dataframe.to_csv(output_path, index=False, encoding="utf-8-sig")
        self.logger.info("Saved CSV: %s", output_path)
        return str(output_path)

    def write_json(self, payload: Dict[str, Any], filename: str) -> str:
        output_path = self.output_dir / filename
        with output_path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, ensure_ascii=False, default=self._json_default)
        self.logger.info("Saved JSON: %s", output_path)
        return str(output_path)

    def write_markdown(self, content: str, filename: str) -> str:
        output_path = self.output_dir / filename
        with output_path.open("w", encoding="utf-8") as handle:
            handle.write(content or "")
        self.logger.info("Saved markdown: %s", output_path)
        return str(output_path)

    def build_markdown_summary(
        self,
        overview: Dict[str, Any],
        missing_summary: pd.DataFrame,
        numeric_summary: pd.DataFrame,
        outlier_summary: pd.DataFrame,
        correlation_matrix: pd.DataFrame,
        groupby_summary: pd.DataFrame,
        time_series_summary: pd.DataFrame,
        chart_files: Sequence[str],
    ) -> str:
        """
        生成面向阅读的 Markdown 摘要。

        仅保留图表章节，避免在摘要里重复 CSV 已有统计信息。
        """
        # 保留方法签名兼容上层调用；当前仅使用图表信息生成摘要。
        _ = overview, missing_summary, numeric_summary, outlier_summary, correlation_matrix, groupby_summary, time_series_summary
        lines = ["# 数据分析总结"]

        chart_paths = self._resolve_markdown_chart_paths(chart_files)
        if chart_paths:
            chart_groups = self._group_chart_paths_by_category(chart_paths)
            for category, paths in chart_groups:
                lines.extend(["", f"## {category}"])
                for path in paths:
                    filename = Path(path).name
                    lines.append(f"- [{filename}](<{path}>)")
                    lines.append(f"![{filename}](<{path}>)")
        else:
            lines.extend(["", "## 图表分析", "- 未生成可展示的图表。"])
        return "\n".join(lines) + "\n"

    @staticmethod
    def find_strongest_correlation_pair(correlation_matrix: pd.DataFrame) -> tuple[str, str, float] | None:
        """
        在相关矩阵中找到绝对值最大的非对角相关系数对。

        返回 (列A, 列B, 系数)；若矩阵无效则返回 None。
        """
        if correlation_matrix.empty or len(correlation_matrix.columns) < 2:
            return None
        best_pair: tuple[str, str, float] | None = None
        columns = list(correlation_matrix.columns)
        for i in range(len(columns)):
            for j in range(i + 1, len(columns)):
                value = correlation_matrix.iloc[i, j]
                if pd.isna(value):
                    continue
                if best_pair is None or abs(value) > abs(best_pair[2]):
                    best_pair = (columns[i], columns[j], float(value))
        return best_pair

    def _resolve_markdown_chart_paths(self, chart_files: Sequence[str]) -> list[str]:
        """将图表路径标准化为 markdown 可用路径，优先使用相对 output_dir 的路径。"""
        resolved: list[str] = []
        for item in chart_files:
            chart_path = Path(item).expanduser().resolve()
            try:
                path_for_markdown = chart_path.relative_to(self.output_dir).as_posix()
            except ValueError:
                path_for_markdown = chart_path.as_posix()
            resolved.append(path_for_markdown)
        return resolved

    @staticmethod
    def _group_chart_paths_by_category(chart_paths: Sequence[str]) -> list[tuple[str, list[str]]]:
        """按图表文件名将图片分组，便于在 markdown 中分节展示。"""
        groups: dict[str, list[str]] = {
            "缺失值分析": [],
            "数值分布分析": [],
            "相关性分析": [],
            "时间序列分析": [],
            "其他图表": [],
        }
        for path in chart_paths:
            filename = Path(path).name.lower()
            if filename.startswith("missing_values"):
                groups["缺失值分析"].append(path)
            elif filename.startswith("numeric_histograms") or filename.startswith("numeric_boxplot"):
                groups["数值分布分析"].append(path)
            elif filename.startswith("correlation_heatmap"):
                groups["相关性分析"].append(path)
            elif filename.startswith("time_trend"):
                groups["时间序列分析"].append(path)
            else:
                groups["其他图表"].append(path)

        ordered_groups: list[tuple[str, list[str]]] = []
        for name in ["缺失值分析", "数值分布分析", "相关性分析", "时间序列分析", "其他图表"]:
            paths = groups[name]
            if paths:
                ordered_groups.append((name, paths))
        return ordered_groups

    @staticmethod
    def _json_default(value: Any) -> Any:
        if isinstance(value, (np.integer, np.floating)):
            return value.item()
        if isinstance(value, (pd.Timestamp, pd.Timedelta)):
            return str(value)
        return str(value)
