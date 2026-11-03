# Retail Sales ETL and Analytics Pipeline

A small, complete data engineering project: raw retail sales data is **extracted** from CSV, **cleaned and transformed** with Pandas, **loaded** into a SQLite database, and **analysed** with SQL and Matplotlib. It runs with a single command and is covered by automated Pytest tests.

> **Data disclaimer:** `data/raw/retail_sales.csv` is a **synthetic dataset** created by `scripts/generate_sample_data.py` (fixed random seed, 830 rows). It is **not real company data**. Data-quality problems (missing values, duplicates, mixed date formats, invalid entries, inconsistent spellings) were injected on purpose to demonstrate the cleaning logic.

## Problem Statement

Raw sales exports are rarely analysis-ready: dates come in different formats, rows are duplicated, values are missing or invalid, and the same region or category is spelled several ways. Reporting on such data produces wrong revenue numbers. This project builds a repeatable pipeline that turns messy sales records into a trustworthy relational dataset and business insights.

## Objectives

- Ingest a raw CSV file and profile its quality problems.
- Clean it using documented, testable rules and log record counts before/after.
- Store it in a relational SQLite database with primary keys, constraints and no duplicate inserts on re-runs.
- Answer business questions with SQL (revenue, orders, category/region/monthly performance, top products).
- Produce charts and a summary report.
- Verify the behaviour with automated tests.

## Architecture and Pipeline Workflow

```
 data/raw/retail_sales.csv
          |
          v
 [1] EXTRACT   src/extract.py     read CSV as text, validate columns
          |
          v
 [2] TRANSFORM src/transform.py   clean, validate, standardise, Total_Sales
          |                       --> data/processed/retail_sales_clean.csv
          v
 [3] LOAD      src/load.py        create schema, upsert into SQLite
          |                       --> database/retail_sales.db
          v
 [4] ANALYSE   src/analytics.py   SQL queries -> charts + summary report
                                  --> outputs/charts/*.png, outputs/summary_report.txt

 src/pipeline.py orchestrates all four stages and writes logs/pipeline.log
```

### Cleaning rules

| Field | Rule |
|---|---|
| Order_ID, Product | Missing -> row dropped (cannot be recovered) |
| Order_Date | Parsed from 4 known formats (day-first for `dd/mm/yyyy`); unparseable, before 2000 or in the future -> dropped. Output is ISO `YYYY-MM-DD` |
| Quantity | Must be a whole number from 1 to 1000; missing, text, zero, negative or absurd values -> dropped |
| Unit_Price | Missing, text, zero or negative -> imputed with the median valid price of the same product |
| Category / Region | Whitespace and case normalised, synonyms mapped (e.g. `Apparel` -> `Clothing`, `N` -> `North`); missing category recovered from the product; missing region -> `Unknown` |
| Customer_ID | Missing -> `UNKNOWN` |
| Duplicates | Exact duplicates removed, then repeated Order_ID removed (first kept) |
| Total_Sales | `Quantity x Unit_Price`, rounded to 2 decimals |

### Database design

- `products(product_name PK, category)`
- `sales(order_id PK, order_date, customer_id, product FK -> products, quantity, unit_price, total_sales, region)` with `CHECK` constraints and indexes
- `etl_runs` — one audit row per pipeline execution

**Idempotency:** rows are written with `INSERT ... ON CONFLICT(order_id) DO UPDATE` (upsert), so running the pipeline repeatedly never creates duplicate sales rows. (Note: a row that disappears from the raw CSV is not deleted from the database; see Future Enhancements.)

## Technologies Used

Python 3.10+, Pandas, SQLite (`sqlite3` standard library), SQL, Matplotlib, Pytest, Git/GitHub.

## Repository Structure

```
retail-sales-etl-pipeline/
├── data/
│   ├── raw/retail_sales.csv          # synthetic raw data (input)
│   └── processed/                    # cleaned CSV (generated)
├── database/schema.sql               # tables, keys, indexes
├── scripts/generate_sample_data.py   # recreates the synthetic dataset
├── src/
│   ├── extract.py  transform.py  load.py  analytics.py  pipeline.py
├── sql/analysis_queries.sql          # named analytical queries
├── outputs/charts/                   # PNG charts
├── tests/test_transform.py  test_pipeline.py
├── logs/                             # pipeline.log (generated)
├── requirements.txt  .gitignore  .env.example  LICENSE  README.md
```

