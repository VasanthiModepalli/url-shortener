from datetime import datetime, timezone

from fastapi import FastAPI, Depends, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from . import models, schemas
from .database import engine, get_db
from .utils import generate_code

models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="URL Shortener")

# Aliases that would clash with real routes
RESERVED = {"docs", "redoc", "openapi.json", "shorten", "stats", "links"}


def as_utc(dt: datetime) -> datetime:
    """SQLite drops timezone info, so treat naive datetimes as UTC."""
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def get_link_or_404(code: str, db: Session) -> models.Link:
    link = db.scalar(select(models.Link).where(models.Link.code == code))
    if link is None:
        raise HTTPException(status_code=404, detail="Short link not found")
    return link


@app.post("/shorten", response_model=schemas.LinkOut, status_code=201)
def shorten(payload: schemas.LinkCreate, request: Request, db: Session = Depends(get_db)):
    if payload.expires_at is not None and as_utc(payload.expires_at) <= datetime.now(timezone.utc):
        raise HTTPException(status_code=422, detail="expires_at must be in the future")

    if payload.alias:
        if payload.alias.lower() in RESERVED:
            raise HTTPException(status_code=409, detail="This alias is reserved")
        taken = db.scalar(select(models.Link).where(models.Link.code == payload.alias))
        if taken:
            raise HTTPException(status_code=409, detail="This alias is already taken")
        code = payload.alias
    else:
        # Retry in the rare case a generated code already exists
        for _ in range(5):
            code = generate_code()
            exists = db.scalar(select(models.Link).where(models.Link.code == code))
            if not exists:
                break
        else:
            raise HTTPException(status_code=500, detail="Could not generate a unique code")

    link = models.Link(
        code=code,
        original_url=str(payload.url),
        expires_at=as_utc(payload.expires_at) if payload.expires_at else None,
    )
    db.add(link)
    db.commit()
    db.refresh(link)

    return schemas.LinkOut(
        code=link.code,
        short_url=f"{request.base_url}{link.code}",
        original_url=link.original_url,
        created_at=link.created_at,
        expires_at=link.expires_at,
    )


@app.get("/stats/{code}", response_model=schemas.StatsOut)
def stats(code: str, db: Session = Depends(get_db)):
    link = get_link_or_404(code, db)

    total = db.scalar(
        select(func.count(models.Click.id)).where(models.Click.link_id == link.id)
    )

    day = func.date(models.Click.clicked_at)
    per_day = db.execute(
        select(day, func.count())
        .where(models.Click.link_id == link.id)
        .group_by(day)
        .order_by(day)
    ).all()

    top_referrers = db.execute(
        select(models.Click.referrer, func.count())
        .where(models.Click.link_id == link.id, models.Click.referrer.is_not(None))
        .group_by(models.Click.referrer)
        .order_by(func.count().desc())
        .limit(5)
    ).all()

    return schemas.StatsOut(
        code=link.code,
        original_url=link.original_url,
        created_at=link.created_at,
        expires_at=link.expires_at,
        total_clicks=total,
        clicks_per_day=[schemas.DayCount(date=d, clicks=n) for d, n in per_day],
        top_referrers=[schemas.ReferrerCount(referrer=r, clicks=n) for r, n in top_referrers],
    )


@app.delete("/links/{code}", status_code=204)
def delete_link(code: str, db: Session = Depends(get_db)):
    link = get_link_or_404(code, db)
    db.delete(link)
    db.commit()
    return Response(status_code=204)

@app.get("/", include_in_schema=False)
def home():
    return RedirectResponse(url="/docs")

@app.get("/{code}")
def redirect(code: str, request: Request, db: Session = Depends(get_db)):
    link = get_link_or_404(code, db)

    if link.expires_at is not None and as_utc(link.expires_at) <= datetime.now(timezone.utc):
        raise HTTPException(status_code=410, detail="This link has expired")

    # Log the click before redirecting
    user_agent = request.headers.get("user-agent")
    referrer = request.headers.get("referer")  # the HTTP header is spelled "referer"
    click = models.Click(
        link_id=link.id,
        user_agent=user_agent[:512] if user_agent else None,
        referrer=referrer[:2048] if referrer else None,
    )
    db.add(click)
    db.commit()

    return RedirectResponse(url=link.original_url, status_code=307)