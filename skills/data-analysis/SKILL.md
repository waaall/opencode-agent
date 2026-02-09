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

## 目录与模块

本 skill 的核心模块：
- `data_loader.py`
  - 文件发现、格式识别、读取分发。
  - `csv` 使用 `pd.read_csv`（编码与分隔符回退）。
  - `xlsx/xls` 使用 `pd.read_excel`（`calamine -> openpyxl` 回退）。
- `analyzer.py`
  - 纯 pandas 的通用分析函数集合。
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
4. 合并 DataFrame：`pd.concat(...)`。
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
  - 自动识别时间字段（列名含 `date/time/日期/时间`）或使用显式配置。

- `build_overview(...)`
  - 数据规模与质量总览：行列数、缺失率、重复行、内存占用、来源文件数。

- `analyze_missing_values(dataframe)`
  - 缺失值统计（字段级 `missing_count/missing_ratio`）。

- `summarize_numeric(dataframe, numeric_columns)`
  - 数值统计：`count/mean/std/min/q1/median/q3/max/iqr/cv`。

- `summarize_categorical(dataframe, categorical_columns, top_n)`
  - 分类型统计：非空数、缺失数、唯一值个数、TopN 值分布。

- `build_correlation_matrix(dataframe, numeric_columns)`
  - 数值字段 Pearson 相关系数矩阵。

- `detect_outliers_iqr(dataframe, numeric_columns)`
  - IQR 异常值检测（上下界、异常数量、异常占比）。

- `group_aggregate(dataframe, groupby_columns, numeric_columns)`
  - 分组聚合（组内样本数、数值字段均值/中位数）。

- `time_series_summary(dataframe, datetime_columns, numeric_columns, frequency)`
  - 按时间频率聚合（`D/W/M`）并给出每期样本量与数值均值趋势。

- `build_markdown_summary(...)`
  - 自动生成可读性较高的 `summary.md` 文本结论。

## 图表模块（matplotlib）

`plotter.py` 默认生成以下图表（数据可用时才生成）：
- `missing_values_top20.png`：缺失值最高字段柱状图。
- `numeric_histograms.png`：数值字段直方图。
- `numeric_boxplot.png`：数值字段箱线图。
- `correlation_heatmap.png`：相关性热力图。
- `category_top_<column>.png`：分类字段 TopN 频次图。
- `time_trend.png`：时间趋势图（样本量 + 首个均值指标）。

图表生成原则：
- 仅使用 matplotlib（无交互依赖，适合无头环境）。
- 对空数据自动跳过，不因单图失败而中断整体流程。
- 图文件统一输出到 `output/plots/`。

## 输出契约

运行完成后固定输出：
- `processed_data.csv`
- `missing_summary.csv`
- `numeric_summary.csv`
- `categorical_summary.csv`
- `correlation_matrix.csv`
- `outlier_summary.csv`
- `groupby_summary.csv`
- `time_series_summary.csv`
- `summary.md`
- `analysis_bundle.json`
- `plots/*.png`

`analysis_bundle.json` 用于机器消费，至少包含：
- `overview`（关键统计）
- `files`（各产物文件名）
- `generated_charts`（图表路径列表）

## 配置与命令

默认配置文件：`config.json`

关键参数：
- `input_path`: 输入文件或目录
- `output_dir`: 输出目录
- `recursive`: 是否递归扫描目录
- `sheet_name`: `first/all/<sheet>/<index>`
- `datetime_columns`: 显式时间字段列表
- `groupby_columns`: 分组字段列表
- `numeric_columns`: 显式数值字段列表（可选）
- `categorical_top_n`: 分类 TopN
- `max_numeric_plots`: 数值图字段上限
- `max_category_plots`: 分类图字段上限
- `time_frequency`: 时间频率（`D/W/M`）

CLI 覆盖示例：

```bash
python skills/data-analysis/main.py \
  --input_path data \
  --output_dir output \
  --sheet_name all \
  --datetime_columns event_time \
  --groupby_columns region,channel \
  --time_frequency D
```

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
