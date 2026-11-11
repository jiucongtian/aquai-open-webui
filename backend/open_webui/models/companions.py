"""Private companion records, isolated from general-purpose user memories."""

from open_webui.internal.db import Base
from pydantic import BaseModel, Field
from sqlalchemy import JSON, BigInteger, Boolean, Column, Integer, String, Text


class Companion(Base):
    __tablename__ = 'companion'
    id = Column(String, primary_key=True)
    user_id = Column(String, nullable=False, index=True)
    name = Column(String, nullable=False)
    persona = Column(Text, nullable=False)
    model_id = Column(String, nullable=False, default='')
    state = Column(JSON, nullable=False, default=dict)
    version = Column(Integer, nullable=False, default=0)
    target_chat_id = Column(String, nullable=True)
    next_tick = Column(BigInteger, nullable=False, default=0, index=True)
    lease = Column(String, nullable=True)
    created_at = Column(BigInteger, nullable=False)


class CompanionChat(Base):
    __tablename__ = 'companion_chat'
    chat_id = Column(String, primary_key=True)
    user_id = Column(String, nullable=False, index=True)
    role_id = Column(String, nullable=True)
    enabled = Column(Boolean, nullable=False, default=False)
    used = Column(Boolean, nullable=False, default=False)
    revision = Column(Integer, nullable=False, default=0)


class CompanionPreference(Base):
    __tablename__ = 'companion_preference'
    user_id = Column(String, primary_key=True)
    data = Column(JSON, nullable=False, default=dict)


class CompanionTurn(Base):
    __tablename__ = 'companion_turn'
    # One observation per user message and role, including regenerated responses.
    id = Column(String, primary_key=True)
    role_id = Column(String, nullable=False, index=True)
    created_at = Column(BigInteger, nullable=False)


class RoleForm(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    persona: str = Field(min_length=1, max_length=12000)
    model_id: str = Field(default='', max_length=256)


class ChatForm(BaseModel):
    enabled: bool = False
    role_id: str | None = None


class PreferenceForm(ChatForm):
    pass


class ProactiveForm(BaseModel):
    chat_id: str | None = None
    interval_minutes: int = Field(default=120, ge=30, le=1440)
    daily_max: int = Field(default=3, ge=1, le=10)
    awake_from: int = Field(default=8, ge=0, le=23)
    awake_to: int = Field(default=23, ge=1, le=24)
    timezone: str = 'Asia/Shanghai'


class MemoryForm(BaseModel):
    text: str = Field(min_length=1, max_length=500)


def role_data(role):
    return {
        key: getattr(role, key) for key in ('id', 'name', 'persona', 'model_id', 'state', 'target_chat_id', 'version')
    }
