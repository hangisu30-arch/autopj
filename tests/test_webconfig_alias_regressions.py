from pathlib import Path

from app.io.execution_core_apply import _normalize_out_path, _canonicalize_auth_raw_path
from app.ui.fallback_builder import build_builtin_fallback_content
from app.validation.generated_project_validator import _is_illegal_infra_artifact_rel
from app.validation.backend_compile_repair import enforce_generated_project_invariants
from execution_core.builtin_crud import schema_for
from execution_core.feature_rules import FEATURE_KIND_AUTH


def _write(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding='utf-8')


def test_normalize_out_path_maps_webconfig_to_webmvcconfig():
    rel = _normalize_out_path(
        'src/main/java/egovframework/test/spring/WebConfig.java',
        'egovframework.test',
        'Login',
        '',
        '',
    )
    assert rel == 'src/main/java/egovframework/test/config/WebMvcConfig.java'


def test_canonicalize_auth_raw_path_maps_webconfig_alias():
    schema_map = {'Login': schema_for('Login', feature_kind=FEATURE_KIND_AUTH)}
    logical = _canonicalize_auth_raw_path('src/main/java/egovframework/test/spring/WebConfig.java', schema_map)
    assert logical == 'java/config/WebMvcConfig.java'


def test_fallback_builder_generates_webmvcconfig_for_webconfig_alias():
    body = build_builtin_fallback_content(
        'src/main/java/egovframework/test/spring/WebConfig.java',
        'spring web config helper',
        project_name='test',
    )
    assert 'class WebMvcConfig {' in body
    assert 'WebMvcConfigurer' not in body


def test_validator_marks_webconfig_mapper_as_illegal_infra_artifact():
    assert _is_illegal_infra_artifact_rel('src/main/resources/egovframework/mapper/spring/WebConfigMapper.xml') is True


def test_invariants_remove_webconfig_crud_artifacts(tmp_path: Path):
    _write(tmp_path / 'src/main/java/egovframework/test/spring/WebConfig.java', 'package egovframework.test.spring; public class WebConfig {}')
    _write(tmp_path / 'src/main/java/egovframework/test/spring/service/impl/WebConfigServiceImpl.java', 'package egovframework.test.spring.service.impl; public class WebConfigServiceImpl {}')
    _write(tmp_path / 'src/main/resources/egovframework/mapper/spring/WebConfigMapper.xml', '<mapper namespace="egovframework.test.spring.webConfig.service.mapper.WebConfigMapper"></mapper>')
    result = enforce_generated_project_invariants(tmp_path)
    changed_paths = {item['path'] for item in result.get('changed') or []}
    assert 'src/main/java/egovframework/test/spring/WebConfig.java' in changed_paths
    assert 'src/main/java/egovframework/test/spring/service/impl/WebConfigServiceImpl.java' in changed_paths
    assert 'src/main/resources/egovframework/mapper/spring/WebConfigMapper.xml' in changed_paths
