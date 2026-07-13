import re, secrets
from datetime import datetime, timedelta, timezone
from fastapi import Cookie, Depends, HTTPException, WebSocket
from pwdlib import PasswordHash
from sqlalchemy import select
from sqlalchemy.orm import Session as DBSession
from .config import settings
from .database import DB, Session, User

hasher = PasswordHash.recommended()

def db_session():
    with DB() as db: yield db

def validate_credentials(username: str, password: str):
    if not re.fullmatch(r"[A-Za-z0-9_\u4e00-\u9fff]{3,24}", username): raise HTTPException(400, "用户名需为3-24位中文、字母、数字或下划线")
    if len(password) < 8 or len(password) > 128: raise HTTPException(400, "密码需为8-128位")

def create_session(db: DBSession, user_id: int):
    token = secrets.token_urlsafe(32)
    db.add(Session(token=token, user_id=user_id, expires_at=datetime.now(timezone.utc).replace(tzinfo=None)+timedelta(days=settings.session_days)))
    db.commit(); return token

def user_from_token(db: DBSession, token: str | None):
    if not token: return None
    row = db.scalar(select(Session).where(Session.token == token))
    if not row or row.expires_at < datetime.now(timezone.utc).replace(tzinfo=None): return None
    return db.get(User, row.user_id)

def current_user(mgw_session: str | None = Cookie(None), db: DBSession = Depends(db_session)):
    user = user_from_token(db, mgw_session)
    if not user: raise HTTPException(401, "请先登录")
    return user

def websocket_user(ws: WebSocket):
    token = ws.cookies.get("mgw_session") or ws.query_params.get("token")
    with DB() as db: return user_from_token(db, token)
