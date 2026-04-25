from pathlib import Path

from execution_core.builtin_crud import builtin_file, schema_for
from execution_core.profiles.egov_spring_jsp import EgovSpringJspProfile


class _Ctx:
    def __init__(self):
        self.project_root = Path('/tmp/project')
        self.base_package = 'egovframework.test'


def test_builtin_file_uses_safe_package_segment_for_java_keyword_entity() -> None:
    schema = schema_for('If')
    vo = builtin_file('java/service/vo/IfVO.java', 'egovframework.test', schema)
    service_impl = builtin_file('java/service/impl/IfServiceImpl.java', 'egovframework.test', schema)

    assert vo is not None
    assert service_impl is not None
    assert 'package egovframework.test.if_.service.vo;' in vo
    assert 'package egovframework.test.if_.service.impl;' in service_impl
    assert 'import egovframework.test.if_.service.IfService;' in service_impl
    assert 'import egovframework.test.if_.service.mapper.IfMapper;' in service_impl
    assert 'import egovframework.test.if_.service.vo.IfVO;' in service_impl


def test_profile_resolve_path_uses_safe_directory_segment_for_java_keyword_entity() -> None:
    profile = EgovSpringJspProfile(_Ctx())
    resolved = profile.resolve_path('java/service/vo/IfVO.java')
    assert str(resolved).endswith('src/main/java/egovframework/test/if_/service/vo/IfVO.java')
