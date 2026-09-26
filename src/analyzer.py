"""Send each new item to Claude for scoring, BLUF generation, and
categorization.

Uses a lightweight/fast Claude model by default since this runs once a
day over a batch of short news items and doesn't need a frontier model.
Override with the ANALYSIS_MODEL env var if you'd rather point it at a
different model.
"""
from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import List, Optional

import anthropic

from .models import AnalyzedItem, RawItem, VALID_CATEGORIES

logger = logging.getLogger(__name__)

DEFAULT_MODEL = os.environ.get("ANALYSIS_MODEL", "claude-haiku-4-5-20251001")
MAX_RETRIES = 2
RETRY_BACKOFF_SECONDS = 3

SYSTEM_PROMPT = f"""You are a policy analyst supporting a Jewish communal \
and government-affairs intern who tracks US-Israel relations and issues \
affecting American Jewry. For each news item you are given, assess its \
actual strategic and policy significance -- not just whether it mentions \
Israel or Jewish topics in passing.

Respond with ONLY a single JSON object (no markdown fences, no preamble), \
matching this exact shape:

{{
  "importance_score": <integer 1-5, where 5 = major strategic/policy \
development (e.g. a new sanctions bill, a shift in US defense posture, a \
high-profile antisemitism incident with policy fallout) and 1 = routine or \
low-impact news>,
  "bluf": "<one crisp sentence, Bottom-Line-Up-Front, stating what happened \
and why it matters>",
  "implications": ["<analytical bullet 1>", "<analytical bullet 2>", \
"<optional analytical bullet 3>"],
  "category": "<exactly one of: {', '.join(VALID_CATEGORIES)}>"
}}

The "implications" bullets should be genuinely analytical -- strategic \
reasoning about what this could mean for Israeli policymakers or Jewish \
communal leadership -- not a restatement of the headline. Keep the bluf \
under 35 words and each implication under 30 words."""


def _build_user_prompt(item: RawItem) -> str:
    return (
        f"SOURCE: {item.source}\n"
        f"TITLE: {item.title}\n"
        f"PUBLISHED: {item.published_iso}\n"
        f"SUMMARY/EXCERPT: {item.summary or '(no summary available)'}\n\n"
        "Analyze this item per your instructions."
    )


def _parse_response_text(text: str) -> Optional[dict]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:]
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        logger.warning("Could not parse Claude JSON response: %s", cleaned[:200])
        return None


def _analyze_one(client: anthropic.Anthropic, item: RawItem, model: str) -> Optional[AnalyzedItem]:
    last_error = None
    for attempt in range(MAX_RETRIES + 1):
        try:
            response = client.messages.create(
                model=model,
                max_tokens=500,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": _build_user_prompt(item)}],
            )
            text_blocks = [b.text for b in response.content if getattr(b, "type", None) == "text"]
            parsed = _parse_response_text("\n".join(text_blocks))
            if parsed is None:
                return None

            category = parsed.get("category", "").strip()
            if category not in VALID_CATEGORIES:
                # Fall back to the feed's own category tag if Claude drifts.
                category = item.feed_category

            score = int(parsed.get("importance_score", 1))
            score = max(1, min(5, score))

            implications = parsed.get("implications") or []
            if isinstance(implications, str):
                implications = [implications]

            return AnalyzedItem(
                url_hash=item.url_hash,
                title=item.title,
                link=item.link,
                source=item.source,
                published_iso=item.published_iso,
                fetched_iso=datetime.now(timezone.utc).isoformat(),
                category=category,
                importance_score=score,
                bluf=str(parsed.get("bluf", "")).strip(),
                implications=[str(x).strip() for x in implications][:3],
            )
        except anthropic.RateLimitError as exc:
            last_error = exc
            time.sleep(RETRY_BACKOFF_SECONDS * (attempt + 1))
        except anthropic.APIError as exc:
            last_error = exc
            logger.warning("Claude API error on attempt %d for %r: %s", attempt + 1, item.title, exc)
            time.sleep(RETRY_BACKOFF_SECONDS)
        except Exception as exc:  # noqa: BLE001 - one bad item must not kill the run
            last_error = exc
            logger.warning("Unexpected error analyzing %r: %s", item.title, exc)
            break

    logger.error("Giving up on %r after retries: %s", item.title, last_error)
    return None


def analyze_items(items: List[RawItem], api_key: Optional[str] = None, model: str = DEFAULT_MODEL) -> List[AnalyzedItem]:
    """Analyze a batch of raw items via the Claude API. Items that fail
    analysis after retries are skipped (logged, not raised) so a single
    bad response doesn't sink the whole daily run."""
    api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY is not set. Add it as a GitHub Actions secret "
            "and reference it in the workflow's env, or export it locally."
        )

    client = anthropic.Anthropic(api_key=api_key)
    results: List[AnalyzedItem] = []

    for i, item in enumerate(items, start=1):
        logger.info("Analyzing item %d/%d: %s", i, len(items), item.title[:80])
        analyzed = _analyze_one(client, item, model)
        if analyzed:
            results.append(analyzed)

    logger.info("Successfully analyzed %d/%d items", len(results), len(items))
    return results
