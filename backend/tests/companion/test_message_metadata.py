"""Exercise the real pure history updater without loading the app/database stack."""
import ast
from pathlib import Path


def history_updater():
    source = Path(__file__).parents[2] / 'open_webui/models/chats.py'
    tree = ast.parse(source.read_text())
    cls = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == 'ChatTable')
    cls.body = [node for node in cls.body if isinstance(node, ast.FunctionDef)
                and node.name in {'upsert_message_to_history', '_add_child_id_to_parent'}]
    namespace = {}
    exec(compile(ast.Module(body=[cls], type_ignores=[]), str(source), 'exec'), namespace)
    return namespace['ChatTable'].upsert_message_to_history


def test_companion_marker_survives_approval_resume_and_timing_updates():
    update = history_updater()
    marker = {'version': 1, 'name': '测试角色', 'mood': 60}
    history = {'messages': {'reply': {'meta': {'companion_display': marker, 'companion_proactive': True}}}}
    update(history, 'reply', {'meta': {'approval': 'pending'}})
    update(history, 'reply', {'meta': {'response_ended_at': 12}})
    assert history['messages']['reply']['meta'] == {
        'companion_display': marker, 'companion_proactive': True,
        'approval': 'pending', 'response_ended_at': 12,
    }
    update(history, 'reply', {'meta': {'approval': 'resolved'}})
    assert history['messages']['reply']['meta']['companion_display'] == marker


def test_announcing_companion_does_not_replace_existing_approval_metadata():
    history = {'messages': {'reply': {'meta': {'approval': 'pending', 'voice': {'id': 'v'}}}}}
    history_updater()(history, 'reply', {'meta': {'companion_display': {'version': 1}}})
    assert history['messages']['reply']['meta']['approval'] == 'pending'
    assert history['messages']['reply']['meta']['voice'] == {'id': 'v'}


def test_ordinary_metadata_replacement_does_not_invent_companion_state():
    history = {'messages': {'reply': {'meta': {'stale': 'remove', 'voice': {}}}}}
    history_updater()(history, 'reply', {'meta': {'approval': 'new'}})
    assert history['messages']['reply']['meta'] == {'voice': {}, 'approval': 'new'}
