from pathlib import Path

from app.ui.state import ProjectConfig
from app.validation.backend_compile_repair import _local_contract_repair

REQ = """
테이블 이름: users
컬럼 목록:
- user_id
- login_id
- password
- role_cd
"""


def test_local_contract_repair_materializes_user_bundle_from_service_impl_target(tmp_path):
    project_root = tmp_path
    svc_impl = project_root / 'src/main/java/egovframework/test/user/service/impl/UserServiceImpl.java'
    svc_impl.parent.mkdir(parents=True, exist_ok=True)
    svc_impl.write_text(
        'package egovframework.test.user.service.impl;\n\n'
        'import org.springframework.stereotype.Service;\n'
        'import egovframework.test.user.service.UserService;\n'
        'import egovframework.test.user.service.mapper.UserMapper;\n'
        'import egovframework.test.user.service.vo.UserVO;\n\n'
        '@Service("userService")\n'
        'public class UserServiceImpl implements UserService {\n'
        '  private final UserMapper userMapper;\n'
        '  public UserServiceImpl(UserMapper userMapper) { this.userMapper = userMapper; }\n'
        '  public UserVO demo(String id) { return userMapper.selectUser(id); }\n'
        '}\n',
        encoding='utf-8',
    )
    manifest = {
        'src/main/java/egovframework/test/user/service/impl/UserServiceImpl.java': {
            'spec': REQ + '\n사용자 관리 CRUD를 구현해줘.'
        }
    }
    runtime_report = {
        'compile': {
            'errors': [
                {'code': 'cannot_find_symbol', 'path': 'src/main/java/egovframework/test/user/service/impl/UserServiceImpl.java'},
                {'code': 'cannot_find_symbol', 'path': 'src/main/java/egovframework/test/user/service/impl/UserServiceImpl.java'},
            ]
        }
    }
    cfg = ProjectConfig(project_name='test', frontend_key='jsp')

    changed = _local_contract_repair(project_root, cfg, manifest, [
        'src/main/java/egovframework/test/user/service/impl/UserServiceImpl.java'
    ], runtime_report)

    assert changed
    assert (project_root / 'src/main/java/egovframework/test/user/service/UserService.java').exists()
    assert (project_root / 'src/main/java/egovframework/test/user/service/mapper/UserMapper.java').exists()
    assert (project_root / 'src/main/java/egovframework/test/user/service/vo/UserVO.java').exists()
    body = (project_root / 'src/main/java/egovframework/test/user/service/impl/UserServiceImpl.java').read_text(encoding='utf-8')
    assert 'import egovframework.test.user.service.mapper.UserMapper;' in body
    assert 'import egovframework.test.user.service.vo.UserVO;' in body
