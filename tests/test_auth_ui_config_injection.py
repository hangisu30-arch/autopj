from app.ui.state import ProjectConfig
from app.ui.analysis_bridge import build_analysis_from_config


def test_effective_extra_requirements_includes_ui_confirmed_auth_settings():
    cfg = ProjectConfig(
        project_name='authproj',
        frontend_key='jsp',
        database_key='mysql',
        extra_requirements='일정 관리와 로그인 기능을 만들어줘.',
        login_feature_enabled=True,
        auth_general_login=True,
        auth_unified_auth=True,
        auth_cert_login=True,
        auth_jwt_login=True,
        auth_primary_mode='jwt',
    ).normalize()

    text = cfg.effective_extra_requirements()
    assert '[AUTH UI CONFIRMED SETTINGS - SOURCE OF TRUTH]' in text
    assert '- 로그인 기능 포함' in text
    assert '- 통합인증 포함' in text
    assert '- 인증서 로그인 포함' in text
    assert '- JWT 로그인 포함' in text
    assert '- 기본 진입 방식: JWT 로그인 우선' in text


def test_analysis_uses_effective_extra_requirements_for_auth_domain_detection():
    cfg = ProjectConfig(
        project_name='authproj',
        frontend_key='jsp',
        database_key='mysql',
        extra_requirements='메인 화면을 만들어줘.',
        login_feature_enabled=True,
        auth_unified_auth=True,
        auth_jwt_login=True,
    ).normalize()

    result = build_analysis_from_config(cfg).to_dict()
    domains = result.get('domains') or []
    feature_kinds = {(d.get('feature_kind') or '').upper() for d in domains}
    assert 'AUTH' in feature_kinds
