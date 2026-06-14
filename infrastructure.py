"""
البنية التحتية: PostgreSQL + Redis + JWT
"""

import json
import redis
from datetime import datetime, timedelta, timezone
from typing import Optional, Any

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


# ─────────────────────────────────────────────
# Settings  (pydantic-settings v2)
# ─────────────────────────────────────────────
class Settings(BaseSettings):
    # API Keys — مطلوبة، ترفع خطأ واضحاً إن غابت
    anthropic_api_key: str
    secret_key: str

    # Database & Cache
    database_url: str
    redis_url: str = "redis://localhost:6379/0"

    # Security
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30

    # Claude
    claude_model: str   = "claude-sonnet-4-6"
    claude_max_tokens: int   = 16000
    claude_temperature: float = 0.0

    # pydantic-settings v2: يستبدل class Config
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,   # ANTHROPIC_API_KEY == anthropic_api_key
        extra="ignore",         # يتجاهل متغيرات .env الإضافية
    )

    # ── Validators ───────────────────────────
    @field_validator("anthropic_api_key")
    @classmethod
    def _api_key_not_placeholder(cls, v: str) -> str:
        if not v or v.startswith("your-"):
            raise ValueError(
                "ANTHROPIC_API_KEY غير مضبوط — عدّل ملف .env"
            )
        return v

    @field_validator("claude_temperature")
    @classmethod
    def _temp_range(cls, v: float) -> float:
        if not (0.0 <= v <= 1.0):
            raise ValueError("claude_temperature يجب أن يكون بين 0.0 و 1.0")
        return v

    @field_validator("access_token_expire_minutes")
    @classmethod
    def _token_expire_positive(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("access_token_expire_minutes يجب أن يكون أكبر من صفر")
        return v


settings = Settings()


# ─────────────────────────────────────────────
# PostgreSQL
# ─────────────────────────────────────────────
engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,       # يتحقق من الاتصال قبل كل استعلام
    pool_size=10,
    max_overflow=20,
    echo=False                # True لتفعيل SQL logging
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    """Dependency لـ FastAPI — يُغلق الجلسة تلقائياً"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """إنشاء الجداول عند بدء التطبيق"""
    from models import Base
    Base.metadata.create_all(bind=engine)
    print("✅ تم إنشاء جداول قاعدة البيانات")


# ─────────────────────────────────────────────
# Redis — جلسات المحادثة
# ─────────────────────────────────────────────
redis_client = redis.from_url(
    settings.redis_url,
    decode_responses=True,
    socket_connect_timeout=5,
    retry_on_timeout=True
)

CHAT_TTL = 60 * 60 * 24  # 24 ساعة


class ChatSessionStore:
    """إدارة جلسات المحادثة في Redis"""

    @staticmethod
    def _key(session_id: str) -> str:
        return f"chat:session:{session_id}"

    @staticmethod
    def get_history(session_id: str) -> list[dict]:
        raw = redis_client.get(ChatSessionStore._key(session_id))
        return json.loads(raw) if raw else []

    @staticmethod
    def append_message(session_id: str, role: str, content: str):
        key = ChatSessionStore._key(session_id)
        history = ChatSessionStore.get_history(session_id)
        history.append({"role": role, "content": content})
        redis_client.setex(key, CHAT_TTL, json.dumps(history, ensure_ascii=False))

    @staticmethod
    def reset(session_id: str):
        redis_client.delete(ChatSessionStore._key(session_id))

    @staticmethod
    def get_turn_count(session_id: str) -> int:
        return len(ChatSessionStore.get_history(session_id)) // 2


# ─────────────────────────────────────────────
# JWT Authentication
# ─────────────────────────────────────────────
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=settings.access_token_expire_minutes)
    )
    to_encode["exp"] = expire
    return jwt.encode(to_encode, settings.secret_key, algorithm=settings.algorithm)


def decode_token(token: str) -> Optional[dict]:
    try:
        return jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
    except JWTError:
        return None


# ─────────────────────────────────────────────
# Cache Helper (Redis)
# ─────────────────────────────────────────────
class Cache:
    """كاش عام للنتائج المتكررة"""

    @staticmethod
    def get(key: str) -> Optional[Any]:
        raw = redis_client.get(f"cache:{key}")
        return json.loads(raw) if raw else None

    @staticmethod
    def set(key: str, value: Any, ttl: int = 3600):
        redis_client.setex(f"cache:{key}", ttl, json.dumps(value, ensure_ascii=False))

    @staticmethod
    def delete(key: str):
        redis_client.delete(f"cache:{key}")

    @staticmethod
    def valuation_key(company_id: int) -> str:
        return f"valuation:{company_id}:latest"
