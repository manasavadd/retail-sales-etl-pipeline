-- SQLite schema for the Retail Sales ETL pipeline.
-- Every statement uses IF NOT EXISTS so the script is safe to run repeatedly.

-- Dimension table: one row per product, with its (single) category.
CREATE TABLE IF NOT EXISTS products (
    product_name TEXT PRIMARY KEY,
    category     TEXT NOT NULL
);

-- Fact table: one row per order. order_id is the primary key, which is what
-- makes repeated pipeline runs idempotent (rows are upserted, never duplicated).
CREATE TABLE IF NOT EXISTS sales (
    order_id    TEXT PRIMARY KEY,
    order_date  TEXT NOT NULL,                       -- ISO format YYYY-MM-DD
    customer_id TEXT NOT NULL,
    product     TEXT NOT NULL,
    quantity    INTEGER NOT NULL CHECK (quantity > 0),
    unit_price  REAL NOT NULL CHECK (unit_price > 0),
    total_sales REAL NOT NULL CHECK (total_sales > 0),
    region      TEXT NOT NULL,
    FOREIGN KEY (product) REFERENCES products (product_name)
);

CREATE INDEX IF NOT EXISTS idx_sales_order_date ON sales (order_date);
CREATE INDEX IF NOT EXISTS idx_sales_region     ON sales (region);
CREATE INDEX IF NOT EXISTS idx_sales_product    ON sales (product);

-- Audit table: one row per pipeline execution.
CREATE TABLE IF NOT EXISTS etl_runs (
    run_id            INTEGER PRIMARY KEY AUTOINCREMENT,
    run_timestamp     TEXT NOT NULL,
    raw_records       INTEGER NOT NULL,
    cleaned_records   INTEGER NOT NULL,
    rows_in_sales     INTEGER NOT NULL
);
