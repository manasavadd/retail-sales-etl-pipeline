"""TRANSFORM step: clean, validate and enrich the raw sales data with pandas.

Cleaning rules (all documented here and in the README)
-------------------------------------------------------
1. Blank strings / "N/A" / "null" style values are treated as missing.
2. Order_ID, Product: rows with a missing value are DROPPED (cannot be recovered).
3. Order_Date: parsed using a list of known formats. Day-first is assumed for
   dd/mm/yyyy. Unparseable dates, dates before 2000-01-01 and dates in the
   future are DROPPED.
4. Quantity: must be a whole number between 1 and MAX_QUANTITY. Missing,
   non-numeric, zero, negative or absurdly large values are DROPPED.
5. Unit_Price: missing, non-numeric, zero or negative prices are IMPUTED with
   the median valid price of the same product (dropped if the product has no
   valid price at all).
6. Category / Region: whitespace and case are normalised, known synonyms are
   mapped to a standard name. Missing category is recovered from the product's
   most common category; missing region becomes "Unknown".
7. Customer_ID: missing values become "UNKNOWN".
8. Duplicates: exact duplicate rows are removed, then any remaining repeated
   Order_ID is removed (first occurrence is kept) because Order_ID is the
   primary key.
9. Total_Sales = Quantity x Unit_Price (rounded to 2 decimals).
"""

import logging
from datetime import datetime

import pandas as pd

logger = logging.getLogger(__name__)

DATE_FORMATS = ["%Y-%m-%d", "%d/%m/%Y", "%d-%b-%Y", "%b %d, %Y"]
MIN_VALID_DATE = pd.Timestamp("2000-01-01")
MAX_QUANTITY = 1000

CATEGORY_MAP = {
    "electronics": "Electronics",
    "electronic": "Electronics",
    "furniture": "Furniture",
    "office supplies": "Office Supplies",
    "office supply": "Office Supplies",
    "stationery": "Office Supplies",
    "clothing": "Clothing",
    "apparel": "Clothing",
    "groceries": "Groceries",
    "grocery": "Groceries",
}

REGION_MAP = {
    "north": "North",
    "n": "North",
    "south": "South",
    "s": "South",
    "east": "East",
    "e": "East",
    "west": "West",
    "w": "West",
    "central": "Central",
    "c": "Central",
}

MISSING_TOKENS = {"", "nan", "none", "null", "n/a", "na", "-"}

OUTPUT_COLUMNS = [
    "Order_ID",
    "Order_Date",
    "Customer_ID",
    "Product",
    "Category",
    "Quantity",
    "Unit_Price",
    "Total_Sales",
    "Region",
]


# --------------------------------------------------------------------------
# Small helper functions (each does one job and is unit-tested)
# --------------------------------------------------------------------------
def normalize_missing(series: pd.Series) -> pd.Series:
    """Strip whitespace, collapse inner spaces and turn missing-like tokens into NA."""
    cleaned = series.astype("object").where(series.notna(), None)
    cleaned = cleaned.map(lambda v: " ".join(str(v).split()) if v is not None else None)
    return cleaned.map(lambda v: None if v is None or v.lower() in MISSING_TOKENS else v)


def standardize_names(series: pd.Series, mapping: dict) -> pd.Series:
    """Map spelling/case variants to a standard name.

    Unknown (but non-missing) values fall back to Title Case. Missing values stay missing.
    """

    def _fix(value):
        if value is None or pd.isna(value):
            return None
        key = str(value).strip().lower()
        return mapping.get(key, str(value).strip().title())

    return series.map(_fix)


def parse_dates(series: pd.Series) -> pd.Series:
    """Parse mixed-format date text into datetimes; unparseable values become NaT."""
    result = None
    for fmt in DATE_FORMATS:
        parsed = pd.to_datetime(series, format=fmt, errors="coerce")
        result = parsed if result is None else result.fillna(parsed)
    return result


def _canonical_spelling(series: pd.Series) -> pd.Series:
    """Unify case variants of the same text (e.g. 'usb-c cable' -> most common spelling)."""
    keys = series.str.lower()
    canonical = series.groupby(keys).agg(lambda s: s.value_counts().idxmax())
    return keys.map(canonical).where(series.notna(), None)


