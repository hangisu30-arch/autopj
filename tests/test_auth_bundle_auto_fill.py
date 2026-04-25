from pathlib import Path

from app.io.execution_core_apply import _ensure_auth_bundle_files
from app.ui.state import ProjectConfig
from execution_core.builtin_crud import schema_for
from execution_core.feature_rules import FEATURE_KIND_AUTH


def test_missing_auth_bundle_files_are_synthesized(tmp_path: Path):
    cfg = ProjectConfig(frontend_key='jsp', login_feature_enabled=True, auth_unified_auth=True)
    schema = schema_for('Login', feature_kind=FEATURE_KIND_AUTH, unified_auth=True)
    changed = _ensure_auth_bundle_files(tmp_path, 'egovframework.test', {'Login': schema}, cfg)

    expected = [
        'src/main/java/egovframework/test/login/service/LoginService.java',
        'src/main/java/egovframework/test/login/service/vo/LoginVO.java',
        'src/main/java/egovframework/test/login/service/impl/LoginServiceImpl.java',
        'src/main/java/egovframework/test/login/service/impl/LoginDAO.java',
        'src/main/java/egovframework/test/login/service/mapper/LoginMapper.java',
        'src/main/java/egovframework/test/login/web/LoginController.java',
        'src/main/webapp/WEB-INF/views/login/main.jsp',
        'src/main/webapp/WEB-INF/views/login/integrationGuide.jsp',
    ]

    for rel in expected:
        assert (tmp_path / rel).exists(), rel
    assert changed
