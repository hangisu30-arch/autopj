from types import SimpleNamespace
from pathlib import Path

from app.ui.fallback_builder import build_builtin_fallback_content
from app.validation.backend_compile_repair import _align_java_public_type_to_filename, _remove_boot_crud_artifacts
from app.validation.project_auto_repair import _repair_mapper_namespace_mismatch
from app.validation.generated_project_validator import validate_generated_project


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding='utf-8')


def test_mapper_namespace_repair_does_not_inject_control_character(tmp_path: Path):
    project_root = tmp_path / 'test'
    mapper_java = project_root / 'src/main/java/egovframework/test/user/service/mapper/UserMapper.java'
    mapper_xml = project_root / 'src/main/resources/egovframework/mapper/user/UserMapper.xml'

    _write(
        mapper_java,
        'package egovframework.test.user.service.mapper;\n\n'
        'public interface UserMapper {}\n',
    )
    _write(
        mapper_xml,
        '<mapper namespace="egovframework.wrong.user.service.mapper.UserMapper">\n'
        '</mapper>\n',
    )

    changed = _repair_mapper_namespace_mismatch(mapper_xml, project_root=project_root)

    assert changed is True
    xml = mapper_xml.read_text(encoding='utf-8')
    assert '\x03' not in xml
    assert 'namespace="egovframework.test.user.service.mapper.UserMapper"' in xml


def test_boot_artifacts_are_removed_and_not_rebuilt(tmp_path: Path):
    project_root = tmp_path / 'test'
    bogus_java = project_root / 'src/main/java/egovframework/test/service/EgovBootApplicationService.java'
    bogus_xml = project_root / 'src/main/resources/egovframework/mapper/test/EgovBootApplicationMapper.xml'

    _write(bogus_java, 'package egovframework.test.service; public interface EgovBootApplicationService {}\n')
    _write(bogus_xml, '<mapper namespace="egovframework.test.generated.egovBootApplication.service.mapper.EgovBootApplicationMapper"></mapper>\n')

    removed = _remove_boot_crud_artifacts(project_root)

    assert 'src/main/java/egovframework/test/service/EgovBootApplicationService.java' in removed
    assert 'src/main/resources/egovframework/mapper/test/EgovBootApplicationMapper.xml' in removed
    assert not bogus_java.exists()
    assert not bogus_xml.exists()
    assert build_builtin_fallback_content('src/main/java/egovframework/test/service/EgovBootApplicationService.java', 'boot artifact', project_name='test') == ''


def test_align_java_public_type_to_filename_repairs_case_mismatch(tmp_path: Path):
    java_file = tmp_path / 'src/main/java/egovframework/test/user/service/vo/UserVO.java'
    _write(
        java_file,
        'package egovframework.test.user.service.vo;\n\n'
        'public class userVO {\n'
        '    private String name;\n'
        '}\n',
    )

    changed = _align_java_public_type_to_filename(java_file)

    assert changed is True
    body = java_file.read_text(encoding='utf-8')
    assert 'public class UserVO' in body
    assert 'public class userVO' not in body


def test_generated_project_validator_skips_boot_mapper_artifacts(tmp_path: Path):
    project_root = tmp_path / 'test'
    mapper_java = project_root / 'src/main/java/egovframework/test/generated/egovBootApplication/service/mapper/EgovBootApplicationMapper.java'
    mapper_xml = project_root / 'src/main/resources/egovframework/mapper/generated/EgovBootApplicationMapper.xml'

    _write(
        mapper_java,
        'package egovframework.test.generated.egovBootApplication.service.mapper;\n\n'
        'public interface EgovBootApplicationMapper {}\n',
    )
    _write(
        mapper_xml,
        '<mapper namespace="egovframework.test.generated.egovBootApplication.service.mapper.EgovBootApplicationMapper">\n'
        '</mapper>\n',
    )

    report = validate_generated_project(project_root, SimpleNamespace(frontend_key='jsp'), include_runtime=False)

    assert isinstance(report, dict)
    issues = report.get('issues', [])
    assert not any(issue.get('type') == 'mapper_namespace_mismatch' for issue in issues)
