"""Safe, format-aware ingestion for user-supplied structured datasets."""
from __future__ import annotations

from io import BytesIO
import json
from pathlib import Path
from typing import BinaryIO

import pandas as pd

SUPPORTED_EXTENSIONS = {".csv", ".xlsx", ".xls", ".json", ".jsonl", ".ndjson", ".parquet"}
DEFAULT_MAX_UPLOAD_BYTES = 100 * 1024 * 1024
DEFAULT_MAX_ROWS = 1_000_000


class DatasetIngestionError(ValueError):
    """Raised when a dataset cannot be safely read as a tabular frame."""


def read_dataset(
    filename: str,
    source: bytes | bytearray | BinaryIO,
    *,
    max_upload_bytes: int = DEFAULT_MAX_UPLOAD_BYTES,
    max_rows: int = DEFAULT_MAX_ROWS,
) -> pd.DataFrame:
    """Read CSV, Excel, JSON/JSONL or Parquet without executing uploaded content."""
    suffix = Path(filename).suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        raise DatasetIngestionError(
            f"Unsupported file type '{suffix or '(no extension)'}'. Supported formats: "
            "CSV, XLSX, XLS, JSON, JSONL, NDJSON and Parquet."
        )
    if isinstance(source, (bytes, bytearray)):
        payload = bytes(source)
    else:
        payload = source.read()
    if not payload:
        raise DatasetIngestionError("The uploaded file is empty.")
    if len(payload) > max_upload_bytes:
        raise DatasetIngestionError(
            f"File is {len(payload) / (1024 * 1024):.1f} MB; the configured upload limit is "
            f"{max_upload_bytes / (1024 * 1024):.0f} MB."
        )

    stream = BytesIO(payload)
    try:
        if suffix == ".csv":
            frame = pd.read_csv(stream, low_memory=False)
        elif suffix in {".xlsx", ".xls"}:
            frame = pd.read_excel(stream)
        elif suffix == ".parquet":
            frame = pd.read_parquet(stream)
        elif suffix in {".jsonl", ".ndjson"}:
            frame = pd.read_json(stream, lines=True)
        else:
            raw = json.loads(payload.decode("utf-8-sig"))
            if isinstance(raw, dict):
                # Common API exports wrap records in a named list.
                record_candidates = [value for value in raw.values() if isinstance(value, list)]
                if len(record_candidates) == 1 and record_candidates[0] and isinstance(record_candidates[0][0], dict):
                    raw = record_candidates[0]
                elif all(not isinstance(value, (dict, list)) for value in raw.values()):
                    raw = [raw]
            frame = pd.json_normalize(raw) if isinstance(raw, (dict, list)) else pd.DataFrame()
    except ImportError as exc:
        missing = "pyarrow" if suffix == ".parquet" else "the relevant Excel/JSON reader dependency"
        raise DatasetIngestionError(
            f"Cannot read this format because {missing} is unavailable. Install the platform requirements."
        ) from exc
    except Exception as exc:
        raise DatasetIngestionError(f"Could not parse '{filename}': {type(exc).__name__}: {exc}") from exc

    if not isinstance(frame, pd.DataFrame) or frame.empty:
        raise DatasetIngestionError("The file was read, but it contains no tabular rows.")
    if frame.shape[0] > max_rows:
        raise DatasetIngestionError(
            f"Dataset has {frame.shape[0]:,} rows; the configured ingestion limit is {max_rows:,}. "
            "Use a filtered or sampled extract."
        )
    if frame.shape[1] < 1:
        raise DatasetIngestionError("The dataset has no columns.")
    frame.columns = [str(column).strip() or f"column_{index + 1}" for index, column in enumerate(frame.columns)]
    if frame.columns.duplicated().any():
        counts: dict[str, int] = {}
        unique = []
        for column in frame.columns:
            counts[column] = counts.get(column, 0) + 1
            unique.append(column if counts[column] == 1 else f"{column}_{counts[column]}")
        frame.columns = unique
    return frame
