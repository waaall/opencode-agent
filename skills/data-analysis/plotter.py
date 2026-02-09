from __future__ import annotations

import logging
import math
import os
from pathlib import Path
import tempfile
from typing import List, Sequence

MPL_CACHE_DIR = Path(tempfile.gettempdir()) / "data-analysis-mplconfig"
MPL_CACHE_DIR.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("MPLCONFIGDIR", str(MPL_CACHE_DIR))
GENERIC_CACHE_DIR = Path(tempfile.gettempdir()) / "data-analysis-cache"
GENERIC_CACHE_DIR.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("XDG_CACHE_HOME", str(GENERIC_CACHE_DIR))

import matplotlib
import numpy as np
import pandas as pd

from analyzer import AnalysisResult

matplotlib.use("Agg")
import matplotlib.pyplot as plt


class DataPlotter:
    """Generate matplotlib charts from analysis results."""

    def __init__(self, output_dir: str | Path, logger: logging.Logger | None = None) -> None:
        self.logger = logger or logging.getLogger("data-analysis")
        self.output_dir = Path(output_dir).expanduser().resolve()
        self.plot_dir = self.output_dir / "plots"
        self.plot_dir.mkdir(parents=True, exist_ok=True)
        plt.style.use("ggplot")

    def generate_all_plots(
        self,
        result: AnalysisResult,
        max_numeric_plots: int = 8,
        max_category_plots: int = 4,
        categorical_top_n: int = 10,
    ) -> List[str]:
        generated: List[str] = []
        generated.extend(
            self._optional(
                self._safe_plot("missing_values", self.plot_missing_values, result.missing_summary)
            )
        )
        generated.extend(
            self._optional(
                self._safe_plot(
                    "numeric_histograms",
                    self.plot_numeric_histograms,
                    dataframe=result.dataframe,
                    numeric_columns=result.overview.get("numeric_columns", []),
                    max_columns=max_numeric_plots,
                )
            )
        )
        generated.extend(
            self._optional(
                self._safe_plot(
                    "numeric_boxplot",
                    self.plot_numeric_boxplot,
                    dataframe=result.dataframe,
                    numeric_columns=result.overview.get("numeric_columns", []),
                    max_columns=max_numeric_plots,
                )
            )
        )
        generated.extend(
            self._optional(
                self._safe_plot(
                    "correlation_heatmap",
                    self.plot_correlation_heatmap,
                    result.correlation_matrix,
                )
            )
        )
        generated.extend(
            self._safe_plot(
                "category_top_charts",
                self.plot_category_top_charts,
                dataframe=result.dataframe,
                categorical_columns=result.overview.get("categorical_columns", []),
                max_columns=max_category_plots,
                top_n=categorical_top_n,
                default_value=[],
            )
        )
        generated.extend(
            self._optional(
                self._safe_plot("time_trend", self.plot_time_trend, result.time_series_summary)
            )
        )
        return generated

    def plot_missing_values(self, missing_summary: pd.DataFrame) -> str | None:
        if missing_summary.empty:
            return None
        focus = missing_summary[missing_summary["missing_count"] > 0].head(20)
        if focus.empty:
            return None
        fig, ax = plt.subplots(figsize=(10, max(4, 0.45 * len(focus))))
        ax.barh(focus["column"], focus["missing_ratio"] * 100, color="#d9534f")
        ax.set_xlabel("Missing Ratio (%)")
        ax.set_title("Top Missing Columns")
        fig.tight_layout()
        return self._save_figure(fig, "missing_values_top20.png")

    def plot_numeric_histograms(
        self,
        dataframe: pd.DataFrame,
        numeric_columns: Sequence[str],
        max_columns: int = 8,
    ) -> str | None:
        columns = [column for column in numeric_columns if column in dataframe.columns][:max(max_columns, 1)]
        if not columns:
            return None

        n_cols = 2
        n_rows = math.ceil(len(columns) / n_cols)
        fig, axes = plt.subplots(n_rows, n_cols, figsize=(14, max(4, n_rows * 3.5)))
        axes = np.atleast_1d(axes).reshape(n_rows, n_cols)

        for idx, column in enumerate(columns):
            row, col = divmod(idx, n_cols)
            ax = axes[row, col]
            series = pd.to_numeric(dataframe[column], errors="coerce").dropna()
            if series.empty:
                ax.text(0.5, 0.5, "No numeric data", ha="center", va="center")
            else:
                ax.hist(series, bins=30, color="#337ab7", alpha=0.85, edgecolor="white")
            ax.set_title(column)
            ax.set_xlabel("Value")
            ax.set_ylabel("Count")

        total_axes = n_rows * n_cols
        for idx in range(len(columns), total_axes):
            row, col = divmod(idx, n_cols)
            axes[row, col].axis("off")

        fig.suptitle("Numeric Distribution Histograms", fontsize=14)
        fig.tight_layout()
        return self._save_figure(fig, "numeric_histograms.png")

    def plot_numeric_boxplot(
        self,
        dataframe: pd.DataFrame,
        numeric_columns: Sequence[str],
        max_columns: int = 8,
    ) -> str | None:
        columns = [column for column in numeric_columns if column in dataframe.columns][:max(max_columns, 1)]
        if not columns:
            return None
        plot_frame = dataframe[columns].apply(pd.to_numeric, errors="coerce")
        if plot_frame.dropna(how="all").empty:
            return None

        fig, ax = plt.subplots(figsize=(14, max(5, 0.8 * len(columns))))
        plot_frame.boxplot(ax=ax, vert=False)
        ax.set_title("Numeric Boxplot")
        ax.set_xlabel("Value")
        fig.tight_layout()
        return self._save_figure(fig, "numeric_boxplot.png")

    def plot_correlation_heatmap(self, correlation_matrix: pd.DataFrame) -> str | None:
        if correlation_matrix.empty:
            return None
        matrix = correlation_matrix.copy()
        size = len(matrix.columns)
        fig, ax = plt.subplots(figsize=(max(6, 1.2 * size), max(5, 1.0 * size)))
        image = ax.imshow(matrix.values, cmap="coolwarm", vmin=-1, vmax=1)
        ax.set_xticks(range(size))
        ax.set_yticks(range(size))
        ax.set_xticklabels(matrix.columns, rotation=45, ha="right")
        ax.set_yticklabels(matrix.index)
        ax.set_title("Correlation Heatmap (Pearson)")
        if size <= 12:
            for i in range(size):
                for j in range(size):
                    value = matrix.iloc[i, j]
                    if pd.notna(value):
                        ax.text(j, i, f"{value:.2f}", ha="center", va="center", fontsize=8, color="black")
        fig.colorbar(image, ax=ax, fraction=0.045, pad=0.04)
        fig.tight_layout()
        return self._save_figure(fig, "correlation_heatmap.png")

    def plot_category_top_charts(
        self,
        dataframe: pd.DataFrame,
        categorical_columns: Sequence[str],
        max_columns: int = 4,
        top_n: int = 10,
    ) -> List[str]:
        generated: List[str] = []
        selected = [column for column in categorical_columns if column in dataframe.columns][:max(max_columns, 1)]
        for column in selected:
            series = dataframe[column].dropna()
            if series.empty:
                continue
            counts = series.value_counts().head(max(top_n, 1))
            fig, ax = plt.subplots(figsize=(11, max(4, 0.5 * len(counts))))
            ax.barh(counts.index.astype(str), counts.values, color="#5cb85c")
            ax.set_title(f"Top {len(counts)} Categories - {column}")
            ax.set_xlabel("Count")
            ax.set_ylabel("Category")
            fig.tight_layout()
            filename = f"category_top_{self._sanitize_filename(column)}.png"
            generated.extend(self._optional(self._save_figure(fig, filename)))
        return generated

    def plot_time_trend(self, time_summary: pd.DataFrame) -> str | None:
        if time_summary.empty or "time_period" not in time_summary.columns:
            return None
        frame = time_summary.sort_values(by="time_period")
        fig, ax = plt.subplots(figsize=(12, 5))
        ax.plot(frame["time_period"], frame["row_count"], marker="o", color="#f0ad4e", label="row_count")
        ax.set_xlabel("Time Period")
        ax.set_ylabel("Row Count")
        ax.set_title("Time Trend")

        mean_columns = [column for column in frame.columns if column.endswith("__mean")]
        if mean_columns:
            secondary = ax.twinx()
            focus = mean_columns[0]
            secondary.plot(
                frame["time_period"],
                frame[focus],
                marker="s",
                linestyle="--",
                color="#337ab7",
                label=focus,
            )
            secondary.set_ylabel(focus)
            secondary.legend(loc="upper right")
        ax.legend(loc="upper left")
        fig.autofmt_xdate()
        fig.tight_layout()
        return self._save_figure(fig, "time_trend.png")

    @staticmethod
    def _sanitize_filename(name: str) -> str:
        text = str(name).strip().replace(" ", "_")
        return "".join(ch for ch in text if ch.isalnum() or ch in ("_", "-")).strip("_")[:60] or "column"

    @staticmethod
    def _optional(path_value: str | None) -> List[str]:
        return [path_value] if path_value else []

    def _safe_plot(self, name: str, plot_func, *args, default_value=None, **kwargs):
        try:
            return plot_func(*args, **kwargs)
        except Exception as exc:  # pylint: disable=broad-except
            self.logger.error("Skip plot %s because of error: %s", name, exc)
            return default_value

    def _save_figure(self, fig: plt.Figure, filename: str) -> str:
        output_path = self.plot_dir / filename
        fig.savefig(output_path, dpi=150, bbox_inches="tight")
        plt.close(fig)
        self.logger.info("Saved chart: %s", output_path)
        return str(output_path)
