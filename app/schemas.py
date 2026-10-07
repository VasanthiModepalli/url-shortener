from datetime import datetime
from pydantic import BaseModel, HttpUrl


class LinkCreate(BaseModel):
    url: HttpUrl


class LinkOut(BaseModel):
    code: str
    short_url: str
    original_url: str
    created_at: datetime


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
    total_clicks: int
    clicks_per_day: list[DayCount]
    top_referrers: list[ReferrerCount]