from pathlib import Path

from app.io.execution_core_apply import _write_schema_sql_from_schemas
from execution_core.builtin_crud import Schema


def test_incremental_schema_merge_preserves_existing_tables(tmp_path: Path):
    res = tmp_path / 'src/main/resources'
    res.mkdir(parents=True, exist_ok=True)
    (res / 'schema.sql').write_text(
        'CREATE TABLE IF NOT EXISTS user (user_id VARCHAR(64) NOT NULL PRIMARY KEY);\n',
        encoding='utf-8',
    )

    schedule = Schema(
        entity='Schedule',
        entity_var='schedule',
        table='schedule',
        id_prop='scheduleId',
        id_column='schedule_id',
        fields=[('scheduleId', 'schedule_id', 'String'), ('title', 'title', 'String')],
        routes={},
        views={},
    )

    path = _write_schema_sql_from_schemas(tmp_path, {'Schedule': schedule})
    body = path.read_text(encoding='utf-8').lower()

    assert 'create table if not exists user' in body
    assert 'create table if not exists schedule' in body
