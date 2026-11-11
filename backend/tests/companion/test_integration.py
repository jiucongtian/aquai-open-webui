import asyncio
import json
import time
from types import SimpleNamespace

import pytest


async def role(h, name='朋友'):
    response = await h.client.post('/companions/', json={'name': name, 'persona': '自然体贴，喜欢学习'})
    assert response.status_code == 200
    return response.json()['id']


async def bind(h, role_id, chat='a', enabled=True):
    result = await h.client.put(f'/companions/chats/{chat}', json={'role_id': role_id, 'enabled': enabled})
    assert result.status_code == 200


@pytest.mark.asyncio
async def test_owner_isolation_and_shared_role_state(harness):
    h = harness
    role_id = await role(h)
    await bind(h, role_id, 'a')
    await bind(h, role_id, 'b')
    assert (await h.client.get('/companions/', headers={'x-test-user': 'bob'})).json() == []
    assert (
        await h.client.put(f'/companions/{role_id}', headers={'x-test-user': 'bob'}, json={'name': 'x', 'persona': 'x'})
    ).status_code == 404
    assert (await h.client.put('/companions/chats/c', json={'role_id': role_id, 'enabled': True})).status_code == 404
    async with h.db() as db:
        obj = await db.get(h.models.Companion, role_id)
        obj.state = {'mood': 82, 'memories': [{'id': 'm', 'text': '喜欢茶'}]}
        await db.commit()
    a = await h.service.resolve_companion('alice', 'a')
    b = await h.service.resolve_companion('alice', 'b')
    assert a['state'] == b['state']
    assert await h.service.resolve_companion('bob', 'a') is None


@pytest.mark.asyncio
async def test_unique_target_disable_and_defaults_do_not_change_existing(harness):
    h = harness
    rid = await role(h)
    await bind(h, rid, 'a')
    await bind(h, rid, 'b')
    for target in ('a', 'b'):
        assert (await h.client.put(f'/companions/{rid}/proactive', json={'chat_id': target})).status_code == 200
    assert (await h.client.get('/companions/')).json()[0]['target_chat_id'] == 'b'
    await h.client.put('/companions/preferences', json={'enabled': False, 'role_id': rid})
    assert (await h.client.get('/companions/chats/b')).json()['enabled']
    await bind(h, rid, 'b', False)
    assert (await h.client.get('/companions/')).json()[0]['target_chat_id'] is None
    assert (await h.client.put(f'/companions/{rid}/proactive', json={'chat_id': 'b'})).status_code == 400


@pytest.mark.asyncio
async def test_stale_client_cannot_reenable_and_temporary_does_not_persist(harness):
    h = harness
    rid = await role(h)
    await bind(h, rid, enabled=False)
    metadata = {'chat_id': 'a', 'companion': {'id': 'forged'}}
    payload = {'model': 'test', 'messages': [{'role': 'user', 'content': 'hi'}]}
    await h.service.prepare_companion(
        None,
        payload,
        SimpleNamespace(id='alice'),
        metadata,
        {'memory': True, 'companion': {'enabled': True, 'role_id': rid}},
    )
    assert 'companion' not in metadata
    before = (await h.client.get('/companions/')).json()
    metadata = {'chat_id': 'temporary:session'}
    await h.service.prepare_companion(
        None, payload, SimpleNamespace(id='alice'), metadata, {'companion': {'enabled': True, 'role_id': rid}}
    )
    assert metadata['companion_temporary']
    assert (await h.client.get('/companions/')).json() == before
    async with h.db() as db:
        assert await db.get(h.models.CompanionChat, 'temporary:session') is None


async def review_context(h, rid):
    role = await h.service.resolve_companion('alice', 'a')
    ctx = {
        'user': SimpleNamespace(id='alice'),
        'request': None,
        'metadata': {
            'chat_id': 'a',
            'user_message_id': 'question',
            'companion': {'id': rid, 'revision': role['revision'], 'version': role['version']},
        },
        'form_data': {'model': 'test'},
    }
    messages = [{'role': 'user', 'content': '我喜欢喝茶'}, {'role': 'assistant', 'content': '记住了'}]
    return ctx, messages