# --------------------------------------------------------------------------
# Main transformation
# --------------------------------------------------------------------------
def clean_sales_data(raw_df: pd.DataFrame, today=None):
    """Clean and enrich raw sales data.

    Args:
        raw_df: DataFrame with the raw (text) columns from the extract step.
        today: optional ``datetime``/``Timestamp`` used as the latest allowed
            order date (defaults to now; injectable to make tests deterministic).

    Returns:
        (clean_df, report) where ``report`` is a dict counting what happened
        to the records at each step.

    Raises:
        ValueError: if ``raw_df`` is empty or lacks required columns.
    """
    required = [c for c in OUTPUT_COLUMNS if c != "Total_Sales"]
    missing_cols = [c for c in required if c not in raw_df.columns]
    if missing_cols:
        raise ValueError(f"Missing required columns: {missing_cols}")
    if raw_df.empty:
        raise ValueError("Cannot clean an empty DataFrame")

    max_date = pd.Timestamp(today or datetime.now()).normalize()
    df = raw_df[required].copy()
    report = {"records_before": len(df)}

    # 1. Normalise whitespace and missing-like tokens in every column.
    for col in required:
        df[col] = normalize_missing(df[col])
    report["missing_values_found"] = {c: int(df[c].isna().sum()) for c in required}

    # 2. Drop rows whose key fields cannot be recovered.
    before = len(df)
    df = df.dropna(subset=["Order_ID", "Product"]).copy()
    report["dropped_missing_order_id_or_product"] = before - len(df)

    df["Order_ID"] = df["Order_ID"].str.upper()
    df["Product"] = _canonical_spelling(df["Product"])
    df["Customer_ID"] = df["Customer_ID"].str.upper()

    # 3. Dates.
    df["Order_Date"] = parse_dates(df["Order_Date"])
    before = len(df)
    valid_date = df["Order_Date"].notna() & (df["Order_Date"] >= MIN_VALID_DATE) & (df["Order_Date"] <= max_date)
    df = df[valid_date].copy()
    report["dropped_invalid_date"] = before - len(df)

    # 4. Quantity: numeric, whole number, 1..MAX_QUANTITY.
    qty = pd.to_numeric(df["Quantity"], errors="coerce")
    valid_qty = qty.notna() & (qty >= 1) & (qty <= MAX_QUANTITY) & (qty == qty.round())
    report["dropped_invalid_quantity"] = int((~valid_qty).sum())
    df = df[valid_qty].copy()
    df["Quantity"] = qty[valid_qty].astype(int)

    # 5. Unit price: numeric; zero/negative/non-numeric become missing (imputed later).
    price = pd.to_numeric(df["Unit_Price"], errors="coerce")
    price = price.where(price > 0)
    df["Unit_Price"] = price

    # 6. Category / region standardisation.
    df["Category"] = standardize_names(df["Category"], CATEGORY_MAP)
    df["Region"] = standardize_names(df["Region"], REGION_MAP)

    # 7. Remove duplicates BEFORE imputing so copies cannot skew medians.
    before = len(df)
    df = df.drop_duplicates().copy()
    report["exact_duplicates_removed"] = before - len(df)
    before = len(df)
    df = df.drop_duplicates(subset="Order_ID", keep="first").copy()
    report["duplicate_order_ids_removed"] = before - len(df)

    # 8. Impute / fill.
    medians = df.groupby("Product")["Unit_Price"].median()
    missing_price = df["Unit_Price"].isna()
    if missing_price.any():
       df.loc[missing_price, "Unit_Price"] = (
          df.loc[missing_price, "Product"].map(medians)
    )
    still_missing = df["Unit_Price"].isna()
    report["dropped_unrecoverable_price"] = int(still_missing.sum())
    report["unit_price_imputed"] = int(missing_price.sum() - still_missing.sum())
    df = df[~still_missing].copy()

    product_category = df.dropna(subset=["Category"]).groupby("Product")["Category"].agg(
        lambda s: s.value_counts().idxmax()
    )
    missing_cat = df["Category"].isna()
    df["Category"] = df["Product"].map(product_category).fillna("Uncategorized")
    report["category_filled_from_product"] = int(missing_cat.sum())

    report["region_filled_unknown"] = int(df["Region"].isna().sum())
    df["Region"] = df["Region"].fillna("Unknown")
    report["customer_filled_unknown"] = int(df["Customer_ID"].isna().sum())
    df["Customer_ID"] = df["Customer_ID"].fillna("UNKNOWN")

    # 9. Calculated column and final formatting.
    df["Unit_Price"] = df["Unit_Price"].round(2)
    df["Total_Sales"] = (df["Quantity"] * df["Unit_Price"]).round(2)
    df["Order_Date"] = df["Order_Date"].dt.strftime("%Y-%m-%d")
    df = df[OUTPUT_COLUMNS].sort_values(["Order_Date", "Order_ID"]).reset_index(drop=True)

    report["records_after"] = len(df)
    report["records_removed_total"] = report["records_before"] - report["records_after"]
    logger.info("Cleaning finished: %d records before, %d after", report["records_before"], report["records_after"])
    for key, value in report.items():
        if key not in ("records_before", "records_after"):
            logger.info("  %s: %s", key, value)
    return df, report
