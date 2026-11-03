"""Integration tests: run the real pipeline against a temporary workspace."""

import shutil
import sqlite3
from pathlib import Path

import pandas as pd
import pytest

from src.analytics import load_queries, run_query
from src.extract import ExtractionError, extract_raw_data
from src.pipeline import PROJECT_ROOT, Paths, run_pipeline

SAMPLE_CSV = """Order_ID,Order_Date,Customer_ID,Product,Category,Quantity,Unit_Price,Region
ORD-1,2025-01-10,CUST-1,Wireless Mouse,Electronics,2,500,North
ORD-2,11/01/2025,CUST-2,Hoodie,apparel,1,1500,south
ORD-2,11/01/2025,CUST-2,Hoodie,apparel,1,1500,south
ORD-3,2025-02-05,CUST-3,Wireless Mouse,Electronics,-1,500,East
ORD-4,2025-02-07,,Hoodie,Clothing,3,,West
"""


@pytest.fixture()
def workspace(tmp_path) -> Paths:
    """A temporary project workspace with its own raw CSV, reusing the real schema/SQL files."""
    raw = tmp_path / "data" / "raw" / "retail_sales.csv"
    raw.parent.mkdir(parents=True)
    raw.write_text(SAMPLE_CSV, encoding="utf-8")
    return Paths(
        raw_csv=raw,
        processed_csv=tmp_path / "data" / "processed" / "clean.csv",
        db=tmp_path / "database" / "test.db",
        schema=PROJECT_ROOT / "database" / "schema.sql",
        queries=PROJECT_ROOT / "sql" / "analysis_queries.sql",
        charts_dir=tmp_path / "outputs" / "charts",
        report=tmp_path / "outputs" / "summary.txt",
        logs_dir=tmp_path / "logs",
    )


def count_rows(db_path, table="sales") -> int:
    with sqlite3.connect(db_path) as conn:
        return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


def test_pipeline_loads_clean_data_into_database(workspace):
    result = run_pipeline(workspace)
    # ORD-1 ok, ORD-2 (duplicate removed), ORD-3 dropped (negative qty), ORD-4 price imputed from Hoodie median
    assert result["records_before"] == 5
    assert result["records_after"] == 3
    assert count_rows(workspace.db) == 3
    clean = pd.read_csv(workspace.processed_csv)
    assert set(clean["Order_ID"]) == {"ORD-1", "ORD-2", "ORD-4"}
    assert "Total_Sales" in clean.columns


def test_running_pipeline_twice_does_not_duplicate_rows(workspace):
    run_pipeline(workspace)
    run_pipeline(workspace)
    assert count_rows(workspace.db) == 3
    assert count_rows(workspace.db, "etl_runs") == 2  # two audited runs, still 3 sales rows


def test_database_totals_match_processed_csv(workspace):
    run_pipeline(workspace)
    expected = pd.read_csv(workspace.processed_csv)["Total_Sales"].sum()
    with sqlite3.connect(workspace.db) as conn:
        actual = conn.execute("SELECT SUM(total_sales) FROM sales").fetchone()[0]
    assert actual == pytest.approx(expected)


def test_all_sql_queries_execute(workspace):
    run_pipeline(workspace)
    queries = load_queries(workspace.queries)
    assert {"total_revenue", "total_orders", "revenue_by_category", "monthly_sales_trend",
            "top_5_products", "regional_performance"} <= set(queries)
    with sqlite3.connect(workspace.db) as conn:
        for name in queries:
            run_query(conn, queries, name)  # raises on any SQL error
        assert run_query(conn, queries, "total_orders").iloc[0, 0] == 3


def test_charts_and_report_are_created(workspace):
    result = run_pipeline(workspace)
    assert len(result["charts"]) == 4
    assert all(Path(p).is_file() and Path(p).stat().st_size > 0 for p in result["charts"])
    assert "Total revenue" in workspace.report.read_text(encoding="utf-8")


def test_missing_raw_file_raises_clear_error(tmp_path):
    with pytest.raises(ExtractionError, match="not found"):
        extract_raw_data(tmp_path / "nope.csv")


def test_missing_columns_raise_clear_error(tmp_path):
    bad = tmp_path / "bad.csv"
    bad.write_text("Order_ID,Region\n1,North\n", encoding="utf-8")
    with pytest.raises(ExtractionError, match="missing required columns"):
        extract_raw_data(bad)


def test_real_sample_dataset_runs_end_to_end(tmp_path):
    """The CSV shipped in the repository must be processable."""
    raw = PROJECT_ROOT / "data" / "raw" / "retail_sales.csv"
    assert raw.is_file(), "Run: python scripts/generate_sample_data.py"
    shutil.copy(raw, tmp_path / "raw.csv")
    paths = Paths(
        raw_csv=tmp_path / "raw.csv", processed_csv=tmp_path / "clean.csv", db=tmp_path / "t.db",
        schema=PROJECT_ROOT / "database" / "schema.sql", queries=PROJECT_ROOT / "sql" / "analysis_queries.sql",
        charts_dir=tmp_path / "charts", report=tmp_path / "report.txt", logs_dir=tmp_path / "logs",
    )
    result = run_pipeline(paths)
    assert 0 < result["records_after"] < result["records_before"]
    assert count_rows(paths.db) == result["records_after"]
