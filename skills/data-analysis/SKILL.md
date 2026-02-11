---
name: data-analysis
description: 通用表格数据分析技能。Use when Codex needs to read CSV/XLS/XLSX files, convert data to pandas DataFrame, run reusable EDA/quality/correlation/group/time-series/outlier analysis, generate markdown+CSV+JSON summaries, and create matplotlib charts for reporting.
---

# Data Analysis Skill

实现目标：
- 读取 `csv/xlsx/xls` 并统一为 pandas DataFrame。
- 对数据执行通用可复用分析，而不是绑定某个业务字段。
- 输出结构化分析结果（`csv/json/md`）和常用图表（matplotlib）。
- 保持高可靠（容错、回退、日志）、高复用（模块化函数）、高可读（清晰输入输出约定）。
- 最终完善程序生成的 @output/summary.md ； 对应章节的分析，读取 对应的 csv 获取详细信息。

## 目录与模块

本 skill 的核心模块：
- `data_loader.py`
  - 文件发现、格式识别、读取分发。
  - `csv` 使用 `pd.read_csv`（编码与分隔符回退）。
  - `xlsx/xls` 使用 `pd.read_excel`（`calamine -> openpyxl` 回退）。
- `datetime_parser.py`
  - 独立时间解析模块，支持多策略解析与单独 CLI 调试。
  - 处理混合时间格式（标准字符串、中文时间、Excel 序列号、Unix 时间戳、松散格式如 `2026.0000`）。
- `analyzer.py`
  - 纯 pandas 的通用分析函数集合。
  - 调用 `datetime_parser.py` 完成时间字段解析与解析日志输出。
  - 产出 `AnalysisResult`，供报告与图表层消费。
- `plotter.py`
  - 使用 matplotlib 生成常见分析图。
- `report_writer.py`
  - 将分析结果写入 `csv/json/md`。
- `config.py`
  - 统一读取 `config.json + CLI`。
- `main.py`
  - 将读取、分析、绘图、写出串成一条稳定 pipeline。

## 固定执行流程

按以下顺序执行：
1. 读取配置：`AppConfig.load()`。
2. 初始化日志：`setup_logger()`。
3. 发现并读取文件：`DataLoader.load_path()`。
4. 根据 `analysis_mode` 决定分析方式：
   - `combined`：先 `pd.concat(...)` 再分析。
   - `separate`：对每个数据集单独分析。
   - `both`：先做合并分析，再做逐数据集分析。
5. 执行分析：`DataAnalyzer.run_full_analysis()`。
6. 生成图表：`DataPlotter.generate_all_plots()`。
7. 写出产物：`ReportWriter.write_full_report()`。
8. 输出控制台摘要与日志。

## 读取策略（必须遵守）

使用 `data_loader.py` 统一读取入口：
- `csv`：
  - `DataLoader._load_csv()` -> `pd.read_csv(...)`
  - 自动尝试多个编码（`utf-8`, `utf-8-sig`, `gbk`, `gb18030`, `latin1`）
  - 分隔符自动/回退（自动推断、`,`、`;`、`\t`、`|`）
- `xlsx/xls`：
  - `DataLoader._load_excel()` -> `pd.read_excel(...)`
  - 优先 `engine="calamine"`，失败后回退 `engine="openpyxl"`
  - 支持 `sheet_name=first/all/具体名称/索引`

读取后统一处理：
- 标准化列名（去空白、空列名补齐、重复列名去重）。
- 增加来源元数据列：`__source_file`, `__source_sheet`。

## 通用分析模块（常见方法）

`analyzer.py` 提供以下可复用方法：

- `prepare_dataframe(dataframe, datetime_columns)`
  - 清理全空行列、字符串去空白、时间字段解析。
  - 自动识别时间字段（列名含 `date/time/timestamp/datetime/日期/时间/时刻/开始/结束`）或使用显式配置。
  - 解析时调用 `DateTimeParser.parse_series()`，按解析率阈值决定是否落为 datetime 列。

- `build_overview(...)`
  - 数据规模与质量总览：行列数、缺失率、重复行、内存占用、来源文件数。

- `analyze_missing_values(dataframe)`
  - 缺失值统计（字段级 `missing_count/missing_ratio`）。

- `summarize_numeric(dataframe, numeric_columns)`
  - 数值统计：`count/mean/std/min/q1/median/q3/max/iqr/cv`。

- `build_correlation_matrix(dataframe, numeric_columns)`
  - 数值字段 Pearson 相关系数矩阵。

- `detect_outliers_iqr(dataframe, numeric_columns)`
  - IQR 异常值检测（上下界、异常数量、异常占比）。

- `group_aggregate(dataframe, groupby_columns, numeric_columns)`
  - 分组聚合（组内样本数、数值字段均值/中位数）。

- `time_series_summary(dataframe, datetime_columns, numeric_columns, frequency)`
  - 按时间频率聚合（默认 `auto` 在 `H/D` 间自动选择，也支持手动 `H/D/W/M`）并给出每期样本量与数值均值趋势。

## 时间解析模块（datetime_parser.py）

`datetime_parser.py` 既可被 `analyzer.py` 调用，也可单独运行用于排查时间列问题。

核心能力：
- 分层解析策略：Excel 序列号、Unix 时间戳（s/ms/us/ns）、显式格式列表、通用 parser 回退。
- 噪声清洗：中文年月日时分秒、全角符号、重复分隔符、空值文本标准化。
- 时区处理：支持带时区偏移文本（如 `Z`、`+08:00`），统一为 tz-naive `datetime64[ns]`。
- 解析可观测性：输出每列 `parse_ratio` 与 `strategy_counts`，便于定位脏数据。

独立脚本示例：

