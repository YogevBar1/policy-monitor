"""Render the analyzed items into a static dist/index.html dashboard."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import List

from dateutil import parser as dateparser
from jinja2 import Environment, FileSystemLoader, select_autoescape

from .models import AnalyzedItem, VALID_CATEGORIES

logger = logging.getLogger(__name__)

IST_OFFSET_HOURS = 5.5  # for display purposes only; server runs in UTC


def _format_display_time(iso_str: str) -> str:
    try:
        dt = dateparser.isoparse(iso_str)
        return dt.strftime("%b %d, %Y %H:%M UTC")
    except (ValueError, TypeError):
        return iso_str


def _prepare_item(item: AnalyzedItem) -> dict:
    d = item.to_dict()
    d["published_display"] = _format_display_time(item.published_iso)
    return d


def build_dashboard(
    items: List[AnalyzedItem],
    templates_dir: Path,
    output_path: Path,
) -> None:
    env = Environment(
        loader=FileSystemLoader(str(templates_dir)),
        autoescape=select_autoescape(["html"]),
    )
    template = env.get_template("dashboard.html")

    prepared = [_prepare_item(i) for i in items]
    prepared.sort(key=lambda d: (-d["importance_score"], d["published_iso"]), reverse=False)
    # sort: highest score first, then most recent within same score
    prepared.sort(key=lambda d: d["published_iso"], reverse=True)
    prepared.sort(key=lambda d: d["importance_score"], reverse=True)

    high_priority = [d for d in prepared if d["importance_score"] >= 4]

    categories = []
    for cat_name in VALID_CATEGORIES:
        cat_items = [d for d in prepared if d["category"] == cat_name]
        categories.append({"name": cat_name, "entries": cat_items})

    metrics = {
        "total": len(prepared),
        "high_priority": len(high_priority),
        "sources": len({d["source"] for d in prepared}) or 0,
        "categories": len(VALID_CATEGORIES),
    }

    now_utc = datetime.now(timezone.utc)
    last_updated = now_utc.strftime("%b %d, %Y %H:%M UTC")

    html = template.render(
        last_updated=last_updated,
        metrics=metrics,
        high_priority_items=high_priority,
        categories=categories,
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")
    logger.info("Wrote dashboard to %s (%d items, %d high priority)", output_path, metrics["total"], metrics["high_priority"])