@pytest.mark.asyncio
async def test_review_is_idempotent_and_separate_from_other_roles(harness, monkeypatch):
    h = harness
    rid = await role(h)
    other = await role(h, '另一个角色')
    await bind(h, rid)

    async def model(*args):
        return json.dumps({'mood_delta': 8, 'confidence': 0.9, 'memories': [{'text': '用户喜欢喝茶'}]})

    monkeypatch.setattr(h.service, 'model_text', model)
    ctx, messages = await review_context(h, rid)
    await h.service.review_companion_turn(ctx, messages)
    first = await h.service.resolve_companion('alice', 'a')
    await h.service.review_companion_turn(ctx, messages)
    assert (await h.service.resolve_companion('alice', 'a'))['state'] == first['state']
    assert len(first['state']['memories']) == 1
    async with h.db() as db:
        assert (await db.get(h.models.Companion, other)).state == {}


@pytest.mark.asyncio
@pytest.mark.parametrize('change', ['disable', 'reset', 'delete'])
async def test_review_drops_results_after_consent_or_state_changes(harness, monkeypatch, change):
    h = harness
    rid = await role(h)
    await bind(h, rid)

    async def model(*args):
        if change == 'disable':
            await bind(h, rid, enabled=False)
        elif change == 'reset':
            await h.client.delete(f'/companions/{rid}/state')
        else:
            await h.client.delete(f'/companions/{rid}')
        return '{"memories":[{"text":"不能写回的旧信息"}]}'

    monkeypatch.setattr(h.service, 'model_text', model)
    ctx, messages = await review_context(h, rid)
    await h.service.review_companion_turn(ctx, messages)
    async with h.db() as db:
        row = await db.get(h.models.Companion, rid)
        assert row is None or not row.state.get('memories')


async def due_role(h):
    rid = await role(h)
    await bind(h, rid)
    await h.client.put(f'/companions/{rid}/proactive', json={'chat_id': 'a', 'awake_from': 0, 'awake_to': 24})
    async with h.db() as db:
        row = await db.get(h.models.Companion, rid)
        row.state = {**row.state, 'last_user_at': int(time.time()) - 10000, 'pending': '面试结果', 'last_model': 'test'}
        row.next_tick = 0
        await db.commit()
    return rid


@pytest.mark.asyncio
async def test_concurrent_workers_deliver_once_and_persist_for_offline_user(harness, monkeypatch):
    h = harness
    rid = await due_role(h)
    calls = []

    async def model(*args):
        calls.append(1)
        await asyncio.sleep(0.03)
        return '之前说的面试，后来怎么样了？'

    monkeypatch.setattr(h.service, 'model_text', model)
    await asyncio.gather(h.service.run_companion_tick(h.app), h.service.run_companion_tick(h.app))
    assert len(calls) == 1
    assert len(h.events) == 1
    async with h.db() as db:
        row = await db.get(h.models.Companion, rid)
        assert row.state['attempts'] == 1
        assert row.state['last_outcome'] == 'sent'
        chat = await db.get(h.Chat, 'a')
        assert len(chat.chat['history']['messages']) == 3
        message = chat.chat['history']['messages'][chat.current_message_id]
        assert message['meta']['companion_proactive'] == rid
        assert await db.get(h.ChatMessage, 'a:' + message['id']) is not None


@pytest.mark.asyncio
@pytest.mark.parametrize('change', ['disable', 'reset', 'new_message', 'silence', 'deactivate'])
async def test_proactive_does_not_send_stale_or_unwanted_messages(harness, monkeypatch, change):
    h = harness
    rid = await due_role(h)

    async def model(*args):
        if change == 'disable':
            await bind(h, rid, enabled=False)
        elif change == 'reset':
            await h.client.delete(f'/companions/{rid}/state')
        elif change == 'new_message':
            async with h.db() as db:
                chat = await db.get(h.Chat, 'a')
                chat.chat = {'history': {'currentId': 'new', 'messages': {}}}
                await db.commit()
        elif change == 'deactivate':
            h.active['alice'] = False
        return '[沉默]' if change == 'silence' else '不该发出的消息'

    monkeypatch.setattr(h.service, 'model_text', model)
    await h.service.run_companion_tick(h.app)
    assert h.events == []


@pytest.mark.asyncio
async def test_deleted_target_and_inactive_user_do_not_generate(harness, monkeypatch):
    h = harness
    await due_role(h)
    h.active['alice'] = False

    async def model(*args):
        raise AssertionError('inactive user must not generate')

    monkeypatch.setattr(h.service, 'model_text', model)
    await h.service.run_companion_tick(h.app)
    assert not h.events


