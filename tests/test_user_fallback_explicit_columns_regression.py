from app.ui.fallback_builder import build_builtin_fallback_content

REQ = """
테이블 이름: users
컬럼 목록:
- id
- login_id
- password
- created_at
사용자 관리 CRUD를 구현해줘.
"""


def test_user_vo_fallback_respects_explicit_column_list():
    body = build_builtin_fallback_content(
        'src/main/java/egovframework/test/user/service/vo/UserVO.java',
        REQ,
        project_name='test',
    )
    assert 'private String id;' in body
    assert 'private String loginId;' in body
    assert 'private String password;' in body
    assert 'private String createdAt;' in body
    assert 'userName' not in body
    assert 'email' not in body
