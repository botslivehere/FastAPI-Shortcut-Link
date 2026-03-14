import os
import secrets
import string
import redis.asyncio as aioredis
from datetime import datetime, timedelta, timezone
from typing import Optional
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from auth import auth_user, guest_user
from db import Link, Session, User, get_db
from schemas import LinkCreate, LinkOut, LinkUpdate

TTL = 3600
redis_client: aioredis.Redis = aioredis.from_url(
    os.getenv("REDIS_URL", "changeme"), decode_responses=True
)

router = APIRouter()

def create_random_url_prefix() -> str:
    return "".join(secrets.choice(string.ascii_letters + string.digits) for _ in range(6))

async def get_link(code: str, db: AsyncSession) -> Link:
    link = (await db.execute(select(Link).where(Link.short_code == code))).scalars().first()
    if not link:
        raise HTTPException(404, "Not found")
    return link

async def inc_link_counter(code: str) -> None:
    async with Session() as s:
        link = (await s.execute(select(Link).where(Link.short_code == code))).scalars().first()
        if link:
            link.clicks_count += 1
            link.last_used_at = datetime.now(timezone.utc).replace(tzinfo=None)
            await s.commit()

@router.post("/links/shorten", response_model=LinkOut)
async def shorten(data: LinkCreate, db: AsyncSession = Depends(get_db), user: Optional[User] = Depends(guest_user)):
    code = data.custom_alias
    if code:
        if (await db.execute(select(Link).where(Link.short_code == code))).scalars().first():
            raise HTTPException(400, "Alias taken")
    else:
        while True:
            code = create_random_url_prefix()
            if not (await db.execute(select(Link).where(Link.short_code == code))).scalars().first():
                break
    link = Link(short_code=code, original_url=data.original_url, custom_alias=data.custom_alias,
                expires_at=data.expires_at, project=data.project, user_id=user.id if user else None)
    db.add(link)
    await db.commit()
    await db.refresh(link)
    return link

@router.get("/links/search")
async def search(original_url: str, db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(Link).where(Link.original_url == original_url))).scalars().all()
    return [{"short_code": l.short_code, "original_url": l.original_url} for l in rows]

@router.get("/links/expired")
async def expired(db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(
        select(Link).where(Link.expires_at.isnot(None), Link.expires_at < datetime.now(timezone.utc).replace(tzinfo=None))
    )).scalars().all()
    return [{"short_code": l.short_code, "original_url": l.original_url,
             "expires_at": l.expires_at, "clicks_count": l.clicks_count} for l in rows]

@router.get("/links/{short_code}/stats")
async def stats(short_code: str, db: AsyncSession = Depends(get_db)):
    l = await get_link(short_code, db)
    return {"original_url": l.original_url, "created_at": l.created_at,
            "clicks_count": l.clicks_count, "last_used_at": l.last_used_at}

@router.get("/links/{short_code}")
async def redirect(short_code: str, bg: BackgroundTasks, db: AsyncSession = Depends(get_db)):
    cached = await redis_client.get(f"link:{short_code}")
    if cached == "EXPIRED":
        raise HTTPException(410, "Expired")
    if not cached:
        l = await get_link(short_code, db)
        if l.expires_at and l.expires_at < datetime.now(timezone.utc).replace(tzinfo=None):
            await redis_client.setex(f"link:{short_code}", TTL, "EXPIRED")
            raise HTTPException(410, "Expired")
        cached = l.original_url
        await redis_client.setex(f"link:{short_code}", TTL, cached)
    bg.add_task(inc_link_counter, short_code)
    return RedirectResponse(cached, status_code=307)

@router.put("/links/{short_code}")
async def update(short_code: str, data: LinkUpdate, db: AsyncSession = Depends(get_db), user: User = Depends(auth_user)):
    l = await get_link(short_code, db)
    if l.user_id != user.id:
        raise HTTPException(403, "Forbidden")
    l.original_url = data.new_original_url
    await db.commit()
    await redis_client.delete(f"link:{short_code}")
    return {"message": "Updated"}

@router.delete("/links/{short_code}")
async def remove(short_code: str, db: AsyncSession = Depends(get_db), user: User = Depends(auth_user)):
    l = await get_link(short_code, db)
    if l.user_id != user.id:
        raise HTTPException(403, "Forbidden")
    await db.delete(l)
    await db.commit()
    await redis_client.delete(f"link:{short_code}")
    return {"message": "Deleted"}

@router.get("/projects/{project}/links")
async def by_project(project: str, db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(Link).where(Link.project == project))).scalars().all()
    return {"project": project, "links": [{"short_code": l.short_code, "original_url": l.original_url} for l in rows]}

@router.delete("/secret/unused/cleanup")
async def cleanup(days: int = 30, db: AsyncSession = Depends(get_db)):
    cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=days)
    res = await db.execute(delete(Link).where(
        (Link.last_used_at < cutoff) | (Link.last_used_at.is_(None) & (Link.created_at < cutoff))
    ))
    await db.commit()
    return {"deleted": res.rowcount}