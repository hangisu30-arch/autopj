from pathlib import Path

from app.io.execution_core_apply import _schema_map_from_file_ops
from app.ui.state import ProjectConfig
from app.validation.backend_compile_repair import _local_contract_repair
from execution_core.builtin_crud import extract_explicit_requirement_schemas

REQ = """
테이블 이름: users
컬럼 목록:
- user_id
- login_id
- password
- role_cd
"""


def test_extract_explicit_requirement_schemas_singularizes_plural_users_table():
    schema_map = extract_explicit_requirement_schemas(REQ)
    assert 'User' in schema_map
    assert 'Users' not in schema_map
    schema = schema_map['User']
    assert schema.table == 'users'
    assert [col for _prop, col, _jt in schema.fields] == ['user_id', 'login_id', 'password', 'role_cd']



def test_schema_map_from_file_ops_uses_user_key_for_users_table_contract():
    file_ops = [
        {
            'path': 'src/main/java/egovframework/test/user/web/UserController.java',
            'content': 'package egovframework.test.user.web; public class UserController {}',
        }
    ]
    schema_map = _schema_map_from_file_ops(file_ops, extra_requirements=REQ)
    assert 'User' in schema_map
    assert 'Users' not in schema_map
    schema = schema_map['User']
    assert schema.table == 'users'
    assert [col for _prop, col, _jt in schema.fields] == ['user_id', 'login_id', 'password', 'role_cd']



def test_local_contract_repair_materializes_missing_user_bundle(tmp_path):
    project_root = tmp_path
    controller = project_root / 'src/main/java/egovframework/test/user/web/UserController.java'
    controller.parent.mkdir(parents=True, exist_ok=True)
    controller.write_text(
        'package egovframework.test.user.web;\n\n'
        'import egovframework.test.user.service.UserService;\n'
        'import egovframework.test.user.service.vo.UserVO;\n'
        'public class UserController {\n'
        '  private final UserService userService;\n'
        '  public UserController(UserService userService) { this.userService = userService; }\n'
        '  public UserVO demo() { return null; }\n'
        '}\n',
        encoding='utf-8',
    )
    manifest = {
        'src/main/java/egovframework/test/user/web/UserController.java': {
            'spec': REQ + '\n사용자 관리 기능을 구현해줘. CRUD가 필요해.'
        }
    }
    runtime_report = {
        'compile': {
            'errors': [
                {'code': 'cannot_find_symbol', 'path': 'src/main/java/egovframework/test/user/web/UserController.java'}
            ]
        }
    }
    cfg = ProjectConfig(project_name='test', frontend_key='jsp')

    changed = _local_contract_repair(project_root, cfg, manifest, [
        'src/main/java/egovframework/test/user/web/UserController.java'
    ], runtime_report)

    assert changed
    service_path = project_root / 'src/main/java/egovframework/test/user/service/UserService.java'
    impl_path = project_root / 'src/main/java/egovframework/test/user/service/impl/UserServiceImpl.java'
    vo_path = project_root / 'src/main/java/egovframework/test/user/service/vo/UserVO.java'
    mapper_java = project_root / 'src/main/java/egovframework/test/user/service/mapper/UserMapper.java'
    mapper_xml = project_root / 'src/main/resources/egovframework/mapper/user/UserMapper.xml'
    assert service_path.exists()
    assert impl_path.exists()
    assert vo_path.exists()
    assert mapper_java.exists()
    assert mapper_xml.exists()
    assert 'interface UserService' in service_path.read_text(encoding='utf-8')
    assert 'class UserServiceImpl' in impl_path.read_text(encoding='utf-8')
    assert 'class UserVO' in vo_path.read_text(encoding='utf-8')
