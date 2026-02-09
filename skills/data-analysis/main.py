from __future__ import annotations

import sys

import pandas as pd

from analyzer import AnalysisOptions, DataAnalyzer
from config import AppConfig
from data_loader import DataLoader
from logger import setup_logger
from plotter import DataPlotter
from report_writer import ReportWriter


def print_console_summary(overview: dict, chart_count: int) -> None:
    print("\n" + "=" * 64)
    print("Data Analysis Report")
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


def main() -> int:
    config = AppConfig.load()
    logger = setup_logger(config.log_file_path, level=config.log_level)

    logger.info("Starting generic data-analysis pipeline")
    logger.info("Input path: %s", config.input_path)
    logger.info("Output dir: %s", config.output_dir)

    loader = DataLoader(logger=logger)
    datasets = loader.load_path(
        input_path=config.input_path,
        recursive=config.recursive,
        sheet_name=config.sheet_name,
    )
    if not datasets:
        logger.error("No dataset loaded. Check input path and file formats.")
        return 1

    combined = pd.concat([item.dataframe for item in datasets], ignore_index=True, sort=False)
    logger.info("Loaded %s datasets with total rows=%s", len(datasets), len(combined))

    analyzer = DataAnalyzer(logger=logger)
    options = AnalysisOptions(
        datetime_columns=config.datetime_columns,
        preferred_numeric_columns=config.numeric_columns,
        groupby_columns=config.groupby_columns,
        categorical_top_n=config.categorical_top_n,
        time_frequency=config.time_frequency,
    )
    analysis_result = analyzer.run_full_analysis(combined, options)

    plotter = DataPlotter(output_dir=config.output_dir, logger=logger)
    chart_files = plotter.generate_all_plots(
        result=analysis_result,
        max_numeric_plots=config.max_numeric_plots,
        max_category_plots=config.max_category_plots,
        categorical_top_n=config.categorical_top_n,
    )

    writer = ReportWriter(output_dir=config.output_dir, logger=logger)
    writer.write_full_report(result=analysis_result, chart_files=chart_files)

    print_console_summary(analysis_result.overview, chart_count=len(chart_files))
    logger.info("Pipeline completed successfully")
    return 0


if __name__ == "__main__":
    sys.exit(main())