```bash
python skills/data-analysis/datetime_parser.py \
  --input_path data.xlsx \
  --column 开始时刻,结束时刻 \
  --output_path output/datetime_preview.csv
```

## 图表模块（matplotlib）

`plotter.py` 默认生成以下图表（数据可用时才生成）：
- `missing_values_top20.png`：缺失值最高字段柱状图。
- `numeric_histograms.png`：数值字段直方图。
- `numeric_boxplot.png` 或 `numeric_boxplot_group_XX.png`：数值字段箱线图（按 `group_plot_threshold` 可能拆分为多张）。
- `correlation_heatmap.png`：相关性热力图。
- `time_trend.png` 或 `time_trend_group_XX.png`：时间趋势图（按 `group_plot_threshold` 可能拆分为多张）。

图表生成原则：
- 仅使用 matplotlib（无交互依赖，适合无头环境）。
- 对空数据自动跳过，不因单图失败而中断整体流程。
- 图文件统一输出到 `output/plots/`。

## 输出契约

`combined` 模式下，运行完成后固定输出到 `output_dir`：
- `processed_data.csv`
- `missing_summary.csv`
- `numeric_summary.csv`
- `correlation_matrix.csv`
- `outlier_summary.csv`
- `groupby_summary.csv`
- `time_series_summary.csv`
- `summary.md`
- `analysis_bundle.json`
- `plots/*.png`

`separate` 模式下，会在 `output_dir/by_dataset/<dataset_slug>/` 为每个数据集生成同样一组文件。
`both` 模式下，以上两类输出都会生成。

`analysis_bundle.json` 用于机器消费，至少包含：
- `overview`（关键统计）
- `files`（各产物文件名）
- `generated_charts`（图表路径列表）

## 报告完善规则（必须遵守）

- 最终完善程序生成的 @output/summary.md ； 对应章节的分析，读取 对应的 csv 获取详细信息。
增加生成的 `summary.md` 对应章节的分析，遵守以下约束：
- 仅保留图表分组章节，不输出“数据规模与质量/字段结构/产物说明”等通用模板章节。
- 图表分组使用二级标题（`##`），例如：`## 缺失值分析`、`## 数值分布分析`、`## 相关性分析`、`## 时间序列分析`。
- 每个图表分组下的结论必须来自对应 CSV 统计文件，禁止只写泛化描述。

图表与 CSV 的对应关系（如果对应的为空就不增加对应章节的内容）：
- 缺失值分析 -> `missing_summary.csv`
- 数值分布分析 -> `numeric_summary.csv` + `outlier_summary.csv`
- 相关性分析 -> `correlation_matrix.csv`
- 时间序列分析 -> `time_series_summary.csv`

## 配置与命令

配置加载优先级：
1. `--config <path>`（CLI 显式传入）
2. 环境变量 `DATA_ANALYSIS_CONFIG`
3. 当前工作区 `job/data-analysis.config.json`（服务端运行推荐）
4. `skills/data-analysis/config.json`（仅本地调试默认）

关键参数：
- `input_path`: 输入文件或目录
- `output_dir`: 输出目录
- `workspace_root`: 路径解析根目录（默认当前工作目录）
- `allow_external_paths`: 是否允许读写工作区外路径（默认 `false`）
- `fallback_to_temp_output`: 输出目录不可写时，是否自动回退到系统临时目录（默认 `true`）
- `temp_output_dir`: 可选，临时回退目录（不填则使用系统临时目录下 `data-analysis-output`）
- `analysis_mode`: 分析模式（`combined/separate/both`）
- `recursive`: 是否递归扫描目录
- `sheet_name`: `first/all/<sheet>/<index>`
- `datetime_columns`: 显式时间字段列表
- `groupby_columns`: 分组字段列表
- `numeric_columns`: 显式数值字段列表（可选）
- `max_numeric_plots`: 数值图字段上限
- `time_frequency`: 时间频率（默认 `auto`，会在 `H/D` 间自动选择；也可手动设为 `H/D/W/M`）

CLI 覆盖示例：

```bash
python skills/data-analysis/main.py \
  --config job/data-analysis.config.json \
  --input_path data \
  --output_dir output \
  --analysis_mode both \
  --sheet_name all \
  --datetime_columns event_time \
  --groupby_columns region,channel \
  --time_frequency auto
```

权限与路径安全建议：
- 服务端运行时将 `output_dir` 固定为工作区 `outputs`，并保持 `allow_external_paths=false`。
- 本地调试时可开启 `fallback_to_temp_output=true`，当 `output_dir` 不可写会自动回退到系统临时目录。
- `log_file` 使用相对路径（如 `run.log`），不要配置绝对路径或 `..`。
- 仅在离线调试场景下才允许外部路径，并显式设置 `allow_external_paths=true`。

## 可靠性要求

执行时遵守以下规则：
- 文件读取失败时记录日志并继续读取其他文件。
- 单个分析步骤失败不得导致整个 pipeline 崩溃（除输入完全不可用）。
- 所有输出都写入 `output_dir`，避免散落写文件。
- 所有关键步骤写日志，便于追踪问题。
- 保持函数单一职责，优先复用已有函数，不重复实现读取/统计逻辑。

## 扩展方式

扩展优先路径：
1. 在 `analyzer.py` 增加新分析函数，并在 `run_full_analysis` 注册。
2. 在 `plotter.py` 新增图函数，并在 `generate_all_plots` 串联。
3. 在 `report_writer.py` 增加新输出文件类型（如 parquet/xlsx）。
4. 在 `config.py` 增加参数，并保证可被 CLI 覆盖。

扩展时保持：
- 不修改既有输出字段语义。
- 不在 `main.py` 写复杂业务逻辑，保持编排层职责。
