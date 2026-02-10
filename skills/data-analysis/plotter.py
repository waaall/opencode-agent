"""
数据分析绘图模块（matplotlib 版）

职责：
1. 读取 `AnalysisResult` 中的结构化统计结果，生成可落盘 PNG 图表。
2. 对每类图做空数据保护，避免单个图失败影响整批输出。
3. 在无图形界面环境（CI、服务端）下稳定运行。
"""

from __future__ import annotations

import logging
import math
import os
from pathlib import Path
import tempfile
from typing import List, Sequence

# 将 matplotlib 缓存目录重定向到系统临时目录，避免在受限环境写入用户目录失败。
MPL_CACHE_DIR = Path(tempfile.gettempdir()) / "data-analysis-mplconfig"
MPL_CACHE_DIR.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("MPLCONFIGDIR", str(MPL_CACHE_DIR))

# 一些底层依赖会参考 XDG_CACHE_HOME，这里一并重定向。
GENERIC_CACHE_DIR = Path(tempfile.gettempdir()) / "data-analysis-cache"
GENERIC_CACHE_DIR.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("XDG_CACHE_HOME", str(GENERIC_CACHE_DIR))

import matplotlib
import numpy as np
import pandas as pd
from matplotlib import font_manager

from analyzer import AnalysisResult

# 使用无 GUI 的 Agg 后端，确保在服务器/容器中可绘图。
matplotlib.use("Agg")
import matplotlib.pyplot as plt


