from __future__ import annotations

"""
data-analysis 配置加载与路径安全控制。

配置来源优先级（高 -> 低）：
1) CLI `--config`
2) 环境变量 `DATA_ANALYSIS_CONFIG`
3) 当前工作目录下 `job/data-analysis.config.json`
4) skill 目录默认 `config.json`

路径策略：
- `allow_external_paths=false` 时，输入/输出/日志路径必须位于 `workspace_root` 内；
- 输出目录不可用时，可按 `fallback_to_temp_output` 回退到系统临时目录；
- 回退主要用于本地调试，服务端建议关闭。
"""

import argparse
import json
import os
import tempfile
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Sequence


def parse_list(raw_value: str | Sequence[str] | None) -> list[str]:
    """把逗号分隔字符串或字符串序列统一为去空白列表。"""
    if raw_value is None:
        return []
    if isinstance(raw_value, str):
        return [item.strip() for item in raw_value.split(",") if item.strip()]
    return [str(item).strip() for item in raw_value if str(item).strip()]


def parse_bool(raw_value: str | bool | None, default: bool) -> bool:
    """解析布尔配置，兼容 1/0/true/false/yes/no。"""
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


def parse_analysis_mode(raw_value: str | None, default: str = "combined") -> str:
    """限制分析模式为 combined/separate/both。"""
    if raw_value is None:
        return default
    mode = str(raw_value).strip().lower()
    if mode in {"combined", "separate", "both"}:
        return mode
    raise ValueError(
        f"Invalid analysis_mode: {raw_value}. Supported values: combined, separate, both"
    )


def parse_time_frequency(raw_value: str | None, default: str = "auto") -> str:
    """
    解析时间频率配置。

    说明：
    - 支持 auto/H/D/W/M；
    - auto 表示由分析器在 H 与 D 间自动决策。
    """
    value = str(raw_value or default).strip().upper()
    if value in {"AUTO", "H", "D", "W", "M"}:
        return value
    raise ValueError(
        f"Invalid time_frequency: {raw_value}. Supported values: auto, H, D, W, M"
    )