@pytest.mark.asyncio
async def test_failed_generation_consumes_budget_and_does_not_retry_immediately(harness, monkeypatch):
    h = harness
    rid = await due_role(h)
    calls = []

    async def model(*args):
        calls.append(1)
        raise RuntimeError('simulated model failure')

    monkeypatch.setattr(h.service, 'model_text', model)
    await h.service.run_companion_tick(h.app)
    await h.service.run_companion_tick(h.app)
    assert len(calls) == 1
    async with h.db() as db:
        record = await db.get(h.models.Companion, rid)
        assert record.state['attempts'] == 1
        assert record.state['last_outcome'] == 'failed'
        assert record.next_tick > time.time()
        assert record.lease is None


@pytest.mark.asyncio
async def test_general_memory_is_isolated_even_after_companion_disabled(harness):
    h = harness
    rid = await role(h)
    await bind(h, rid)
    await bind(h, rid, enabled=False)
    payload = {'model': 'test', 'messages': [{'role': 'user', 'content': '普通聊天'}]}
    features = {'memory': True}
    metadata = {'chat_id': 'a'}
    await h.service.prepare_companion(None, payload, SimpleNamespace(id='alice'), metadata, features)
    assert features['memory'] is False
    assert metadata['companion_history']
    assert 'companion' not in metadata
    assert len(payload['messages']) == 1


@pytest.mark.asyncio
async def test_ordinary_chat_keeps_memory_and_does_not_touch_role(harness):
    h = harness
    await role(h)
    before = (await h.client.get('/companions/')).json()
    payload = {'model': 'test', 'messages': [{'role': 'user', 'content': '普通聊天'}]}
    features = {'memory': True}
    metadata = {'chat_id': 'a'}
    await h.service.prepare_companion(None, payload, SimpleNamespace(id='alice'), metadata, features)
    assert features['memory'] is True
    assert 'companion_history' not in metadata
    assert len(payload['messages']) == 1
    assert (await h.client.get('/companions/')).json() == before


@pytest.mark.asyncio
async def test_deleted_target_is_unbound_without_generating(harness, monkeypatch):
    h = harness
    rid = await due_role(h)
    async with h.db() as db:
        await db.delete(await db.get(h.Chat, 'a'))
        await db.commit()

    async def model(*args):
        raise AssertionError('deleted target must not generate')

    monkeypatch.setattr(h.service, 'model_text', model)
    await h.service.run_companion_tick(h.app)
    async with h.db() as db:
        assert (await db.get(h.models.Companion, rid)).target_chat_id is None
    assert not h.events


@pytest.mark.asyncio
async def test_memory_correction_and_deletion_clear_derived_summaries(harness):
    h = harness
    rid = await role(h)
    async with h.db() as db:
        r = await db.get(h.models.Companion, rid)
        r.state = {
            'profile': '旧画像',
            'experience': ['旧经验'],
            'pending': '旧话题',
            'memories': [{'id': 'm', 'text': '旧事实', 'invalid': True}],
        }
        await db.commit()
    response = await h.client.put(f'/companions/{rid}/memories/m', json={'text': '正确事实'})
    assert response.status_code == 200
    state = (await h.client.get('/companions/')).json()[0]['state']
    assert state['memories'][0]['text'] == '正确事实'
    assert not state['memories'][0]['invalid']
    assert not state['profile'] and not state['experience'] and not state['pending']
    await h.client.delete(f'/companions/{rid}/memories/m')
    assert (await h.client.get('/companions/')).json()[0]['state']['memories'] == []


@pytest.mark.asyncio
async def test_reset_while_foreground_generates_prevents_later_extraction(harness, monkeypatch):
    h = harness
    rid = await role(h)
    await bind(h, rid)
    metadata = {'chat_id': 'a', 'user_message_id': 'question'}
    payload = {'model': 'test', 'messages': [{'role': 'user', 'content': '我喜欢喝茶'}]}
    user = SimpleNamespace(id='alice')
    await h.service.prepare_companion(None, payload, user, metadata, {})
    await h.client.delete(f'/companions/{rid}/state')

    async def model(*args):
        raise AssertionError('A reset during foreground generation must prevent later extraction')

    monkeypatch.setattr(h.service, 'model_text', model)
    ctx = {'user': user, 'metadata': metadata, 'request': None, 'form_data': payload}
    await h.service.review_companion_turn(
        ctx, [{'role': 'user', 'content': '我喜欢喝茶'}, {'role': 'assistant', 'content': '记住了'}]
    )
    assert (await h.client.get('/companions/')).json()[0]['state'] == {}


