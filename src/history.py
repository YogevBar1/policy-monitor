"""Persistence for analyzed items across daily runs.

Uses a single committed JSON file (data/history.json) rather than a
database engine -- it's small, human-diffable in PRs, and needs no
extra infra. If the archive ever grows large enough to matter, swap
this module for SQLite without touching callers (same function
signatures).
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List

from dateutil import parser as dateparser

from .models import AnalyzedItem

logger = logging.getLogger(__name__)


def load_history(path: Path) -> List[AnalyzedItem]:
    if not path.exists():
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        cleaned = []
        for entry in raw:
            if not isinstance(entry, dict):
                continue
            if "implications" not in entry:
                entry["implications"] = entry.get("strategic_implications", [])
            if "fetched_iso" not in entry:
                entry["fetched_iso"] = datetime.now(timezone.utc).isoformat()
            try:
                cleaned.append(AnalyzedItem(**entry))
            except Exception:
                continue
        return cleaned
    except (json.JSONDecodeError, OSError, TypeError) as exc:
        logger.warning("Could not load history at %s (%s), starting fresh", path, exc)
        return []


def append_and_save(
    path: Path,
    existing: List[AnalyzedItem],
    new_items: List[dict | AnalyzedItem],
    retention_days: int,
) -> List[AnalyzedItem]:
    """Merge new items into existing history, drop anything older than
    retention_days (by published date), de-dupe by url_hash, and write
    the result back out. Returns the merged, trimmed list."""
    by_hash = {item.url_hash: item for item in existing}
    
    for raw in new_items:
        if isinstance(raw, dict):
            try:
                item = AnalyzedItem(**raw)
            except Exception as e:
                logger.warning("Could not convert item to AnalyzedItem: %s", e)
                continue
        else:
            item = raw
            
        by_hash[item.url_hash] = item

    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
    kept = []
    for item in by_hash.values():
        try:
            pub_dt = dateparser.isoparse(item.published_iso)
        except (ValueError, TypeError):
            pub_dt = datetime.now(timezone.utc)
        if pub_dt >= cutoff:
            kept.append(item)

    kept.sort(key=lambda i: i.published_iso, reverse=True)

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps([i.to_dict() for i in kept], indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return kept


def items_within_hours(items: List[AnalyzedItem], hours: int) -> List[AnalyzedItem]:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    result = []
    for item in items:
        try:
            pub_dt = dateparser.isoparse(item.published_iso)
        except (ValueError, TypeError):
            continue
        if pub_dt >= cutoff:
            result.append(item)
    return result