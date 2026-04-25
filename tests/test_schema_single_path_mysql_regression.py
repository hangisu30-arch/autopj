from pathlib import Path

from execution_core.project_patcher import _dedupe_create_table_statements, patch_application_properties
from execution_core.builtin_crud import schema_for
from app.io.execution_core_apply import _write_auth_sql_artifacts


def test_dedupe_schema_sql_strips_mysql_dialect_mix_and_schema_qualifier(tmp_path: Path):
    raw = (
        "DROP TABLE IF EXISTS `backend`;\n\n"
        "CREATE TABLE IF NOT EXISTS `backend`.`TB_MEMBER` (\n"
        "  `USE_YN` CHAR( (1) ) NOT NULL DEFAULT 'Y' COMMENT '사용 여부'\n"
        ");\n\n"
        "COMMENT ON TABLE backend.TB_MEMBER IS '사용자 및 관리자 관리 테이블';\n"
        "DELIMITER $$\n"
        "CREATE TRIGGER `tr_tb_member_bu` BEFORE UPDATE ON `backend`.`TB_MEMBER` FOR EACH ROW\n"
        "BEGIN\n"
        "    SET NEW.REG_DT = OLD.REG_DT;\n"
        "END$$\n"
        "DELIMITER;\n"
    )
    rendered = _dedupe_create_table_statements(raw)
    assert 'DROP TABLE IF EXISTS `backend`' not in rendered
    assert '`backend`.`TB_MEMBER`' not in rendered
    assert 'COMMENT ON TABLE' not in rendered
    assert 'CREATE TRIGGER' not in rendered
    assert 'CHAR(1)' in rendered
    assert 'CREATE TABLE IF NOT EXISTS `TB_MEMBER`' in rendered


def test_auth_sql_bootstrap_uses_single_schema_and_data_path(tmp_path: Path):
    props = patch_application_properties(tmp_path, 'egovframework.test', 'jsp')
    body = props.read_text(encoding='utf-8')
    assert 'optional:classpath:schema.sql' in body
    assert 'optional:classpath:login-schema.sql' not in body
    assert 'optional:classpath:data.sql' in body
    assert 'optional:classpath:login-data.sql' not in body


def test_auth_sql_artifacts_remove_legacy_files_and_append_seed_to_data_sql(tmp_path: Path):
    (tmp_path / 'src/main/resources').mkdir(parents=True, exist_ok=True)
    (tmp_path / 'src/main/java/egovframework/test/config').mkdir(parents=True, exist_ok=True)
    (tmp_path / 'src/main/resources/login-schema.sql').write_text('legacy', encoding='utf-8')
    (tmp_path / 'src/main/resources/login-data.sql').write_text('legacy', encoding='utf-8')
    (tmp_path / 'src/main/java/egovframework/test/config/LoginDatabaseInitializer.java').write_text('legacy', encoding='utf-8')

    schema = schema_for('Login', feature_kind='AUTH')
    patched = _write_auth_sql_artifacts(tmp_path, {'Login': schema}, 'egovframework.test')

    assert not (tmp_path / 'src/main/resources/login-schema.sql').exists()
    assert not (tmp_path / 'src/main/resources/login-data.sql').exists()
    assert not (tmp_path / 'src/main/java/egovframework/test/config/LoginDatabaseInitializer.java').exists()
    assert 'data.sql.auth-seed' in patched
    data = (tmp_path / 'src/main/resources/data.sql').read_text(encoding='utf-8')
    assert 'INSERT INTO tb_login' in data
