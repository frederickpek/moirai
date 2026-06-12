"""Local storage helpers for raw and processed esports data."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from moirai.config import PROCESSED_DATA_DIR, RAW_DATA_DIR


def ensure_data_dirs() -> None:
    RAW_DATA_DIR.mkdir(parents=True, exist_ok=True)
    PROCESSED_DATA_DIR.mkdir(parents=True, exist_ok=True)


def raw_json_path(name: str, *, raw_dir: Path = RAW_DATA_DIR) -> Path:
    return raw_dir / f"{slugify(name)}.json"


def processed_parquet_path(name: str, *, processed_dir: Path = PROCESSED_DATA_DIR) -> Path:
    return processed_dir / f"{slugify(name)}.parquet"


def save_raw_json(name: str, payload: Any, *, raw_dir: Path = RAW_DATA_DIR) -> Path:
    raw_dir.mkdir(parents=True, exist_ok=True)
    path = raw_json_path(name, raw_dir=raw_dir)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str), encoding="utf-8")
    return path


def load_raw_json(name: str, *, raw_dir: Path = RAW_DATA_DIR) -> Any | None:
    path = raw_json_path(name, raw_dir=raw_dir)
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def save_matches(matches: pd.DataFrame, name: str = "matches") -> Path:
    PROCESSED_DATA_DIR.mkdir(parents=True, exist_ok=True)
    path = processed_parquet_path(name)
    matches.to_parquet(path, index=False)
    return path


def load_matches(name: str = "matches") -> pd.DataFrame:
    path = processed_parquet_path(name)
    if not path.exists():
        raise FileNotFoundError(f"No processed match file found at {path}")
    return pd.read_parquet(path)


def query_processed(sql: str, name: str = "matches") -> pd.DataFrame:
    import duckdb

    path = processed_parquet_path(name)
    if not path.exists():
        raise FileNotFoundError(f"No processed match file found at {path}")
    return duckdb.sql(sql.replace("{matches}", f"'{path.as_posix()}'")).to_df()


def slugify(value: str) -> str:
    slug = "".join(char.lower() if char.isalnum() else "-" for char in value)
    slug = "-".join(part for part in slug.split("-") if part)
    return slug or "data"
