from fastapi import FastAPI, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from . import models, schemas
from .database import engine, get_db
from .utils import generate_code

models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="URL Shortener")


def get_link_or_404(code: str, db: Session) -> models.Link:
    link = db.scalar(select(models.Link).where(models.Link.code == code))
    if link is None:
        raise HTTPException(status_code=404, detail="Short link not found")
    return link


@app.post("/shorten", response_model=schemas.LinkOut, status_code=201)
def shorten(payload: schemas.LinkCreate, request: Request, db: Session = Depends(get_db)):
    # Retry in the rare case a generated code already exists
    for _ in range(5):
        code = generate_code()
        exists = db.scalar(select(models.Link).where(models.Link.code == code))
        if not exists:
            break
    else:
        raise HTTPException(status_code=500, detail="Could not generate a unique code")

    link = models.Link(code=code, original_url=str(payload.url))
    db.add(link)
    db.commit()
    db.refresh(link)

    return schemas.LinkOut(
        code=link.code,
        short_url=f"{request.base_url}{link.code}",
        original_url=link.original_url,
        created_at=link.created_at,
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
        total_clicks=total,
        clicks_per_day=[schemas.DayCount(date=d, clicks=n) for d, n in per_day],
        top_referrers=[schemas.ReferrerCount(referrer=r, clicks=n) for r, n in top_referrers],
    )


@app.get("/{code}")
def redirect(code: str, request: Request, db: Session = Depends(get_db)):
    link = get_link_or_404(code, db)

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