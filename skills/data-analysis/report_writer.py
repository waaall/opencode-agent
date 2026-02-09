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
        self.write_dataframe(result.categorical_summary, "categorical_summary.csv")
        self.write_dataframe(result.correlation_matrix, "correlation_matrix.csv")
        self.write_dataframe(result.outlier_summary, "outlier_summary.csv")
        self.write_dataframe(result.groupby_summary, "groupby_summary.csv")
        self.write_dataframe(result.time_series_summary, "time_series_summary.csv")

        self.write_markdown(result.markdown_summary, "summary.md")

        report_meta = {
            "overview": result.overview,
            "files": {
                "processed_data": "processed_data.csv",
                "missing_summary": "missing_summary.csv",
                "numeric_summary": "numeric_summary.csv",
                "categorical_summary": "categorical_summary.csv",
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

    @staticmethod
    def _json_default(value: Any) -> Any:
        if isinstance(value, (np.integer, np.floating)):
            return value.item()
        if isinstance(value, (pd.Timestamp, pd.Timedelta)):
            return str(value)
        return str(value)
