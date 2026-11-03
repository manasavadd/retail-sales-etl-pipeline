"""Pipeline orchestrator: Extract -> Transform -> Load -> Analyse.

Run the whole project with one command from the project root:

    python -m src.pipeline

Optional environment variables (see .env.example) can override the default paths.
"""

import argparse
import logging
import os
import sys
from dataclasses import dataclass
from pathlib import Path

from src.analytics import AnalyticsError, create_charts, generate_summary_report, load_queries
from src.extract import ExtractionError, extract_raw_data
from src.load import DatabaseLoadError, get_connection, init_schema, load_sales
from src.transform import clean_sales_data

logger = logging.getLogger("pipeline")

PROJECT_ROOT = Path(__file__).resolve().parents[1]


@dataclass
class Paths:
    """All file locations used by the pipeline (relative to the project root by default)."""

    raw_csv: Path
    processed_csv: Path
    db: Path
    schema: Path
    queries: Path
    charts_dir: Path
    report: Path
    logs_dir: Path

    @classmethod
    def from_root(cls, root=PROJECT_ROOT) -> "Paths":
        root = Path(root)
        return cls(
            raw_csv=root / os.getenv("RAW_DATA_PATH", "data/raw/retail_sales.csv"),
            processed_csv=root / os.getenv("PROCESSED_DATA_PATH", "data/processed/retail_sales_clean.csv"),
            db=root / os.getenv("DATABASE_PATH", "database/retail_sales.db"),
            schema=root / "database" / "schema.sql",
            queries=root / "sql" / "analysis_queries.sql",
            charts_dir=root / "outputs" / "charts",
            report=root / "outputs" / "summary_report.txt",
            logs_dir=root / "logs",
        )


def setup_logging(logs_dir) -> None:
    """Log to both the console and logs/pipeline.log."""
    Path(logs_dir).mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(Path(logs_dir) / "pipeline.log", encoding="utf-8"),
        ],
        force=True,
    )
    logging.getLogger("matplotlib").setLevel(logging.WARNING)  # hide chatty library messages


def run_pipeline(paths: Paths, make_outputs: bool = True) -> dict:
    """Execute every stage and return a dictionary of results (counts and file paths).

    Raises:
        ExtractionError, ValueError, DatabaseLoadError, AnalyticsError on failure.
    """
    logger.info("=== Pipeline started ===")

    # EXTRACT
    raw_df = extract_raw_data(paths.raw_csv)

    # TRANSFORM
    clean_df, cleaning_report = clean_sales_data(raw_df)
    if clean_df.empty:
        raise ValueError("All records were removed during cleaning; nothing to load")
    paths.processed_csv.parent.mkdir(parents=True, exist_ok=True)
    clean_df.to_csv(paths.processed_csv, index=False)
    logger.info("Cleaned data saved to %s", paths.processed_csv)

    # LOAD
    conn = get_connection(paths.db)
    try:
        init_schema(conn, paths.schema)
        rows_in_db = load_sales(conn, clean_df, raw_records=len(raw_df))

        # ANALYSE
        result = {
            "records_before": cleaning_report["records_before"],
            "records_after": cleaning_report["records_after"],
            "rows_in_db": rows_in_db,
            "cleaning_report": cleaning_report,
            "database": paths.db,
            "processed_csv": paths.processed_csv,
        }
        if make_outputs:
            queries = load_queries(paths.queries)
            result["charts"] = create_charts(conn, queries, paths.charts_dir)
            result["report"] = generate_summary_report(conn, queries, paths.report, cleaning_report)
    finally:
        conn.close()

    logger.info("=== Pipeline finished successfully ===")
    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Retail Sales ETL and Analytics Pipeline")
    parser.add_argument("--skip-outputs", action="store_true", help="skip charts and the summary report")
    args = parser.parse_args(argv)

    paths = Paths.from_root()
    setup_logging(paths.logs_dir)
    try:
        result = run_pipeline(paths, make_outputs=not args.skip_outputs)
    except (ExtractionError, ValueError, DatabaseLoadError, AnalyticsError) as exc:
        logger.error("Pipeline failed: %s", exc)
        return 1
    except Exception:  # unexpected bug: log the full traceback
        logger.exception("Unexpected error")
        return 1

    print(f"\nRecords before cleaning: {result['records_before']}")
    print(f"Records after cleaning : {result['records_after']}")
    print(f"Rows in database       : {result['rows_in_db']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
