from pathlib import Path

from app.io.execution_core_apply import _canonicalize_auth_raw_path, _normalize_out_path
from app.validation.post_generation_repair import _build_manifest
from app.ui.state import ProjectConfig
from execution_core.builtin_crud import builtin_file, schema_for
from execution_core.feature_rules import FEATURE_KIND_AUTH


def test_canonicalize_auth_raw_path_maps_webmvc_config_to_config_helper():
    schema_map = {'Login': schema_for('Login', feature_kind=FEATURE_KIND_AUTH, unified_auth=True)}
    assert _canonicalize_auth_raw_path('src/main/java/egovframework/test/generic/WebMvcConfig.java', schema_map) == 'java/config/WebMvcConfig.java'


def test_normalize_out_path_canonicalizes_misplaced_webmvc_config():
    rel = _normalize_out_path('src/main/java/egovframework/test/generic/WebMvcConfig.java', 'egovframework.test', 'Login', '', '')
    assert rel == 'src/main/java/egovframework/test/config/WebMvcConfig.java'


def test_build_manifest_uses_canonical_webmvc_config_path_for_execution_core(tmp_path: Path):
    cfg = ProjectConfig(project_name='test', frontend_key='jsp', login_feature_enabled=True, auth_unified_auth=True)
    schema = schema_for('Login', feature_kind=FEATURE_KIND_AUTH, unified_auth=True)
    file_ops = [
        {
            'path': 'src/main/java/egovframework/test/generic/WebMvcConfig.java',
            'purpose': 'web mvc config for login interceptor',
            'content': builtin_file('java/config/WebMvcConfig.java', 'egovframework.test', schema),
        }
    ]

    manifest = _build_manifest(file_ops, tmp_path, cfg, use_execution_core=True)

    assert 'src/main/java/egovframework/test/config/WebMvcConfig.java' in manifest
    assert 'src/main/java/egovframework/test/generic/WebMvcConfig.java' not in manifest
