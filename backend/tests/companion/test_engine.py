import datetime as dt
from zoneinfo import ZoneInfo

from open_webui.utils.companion_engine import (
    apply_review,
    context_text,
    mood_value,
    parse_review,
    proactive_reason,
    recall,
)


def test_mood_returns_to_baseline_and_rejects_untrusted_changes():
    state = {'mood': 90, 'mood_at': 0}
    assert mood_value(state, 6 * 3600) == 75
    result = apply_review(state, {'mood_delta': -100, 'confidence': 0.2}, 6 * 3600, 'turn', lambda: 'm')
    assert result['mood'] == 75
    assert apply_review({}, {'mood_delta': float('nan'), 'confidence': 1}, 1, 't', lambda: 'm')['mood'] == 60


def test_recall_excludes_expired_and_superseded_facts():
    memories = [
        {'id': 'a', 'text': '喜欢咖啡', 'at': 1},
        {'id': 'b', 'text': '喜欢咖啡', 'invalid': True},
        {'id': 'c', 'text': '喜欢咖啡', 'expires_at': 2},
        {'id': 'd', 'text': '喜欢游泳'},
    ]
    assert [m['id'] for m in recall(memories, '咖啡', 100)] == ['a']


def test_replacement_preserves_source_and_does_not_mutate_input():
    state = {'memories': [{'id': 'a', 'text': '喜欢咖啡'}]}
    out = apply_review(state, {'memories': [{'text': '改喝茶了', 'replaces': 'a'}]}, 50, 'chat:turn', lambda: 'b')
    assert 'invalid' not in state['memories'][0]
    assert out['memories'][0]['invalid']
    assert out['memories'][1]['source'] == 'chat:turn'
    assert len(apply_review(out, {'memories': [{'text': '改喝茶了'}]}, 51, 't', lambda: 'c')['memories']) == 2


def test_short_term_context_expires():
    role = {'name': '朋友', 'persona': '自然交流', 'state': {'short_term': '明天见', 'short_term_until': 20}}
    assert '明天见' in context_text(role, '', 10)
    assert '明天见' not in context_text(role, '', 21)


def test_invalid_model_review_is_safe():
    assert parse_review('not json') == {}
    assert parse_review('```json\n{"confidence": 0.9}\n```')['confidence'] == 0.9
    assert apply_review({}, {'memories': 'invalid'}, 1, 't', lambda: 'm')['memories'] == []


def test_proactive_respects_timezone_idle_window_and_daily_budget():
    now = int(dt.datetime(2026, 11, 11, 12, tzinfo=ZoneInfo('Asia/Shanghai')).timestamp())
    state = {'last_user_at': now - 8000, 'pending': '面试后来怎么样了', 'proactive': {'timezone': 'Asia/Shanghai'}}
    assert proactive_reason(state, now) is None
    assert proactive_reason({**state, 'last_user_at': now}, now) == 'active'
    assert proactive_reason({**state, 'day': '2026-11-11', 'attempts': 3}, now) == 'budget'
    assert proactive_reason(state, now + 12 * 3600) == 'quiet'
