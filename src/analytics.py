"""ANALYTICS step: run SQL queries, draw charts with Matplotlib, write a summary report."""

import logging
import re
import sqlite3
from datetime import datetime
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # headless backend: saves PNG files, never opens a window
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

logger = logging.getLogger(__name__)

BAR_COLOR = "#2a6f97"
LINE_COLOR = "#c8553d"


class AnalyticsError(Exception):
    """Raised when queries or charts cannot be produced."""


def load_queries(sql_path) -> dict:
    """Read ``analysis_queries.sql`` and return ``{query_name: sql_text}``."""
    path = Path(sql_path)
    if not path.is_file():
        raise AnalyticsError(f"SQL file not found: {path}")
    text = path.read_text(encoding="utf-8")
    parts = re.split(r"^--\s*name:\s*(\w+)\s*$", text, flags=re.MULTILINE)
    # parts = [preamble, name1, sql1, name2, sql2, ...]
    queries = {parts[i]: parts[i + 1].strip() for i in range(1, len(parts) - 1, 2)}
    if not queries:
        raise AnalyticsError(f"No '-- name:' queries found in {path}")
    return queries


def run_query(conn: sqlite3.Connection, queries: dict, name: str) -> pd.DataFrame:
    """Execute one named query and return the result as a DataFrame."""
    if name not in queries:
        raise AnalyticsError(f"Unknown query: {name}")
    try:
        return pd.read_sql_query(queries[name], conn)
    except (sqlite3.Error, pd.errors.DatabaseError) as exc:
        raise AnalyticsError(f"Query '{name}' failed: {exc}") from exc


def _style_axes(ax, title: str, xlabel: str, ylabel: str) -> None:
    ax.set_title(title, fontsize=13, fontweight="bold", loc="left")
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    ax.spines[["top", "right"]].set_visible(False)
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{v:,.0f}"))
    ax.grid(axis="y", alpha=0.25)
    ax.set_axisbelow(True)


def _bar_chart(df, x, y, title, xlabel, ylabel, path, horizontal=False) -> Path:
    fig, ax = plt.subplots(figsize=(9, 5))
    if horizontal:
        ordered = df.sort_values(y)
        bars = ax.barh(ordered[x], ordered[y], color=BAR_COLOR)
        ax.set_title(title, fontsize=13, fontweight="bold", loc="left")
        ax.set_xlabel(ylabel)
        ax.spines[["top", "right"]].set_visible(False)
        ax.xaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{v:,.0f}"))
        ax.grid(axis="x", alpha=0.25)
        ax.set_axisbelow(True)
        labels = [f"{v:,.0f}" for v in ordered[y]]
    else:
        bars = ax.bar(df[x], df[y], color=BAR_COLOR)
        _style_axes(ax, title, xlabel, ylabel)
        labels = [f"{v:,.0f}" for v in df[y]]
    ax.bar_label(bars, labels=labels, padding=3, fontsize=9)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return path


def create_charts(conn: sqlite3.Connection, queries: dict, charts_dir) -> list:
    """Create the four PNG charts and return their file paths."""
    out = Path(charts_dir)
    out.mkdir(parents=True, exist_ok=True)
    paths = []

    category = run_query(conn, queries, "revenue_by_category")
    paths.append(_bar_chart(category, "category", "revenue", "Revenue by Product Category",
                            "Category", "Revenue", out / "revenue_by_category.png"))

    monthly = run_query(conn, queries, "monthly_sales_trend")
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.plot(monthly["month"], monthly["revenue"], marker="o", color=LINE_COLOR, linewidth=2)
    _style_axes(ax, "Monthly Sales Trend", "Month", "Revenue")
    ax.tick_params(axis="x", rotation=45)
    fig.tight_layout()
    path = out / "monthly_sales_trend.png"
    fig.savefig(path, dpi=150)
    plt.close(fig)
    paths.append(path)

    region = run_query(conn, queries, "regional_performance")
    paths.append(_bar_chart(region, "region", "revenue", "Regional Sales Comparison",
                            "Region", "Revenue", out / "regional_sales.png"))

    top5 = run_query(conn, queries, "top_5_products")
    paths.append(_bar_chart(top5, "product", "revenue", "Top 5 Products by Revenue",
                            "Product", "Revenue", out / "top5_products.png", horizontal=True))

    logger.info("Saved %d charts to %s", len(paths), out)
    return paths


def generate_summary_report(conn: sqlite3.Connection, queries: dict, report_path, cleaning_report=None) -> Path:
    """Write a plain-text report of key business metrics and return its path."""
    revenue = float(run_query(conn, queries, "total_revenue").iloc[0, 0] or 0)
    orders = int(run_query(conn, queries, "total_orders").iloc[0, 0])
    customers = int(run_query(conn, queries, "unique_customers").iloc[0, 0])
    category = run_query(conn, queries, "revenue_by_category")
    monthly = run_query(conn, queries, "monthly_sales_trend")
    top5 = run_query(conn, queries, "top_5_products")
    region = run_query(conn, queries, "regional_performance")

    if orders == 0:
        raise AnalyticsError("No sales data in the database; cannot build a report")

    best_month = monthly.loc[monthly["revenue"].idxmax()]
    lines = [
        "RETAIL SALES - SUMMARY REPORT",
        "=" * 60,
        f"Generated      : {datetime.now():%Y-%m-%d %H:%M:%S}",
        "Data source    : SYNTHETIC sample dataset (not real company data)",
        f"Period covered : {monthly['month'].iloc[0]} to {monthly['month'].iloc[-1]}",
        "",
        "KEY METRICS",
        "-" * 60,
        f"Total revenue          : {revenue:,.2f}",
        f"Total orders           : {orders:,}",
        f"Average order value    : {revenue / orders:,.2f}",
        f"Unique customers       : {customers:,}",
        f"Top category           : {category.iloc[0]['category']} ({category.iloc[0]['revenue']:,.2f})",
        f"Top region             : {region.iloc[0]['region']} ({region.iloc[0]['revenue_share_pct']}% of revenue)",
        f"Best month             : {best_month['month']} ({best_month['revenue']:,.2f})",
        "",
        "TOP 5 PRODUCTS BY REVENUE",
        "-" * 60,
    ]
    for rank, row in enumerate(top5.itertuples(index=False), start=1):
        lines.append(f"{rank}. {row.product:<22} {row.revenue:>14,.2f}  ({int(row.units_sold)} units)")

    lines += ["", "REVENUE BY CATEGORY", "-" * 60]
    lines += [f"{r.category:<18} {r.revenue:>14,.2f}" for r in category.itertuples(index=False)]
    lines += ["", "REVENUE BY REGION", "-" * 60]
    lines += [f"{r.region:<18} {r.revenue:>14,.2f}  ({r.revenue_share_pct}%)" for r in region.itertuples(index=False)]

    if cleaning_report:
        lines += ["", "DATA CLEANING SUMMARY", "-" * 60]
        lines.append(f"Records before cleaning : {cleaning_report['records_before']}")
        lines.append(f"Records after cleaning  : {cleaning_report['records_after']}")
        lines.append(f"Records removed         : {cleaning_report['records_removed_total']}")

    path = Path(report_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    logger.info("Summary report written to %s", path)
    return path
