from pathlib import Path

from app.ui.fallback_builder import build_builtin_fallback_content
from app.validation.backend_compile_repair import _expected_contract_bundle_targets, _contract_bundle_targets


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')


def test_fallback_builder_materializes_webmvc_config_as_auth_helper():
    body = build_builtin_fallback_content(
        'src/main/java/egovframework/test/config/WebMvcConfig.java',
        '전자정부 로그인 인터셉터 설정',
        project_name='test',
    )
    assert 'class WebMvcConfig {' in body
    assert 'WebMvcConfigurer' not in body
    assert '@Configuration' not in body
    assert 'HandlerInterceptor' not in body


def test_expected_contract_bundle_targets_include_auth_interceptor_for_webmvc():
    targets = _expected_contract_bundle_targets('src/main/java/egovframework/test/config/WebMvcConfig.java')
    assert 'src/main/java/egovframework/test/config/AuthLoginInterceptor.java' in targets


def test_contract_bundle_targets_include_existing_auth_interceptor_for_webmvc(tmp_path: Path):
    _write(tmp_path / 'src/main/java/egovframework/test/config/WebMvcConfig.java', 'package egovframework.test.config; public class WebMvcConfig {}')
    _write(tmp_path / 'src/main/java/egovframework/test/config/AuthLoginInterceptor.java', 'package egovframework.test.config; public class AuthLoginInterceptor {}')
    targets = _contract_bundle_targets(tmp_path, 'src/main/java/egovframework/test/config/WebMvcConfig.java')
    assert 'src/main/java/egovframework/test/config/AuthLoginInterceptor.java' in targets


import subprocess


def test_generated_webmvc_config_compiles_without_authlogininterceptor(tmp_path: Path):
    src = tmp_path / 'src/main/java'
    body = build_builtin_fallback_content(
        'src/main/java/egovframework/test/config/WebMvcConfig.java',
        '전자정부 로그인 인터셉터 설정',
        project_name='test',
    )
    _write(src / 'egovframework/test/config/WebMvcConfig.java', body)
    proc = subprocess.run([
        'javac',
        *[str(p) for p in src.rglob('*.java')],
    ], cwd=tmp_path, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
