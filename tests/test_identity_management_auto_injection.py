from pathlib import Path

from app.io.execution_core_apply import (
    _auth_seed_sql,
    _ensure_identity_bundle_files,
    _identity_seed_sql,
    _schema_map_from_file_ops,
)
from app.ui.state import ProjectConfig
from execution_core.builtin_crud import schema_for


REQ = '''
예약 시스템 요구사항
- 사용자가 예약을 요청하면 관리자 승인 후 달력에 반영한다.
- 관리자 모드에서는 사용자와 관리자를 저장/수정할 수 있어야 한다.
'''


def test_schema_map_injects_identity_user_schema_for_admin_approval_requirements():
    schema_map = _schema_map_from_file_ops([], REQ)
    assert 'User' in schema_map
    user = schema_map['User']
    assert user.feature_kind == 'CRUD'
    assert user.table == 'users'
    assert [col for _prop, col, _jt in user.fields] == [
        'user_id', 'login_id', 'password', 'user_name', 'role_cd', 'use_yn', 'reg_dt', 'upd_dt'
    ]
    assert user.field_comments['role_cd'] == '권한코드'



def test_identity_seed_sql_populates_admin_and_user_profiles_for_crud_schema():
    schema = schema_for(
        'User',
        inferred_fields=[
            ('userId', 'user_id', 'String'),
            ('loginId', 'login_id', 'String'),
            ('password', 'password', 'String'),
            ('userName', 'user_name', 'String'),
            ('roleCd', 'role_cd', 'String'),
            ('useYn', 'use_yn', 'String'),
        ],
        table='users',
        feature_kind='CRUD',
        strict_fields=True,
    )
    sql = _identity_seed_sql(schema)
    assert "WHERE NOT EXISTS (SELECT 1 FROM users WHERE login_id = 'admin')" in sql
    assert "WHERE NOT EXISTS (SELECT 1 FROM users WHERE login_id = 'user')" in sql
    assert "'ADMIN'" in sql
    assert "'USER'" in sql



def test_auth_seed_sql_includes_admin_and_user_profiles():
    schema = schema_for('Login', feature_kind='AUTH')
    sql = _auth_seed_sql(schema)
    assert "WHERE NOT EXISTS (SELECT 1 FROM login WHERE login_id = 'admin')" in sql
    assert "WHERE NOT EXISTS (SELECT 1 FROM login WHERE login_id = 'user')" in sql
    assert "'admin1234'" in sql
    assert "'user1234'" in sql



def test_identity_bundle_files_are_materialized_when_admin_mode_requires_user_management(tmp_path: Path):
    schema_map = _schema_map_from_file_ops([], REQ)
    cfg = ProjectConfig(project_name='demo', frontend_key='jsp', extra_requirements=REQ)
    changed = _ensure_identity_bundle_files(tmp_path, 'egovframework.demo', schema_map, cfg, [])
    assert 'src/main/java/egovframework/demo/user/web/UserController.java' in changed
    assert 'src/main/resources/egovframework/mapper/user/UserMapper.xml' in changed
    assert (tmp_path / 'src/main/webapp/WEB-INF/views/UserList.jsp').exists()
