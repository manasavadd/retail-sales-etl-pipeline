"""LOAD step: create the SQLite database and load cleaned data without duplicates."""

import logging
import sqlite3
from datetime import datetime
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)


class DatabaseLoadError(Exception):
    """Raised when the database cannot be created or loaded."""


def get_connection(db_path) -> sqlite3.Connection:
    """Open a SQLite connection (creating the parent folder) with foreign keys enabled."""
    path = Path(db_path)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(path)
        conn.execute("PRAGMA foreign_keys = ON")
        return conn
    except (sqlite3.Error, OSError) as exc:
        raise DatabaseLoadError(f"Could not open database {path}: {exc}") from exc


def init_schema(conn: sqlite3.Connection, schema_path) -> None:
    """Create all tables by running schema.sql (safe to run many times)."""
    path = Path(schema_path)
    if not path.is_file():
        raise DatabaseLoadError(f"Schema file not found: {path}")
    try:
        conn.executescript(path.read_text(encoding="utf-8"))
        conn.commit()
    except sqlite3.Error as exc:
        raise DatabaseLoadError(f"Could not apply schema: {exc}") from exc
    logger.info("Database schema is ready")


def load_sales(conn: sqlite3.Connection, df: pd.DataFrame, raw_records: int) -> int:
    """Upsert cleaned records into ``products`` and ``sales``.

    ``INSERT ... ON CONFLICT DO UPDATE`` on the primary key means that running the
    pipeline again updates existing rows instead of inserting duplicates.

    Returns:
        The total number of rows in the ``sales`` table after loading.
    """
    products = [(str(p), str(c)) for p, c in df[["Product", "Category"]].drop_duplicates().itertuples(index=False)]
    sales = [
        (
            str(r.Order_ID),
            str(r.Order_Date),
            str(r.Customer_ID),
            str(r.Product),
            int(r.Quantity),
            float(r.Unit_Price),
            float(r.Total_Sales),
            str(r.Region),
        )
        for r in df.itertuples(index=False)
    ]
    try:
        with conn:  # one transaction: commits on success, rolls back on error
            conn.executemany(
                "INSERT INTO products (product_name, category) VALUES (?, ?) "
                "ON CONFLICT(product_name) DO UPDATE SET category = excluded.category",
                products,
            )
            conn.executemany(
                "INSERT INTO sales (order_id, order_date, customer_id, product, quantity, "
                "unit_price, total_sales, region) VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(order_id) DO UPDATE SET order_date = excluded.order_date, "
                "customer_id = excluded.customer_id, product = excluded.product, "
                "quantity = excluded.quantity, unit_price = excluded.unit_price, "
                "total_sales = excluded.total_sales, region = excluded.region",
                sales,
            )
            total_rows = conn.execute("SELECT COUNT(*) FROM sales").fetchone()[0]
            conn.execute(
                "INSERT INTO etl_runs (run_timestamp, raw_records, cleaned_records, rows_in_sales) "
                "VALUES (?, ?, ?, ?)",
                (datetime.now().isoformat(timespec="seconds"), raw_records, len(df), total_rows),
            )
    except sqlite3.Error as exc:
        raise DatabaseLoadError(f"Failed to load data into SQLite: {exc}") from exc

    logger.info("Loaded %d cleaned records; sales table now has %d rows", len(df), total_rows)
    return total_rows
