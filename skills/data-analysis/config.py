from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Sequence


def parse_list(raw_value: str | Sequence[str] | None) -> list[str]:
    if raw_value is None:
        return []
    if isinstance(raw_value, str):
        return [item.strip() for item in raw_value.split(",") if item.strip()]
    return [str(item).strip() for item in raw_value if str(item).strip()]


def parse_bool(raw_value: str | bool | None, default: bool) -> bool:
    if raw_value is None:
        return default
    if isinstance(raw_value, bool):
        return raw_value
    lowered = str(raw_value).strip().lower()
    if lowered in {"1", "true", "yes", "y"}:
        return True
    if lowered in {"0", "false", "no", "n"}:
        return False
    raise ValueError(f"Invalid boolean value: {raw_value}")


@dataclass
class AppConfig:
    input_path: str
    output_dir: str
    recursive: bool
    sheet_name: str
    datetime_columns: list[str] = field(default_factory=list)
    groupby_columns: list[str] = field(default_factory=list)
    numeric_columns: list[str] = field(default_factory=list)
    categorical_top_n: int = 10
    max_numeric_plots: int = 8
    max_category_plots: int = 4
    time_frequency: str = "D"
    log_file: str = "run.log"
    log_level: str = "INFO"

    @property
    def log_file_path(self) -> str:
        return str(Path(self.output_dir).expanduser().resolve() / self.log_file)

    @staticmethod
    def _default_config_path() -> Path:
        return Path(__file__).resolve().with_name("config.json")

    @staticmethod
    def _default_values() -> Dict[str, Any]:
        return {
            "input_path": "data",
            "output_dir": "output",
            "recursive": True,
            "sheet_name": "first",
            "datetime_columns": [],
            "groupby_columns": [],
            "numeric_columns": [],
            "categorical_top_n": 10,
            "max_numeric_plots": 8,
            "max_category_plots": 4,
            "time_frequency": "D",
            "log_file": "run.log",
            "log_level": "INFO",
        }

    @classmethod
    def load(
        cls,
        config_path: str | None = None,
        argv: Sequence[str] | None = None,
    ) -> "AppConfig":
        parser = argparse.ArgumentParser(description="Generic Data Analysis Pipeline")
        parser.add_argument("--config", type=str, help="Config JSON path")
        parser.add_argument("--input_path", type=str, help="Input file or directory path")
        parser.add_argument("--output_dir", type=str, help="Output directory")
        parser.add_argument("--recursive", type=str, help="Whether to scan directory recursively")
        parser.add_argument("--sheet_name", type=str, help="Excel sheet selector: first/all/<name>/<index>")
        parser.add_argument("--datetime_columns", type=str, help="Comma separated datetime columns")
        parser.add_argument("--groupby_columns", type=str, help="Comma separated grouping columns")
        parser.add_argument("--numeric_columns", type=str, help="Comma separated numeric columns")
        parser.add_argument("--categorical_top_n", type=int, help="Top N values for categorical stats")
        parser.add_argument("--max_numeric_plots", type=int, help="Max numeric columns to plot")
        parser.add_argument("--max_category_plots", type=int, help="Max categorical columns to plot")
        parser.add_argument("--time_frequency", type=str, help="Time frequency for trend analysis (D/W/M)")
        parser.add_argument("--log_file", type=str, help="Log filename under output_dir")
        parser.add_argument("--log_level", type=str, help="Log level: DEBUG/INFO/WARNING/ERROR")
        args, _ = parser.parse_known_args(argv)

        base = cls._default_values()

        resolved_config_path = Path(
            args.config or config_path or cls._default_config_path()
        ).expanduser()
        if resolved_config_path.exists():
            with resolved_config_path.open("r", encoding="utf-8") as handle:
                file_data = json.load(handle)
            if not isinstance(file_data, dict):
                raise ValueError(f"Config must be a JSON object: {resolved_config_path}")
            base.update(file_data)

        cli_overrides = {
            "input_path": args.input_path,
            "output_dir": args.output_dir,
            "recursive": args.recursive,
            "sheet_name": args.sheet_name,
            "datetime_columns": args.datetime_columns,
            "groupby_columns": args.groupby_columns,
            "numeric_columns": args.numeric_columns,
            "categorical_top_n": args.categorical_top_n,
            "max_numeric_plots": args.max_numeric_plots,
            "max_category_plots": args.max_category_plots,
            "time_frequency": args.time_frequency,
            "log_file": args.log_file,
            "log_level": args.log_level,
        }
        for key, value in cli_overrides.items():
            if value is not None:
                base[key] = value

        output_dir = Path(base["output_dir"]).expanduser().resolve()
        output_dir.mkdir(parents=True, exist_ok=True)

        return cls(
            input_path=str(Path(base["input_path"]).expanduser()),
            output_dir=str(output_dir),
            recursive=parse_bool(base.get("recursive"), default=True),
            sheet_name=str(base.get("sheet_name", "first")),
            datetime_columns=parse_list(base.get("datetime_columns")),
            groupby_columns=parse_list(base.get("groupby_columns")),
            numeric_columns=parse_list(base.get("numeric_columns")),
            categorical_top_n=int(base.get("categorical_top_n", 10)),
            max_numeric_plots=int(base.get("max_numeric_plots", 8)),
            max_category_plots=int(base.get("max_category_plots", 4)),
            time_frequency=str(base.get("time_frequency", "D")),
            log_file=str(base.get("log_file", "run.log")),
            log_level=str(base.get("log_level", "INFO")).upper(),
        )
