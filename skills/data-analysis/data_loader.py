from __future__ import annotations

from dataclasses import dataclass
import logging
from pathlib import Path
from typing import Iterable, List, Optional, Sequence, Union

import pandas as pd

SUPPORTED_EXTENSIONS = {".csv", ".xlsx", ".xls"}


@dataclass
class LoadedDataset:
    """Container for a loaded dataset and its source metadata."""

    source_file: str
    source_sheet: str
    dataframe: pd.DataFrame


class DataLoader:
    """Load CSV and Excel files into pandas DataFrame with reliable fallbacks."""

    def __init__(
        self,
        logger: Optional[logging.Logger] = None,
        csv_encodings: Optional[Sequence[str]] = None,
    ) -> None:
        self.logger = logger or logging.getLogger("data-analysis")
        self.csv_encodings = list(csv_encodings or ("utf-8", "utf-8-sig", "gbk", "gb18030", "latin1"))

    def discover_files(self, input_path: Union[str, Path], recursive: bool = True) -> List[Path]:
        """Return all supported files under a path. Accept a single file or a directory."""
        path = Path(input_path).expanduser().resolve()
        if path.is_file():
            if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
                raise ValueError(f"Unsupported file type: {path.suffix}")
            return [path]
        if not path.is_dir():
            raise FileNotFoundError(f"Input path not found: {path}")

        pattern = "**/*" if recursive else "*"
        files = sorted(
            p
            for p in path.glob(pattern)
            if p.is_file() and p.suffix.lower() in SUPPORTED_EXTENSIONS
        )
        self.logger.info("Discovered %s supported files under %s", len(files), path)
        return files

    def load_path(
        self,
        input_path: Union[str, Path],
        recursive: bool = True,
        sheet_name: Union[str, int, None] = "first",
    ) -> List[LoadedDataset]:
        """Discover and load all supported files from a path."""
        files = self.discover_files(input_path=input_path, recursive=recursive)
        return self.load_many(files=files, sheet_name=sheet_name)

    def load_many(
        self,
        files: Iterable[Union[str, Path]],
        sheet_name: Union[str, int, None] = "first",
    ) -> List[LoadedDataset]:
        """Load many files; skip failed files and keep processing."""
        datasets: List[LoadedDataset] = []
        for file_item in files:
            file_path = Path(file_item).expanduser().resolve()
            try:
                datasets.extend(self.load_file(file_path=file_path, sheet_name=sheet_name))
            except Exception as exc:  # pylint: disable=broad-except
                self.logger.error("Failed to load file %s: %s", file_path, exc)
        return datasets

    def load_file(
        self,
        file_path: Union[str, Path],
        sheet_name: Union[str, int, None] = "first",
    ) -> List[LoadedDataset]:
        """Dispatch by extension: CSV via read_csv, Excel via read_excel."""
        path = Path(file_path).expanduser().resolve()
        suffix = path.suffix.lower()
        if suffix == ".csv":
            frame = self._load_csv(path)
            frame = self._normalize_columns(frame)
            frame = self._attach_source_columns(frame, source_file=path.name, source_sheet="csv")
            return [LoadedDataset(source_file=path.name, source_sheet="csv", dataframe=frame)]
        if suffix in {".xlsx", ".xls"}:
            return self._load_excel(path, sheet_name=sheet_name)
        raise ValueError(f"Unsupported file type: {suffix}")

    def _load_csv(self, file_path: Path) -> pd.DataFrame:
        """Load CSV with encoding and delimiter fallback."""
        parsing_errors: List[str] = []
        for encoding in self.csv_encodings:
            try:
                frame = pd.read_csv(file_path, encoding=encoding, sep=None, engine="python")
                self.logger.info("Loaded CSV %s with auto delimiter, encoding=%s", file_path.name, encoding)
                return frame
            except UnicodeDecodeError:
                continue
            except Exception as exc:  # pylint: disable=broad-except
                parsing_errors.append(f"auto-sep/{encoding}: {exc}")

            for delimiter in [",", ";", "\t", "|"]:
                try:
                    frame = pd.read_csv(file_path, encoding=encoding, sep=delimiter)
                    self.logger.info(
                        "Loaded CSV %s with delimiter='%s', encoding=%s",
                        file_path.name,
                        delimiter,
                        encoding,
                    )
                    return frame
                except UnicodeDecodeError:
                    break
                except Exception as exc:  # pylint: disable=broad-except
                    parsing_errors.append(f"sep={delimiter}/{encoding}: {exc}")

        raise ValueError(
            f"Unable to parse CSV file: {file_path}. "
            f"Tried encodings={self.csv_encodings}. Last errors={parsing_errors[-3:]}"
        )

    def _load_excel(self, file_path: Path, sheet_name: Union[str, int, None]) -> List[LoadedDataset]:
        """Load Excel with `calamine` first, fallback to `openpyxl`."""
        selector = self._resolve_sheet_selector(sheet_name)
        excel_raw = None
        errors: List[str] = []
        for engine in ("calamine", "openpyxl"):
            try:
                excel_raw = pd.read_excel(file_path, sheet_name=selector, engine=engine)
                self.logger.info(
                    "Loaded Excel %s with engine=%s, sheet=%s",
                    file_path.name,
                    engine,
                    "all" if selector is None else selector,
                )
                break
            except Exception as exc:  # pylint: disable=broad-except
                errors.append(f"{engine}: {exc}")

        if excel_raw is None:
            raise ValueError(f"Unable to parse Excel file: {file_path}. Errors={errors}")

        datasets: List[LoadedDataset] = []
        if isinstance(excel_raw, dict):
            for sheet, frame in excel_raw.items():
                cleaned = self._normalize_columns(frame)
                cleaned = self._attach_source_columns(
                    cleaned, source_file=file_path.name, source_sheet=str(sheet)
                )
                datasets.append(
                    LoadedDataset(
                        source_file=file_path.name,
                        source_sheet=str(sheet),
                        dataframe=cleaned,
                    )
                )
            return datasets

        single_sheet = self._infer_sheet_label(selector)
        cleaned = self._normalize_columns(excel_raw)
        cleaned = self._attach_source_columns(
            cleaned,
            source_file=file_path.name,
            source_sheet=single_sheet,
        )
        return [
            LoadedDataset(
                source_file=file_path.name,
                source_sheet=single_sheet,
                dataframe=cleaned,
            )
        ]

    @staticmethod
    def _resolve_sheet_selector(sheet_name: Union[str, int, None]) -> Union[str, int, None]:
        """Convert user-friendly selector into pandas read_excel selector."""
        if sheet_name is None:
            return 0
        if isinstance(sheet_name, int):
            return sheet_name
        value = str(sheet_name).strip()
        if not value or value.lower() == "first":
            return 0
        if value.lower() == "all":
            return None
        if value.isdigit():
            return int(value)
        return value

    @staticmethod
    def _infer_sheet_label(selector: Union[str, int, None]) -> str:
        if selector is None:
            return "all"
        if selector == 0:
            return "first"
        return str(selector)

    @staticmethod
    def _normalize_columns(frame: pd.DataFrame) -> pd.DataFrame:
        """Normalize and de-duplicate column names for safer downstream processing."""
        cleaned = frame.copy()
        raw_columns = [str(column).strip() if column is not None else "" for column in cleaned.columns]
        normalized: List[str] = []
        seen = {}
        for index, column in enumerate(raw_columns, start=1):
            base = column if column else f"unnamed_{index}"
            count = seen.get(base, 0)
            if count:
                normalized.append(f"{base}_{count}")
            else:
                normalized.append(base)
            seen[base] = count + 1
        cleaned.columns = normalized
        return cleaned

    @staticmethod
    def _attach_source_columns(frame: pd.DataFrame, source_file: str, source_sheet: str) -> pd.DataFrame:
        with_meta = frame.copy()
        with_meta["__source_file"] = source_file
        with_meta["__source_sheet"] = source_sheet
        return with_meta
