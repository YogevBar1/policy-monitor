"""Fetch feeds, filter to the lookback window, and de-duplicate against
previously-seen items.

De-duplication is done via a normalized-URL sha256 hash stored in
data/seen_hashes.json. That file is committed back to the repo by the
GitHub Actions workflow after every run, so state persists across days
without needing an external database.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List
from urllib.parse import urlsplit, urlunsplit

import feedparser
import requests
from dateutil import parser as dateparser

from .models import RawItem

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT = 20
USER_AGENT = (
    "Mozilla/5.0 (compatible; PolicyMonitorBot/1.0; "
    "+https://github.com/) PolicyMonitor/1.0"
)

TAG_RE = re.compile(r"<[^>]+>")


def _strip_html(text: str) -> str:
    if not text:
        return ""
    text = TAG_RE.sub(" ", text)
    return re.sub(r"\s+", " ", text).strip()


def _normalize_url(url: str) -> str:
    """Strip tracking params and trailing slashes so the same article
    reached via different query strings still hashes the same."""
    parts = urlsplit(url)
    # Drop query string entirely for dedup purposes -- most tracking
    # params (utm_*, etc.) live there and article identity lives in the path.
    normalized = urlunsplit((parts.scheme, parts.netloc.lower(), parts.path.rstrip("/"), "", ""))
    return normalized


def hash_url(url: str) -> str:
    return hashlib.sha256(_normalize_url(url).encode("utf-8")).hexdigest()


def load_seen_hashes(path: Path) -> Dict[str, str]:
    """Returns {hash: iso_date_first_seen}."""
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        logger.warning("Could not parse %s, starting fresh", path)
        return {}


def save_seen_hashes(path: Path, seen: Dict[str, str], retention_days: int) -> None:
    """Persist seen hashes, trimming anything older than retention_days
    so the file doesn't grow forever."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
    trimmed = {}
    for h, iso_date in seen.items():
        try:
            if dateparser.isoparse(iso_date) >= cutoff:
                trimmed[h] = iso_date
        except (ValueError, TypeError):
            continue
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(trimmed, indent=2, ensure_ascii=False), encoding="utf-8")


def _entry_published_dt(entry) -> datetime | None:
    for key in ("published_parsed", "updated_parsed"):
        struct = getattr(entry, key, None)
        if struct:
            try:
                return datetime(*struct[:6], tzinfo=timezone.utc)
            except (TypeError, ValueError):
                continue
    # Fall back to parsing string fields if struct_time wasn't set.
    for key in ("published", "updated"):
        val = entry.get(key) if hasattr(entry, "get") else None
        if val:
            try:
                dt = dateparser.parse(val)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt.astimezone(timezone.utc)
            except (ValueError, TypeError, OverflowError):
                continue
    return None


def fetch_feed_entries(feed_url: str) -> List[feedparser.FeedParserDict]:
    """Fetch a feed's raw bytes ourselves (with a real User-Agent and
    timeout) then hand them to feedparser, since some sites block the
    default feedparser UA or hang without a timeout."""
    try:
        resp = requests.get(feed_url, headers={"User-Agent": USER_AGENT}, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        parsed = feedparser.parse(resp.content)
    except Exception as exc:  # noqa: BLE001 - a single bad feed must not kill the run
        logger.warning("Feed error for %s: %s", feed_url, exc)
        return []

    if parsed.bozo and not parsed.entries:
        logger.warning("Feed %s parsed with errors and no entries: %s", feed_url, parsed.get("bozo_exception"))
    return parsed.entries or []


def collect_new_items(
    sources: List[dict],
    lookback_hours: int,
    seen: Dict[str, str],
) -> List[RawItem]:
    """Walk every configured feed, keep entries inside the lookback
    window, and drop anything already in `seen`. Mutates `seen` in
    place by adding freshly-collected hashes (caller persists it)."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)
    now_iso = datetime.now(timezone.utc).isoformat()
    new_items: List[RawItem] = []

    for feed in sources:
        name = feed["name"]
        url = feed["url"]
        category = feed["category"]

        entries = fetch_feed_entries(url)
        logger.info("Fetched %d entries from %s", len(entries), name)

        for entry in entries:
            link = entry.get("link")
            title = entry.get("title")
            if not link or not title:
                continue

            published_dt = _entry_published_dt(entry)
            if published_dt is None:
                # Some feeds (esp. Google News) omit reliable dates; include
                # rather than silently drop, tagged with fetch time.
                published_dt = datetime.now(timezone.utc)
            elif published_dt < cutoff:
                continue

            h = hash_url(link)
            if h in seen:
                continue

            summary = _strip_html(entry.get("summary", "") or entry.get("description", ""))[:600]

            new_items.append(
                RawItem(
                    url_hash=h,
                    title=title.strip(),
                    link=link,
                    source=name,
                    feed_category=category,
                    published_iso=published_dt.isoformat(),
                    summary=summary,
                )
            )
            seen[h] = now_iso

    logger.info("Collected %d new items across %d feeds", len(new_items), len(sources))
    return new_items