@pytest.mark.asyncio
async def test_real_prepare_to_review_version_handoff(harness, monkeypatch):
    h = harness
    rid = await role(h)
    await bind(h, rid)
    metadata = {'chat_id': 'a', 'user_message_id': 'question'}
    payload = {'model': 'test', 'messages': [{'role': 'user', 'content': '我喜欢喝茶'}]}
    user = SimpleNamespace(id='alice')
    await h.service.prepare_companion(None, payload, user, metadata, {})

    async def model(*args):
        return '{"memories":[{"text":"用户喜欢喝茶"}]}'

    monkeypatch.setattr(h.service, 'model_text', model)
    await h.service.review_companion_turn(
        {'user': user, 'metadata': metadata, 'request': None, 'form_data': payload},
        [{'role': 'user', 'content': '我喜欢喝茶'}, {'role': 'assistant', 'content': '记住了'}],
    )
    assert (await h.client.get('/companions/')).json()[0]['state']['memories'][0]['text'] == '用户喜欢喝茶'


@pytest.mark.asyncio
async def test_background_model_adapter_loads_models_and_drops_foreground_metadata(harness, monkeypatch):
    import sys
    import types

    from starlette.requests import Request

    h = harness
    h.app.state.MODELS = {}
    calls = []

    async def load_models(request, user):
        calls.append('load')
        request.app.state.MODELS = {'test': {'id': 'test'}}

    async def generate(request, form_data, user):
        assert not hasattr(request.state, 'metadata')
        assert not hasattr(request.state, 'direct')
        assert form_data['tools'] == [] and form_data['stream'] is False
        assert form_data['metadata'] == {'task': 'companion_review'}
        calls.append('generate')
        return {'choices': [{'message': {'content': 'ok'}}]}

    model_module = types.ModuleType('open_webui.utils.models')
    model_module.get_all_models = load_models
    chat_module = types.ModuleType('open_webui.utils.chat')
    chat_module.generate_chat_completion = generate
    monkeypatch.setitem(sys.modules, model_module.__name__, model_module)
    monkeypatch.setitem(sys.modules, chat_module.__name__, chat_module)
    request = Request({'type': 'http', 'app': h.app, 'state': {'metadata': {'tools': 'foreground'}, 'direct': True}})
    result = await h.service.model_text(request, SimpleNamespace(id='alice'), 'test', [], 'companion_review')
    assert result == 'ok' and calls == ['load', 'generate']


@pytest.mark.asyncio
async def test_account_cleanup_is_transactional_and_owner_scoped(harness):
    from sqlalchemy import select

    h = harness
    rid = await role(h)
    await bind(h, rid)
    await h.client.put('/companions/preferences', json={'enabled': True, 'role_id': rid})
    response = await h.client.post(
        '/companions/', headers={'x-test-user': 'bob'}, json={'name': '另一个用户', 'persona': '保持独立'}
    )
    bob_role = response.json()['id']
    async with h.db() as db:
        db.add(h.models.CompanionTurn(id='alice-turn', role_id=rid, created_at=1))
        db.add(h.models.CompanionTurn(id='bob-turn', role_id=bob_role, created_at=1))
        await db.commit()
    async with h.db() as db:
        await h.models.delete_companions_for_user(db, 'alice')
        await db.rollback()
    async with h.db() as db:
        assert await db.get(h.models.Companion, rid)
        assert await db.get(h.models.CompanionTurn, 'alice-turn')
        await h.models.delete_companions_for_user(db, 'alice')
        await db.commit()
    async with h.db() as db:
        assert await db.get(h.models.Companion, rid) is None
        assert await db.get(h.models.CompanionTurn, 'alice-turn') is None
        assert await db.get(h.models.CompanionPreference, 'alice') is None
        assert (
            not (await db.execute(select(h.models.CompanionChat).where(h.models.CompanionChat.user_id == 'alice')))
            .scalars()
            .all()
        )
        assert await db.get(h.models.Companion, bob_role)
        assert await db.get(h.models.CompanionTurn, 'bob-turn')