## Installation

Requires **Python 3.10 or newer** and Git.

```bash
git clone https://github.com/manasavadd/retail-sales-etl-pipeline.git
cd retail-sales-etl-pipeline

# create and activate a virtual environment
python -m venv .venv
# Windows (PowerShell):  .venv\Scripts\Activate.ps1
# Windows (cmd):         .venv\Scripts\activate.bat
# macOS / Linux:         source .venv/bin/activate

pip install -r requirements.txt
```

## VS Code Setup

1. Install VS Code and the **Python** extension (Microsoft).
2. `File > Open Folder...` and choose `retail-sales-etl-pipeline`.
3. Press `Ctrl+Shift+P` -> **Python: Select Interpreter** -> pick the one inside `.venv`.
4. Open a terminal with ``Ctrl+` `` (it activates `.venv` automatically).
5. Optional: install the **SQLite Viewer** extension to open `database/retail_sales.db` and run queries from `sql/analysis_queries.sql`.

## Running the Project

Always run from the project root:

```bash
python -m src.pipeline          # full pipeline (one command)
python -m src.pipeline --skip-outputs   # ETL only, no charts/report
python scripts/generate_sample_data.py  # optional: regenerate the synthetic CSV
```

## Sample SQL Queries

All queries live in `sql/analysis_queries.sql`.

```sql
-- Total revenue
SELECT ROUND(SUM(total_sales), 2) AS total_revenue FROM sales;

-- Revenue by product category
SELECT p.category, ROUND(SUM(s.total_sales), 2) AS revenue
FROM sales s JOIN products p ON p.product_name = s.product
GROUP BY p.category ORDER BY revenue DESC;

-- Monthly sales trend
SELECT strftime('%Y-%m', order_date) AS month, ROUND(SUM(total_sales), 2) AS revenue
FROM sales GROUP BY month ORDER BY month;

-- Top five products by revenue
SELECT product, ROUND(SUM(total_sales), 2) AS revenue
FROM sales GROUP BY product ORDER BY revenue DESC LIMIT 5;
```

## Expected Output

Running the pipeline on the shipped dataset prints:

```
Records before cleaning: 830
Records after cleaning : 731
Rows in database       : 731
```

Re-running it leaves the database at 731 rows (no duplicates). `outputs/summary_report.txt` contains, for example:

```
Total revenue          : 3,966,875.83
Total orders           : 731
Average order value    : 5,426.64
Top category           : Furniture (2,463,538.38)
Top region             : East (28.5% of revenue)
```

Generated charts (in `outputs/charts/`):

| Chart | File |
|---|---|
| Revenue by category | `revenue_by_category.png` |
| Monthly sales trend | `monthly_sales_trend.png` |
| Regional comparison | `regional_sales.png` |
| Top 5 products | `top5_products.png` |

![Revenue by category](outputs/charts/revenue_by_category.png)
![Monthly sales trend](outputs/charts/monthly_sales_trend.png)
![Regional sales](outputs/charts/regional_sales.png)
![Top 5 products](outputs/charts/top5_products.png)

## Testing

```bash
python -m pytest -v
```

31 tests cover missing values, duplicate removal, invalid dates/quantities/prices, standardisation, `Total_Sales`, database loading, idempotent re-runs, SQL queries, chart creation and error handling.

## Future Enhancements

- Delete-and-reload or soft-delete mode so rows removed from the source also leave the database.
- Rejected-records file that stores each dropped row with its reason.
- Incremental loading and scheduling (cron / Airflow).
- Data-quality checks with Great Expectations or Pandera.
- Customer segmentation (RFM) and a dashboard (Streamlit / Power BI).
- PostgreSQL support and a CI workflow (GitHub Actions) that runs the tests on every push.

## License

MIT — see `LICENSE`.