class DataPlotter:
    """把分析结果转换为图表文件。"""

    CJK_FONT_CANDIDATES = (
        "PingFang SC",
        "Hiragino Sans GB",
        "STHeiti",
        "Songti SC",
        "Microsoft YaHei",
        "SimHei",
        "Noto Sans CJK SC",
        "Source Han Sans CN",
        "WenQuanYi Zen Hei",
        "Arial Unicode MS",
    )

    def __init__(self, output_dir: str | Path, logger: logging.Logger | None = None) -> None:
        # logger 用于记录每张图的成功/失败；默认复用 data-analysis 命名空间。
        self.logger = logger or logging.getLogger("data-analysis")
        # 统一输出根目录，并在其下创建 plots 子目录。
        self.output_dir = Path(output_dir).expanduser().resolve()
        self.plot_dir = self.output_dir / "plots"
        self.plot_dir.mkdir(parents=True, exist_ok=True)
        # 全局样式选择 ggplot，保证图表风格一致。
        plt.style.use("ggplot")
        self._configure_fonts()

    def _configure_fonts(self) -> None:
        """
        配置中文字体回退，避免标题/标签中的中文显示为方块。

        说明：
        - 优先使用系统中存在的中文字体，按候选顺序回退；
        - 关闭坐标轴负号 unicode 渲染问题（某些中文字体不含该字符）。
        """
        available_fonts = {font.name for font in font_manager.fontManager.ttflist}
        selected_fonts = [font for font in self.CJK_FONT_CANDIDATES if font in available_fonts]
        plt.rcParams["font.family"] = "sans-serif"
        plt.rcParams["font.sans-serif"] = [*selected_fonts, "DejaVu Sans"]
        plt.rcParams["axes.unicode_minus"] = False
        if selected_fonts:
            self.logger.info("Enabled CJK fonts for matplotlib: %s", ", ".join(selected_fonts))
        else:
            self.logger.warning(
                "No CJK font detected. Chinese text may not render correctly. "
                "Please install one of: %s",
                ", ".join(self.CJK_FONT_CANDIDATES),
            )

    def generate_all_plots(
        self,
        result: AnalysisResult,
        max_numeric_plots: int = 8,
        group_plot_threshold: float = 20.0,
    ) -> List[str]:
        """
        一次性生成所有预设图表，返回已生成文件路径列表。

        说明：
        - 每个绘图步骤都通过 `_safe_plot` 包装，单图失败不会中断整批生成。
        - `_optional` 用于把 `None` 结果统一转成空列表，便于 `extend`。
        """
        generated: List[str] = []

        # 1) 缺失值分布图
        generated.extend(
            self._optional(
                self._safe_plot("missing_values", self.plot_missing_values, result.missing_summary)
            )
        )

        # 2) 数值字段直方图（分布 + 统计标注）
        generated.extend(
            self._optional(
                self._safe_plot(
                    "numeric_histograms",
                    self.plot_numeric_histograms,
                    dataframe=result.dataframe,
                    numeric_columns=result.overview.get("numeric_columns", []),
                    numeric_summary=result.numeric_summary,
                    max_columns=max_numeric_plots,
                )
            )
        )

        # 3) 数值字段箱线图（离散程度与异常点）
        generated.extend(
            self._safe_plot(
                "numeric_boxplot",
                self.plot_numeric_boxplot,
                dataframe=result.dataframe,
                numeric_columns=result.overview.get("numeric_columns", []),
                max_columns=max_numeric_plots,
                mean_group_threshold_pct=group_plot_threshold,
                default_value=[],
            )
        )

        # 4) 相关性热力图
        generated.extend(
            self._optional(
                self._safe_plot(
                    "correlation_heatmap",
                    self.plot_correlation_heatmap,
                    result.correlation_matrix,
                )
            )
        )

        # 5) 时间趋势图
        generated.extend(
            self._safe_plot(
                "time_trend",
                self.plot_time_trend,
                result.time_series_summary,
                mean_group_threshold_pct=group_plot_threshold,
                default_value=[],
            )
        )
        return generated

    def plot_missing_values(self, missing_summary: pd.DataFrame) -> str | None:
        """
        绘制缺失率最高字段的水平条形图（Top 20）。

        输入要求：
        - `missing_summary` 至少包含 `column`、`missing_count`、`missing_ratio` 字段。
        """
        # 没有缺失统计数据时不生成图。
        if missing_summary.empty:
            return None
        # 只关注真实存在缺失值的字段，最多展示 20 个。
        focus = missing_summary[missing_summary["missing_count"] > 0].head(20)
        if focus.empty:
            return None

        # 图高随字段数量线性增大，避免标签挤压。
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
        numeric_summary: pd.DataFrame | None = None,
        max_columns: int = 8,
    ) -> str | None:
        """
        为数值字段绘制直方图网格图，并叠加 numeric_summary 中的统计标注。

        标注内容：
        - mean / median 竖线；
        - q1–q3 四分位区间阴影；
        - 右上角文字：count, std, cv。
        """
        # 只保留存在于 DataFrame 的字段，且至少绘制 1 列（max_columns 下限保护）。
        columns = [column for column in numeric_columns if column in dataframe.columns][:max(max_columns, 1)]
        if not columns:
            return None

        # 将 numeric_summary 转为以 column 名称为 key 的字典，方便逐字段查找。
        stats_lookup: dict[str, dict] = {}
        if numeric_summary is not None and not numeric_summary.empty and "column" in numeric_summary.columns:
            for _, row in numeric_summary.iterrows():
                stats_lookup[row["column"]] = row.to_dict()

        # 固定两列布局，行数按字段数自动上取整。
        n_cols = 2
        n_rows = math.ceil(len(columns) / n_cols)
        fig, axes = plt.subplots(n_rows, n_cols, figsize=(14, max(4, n_rows * 4.0)))

        # 统一把 axes 变成二维数组，兼容 n_rows=1 或 n_cols=1 的情况。
        axes = np.atleast_1d(axes).reshape(n_rows, n_cols)

        for idx, column in enumerate(columns):
            row, col = divmod(idx, n_cols)
            ax = axes[row, col]
            # 非法值转 NaN 后丢弃，避免 hist 报错。
            series = pd.to_numeric(dataframe[column], errors="coerce").dropna()
            if series.empty:
                ax.text(0.5, 0.5, "No numeric data", ha="center", va="center")
                ax.set_title(column)
                ax.set_xlabel("Value")
                ax.set_ylabel("Count")
                continue

            ax.hist(series, bins=30, color="#337ab7", alpha=0.85, edgecolor="white")
            ax.set_title(column)
            ax.set_xlabel("Value")
            ax.set_ylabel("Count")

            # 叠加 numeric_summary 统计标注。
            stats = stats_lookup.get(column)
            if not stats:
                continue

            y_max = ax.get_ylim()[1]

            # mean / median 竖线
            mean_val = stats.get("mean")
            median_val = stats.get("median")
            if pd.notna(mean_val):
                ax.axvline(mean_val, color="#d9534f", linestyle="--", linewidth=1.5, label=f"mean={mean_val:.2f}")
            if pd.notna(median_val):
                ax.axvline(median_val, color="#5cb85c", linestyle="-.", linewidth=1.5, label=f"median={median_val:.2f}")

            # q1–q3 四分位区间阴影
            q1_val = stats.get("q1")
            q3_val = stats.get("q3")
            if pd.notna(q1_val) and pd.notna(q3_val):
                ax.axvspan(q1_val, q3_val, alpha=0.12, color="#f0ad4e", label=f"IQR [{q1_val:.2f}, {q3_val:.2f}]")

            # 右上角统计文字
            text_parts = []
            count_val = stats.get("count")
            if pd.notna(count_val):
                text_parts.append(f"n={int(count_val)}")
            std_val = stats.get("std")
            if pd.notna(std_val):
                text_parts.append(f"std={std_val:.2f}")
            cv_val = stats.get("cv")
            if pd.notna(cv_val):
                text_parts.append(f"cv={cv_val:.2f}")
            if text_parts:
                ax.text(
                    0.97, 0.95, "\n".join(text_parts),
                    transform=ax.transAxes, fontsize=7.5,
                    verticalalignment="top", horizontalalignment="right",
                    bbox=dict(boxstyle="round,pad=0.3", facecolor="white", alpha=0.8, edgecolor="#ccc"),
                )

            ax.legend(fontsize=7, loc="upper left")

        # 若子图总数大于字段数，隐藏多余子图。
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
        mean_group_threshold_pct: float = 15.0,
    ) -> List[str]:
        """
        绘制数值字段箱线图（横向，支持按均值分组拆图）。

        适用场景：
        - 快速查看中位数、四分位区间和潜在异常点分布。
        - 字段数量多且量纲/数值区间差异大时，按均值相近度拆成多张图提高可读性。
        """
        columns = [column for column in numeric_columns if column in dataframe.columns][:max(max_columns, 1)]
        if not columns:
            return []

        # 全列统一转数值，无法转换的值变 NaN。
        plot_frame = dataframe[columns].apply(pd.to_numeric, errors="coerce")
        # 若所有字段都没有有效数值，则不生成图。
        if plot_frame.dropna(how="all").empty:
            return []

        groups = self._group_mean_columns_by_similarity(
            frame=plot_frame,
            mean_columns=columns,
            threshold_pct=mean_group_threshold_pct,
        )
        if not groups:
            return []

        box_palette = [
            "#5B9BD5", "#ED7D31", "#70AD47", "#FFC000",
            "#4472C4", "#A5A5A5", "#FF6F61", "#6B5B95",
        ]

        generated: List[str] = []
        for group_index, group_columns in enumerate(groups, start=1):
            group_frame = plot_frame[group_columns]
            if group_frame.dropna(how="all").empty:
                continue

            fig, ax = plt.subplots(figsize=(14, max(5, 0.8 * len(group_columns))))

            # 准备每列数据（去 NaN），用于手动绘制更精细的箱线图。
            box_data = [
                pd.to_numeric(group_frame[col], errors="coerce").dropna().values
                for col in group_columns
            ]

            bp = ax.boxplot(
                box_data,
                vert=False,
                patch_artist=True,       # 允许填充颜色
                labels=group_columns,
                widths=0.55,
                showmeans=True,
                meanprops=dict(marker="D", markerfacecolor="white", markeredgecolor="#333", markersize=5),
                medianprops=dict(color="#222", linewidth=2),
                whiskerprops=dict(color="#555", linewidth=1.2, linestyle="--"),
                capprops=dict(color="#555", linewidth=1.2),
                flierprops=dict(
                    marker="o", markerfacecolor="#d9534f", markeredgecolor="white",
                    markersize=5, alpha=0.7,
                ),
            )

            # 逐箱体着色，半透明填充 + 深色边框。
            for patch_idx, patch in enumerate(bp["boxes"]):
                color = box_palette[patch_idx % len(box_palette)]
                patch.set_facecolor(color)
                patch.set_alpha(0.45)
                patch.set_edgecolor(color)
                patch.set_linewidth(1.5)

            ax.grid(axis="x", linestyle=":", alpha=0.5)
            group_total = len(groups)
            threshold_text = max(0.0, float(mean_group_threshold_pct))
            ax.set_title(
                f"Numeric Boxplot Group {group_index}/{group_total} "
                f"(threshold={threshold_text:.1f}%)",
                fontsize=13, fontweight="bold",
            )
            ax.set_xlabel("Value")
            fig.tight_layout()
            filename = (
                "numeric_boxplot.png"
                if group_total == 1
                else f"numeric_boxplot_group_{group_index:02d}.png"
            )
            generated.append(self._save_figure(fig, filename))
        return generated

    def plot_correlation_heatmap(self, correlation_matrix: pd.DataFrame) -> str | None:
        """
        绘制相关系数热力图。

        约定：
        - 色阶固定在 [-1, 1]，保证不同数据集图可直接比较。
        - 当字段数 <= 12 时，在格子内标注系数数值。
        """
        if correlation_matrix.empty:
            return None
        matrix = correlation_matrix.copy()
        size = len(matrix.columns)

        # 字段越多画布越大，减少标签重叠。
        fig, ax = plt.subplots(figsize=(max(6, 1.2 * size), max(5, 1.0 * size)))
        image = ax.imshow(matrix.values, cmap="coolwarm", vmin=-1, vmax=1)
        ax.set_xticks(range(size))
        ax.set_yticks(range(size))
        ax.set_xticklabels(matrix.columns, rotation=45, ha="right")
        ax.set_yticklabels(matrix.index)
        ax.set_title("Correlation Heatmap (Pearson)")

        # 小矩阵可直接标注数值；大矩阵只保留颜色信息避免图面过密。
        if size <= 12:
            for i in range(size):
                for j in range(size):
                    value = matrix.iloc[i, j]
                    if pd.notna(value):
                        ax.text(j, i, f"{value:.2f}", ha="center", va="center", fontsize=8, color="black")
        fig.colorbar(image, ax=ax, fraction=0.045, pad=0.04)
        fig.tight_layout()
        return self._save_figure(fig, "correlation_heatmap.png")

    def plot_time_trend(
        self,
        time_summary: pd.DataFrame,
        mean_group_threshold_pct: float = 15.0,
    ) -> List[str]:
        """
        - 按均值相近程度把 `__mean` 字段分组，组间拆分成多张图；
        - 同一组内每条均值曲线叠加其标准差区间（`mean ± std` 浅色带）；
        - 若所有均值都接近，仅输出一张图；
        - 不绘制 `row_count`。
        """
        # 缺少时间粒度列时无法绘制趋势。
        if time_summary.empty or "time_period" not in time_summary.columns:
            return []

        # 按时间排序，确保折线连接顺序正确。
        frame = time_summary.sort_values(by="time_period")
        mean_columns = [column for column in frame.columns if column.endswith("__mean")]
        if not mean_columns:
            return []

        groups = self._group_mean_columns_by_similarity(
            frame=frame,
            mean_columns=mean_columns,
            threshold_pct=mean_group_threshold_pct,
        )
        if not groups:
            return []

        generated: List[str] = []
        color_cycle = plt.rcParams["axes.prop_cycle"].by_key().get(
            "color",
            ["#337ab7", "#d9534f", "#5cb85c", "#f0ad4e", "#5bc0de"],
        )

        for group_index, columns in enumerate(groups, start=1):
            fig, ax = plt.subplots(figsize=(12, 5))

            for index, mean_column in enumerate(columns):
                mean_values = pd.to_numeric(frame[mean_column], errors="coerce")
                if mean_values.dropna().empty:
                    continue
                color = color_cycle[index % len(color_cycle)]
                metric_name = mean_column[: -len("__mean")]

                ax.plot(
                    frame["time_period"],
                    mean_values,
                    marker="s",
                    linewidth=1.8,
                    color=color,
                    label=f"{metric_name} mean",
                )

                std_column = f"{metric_name}__std"
                if std_column not in frame.columns:
                    continue
                std_values = pd.to_numeric(frame[std_column], errors="coerce")
                std_values = std_values.clip(lower=0)
                if std_values.dropna().empty:
                    continue
                upper_band = mean_values + std_values
                lower_band = mean_values - std_values
                ax.fill_between(
                    frame["time_period"],
                    lower_band,
                    upper_band,
                    color=color,
                    alpha=0.18,
                    linewidth=0.0,
                    label=f"{metric_name} std band",
                )

            group_total = len(groups)
            threshold_text = max(0.0, float(mean_group_threshold_pct))
            ax.set_xlabel("Time Period")
            ax.set_ylabel("Value")
            ax.set_title(
                f"Time Trend (Mean +/- Std) Group {group_index}/{group_total} "
                f"(threshold={threshold_text:.1f}%)"
            )

            handles, labels = ax.get_legend_handles_labels()
            if handles:
                ax.legend(handles, labels, loc="upper left", fontsize=8)

            fig.autofmt_xdate()
            fig.tight_layout()
            filename = "time_trend.png" if group_total == 1 else f"time_trend_group_{group_index:02d}.png"
            generated.append(self._save_figure(fig, filename))
        return generated

    @staticmethod
    def _group_mean_columns_by_similarity(
        frame: pd.DataFrame,
        mean_columns: Sequence[str],
        threshold_pct: float,
    ) -> List[List[str]]:
        """
        依据各字段在全时段的均值水平做分组。

        规则：
        - 相邻字段（按均值排序）与当前组中心的相对误差 <= 阈值时归入同组；
        - 阈值单位为百分比（例如 15 表示 15%）。
        """
        candidates: List[tuple[str, float]] = []
        for column in mean_columns:
            if column not in frame.columns:
                continue
            series = pd.to_numeric(frame[column], errors="coerce")
            if series.dropna().empty:
                continue
            candidates.append((column, float(series.mean())))
        if not candidates:
            return []

        ratio = max(0.0, float(threshold_pct)) / 100.0
        candidates.sort(key=lambda item: item[1])

        groups: List[List[str]] = []
        current_columns: List[str] = [candidates[0][0]]
        current_values: List[float] = [candidates[0][1]]

        for column, value in candidates[1:]:
            center = float(np.mean(current_values))
            if abs(center) < 1e-12 and abs(value) < 1e-12:
                relative_error = 0.0
            else:
                relative_error = abs(value - center) / max(abs(value), abs(center), 1e-12)

            if relative_error <= ratio:
                current_columns.append(column)
                current_values.append(value)
            else:
                groups.append(current_columns)
                current_columns = [column]
                current_values = [value]

        groups.append(current_columns)
        return groups

    @staticmethod
    def _optional(path_value: str | None) -> List[str]:
        """把可选单路径统一转为列表，便于上层 `extend` 拼接。"""
        return [path_value] if path_value else []

    def _safe_plot(self, name: str, plot_func, *args, default_value=None, **kwargs):
        """
        执行单个绘图函数并兜底异常。

        设计目标：
        - 单图失败不影响其他图；
        - 失败时记录日志并返回调用方指定的默认值。
        """
        try:
            return plot_func(*args, **kwargs)
        except Exception as exc:  # pylint: disable=broad-except
            self.logger.error("Skip plot %s because of error: %s", name, exc)
            return default_value

    def _save_figure(self, fig: plt.Figure, filename: str) -> str:
        """统一保存并关闭图对象，返回最终文件绝对路径字符串。"""
        output_path = self.plot_dir / filename
        fig.savefig(output_path, dpi=150, bbox_inches="tight")
        # 及时关闭，避免批量绘图时内存持续上涨。
        plt.close(fig)
        self.logger.info("Saved chart: %s", output_path)
        return str(output_path)