@dataclass
class AppConfig:
    """运行时配置对象，字段已完成类型归一与路径解析。"""

    input_path: str
    output_dir: str
    recursive: bool
    sheet_name: str
    workspace_root: str = "."
    allow_external_paths: bool = False
    fallback_to_temp_output: bool = True
    analysis_mode: str = "combined"
    datetime_columns: list[str] = field(default_factory=list)
    groupby_columns: list[str] = field(default_factory=list)
    numeric_columns: list[str] = field(default_factory=list)
    max_numeric_plots: int = 8
    time_frequency: str = "AUTO"
    group_plot_threshold: float = 20.0
    plot_dpi: int = 300
    log_file: str = "run.log"
    log_level: str = "INFO"

    @property
    def log_file_path(self) -> str:
        # 绝对路径日志直接使用；相对路径挂载到 output_dir 下。
        log_path = Path(self.log_file).expanduser()
        if log_path.is_absolute():
            return str(log_path.resolve())
        return str((Path(self.output_dir).expanduser().resolve() / log_path).resolve())

    @staticmethod
    def _default_config_path() -> Path:
        """skill 自带默认配置文件路径。"""
        return Path(__file__).resolve().with_name("config.json")

    @staticmethod
    def _default_temp_output_dir() -> Path:
        """系统级临时输出目录（仅回退场景使用）。"""
        return Path(tempfile.gettempdir()) / "data-analysis-output"

    @staticmethod
    def _runtime_config_path() -> Path:
        """作业工作区的运行时配置文件路径。"""
        return Path.cwd().resolve() / "job" / "data-analysis.config.json"

    @classmethod
    def _resolve_config_path(cls, explicit_path: str | None) -> Path:
        """
        按优先级选择配置文件来源。

        注意：这里返回“候选路径”，是否存在由调用方判断。
        """
        if explicit_path:
            return Path(explicit_path).expanduser().resolve()
        if os.getenv("DATA_ANALYSIS_CONFIG"):
            return Path(os.environ["DATA_ANALYSIS_CONFIG"]).expanduser().resolve()
        runtime_path = cls._runtime_config_path()
        if runtime_path.exists():
            return runtime_path
        return cls._default_config_path()

    @staticmethod
    def _resolve_runtime_path(raw_path: str | Path, workspace_root: Path) -> Path:
        """把相对路径锚定到 workspace_root，避免受启动目录影响。"""
        path = Path(raw_path).expanduser()
        if path.is_absolute():
            return path.resolve()
        return (workspace_root / path).resolve()

    @staticmethod
    def _ensure_under_workspace(path: Path, workspace_root: Path, field_name: str) -> None:
        """强制路径位于工作区内部；越界直接拒绝。"""
        if path.is_relative_to(workspace_root):
            return
        raise ValueError(
            f"{field_name} must stay under workspace_root when allow_external_paths=false. "
            f"path={path}, workspace_root={workspace_root}"
        )

    @staticmethod
    def _normalize_log_file(raw_log_file: str, allow_external_paths: bool) -> str:
        """
        规范化日志文件配置。

        - `allow_external_paths=false` 时禁止绝对路径；
        - 禁止 `..`，防止路径穿越。
        """
        text = str(raw_log_file).strip() or "run.log"
        path = Path(text).expanduser()
        if path.is_absolute():
            if not allow_external_paths:
                raise ValueError("log_file cannot be absolute when allow_external_paths=false")
            return str(path.resolve())
        if ".." in path.parts:
            raise ValueError("log_file cannot contain '..'")
        return str(path)

    @classmethod
    def _resolve_temp_output_dir(
        cls,
        raw_path: str | None,
        workspace_root: Path,
    ) -> Path:
        """解析临时回退目录；可用相对路径或绝对路径。"""
        if raw_path:
            return cls._resolve_runtime_path(raw_path, workspace_root)
        return cls._default_temp_output_dir().resolve()

    @staticmethod
    def _default_values() -> Dict[str, Any]:
        """内置默认配置；用于兜底并作为 merge 基础。"""
        return {
            "input_path": "data",
            "output_dir": "output",
            "workspace_root": ".",
            "allow_external_paths": False,
            "fallback_to_temp_output": True,
            "analysis_mode": "combined",
            "recursive": True,
            "sheet_name": "first",
            "datetime_columns": [],
            "groupby_columns": [],
            "numeric_columns": [],
            "max_numeric_plots": 8,
            "time_frequency": "auto",
            "group_plot_threshold": 15.0,
            "plot_dpi": 300,
            "log_file": "run.log",
            "log_level": "INFO",
        }

    @classmethod
    def load(
        cls,
        config_path: str | None = None,
        argv: Sequence[str] | None = None,
    ) -> "AppConfig":
        """
        加载并规范化配置。

        处理流程：
        1) defaults -> config file -> CLI 覆盖；
        2) 统一解析路径到绝对路径；
        3) 执行工作区约束与输出目录可写性检查；
        4) 必要时回退到临时目录。
        """
        parser = argparse.ArgumentParser(description="Generic Data Analysis Pipeline")
        parser.add_argument("--config", type=str, help="Config JSON path")
        parser.add_argument("--input_path", type=str, help="Input file or directory path")
        parser.add_argument("--output_dir", type=str, help="Output directory")
        parser.add_argument("--workspace_root", type=str, help="Workspace root for path resolution")
        parser.add_argument(
            "--allow_external_paths",
            type=str,
            help="Allow input/output/log paths outside workspace_root",
        )
        parser.add_argument(
            "--fallback_to_temp_output",
            type=str,
            help="Fallback to system temp output dir when configured output_dir is not writable",
        )
        parser.add_argument(
            "--temp_output_dir",
            type=str,
            help="Optional temp fallback output dir; defaults to system temp directory",
        )
        parser.add_argument(
            "--analysis_mode",
            type=str,
            help="Analysis mode: combined/separate/both",
        )
        parser.add_argument("--recursive", type=str, help="Whether to scan directory recursively")
        parser.add_argument("--sheet_name", type=str, help="Excel sheet selector: first/all/<name>/<index>")
        parser.add_argument("--datetime_columns", type=str, help="Comma separated datetime columns")
        parser.add_argument("--groupby_columns", type=str, help="Comma separated grouping columns")
        parser.add_argument("--numeric_columns", type=str, help="Comma separated numeric columns")
        parser.add_argument("--max_numeric_plots", type=int, help="Max numeric columns to plot")
        parser.add_argument(
            "--time_frequency",
            type=str,
            help="Time frequency for trend analysis (auto/H/D, manual also supports W/M)",
        )
        parser.add_argument(
            "--group_plot_threshold",
            type=float,
            help="Relative mean threshold percent for grouping trend lines",
        )
        parser.add_argument("--plot_dpi", type=int, help="PNG output DPI, higher means clearer image")
        parser.add_argument("--log_file", type=str, help="Log filename under output_dir")
        parser.add_argument("--log_level", type=str, help="Log level: DEBUG/INFO/WARNING/ERROR")
        args, _ = parser.parse_known_args(argv)

        # 第 1 层：内置默认值。
        base = cls._default_values()

        # 第 2 层：配置文件（若存在）。
        resolved_config_path = cls._resolve_config_path(args.config or config_path)
        if resolved_config_path.exists():
            with resolved_config_path.open("r", encoding="utf-8") as handle:
                file_data = json.load(handle)
            if not isinstance(file_data, dict):
                raise ValueError(f"Config must be a JSON object: {resolved_config_path}")
            base.update(file_data)

        # 第 3 层：CLI 覆盖（优先级最高）。
        cli_overrides = {
            "input_path": args.input_path,
            "output_dir": args.output_dir,
            "workspace_root": args.workspace_root,
            "allow_external_paths": args.allow_external_paths,
            "fallback_to_temp_output": args.fallback_to_temp_output,
            "temp_output_dir": args.temp_output_dir,
            "analysis_mode": args.analysis_mode,
            "recursive": args.recursive,
            "sheet_name": args.sheet_name,
            "datetime_columns": args.datetime_columns,
            "groupby_columns": args.groupby_columns,
            "numeric_columns": args.numeric_columns,
            "max_numeric_plots": args.max_numeric_plots,
            "time_frequency": args.time_frequency,
            "group_plot_threshold": args.group_plot_threshold,
            "plot_dpi": args.plot_dpi,
            "log_file": args.log_file,
            "log_level": args.log_level,
        }
        for key, value in cli_overrides.items():
            if value is not None:
                base[key] = value

        # 统一路径基准：相对路径全部锚定到 workspace_root。
        workspace_root = cls._resolve_runtime_path(
            base.get("workspace_root") or os.getenv("DATA_ANALYSIS_WORKSPACE_ROOT") or ".",
            Path.cwd().resolve(),
        )
        allow_external_paths = parse_bool(base.get("allow_external_paths"), default=False)
        fallback_to_temp_output = parse_bool(
            base.get("fallback_to_temp_output"),
            default=True,
        )

        input_path = cls._resolve_runtime_path(str(base["input_path"]), workspace_root)
        output_dir = cls._resolve_runtime_path(str(base["output_dir"]), workspace_root)

        # 输入路径不允许越界（严格模式）。
        if not allow_external_paths:
            cls._ensure_under_workspace(input_path, workspace_root, "input_path")
        use_temp_output_fallback = False
        try:
            # 输出路径同样受工作区约束；随后创建目录验证写权限。
            if not allow_external_paths:
                cls._ensure_under_workspace(output_dir, workspace_root, "output_dir")
            output_dir.mkdir(parents=True, exist_ok=True)
        except (PermissionError, OSError, ValueError) as exc:
            # 明确禁用回退时，保留原始错误并终止。
            if not fallback_to_temp_output:
                raise ValueError(
                    f"Cannot use output_dir={output_dir}; fallback_to_temp_output is disabled"
                ) from exc

            # 回退到系统临时目录，保证流程可继续（主要用于本地调试）。
            temp_output_dir = cls._resolve_temp_output_dir(
                raw_path=base.get("temp_output_dir"),
                workspace_root=workspace_root,
            )
            temp_output_dir.mkdir(parents=True, exist_ok=True)
            warnings.warn(
                f"output_dir '{output_dir}' unavailable ({exc}); fallback to temp '{temp_output_dir}'.",
                RuntimeWarning,
                stacklevel=2,
            )
            output_dir = temp_output_dir
            use_temp_output_fallback = True

        # 日志文件单独做规范化；相对路径最终仍落在 output_dir 下。
        log_file = cls._normalize_log_file(
            str(base.get("log_file", "run.log")),
            allow_external_paths=allow_external_paths,
        )
        # 非回退场景下，绝对日志路径也必须受工作区约束。
        if not allow_external_paths and not use_temp_output_fallback and Path(log_file).is_absolute():
            cls._ensure_under_workspace(Path(log_file).resolve(), workspace_root, "log_file")

        return cls(
            input_path=str(input_path),
            output_dir=str(output_dir),
            workspace_root=str(workspace_root),
            allow_external_paths=allow_external_paths,
            fallback_to_temp_output=fallback_to_temp_output,
            analysis_mode=parse_analysis_mode(base.get("analysis_mode"), default="combined"),
            recursive=parse_bool(base.get("recursive"), default=True),
            sheet_name=str(base.get("sheet_name", "first")),
            datetime_columns=parse_list(base.get("datetime_columns")),
            groupby_columns=parse_list(base.get("groupby_columns")),
            numeric_columns=parse_list(base.get("numeric_columns")),
            max_numeric_plots=int(base.get("max_numeric_plots", 8)),
            time_frequency=parse_time_frequency(base.get("time_frequency"), default="auto"),
            group_plot_threshold=max(
                0.0,
                float(base.get("group_plot_threshold", 15.0)),
            ),
            plot_dpi=max(100, min(600, int(base.get("plot_dpi", 300)))),
            log_file=log_file,
            log_level=str(base.get("log_level", "INFO")).upper(),
        )
