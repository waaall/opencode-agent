from __future__ import annotations

import logging
import re
import sys
from pathlib import Path
from typing import Any

import pandas as pd

from analyzer import AnalysisOptions, DataAnalyzer
from config import AppConfig
from data_loader import DataLoader
from logger import setup_logger
from plotter import DataPlotter
from report_writer import ReportWriter


def print_console_summary(overview: dict[str, Any], chart_count: int, title: str) -> None:
    print("\n" + "=" * 64)
    print(title)
    print("=" * 64)
    print(f"Rows: {overview.get('rows', 0)}")
    print(f"Columns: {overview.get('columns', 0)}")
    print(
        "Missing Cells: "
        f"{overview.get('missing_cells', 0)} ({overview.get('missing_ratio', 0.0):.2%})"
    )
    print(f"Duplicate Rows: {overview.get('duplicate_rows', 0)}")
    print(f"Numeric Columns: {len(overview.get('numeric_columns', []))}")
    print(f"Categorical Columns: {len(overview.get('categorical_columns', []))}")
    print(f"Datetime Columns: {', '.join(overview.get('datetime_columns', [])) or 'None'}")
    print(f"Charts Generated: {chart_count}")
    print("=" * 64 + "\n")


def sanitize_part(raw_value: str) -> str:
    text = re.sub(r"\s+", "_", str(raw_value).strip())
    text = re.sub(r"[^0-9A-Za-z_-]+", "", text)
    return text[:60] or "unknown"


def dataset_slug(source_file: str, source_sheet: str, index: int) -> str:
    file_part = sanitize_part(Path(source_file).stem)
    sheet_part = sanitize_part(source_sheet)
    return f"{index:03d}_{file_part}__{sheet_part}"


def run_dataset_analysis(
    *,
    dataframe: pd.DataFrame,
    output_dir: str | Path,
    title: str,
    analyzer: DataAnalyzer,
    options: AnalysisOptions,
    config: AppConfig,
    logger: logging.Logger,
) -> None:
    analysis_result = analyzer.run_full_analysis(dataframe, options)

    plotter = DataPlotter(
        output_dir=output_dir,
        logger=logger,
        plot_dpi=config.plot_dpi,
    )
    chart_files = plotter.generate_all_plots(
        result=analysis_result,
        max_numeric_plots=config.max_numeric_plots,
        group_plot_threshold=config.group_plot_threshold,
    )

    writer = ReportWriter(output_dir=output_dir, logger=logger)
    writer.write_full_report(result=analysis_result, chart_files=chart_files)

    print_console_summary(analysis_result.overview, chart_count=len(chart_files), title=title)


def main() -> int:
    config = AppConfig.load()
    logger = setup_logger(config.log_file_path, level=config.log_level)

    logger.info("Starting generic data-analysis pipeline")
    logger.info("Input path: %s", config.input_path)
    logger.info("Output dir: %s", config.output_dir)
    logger.info("Analysis mode: %s", config.analysis_mode)

    loader = DataLoader(logger=logger)
    datasets = loader.load_path(
        input_path=config.input_path,
        recursive=config.recursive,
        sheet_name=config.sheet_name,
    )
    if not datasets:
        logger.error("No dataset loaded. Check input path and file formats.")
        return 1

    analyzer = DataAnalyzer(logger=logger)
    options = AnalysisOptions(
        datetime_columns=config.datetime_columns,
        preferred_numeric_columns=config.numeric_columns,
        groupby_columns=config.groupby_columns,
        time_frequency=config.time_frequency,
    )

    run_combined = config.analysis_mode in {"combined", "both"}
    run_separate = config.analysis_mode in {"separate", "both"}

    if run_combined:
        combined = pd.concat([item.dataframe for item in datasets], ignore_index=True, sort=False)
        logger.info("Loaded %s datasets with total rows=%s", len(datasets), len(combined))
        run_dataset_analysis(
            dataframe=combined,
            output_dir=config.output_dir,
            title="Data Analysis Report (combined)",
            analyzer=analyzer,
            options=options,
            config=config,
            logger=logger,
        )

    if run_separate:
        base_output = Path(config.output_dir) / "by_dataset"
        base_output.mkdir(parents=True, exist_ok=True)
        for index, dataset in enumerate(datasets, start=1):
            label = f"{dataset.source_file}:{dataset.source_sheet}"
            output_dir = base_output / dataset_slug(
                source_file=dataset.source_file,
                source_sheet=dataset.source_sheet,
                index=index,
            )
            logger.info("Running separate analysis for %s -> %s", label, output_dir)
            run_dataset_analysis(
                dataframe=dataset.dataframe,
                output_dir=output_dir,
                title=f"Data Analysis Report ({label})",
                analyzer=analyzer,
                options=options,
                config=config,
                logger=logger,
            )

    logger.info("Pipeline completed successfully")
    return 0


if __name__ == "__main__":
    sys.exit(main())
