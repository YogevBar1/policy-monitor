#!/usr/bin/env python3
"""Entry point for the US-Israel Relations & American Jewry policy monitor.

Run daily (via GitHub Actions cron) or manually:

    python main.py

Environment variables:
    ANTHROPIC_API_KEY   required - used to score/summarize new items
    ANALYSIS_MODEL      optional - overrides the default Claude model
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

import yaml

from src import scraper, analyzer, history, build_dashboard

ROOT = Path(__file__).parent
CONFIG_PATH = ROOT / "config" / "sources.yaml"
SEEN_HASHES_PATH = ROOT / "data" / "seen_hashes.json"
HISTORY_PATH = ROOT / "data" / "history.json"
TEMPLATES_DIR = ROOT / "templates"
DIST_INDEX = ROOT / "dist" / "index.html"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("main")


def load_config() -> dict:
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def main() -> int:
    config = load_config()
    feeds = config["feeds"]
    lookback_hours = config.get("lookback_hours", 24)
    retention_days = config.get("history_retention_days", 14)

    # 1. Load persisted dedup state and history archive.
    seen_hashes = scraper.load_seen_hashes(SEEN_HASHES_PATH)
    existing_history = history.load_history(HISTORY_PATH)
    logger.info("Loaded %d seen hashes and %d archived items", len(seen_hashes), len(existing_history))

    # 2. Fetch feeds, keep only new items inside the lookback window.
    new_raw_items = scraper.collect_new_items(feeds, lookback_hours, seen_hashes)

    # 3. Analyze new items via Claude (skip the API entirely if nothing's new).
    newly_analyzed = []
    if new_raw_items:
        try:
            newly_analyzed = analyzer.analyze_items(new_raw_items)
        except RuntimeError as exc:
            logger.error(str(exc))
            return 1
    else:
        logger.info("No new items since last run; skipping analysis.")

    # 4. Merge into history and trim to retention window.
    merged_history = history.append_and_save(
        HISTORY_PATH, existing_history, newly_analyzed, retention_days
    )

    # 5. Persist updated dedup state (workflow commits this back to the repo).
    scraper.save_seen_hashes(SEEN_HASHES_PATH, seen_hashes, retention_days)

    # 6. Rebuild the dashboard from whatever's inside the last 24h, so the
    #    site still renders sensibly even on a run with zero new items.
    window_items = history.items_within_hours(merged_history, lookback_hours)
    build_dashboard.build_dashboard(window_items, TEMPLATES_DIR, DIST_INDEX)

    logger.info(
        "Run complete: %d new items analyzed, %d items in dashboard window, %d in full archive.",
        len(newly_analyzed), len(window_items), len(merged_history),
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
