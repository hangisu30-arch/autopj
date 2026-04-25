from pathlib import Path
import subprocess

from execution_core.builtin_crud import builtin_file, schema_for
from execution_core.feature_rules import FEATURE_KIND_AUTH


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding='utf-8')


def test_generated_jwt_token_provider_regression_guard():
    schema = schema_for('Login', feature_kind=FEATURE_KIND_AUTH, unified_auth=True, jwt_login=True)
    jwt_provider = builtin_file('java/config/JwtTokenProvider.java', 'egovframework.test', schema)

    assert 'class JwtTokenProvider' in jwt_provider
    assert 'String header = base64Json(' in jwt_provider
    assert 'String payload = base64Json(' in jwt_provider
    assert 'base64Json("{"alg":"HS256","typ":"JWT"}")' not in jwt_provider
    assert 'base64Json("{"sub":"" + escape(subject) + "","iat":" + now + ","exp":" + exp + "}")' not in jwt_provider
    assert 'return value.replace(' in jwt_provider


def test_generated_jwt_token_provider_compiles_with_minimal_stubs(tmp_path: Path):
    schema = schema_for('Login', feature_kind=FEATURE_KIND_AUTH, unified_auth=True, jwt_login=True)
    jwt_provider = builtin_file('java/config/JwtTokenProvider.java', 'egovframework.test', schema)

    src_root = tmp_path / 'src'
    _write(
        src_root / 'egovframework/test/config/JwtTokenProvider.java',
        jwt_provider,
    )
    _write(
        src_root / 'org/springframework/stereotype/Component.java',
        'package org.springframework.stereotype; public @interface Component {}',
    )
    _write(
        src_root / 'org/springframework/beans/factory/annotation/Value.java',
        'package org.springframework.beans.factory.annotation; public @interface Value { String value(); }',
    )

    result = subprocess.run(
        [
            'javac',
            '-encoding', 'UTF-8',
            '-d', str(tmp_path / 'classes'),
            str(src_root / 'org/springframework/stereotype/Component.java'),
            str(src_root / 'org/springframework/beans/factory/annotation/Value.java'),
            str(src_root / 'egovframework/test/config/JwtTokenProvider.java'),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
