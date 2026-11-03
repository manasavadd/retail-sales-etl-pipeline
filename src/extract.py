"""EXTRACT step: read the raw CSV file into a pandas DataFrame."""

import logging
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)

REQUIRED_COLUMNS = [
    "Order_ID",
    "Order_Date",
    "Customer_ID",
    "Product",
    "Category",
    "Quantity",
    "Unit_Price",
    "Region",
]


class ExtractionError(Exception):
    """Raised when the raw data cannot be read or is structurally invalid."""


def extract_raw_data(csv_path) -> pd.DataFrame:
    """Load the raw sales CSV.

    Every column is read as text (``dtype=str``) so that nothing is silently
    converted. Type conversion and validation happen in the transform step.

    Raises:
        ExtractionError: if the file is missing, empty, unreadable, or lacks
            one of the required columns.
    """
    path = Path(csv_path)
    if not path.is_file():
        raise ExtractionError(f"Raw data file not found: {path}")

    try:
        df = pd.read_csv(path, dtype=str, keep_default_na=False, na_values=[])
    except pd.errors.EmptyDataError as exc:
        raise ExtractionError(f"Raw data file is empty: {path}") from exc
    except (pd.errors.ParserError, UnicodeDecodeError, OSError) as exc:
        raise ExtractionError(f"Could not read {path}: {exc}") from exc

    df.columns = [str(c).strip() for c in df.columns]
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ExtractionError(f"Raw data is missing required columns: {missing}")
    if df.empty:
        raise ExtractionError(f"Raw data file has a header but no rows: {path}")

    logger.info("Extracted %d raw records from %s", len(df), path.name)
    return df[REQUIRED_COLUMNS]
