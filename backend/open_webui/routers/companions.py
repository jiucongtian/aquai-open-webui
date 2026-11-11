"""Owner-only companion management. Chat switches are server-authoritative."""

import time
from uuid import uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, HTTPException
from open_webui.internal.db import get_async_db_context
from open_webui.models.chats import Chats
from open_webui.models.companions import (
    ChatForm,
    Companion,
    CompanionChat,
    CompanionPreference,
    CompanionTurn,
    MemoryForm,
    PreferenceForm,
    ProactiveForm,
    RoleForm,
    role_data,
)
from open_webui.utils.auth import get_verified_user
from sqlalchemy import delete, select, update

router = APIRouter()


async def owned_role(db, role_id, user_id):
    role = await db.get(Companion, role_id)
    if not role or role.user_id != user_id:
        raise HTTPException(404, '角色不存在')
    return role


async def owned_chat(chat_id, user_id):
    chat = await Chats.get_chat_by_id_and_user_id(chat_id, user_id)
    if not chat:
        raise HTTPException(404, '聊天不存在或不属于当前用户')
    return chat


async def write_role(db, role, **values):
    result = await db.execute(
        update(Companion)
        .where(
            Companion.id == role.id,
            Companion.version == role.version,
        )
        .values(**values, version=role.version + 1, lease=None)
    )
    if result.rowcount != 1:
        raise HTTPException(409, '角色状态已变化，请刷新后重试')


@router.get('/')
async def list_roles(user=Depends(get_verified_user)):
    async with get_async_db_context() as db:
        roles = (await db.execute(select(Companion).where(Companion.user_id == user.id))).scalars()
        return [role_data(role) for role in roles]


@router.post('/')
async def create_role(form: RoleForm, user=Depends(get_verified_user)):
    async with get_async_db_context() as db:
        role = Companion(
            id=str(uuid4()),
            user_id=user.id,
            **form.model_dump(),
            state={},
            version=0,
            next_tick=0,
            created_at=int(time.time()),
        )
        db.add(role)
        await db.commit()
        return role_data(role)


@router.get('/preferences')
async def get_preferences(user=Depends(get_verified_user)):
    async with get_async_db_context() as db:
        row = await db.get(CompanionPreference, user.id)
        return row.data if row else {'enabled': False, 'role_id': None}


@router.put('/preferences')
async def set_preferences(form: PreferenceForm, user=Depends(get_verified_user)):
    async with get_async_db_context() as db:
        if form.role_id:
            await owned_role(db, form.role_id, user.id)
        if form.enabled and not form.role_id:
            raise HTTPException(400, '请先选择角色')
        row = await db.get(CompanionPreference, user.id)
        if row:
            row.data = form.model_dump()
        else:
            db.add(CompanionPreference(user_id=user.id, data=form.model_dump()))
        await db.commit()
        return form


@router.get('/chats/{chat_id}')
async def get_chat_setting(chat_id: str, user=Depends(get_verified_user)):
    await owned_chat(chat_id, user.id)
    async with get_async_db_context() as db:
        row = await db.get(CompanionChat, chat_id)
        return (
            {'enabled': row.enabled, 'role_id': row.role_id, 'initialized': True}
            if row
            else {'enabled': False, 'role_id': None, 'initialized': False}
        )


@router.put('/chats/{chat_id}')
async def set_chat_setting(chat_id: str, form: ChatForm, user=Depends(get_verified_user)):
    await owned_chat(chat_id, user.id)
    async with get_async_db_context() as db:
        if form.role_id:
            await owned_role(db, form.role_id, user.id)
        if form.enabled and not form.role_id:
            raise HTTPException(400, '请先选择角色')
        row = await db.get(CompanionChat, chat_id)
        if row:
            await db.execute(
                update(CompanionChat)
                .where(CompanionChat.chat_id == chat_id)
                .values(**form.model_dump(), used=row.used or form.enabled, revision=CompanionChat.revision + 1)
            )
        else:
            db.add(CompanionChat(chat_id=chat_id, user_id=user.id, **form.model_dump(), used=form.enabled, revision=0))
        # Disabling or changing role also unbinds the proactive target. Re-enabling
        # never silently restores consent to proactive messages.
        await db.execute(
            update(Companion)
            .where(
                Companion.user_id == user.id,
                Companion.target_chat_id == chat_id,
                (Companion.id != form.role_id) if form.enabled else True,
            )
            .values(target_chat_id=None, lease=None, version=Companion.version + 1)
        )
        await db.commit()
        return form


