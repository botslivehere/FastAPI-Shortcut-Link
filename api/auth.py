import os
from datetime import datetime, timedelta
from typing import Optional
from fastapi import APIRouter, Depends, Header, HTTPException
import bcrypt
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from db import User, get_db
from schemas import UserAuth

router = APIRouter()

SECRET = os.getenv("SECRET_KEY", "changeme")
ALGO = "HS256"

def get_hash_pw(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

def check_pw(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())

def make_token(username: str) -> str:
    return jwt.encode({"sub": username, "exp": datetime.utcnow() + timedelta(days=1)}, SECRET, ALGO)

async def get_user(token: str, db: AsyncSession) -> User:
    try:
        sub = jwt.decode(token, SECRET, algorithms=[ALGO]).get("sub")
    except JWTError:
        sub = None
    if not sub:
        raise HTTPException(401, "Invalid token")
    u = (await db.execute(select(User).where(User.username == sub))).scalars().first()
    if not u:
        raise HTTPException(401, "User not found")
    return u

async def auth_user(auth: str = Header(None, alias="authorization"), db: AsyncSession = Depends(get_db)) -> User:
    if not auth or not auth.startswith("Bearer "):
        raise HTTPException(401, "Missing token")
    return await get_user(auth.split()[1], db)

async def guest_user(auth: str = Header(None, alias="authorization"), db: AsyncSession = Depends(get_db)) -> Optional[User]:
    if auth and auth.startswith("Bearer "):
        try:
            return await get_user(auth.split()[1], db)
        except HTTPException:
            pass
    return None

@router.post("/register")
async def register(data: UserAuth, db: AsyncSession = Depends(get_db)):
    if (await db.execute(select(User).where(User.username == data.username))).scalars().first():
        raise HTTPException(400, "Username taken")
    db.add(User(username=data.username, hashed_password=get_hash_pw(data.password)))
    await db.commit()
    return {"message": "Registered"}

@router.post("/login")
async def login(data: UserAuth, db: AsyncSession = Depends(get_db)):
    u = (await db.execute(select(User).where(User.username == data.username))).scalars().first()
    if not u or not check_pw(data.password, u.hashed_password):
        raise HTTPException(401, "Bad credentials")
    return {"access_token": make_token(data.username), "token_type": "bearer"}