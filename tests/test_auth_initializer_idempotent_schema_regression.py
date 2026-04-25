from pathlib import Path

from app.io.execution_core_apply import _write_auth_sql_artifacts
from execution_core.builtin_crud import schema_for
from execution_core.feature_rules import FEATURE_KIND_AUTH


def test_auth_initializer_skips_existing_alter_add_column(tmp_path: Path):
    schema = schema_for('Login', feature_kind=FEATURE_KIND_AUTH)
    patched = _write_auth_sql_artifacts(tmp_path, {'Login': schema}, 'egovframework.test')
    initializer = tmp_path / 'src/main/java/egovframework/test/config/LoginDatabaseInitializer.java'
    assert patched['LoginDatabaseInitializer'] == str(initializer)
    body = initializer.read_text(encoding='utf-8')
    assert 'shouldSkipStatement' in body
    assert 'columnExists' in body
    assert 'parseAlterAddColumn' in body
    assert 'indexOfKeyword' in body
    assert 'metaData.getColumns' in body
    assert 'ResourceDatabasePopulator' not in body


def test_prompt_templates_require_idempotent_alter_guards():
    body = Path('app/ui/prompt_templates.py').read_text(encoding='utf-8')
    assert '재실행 가능(idempotent)' in body
    assert 'ALTER TABLE ... ADD COLUMN' in body
    assert '컬럼 존재 여부를 먼저 확인한 뒤' in body
