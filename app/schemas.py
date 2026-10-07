from datetime import datetime
from pydantic import BaseModel, HttpUrl, Field


class LinkCreate(BaseModel):
    url: HttpUrl
    alias: str | None = Field(
        default=None, min_length=3, max_length=20, pattern=r"^[A-Za-z0-9_-]+$"
    )
    expires_at: datetime | None = None


class LinkOut(BaseModel):
    code: str
    short_url: str
    original_url: str
    created_at: datetime
    expires_at: datetime | None = None


class DayCount(BaseModel):
    date: str
    clicks: int


class ReferrerCount(BaseModel):
    referrer: str
    clicks: int


class StatsOut(BaseModel):
    code: str
    original_url: str
    created_at: datetime
    expires_at: datetime | None = None
    total_clicks: int
    clicks_per_day: list[DayCount]
    top_referrers: list[ReferrerCount]