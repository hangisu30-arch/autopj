from pathlib import Path

from app.io.execution_core_apply import _auth_seed_sql, _build_header_jsp, _inject_common_assets_into_jsp, _write_auth_sql_artifacts
from execution_core.builtin_crud import schema_for
from execution_core.feature_rules import FEATURE_KIND_AUTH
from execution_core.project_patcher import patch_datasource_properties


def test_header_jsp_centralizes_common_assets():
    body = _build_header_jsp()
    assert '/css/common.css' in body
    assert '/css/schedule.css' in body
    assert '/js/common.js' in body
    assert '/js/jquery.min.js' in body


def test_inject_common_assets_strips_page_level_shared_links(tmp_path: Path):
    jsp = tmp_path / 'src/main/webapp/WEB-INF/views/schedule/scheduleCalendar.jsp'
    jsp.parent.mkdir(parents=True, exist_ok=True)
    jsp.write_text(
        '<%@ page contentType="text/html; charset=UTF-8" pageEncoding="UTF-8"%>\n'
        '<html><head>\n'
        '  <link rel="stylesheet" href="${pageContext.request.contextPath}/css/common.css" />\n'
        '  <link rel="stylesheet" href="${pageContext.request.contextPath}/css/schedule.css" />\n'
        '</head><body>\n'
        '<div>calendar</div>\n'
        '</body></html>\n',
        encoding='utf-8',
    )

    changed = _inject_common_assets_into_jsp(
        tmp_path,
        'src/main/webapp/WEB-INF/views/schedule/scheduleCalendar.jsp',
        '/css/common.css',
        extra_css_urls=['/css/schedule.css'],
        js_web_urls=['/js/common.js', '/js/schedule.js'],
    )
    assert changed is True
    body = jsp.read_text(encoding='utf-8')
    assert body.count('/css/common.css') == 0
    assert body.count('/css/schedule.css') == 0
    assert '/WEB-INF/views/common/header.jsp' in body
    assert '/WEB-INF/views/common/leftNav.jsp' in body
    assert '/js/schedule.js' in body


def test_auth_seed_sql_is_generated_for_login_schema():
    schema = schema_for('Login', feature_kind=FEATURE_KIND_AUTH)
    sql = _auth_seed_sql(schema)
    assert 'INSERT INTO' in sql
    assert "'admin'" in sql
    assert "'admin1234'" in sql
    assert schema.table in sql


def test_patch_datasource_properties_enables_public_key_retrieval(tmp_path: Path):
    resource_dir = tmp_path / 'src/main/resources'
    resource_dir.mkdir(parents=True, exist_ok=True)
    (resource_dir / 'application.properties').write_text('', encoding='utf-8')
    patch_datasource_properties(
        tmp_path,
        {
            'host': 'localhost',
            'port': 3306,
            'username': 'root',
            'password': 'pw',
            'database': 'sampledb',
        },
    )
    body = (resource_dir / 'application.properties').read_text(encoding='utf-8')
    assert 'allowPublicKeyRetrieval=true' in body


def test_write_auth_sql_artifacts_creates_login_sql_and_init_properties(tmp_path: Path):
    schema = schema_for('Login', feature_kind=FEATURE_KIND_AUTH)
    patched = _write_auth_sql_artifacts(tmp_path, {'Login': schema}, 'egovframework.test')
    login_schema = tmp_path / 'src/main/resources/login-schema.sql'
    login_data = tmp_path / 'src/main/resources/login-data.sql'
    props = tmp_path / 'src/main/resources/application.properties'
    data_sql = tmp_path / 'src/main/resources/data.sql'
    schema_sql = tmp_path / 'src/main/resources/schema.sql'
    initializer = tmp_path / 'src/main/java/egovframework/test/config/LoginDatabaseInitializer.java'

    assert patched['login-schema.sql'] == str(login_schema)
    assert patched['login-data.sql'] == str(login_data)
    assert 'CREATE TABLE IF NOT EXISTS login' in login_schema.read_text(encoding='utf-8')
    assert "'admin'" in login_data.read_text(encoding='utf-8')
    assert (not data_sql.exists()) or ("'admin'" not in data_sql.read_text(encoding='utf-8'))
    assert 'CREATE TABLE IF NOT EXISTS login' in schema_sql.read_text(encoding='utf-8')
    assert initializer.exists()
    body = props.read_text(encoding='utf-8')
    assert 'spring.sql.init.schema-locations=optional:classpath:schema.sql,optional:classpath:login-schema.sql' in body
    assert 'spring.sql.init.data-locations=optional:classpath:data.sql,optional:classpath:login-data.sql' in body


def test_auth_seed_sql_populates_separate_primary_key_when_required():
    schema = schema_for(
        'Login',
        inferred_fields=[
            ('userId', 'user_id', 'String'),
            ('loginId', 'login_id', 'String'),
            ('password', 'password', 'String'),
            ('name', 'name', 'String'),
            ('email', 'email', 'String'),
            ('roleCd', 'role_cd', 'String'),
        ],
        table='tb_users',
        feature_kind=FEATURE_KIND_AUTH,
        strict_fields=True,
    )
    sql = _auth_seed_sql(schema)
    assert 'INSERT INTO tb_users (user_id, login_id, password, name, email' in sql
    assert "'admin'" in sql
    assert "WHERE NOT EXISTS (SELECT 1 FROM tb_users WHERE login_id = 'admin')" in sql


def test_auth_seed_sql_skips_non_auth_like_schedule_table_even_when_marked_auth():
    schema = schema_for(
        'MemberSchedule',
        inferred_fields=[
            ('scheduleId', 'schedule_id', 'String'),
            ('password', 'password', 'String'),
            ('useYn', 'use_yn', 'String'),
        ],
        table='member_schedule',
        feature_kind=FEATURE_KIND_AUTH,
        strict_fields=True,
    )
    sql = _auth_seed_sql(schema)
    assert sql == ''
