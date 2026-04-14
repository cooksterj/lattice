#!/usr/bin/env python3
"""
Lightweight demo for testing targeted execution and context menu features.

A shallow, wide graph with two groups and a few standalone assets.
Every asset sleeps long enough to observe status transitions in the UI.

Run with:
    uv run python examples/web_demo_lite.py

Then open http://localhost:8000 in your browser.

Test scenarios:
    1. Right-click "ingest_api" -> Run + Downstream
       -> runs ingest_api, etl/normalize, etl/dedupe, summary, report
    2. Right-click "etl/normalize" -> Run + Downstream
       -> runs normalize, dedupe, summary (not clean, not report)
    3. Right-click "ingest_csv" -> Run + Downstream
       -> runs ingest_csv, etl/clean, report (not summary)
    4. Click into ETL group during execution
       -> nodes should show live status
    5. Navigate back to overview
       -> group node should reflect aggregate status
"""

import logging
import time

from lattice import AssetKey, SQLiteRunHistoryStore, asset, configure_logging
from lattice.web import serve

configure_logging()
logger = logging.getLogger("lattice")


# -- Standalone source assets (no deps, no group) -------------------------


@asset
def ingest_api() -> list[dict]:
    """Pull records from an external API."""
    logger.info("Calling external API...")
    time.sleep(3)
    return [{"id": 1, "source": "api"}]


@asset
def ingest_csv() -> list[dict]:
    """Read records from a CSV drop."""
    logger.info("Reading CSV file...")
    time.sleep(3)
    return [{"id": 2, "source": "csv"}]


# -- ETL group -------------------------------------------------------------


@asset(group="etl", deps=["ingest_api"])
def normalize(ingest_api: list[dict]) -> list[dict]:
    """Normalize API data into standard schema."""
    logger.info("Normalizing %d records...", len(ingest_api))
    time.sleep(4)
    return [{"id": r["id"], "clean": True} for r in ingest_api]


@asset(group="etl", deps=[AssetKey(name="normalize", group="etl")])
def dedupe(normalize: list[dict]) -> list[dict]:
    """Remove duplicate records."""
    logger.info("Deduplicating %d records...", len(normalize))
    time.sleep(4)
    return list({r["id"]: r for r in normalize}.values())


@asset(group="etl", deps=["ingest_csv"])
def clean(ingest_csv: list[dict]) -> list[dict]:
    """Clean and validate CSV data."""
    logger.info("Cleaning %d CSV records...", len(ingest_csv))
    time.sleep(4)
    return [r for r in ingest_csv if r.get("id")]


# -- Standalone downstream assets ------------------------------------------


@asset(deps=[AssetKey(name="dedupe", group="etl")])
def summary(dedupe: list[dict]) -> dict:
    """Summarise deduplicated records (only depends on dedupe branch)."""
    logger.info("Summarising %d records...", len(dedupe))
    time.sleep(3)
    return {"count": len(dedupe)}


@asset(
    deps=[
        AssetKey(name="dedupe", group="etl"),
        AssetKey(name="clean", group="etl"),
    ],
)
def report(dedupe: list[dict], clean: list[dict]) -> dict:
    """Merge ETL outputs into a final report."""
    logger.info("Building report from %d + %d records...", len(dedupe), len(clean))
    time.sleep(3)
    return {"total": len(dedupe) + len(clean)}


@report.check
def report_non_empty(data: dict) -> bool:
    """Report must contain at least one record."""
    return data.get("total", 0) > 0


if __name__ == "__main__":
    serve(history_store=SQLiteRunHistoryStore())
