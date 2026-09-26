"""Shared data models for the policy monitor pipeline."""
from __future__ import annotations

from typing import List, Optional
from pydantic import BaseModel, Field

VALID_CATEGORIES = [
    "Strategic & Defense",
    "Diplomacy & Regional Affairs",
    "Capitol Hill & Legislation",
    "American Jewry & Civil Society",
]


class RawItem(BaseModel):
    """A single feed entry before analysis."""
    url_hash: str
    title: str
    link: str
    source: str
    feed_category: str
    published_iso: str
    summary: str = ""


class AnalyzedItem(BaseModel):
    """A feed entry after Claude has scored and summarized it."""
    url_hash: str
    title: str
    link: str
    source: str
    published_iso: str
    fetched_iso: str
    category: str = Field(description="One of VALID_CATEGORIES")
    importance_score: int = Field(ge=1, le=5)
    bluf: str
    implications: List[str]

    def to_dict(self) -> dict:
        return self.model_dump()


class AnalysisResult(BaseModel):
    """Raw JSON shape we ask Claude to return for one item."""
    importance_score: int = Field(ge=1, le=5)
    bluf: str
    implications: List[str]
    category: str