@router.put('/{role_id}')
async def edit_role(role_id: str, form: RoleForm, user=Depends(get_verified_user)):
    async with get_async_db_context() as db:
        role = await owned_role(db, role_id, user.id)
        await write_role(db, role, **form.model_dump())
        await db.commit()
        return {'ok': True}


@router.delete('/{role_id}')
async def delete_role(role_id: str, user=Depends(get_verified_user)):
    async with get_async_db_context() as db:
        await owned_role(db, role_id, user.id)
        await db.execute(
            update(CompanionChat)
            .where(CompanionChat.role_id == role_id)
            .values(enabled=False, role_id=None, revision=CompanionChat.revision + 1)
        )
        await db.execute(delete(CompanionTurn).where(CompanionTurn.role_id == role_id))
        await db.execute(delete(Companion).where(Companion.id == role_id, Companion.user_id == user.id))
        pref = await db.get(CompanionPreference, user.id)
        if pref and pref.data.get('role_id') == role_id:
            pref.data = {'enabled': False, 'role_id': None}
        await db.commit()
        return {'ok': True}


@router.put('/{role_id}/proactive')
async def set_proactive(role_id: str, form: ProactiveForm, user=Depends(get_verified_user)):
    try:
        ZoneInfo(form.timezone)
    except (ZoneInfoNotFoundError, ValueError):
        raise HTTPException(400, '无效时区')
    if form.awake_from == form.awake_to:
        raise HTTPException(400, '清醒时间的起止不能相同')
    if form.chat_id:
        await owned_chat(form.chat_id, user.id)
    async with get_async_db_context() as db:
        role = await owned_role(db, role_id, user.id)
        if form.chat_id:
            binding = await db.get(CompanionChat, form.chat_id)
            if not binding or not binding.enabled or binding.role_id != role_id or binding.user_id != user.id:
                raise HTTPException(400, '目标聊天必须已开启该角色的拟人化模式')
        await write_role(
            db,
            role,
            target_chat_id=form.chat_id,
            state={**role.state, 'proactive': form.model_dump(exclude={'chat_id'})},
            next_tick=int(time.time()) + form.interval_minutes * 60,
        )
        await db.commit()
        return {'ok': True}


@router.put('/{role_id}/memories/{memory_id}')
async def edit_memory(role_id: str, memory_id: str, form: MemoryForm, user=Depends(get_verified_user)):
    async with get_async_db_context() as db:
        role = await owned_role(db, role_id, user.id)
        memories = [dict(m) for m in role.state.get('memories', [])]
        memory = next((m for m in memories if m['id'] == memory_id), None)
        if not memory:
            raise HTTPException(404, '记忆不存在')
        memory.update(text=form.text, invalid=False)
        await write_role(
            db,
            role,
            state={
                **role.state,
                'memories': memories,
                'profile': '',
                'experience': [],
                'short_term': '',
                'pending': '',
            },
        )
        await db.commit()
        return {'ok': True}


@router.delete('/{role_id}/memories/{memory_id}')
async def delete_memory(role_id: str, memory_id: str, user=Depends(get_verified_user)):
    async with get_async_db_context() as db:
        role = await owned_role(db, role_id, user.id)
        memories = [m for m in role.state.get('memories', []) if m['id'] != memory_id]
        # Remove derived summaries too, so deleted information cannot reappear there.
        await write_role(
            db,
            role,
            state={
                **role.state,
                'memories': memories,
                'profile': '',
                'experience': [],
                'short_term': '',
                'pending': '',
            },
        )
        await db.commit()
        return {'ok': True}


@router.delete('/{role_id}/state')
async def reset_state(role_id: str, user=Depends(get_verified_user)):
    async with get_async_db_context() as db:
        role = await owned_role(db, role_id, user.id)
        # Retain receipts: regenerating an old turn must not undo a deliberate reset.
        await write_role(db, role, state={}, target_chat_id=None)
        await db.commit()
        return {'ok': True}
