from datetime import datetime, timezone
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker
from .config import settings

class Base(DeclarativeBase): pass

class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(24), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))

class Session(Base):
    __tablename__ = "sessions"
    token: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime)

class PlayerStats(Base):
    __tablename__ = "player_stats"
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    matches: Mapped[int] = mapped_column(Integer, default=0)
    wins: Mapped[int] = mapped_column(Integer, default=0)
    kills: Mapped[int] = mapped_column(Integer, default=0)
    damage: Mapped[int] = mapped_column(Integer, default=0)

class Match(Base):
    __tablename__ = "matches"
    id: Mapped[int] = mapped_column(primary_key=True)
    mode: Mapped[str] = mapped_column(String(16))
    winner: Mapped[str | None] = mapped_column(String(32), nullable=True)
    turns: Mapped[int] = mapped_column(default=0)
    finished: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))

class MatchParticipant(Base):
    __tablename__ = "match_participants"
    id: Mapped[int] = mapped_column(primary_key=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id"),index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"),nullable=True,index=True)
    name: Mapped[str] = mapped_column(String(32))
    team: Mapped[str] = mapped_column(String(32))
    soldiers: Mapped[int] = mapped_column(Integer,default=2)
    kills: Mapped[int] = mapped_column(Integer,default=0)
    won: Mapped[bool] = mapped_column(Boolean,default=False)
    is_ai: Mapped[bool] = mapped_column(Boolean,default=False)

class MatchReplay(Base):
    __tablename__ = "match_replays"
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id"),primary_key=True)
    payload: Mapped[str] = mapped_column(Text)

engine = create_engine(settings.database_url, connect_args={"check_same_thread": False} if settings.database_url.startswith("sqlite") else {})
DB = sessionmaker(engine, expire_on_commit=False)

def init_db(): Base.metadata.create_all(engine)
