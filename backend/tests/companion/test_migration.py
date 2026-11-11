import importlib.util
from pathlib import Path

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations


def test_companion_migration_upgrade_and_downgrade(tmp_path):
    path = Path(__file__).parents[2] / 'open_webui/migrations/versions/f71a02d9c841_add_companion.py'
    spec = importlib.util.spec_from_file_location('companion_migration', path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    engine = sa.create_engine(f'sqlite:///{tmp_path}/migration.db')
    with engine.begin() as connection:
        migration.op = Operations(MigrationContext.configure(connection))
        migration.upgrade()
        tables = sa.inspect(connection).get_table_names()
        assert set(tables) == {'companion', 'companion_chat', 'companion_preference', 'companion_turn'}
        assert {'enabled', 'used', 'revision'} <= {
            c['name'] for c in sa.inspect(connection).get_columns('companion_chat')
        }
        migration.downgrade()
        assert sa.inspect(connection).get_table_names() == []
    engine.dispose()
