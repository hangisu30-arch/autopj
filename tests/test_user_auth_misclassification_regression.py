from execution_core.builtin_crud import infer_schema_from_file_ops
from app.ui.fallback_builder import build_builtin_fallback_content

REQ = """
테이블 이름: users
컬럼 목록:
- user_id
- login_id
- password
- role_cd
"""


def test_infer_schema_from_user_crud_file_ops_does_not_collapse_to_auth():
    file_ops = [
        {
            'path': 'src/main/java/egovframework/test/user/service/impl/UserServiceImpl.java',
            'purpose': 'User service implementation',
            'content': REQ + '\n사용자 관리 CRUD 구현',
        },
        {
            'path': 'src/main/java/egovframework/test/user/web/UserController.java',
            'purpose': 'User controller',
            'content': '@GetMapping("/list.do")',
        },
    ]
    schema = infer_schema_from_file_ops(file_ops, entity='User')
    assert schema.feature_kind == 'CRUD'


def test_fallback_builder_keeps_user_service_impl_as_crud_even_with_login_fields():
    body = build_builtin_fallback_content(
        'src/main/java/egovframework/test/user/service/impl/UserServiceImpl.java',
        REQ + '\n사용자 관리 CRUD를 구현해줘.',
        project_name='test',
    )
    assert 'class UserServiceImpl implements UserService' in body
    assert 'private final UserMapper userMapper;' in body
    assert 'findByLoginId' not in body
