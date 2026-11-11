"""Component integration harness.

Runs the actual companion ORM, routes and service against isolated SQLite.
Only host authentication, chat transport and LLM adapters are substituted;
these tests do not claim to exercise a deployed Open WebUI or a real model.
"""

import copy
import importlib
import sys
import types
from contextlib import asynccontextmanager
from types import SimpleNamespace

import httpx
import pytest_asyncio
from fastapi import FastAPI, Request
from sqlalchemy import JSON, Column, Integer, String
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import declarative_base


@pytest_asyncio.fixture
async def harness(tmp_path, monkeypatch):  # noqa: C901 - isolated host adapters kept local to the fixture
    base = declarative_base()
    engine = create_async_engine(f'sqlite+aiosqlite:///{tmp_path}/test.db')
    sessions = async_sessionmaker(engine, expire_on_commit=False)

    @asynccontextmanager
    async def db_context(*args, **kwargs):
        async with sessions() as db:
            yield db

    def module(name, **attrs):
        value = types.ModuleType(name)
        value.__dict__.update(attrs)
        monkeypatch.setitem(sys.modules, name, value)

    module('open_webui.internal.db', Base=base, get_async_db_context=db_context)

    class Chat(base):
        __tablename__ = 'chat'
        id = Column(String, primary_key=True)
        user_id = Column(String)
        chat = Column(JSON)
        current_message_id = Column(String)
        updated_at = Column(Integer)

    class ChatMessage(base):
        __tablename__ = 'chat_message'
        id = Column(String, primary_key=True)
        data = Column(JSON)

    class Chats:
        @staticmethod
        async def get_chat_by_id_and_user_id(chat_id, user_id):
            async with sessions() as db:
                chat = await db.get(Chat, chat_id)
                return chat if chat and chat.user_id == user_id else None

        @staticmethod
        def upsert_message_to_history(history, message_id, message):
            history.setdefault('messages', {})[message_id] = message
            parent = history['messages'].get(message.get('parentId'))
            if parent:
                parent.setdefault('childrenIds', []).append(message_id)
            history['currentId'] = message_id
            return message

    class ChatMessages:
        @staticmethod
        async def upsert_message(message_id, chat_id, user_id, data, db):
            key = chat_id + ':' + message_id
            row = await db.get(ChatMessage, key)
            if row:
                row.data = copy.deepcopy(data)
            else:
                db.add(ChatMessage(id=key, data=copy.deepcopy(data)))

    async def verified(request: Request):
        return SimpleNamespace(id=request.headers.get('x-test-user', 'alice'), role='user')

    active = {'alice': True, 'bob': True}

    class Users:
        @staticmethod
        async def get_user_by_id(user_id):
            return SimpleNamespace(id=user_id, role='user')

    class Auths:
        @staticmethod
        async def get_auth_by_id(user_id):
            return SimpleNamespace(active=active.get(user_id, False))

    events = []

    class Socket:
        async def emit(self, *args, **kwargs):
            events.append((args, kwargs))

    def add_system(content, messages, append=False):
        return [{'role': 'system', 'content': content}, *messages]

    module('open_webui.models.chats', Chat=Chat, Chats=Chats)
    module('open_webui.models.chat_messages', ChatMessages=ChatMessages)
    module('open_webui.models.users', Users=Users)
    module('open_webui.models.auths', Auths=Auths)
    module('open_webui.utils.auth', get_verified_user=verified)
    module('open_webui.utils.misc', add_or_update_system_message=add_system)
    module('open_webui.utils.automations', _build_request=lambda app: None)
    module('open_webui.socket.main', sio=Socket())
    names = ['open_webui.models.companions', 'open_webui.routers.companions', 'open_webui.utils.companions']
    for name in names:
        monkeypatch.delitem(sys.modules, name, raising=False)
    models, router, service = [importlib.import_module(name) for name in names]
    async with engine.begin() as connection:
        await connection.run_sync(base.metadata.create_all)
    async with sessions() as db:
        for chat_id, owner in [('a', 'alice'), ('b', 'alice'), ('c', 'bob')]:
            db.add(
                Chat(
                    id=chat_id,
                    user_id=owner,
                    chat={
                        'history': {
                            'currentId': 'answer',
                            'messages': {
                                'question': {
                                    'id': 'question',
                                    'role': 'user',
                                    'content': '我喜欢喝茶',
                                    'childrenIds': ['answer'],
                                },
                                'answer': {
                                    'id': 'answer',
                                    'role': 'assistant',
                                    'content': '下次聊聊茶',
                                    'parentId': 'question',
                                    'done': True,
                                },
                            },
                        }
                    },
                    current_message_id='answer',
                    updated_at=0,
                )
            )
        await db.commit()
    app = FastAPI()
    app.include_router(router.router, prefix='/companions')
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
        yield SimpleNamespace(
            client=client,
            db=sessions,
            models=models,
            service=service,
            router=router,
            Chat=Chat,
            ChatMessage=ChatMessage,
            active=active,
            events=events,
            app=app,
        )
    for name in names:
        sys.modules.pop(name, None)
    await engine.dispose()
