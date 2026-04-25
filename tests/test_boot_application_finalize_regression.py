from pathlib import Path
from types import SimpleNamespace

from execution_core.project_patcher import patch_boot_application
from app.io.execution_core_apply import apply_file_ops_with_execution_core
from app.ui.state import ProjectConfig
from app.validation.backend_compile_repair import _local_contract_repair


def _read(path: Path) -> str:
    return path.read_text(encoding='utf-8')


def test_patch_boot_application_rewrites_invalid_existing_boot_source(tmp_path: Path):
    boot_path = tmp_path / 'src/main/java/egovframework/test/EgovBootApplication.java'
    boot_path.parent.mkdir(parents=True, exist_ok=True)
    boot_path.write_text(
        'package egovframework.test;\n\n'
        'import missing.symbol.BootThing;\n\n'
        '@SpringBootApplication(scanBasePackages = {egovframework.test})\n'
        'public class EgovBootApplication {\n'
        '    public static void main(String[] args) {\n'
        '        SpringApplication.run(BootThing.class, args);\n'
        '    }\n'
        '}\n',
        encoding='utf-8',
    )
    member_vo = tmp_path / 'src/main/java/egovframework/test/member/service/vo/MemberVO.java'
    member_vo.parent.mkdir(parents=True, exist_ok=True)
    member_vo.write_text(
        'package egovframework.test.member.service.vo;\n\npublic class MemberVO {}\n',
        encoding='utf-8',
    )

    patched = patch_boot_application(tmp_path, 'egovframework.test')

    body = _read(patched)
    assert patched == boot_path
    assert 'import missing.symbol.BootThing;' not in body
    assert '@SpringBootApplication(scanBasePackages = {"egovframework.test"})' in body
    assert 'SpringApplication.run(EgovBootApplication.class, args);' in body


def test_apply_file_ops_finalizes_bad_generated_boot_application(tmp_path: Path):
    cfg = ProjectConfig(project_name='test', frontend_key='jsp', database_key='sqlite')
    file_ops = [
        {
            'path': 'src/main/java/egovframework/test/EgovBootApplication.java',
            'content': (
                'package egovframework.test;\n\n'
                'import bad.missing.Symbol;\n\n'
                '@SpringBootApplication(scanBasePackages = {egovframework.test})\n'
                'public class EgovBootApplication {\n'
                '    public static void main(String[] args) {\n'
                '        SpringApplication.run(Symbol.class, args);\n'
                '    }\n'
                '}\n'
            ),
        },
        {
            'path': 'java/service/vo/MemberVO.java',
            'content': 'package egovframework.test.member.service.vo;\n\npublic class MemberVO {}\n',
        },
    ]

    report = apply_file_ops_with_execution_core(file_ops, tmp_path, cfg, overwrite=True)

    boot_path = tmp_path / 'src/main/java/egovframework/test/EgovBootApplication.java'
    body = _read(boot_path)
    assert 'bad.missing.Symbol' not in body
    assert 'SpringApplication.run(EgovBootApplication.class, args);' in body
    assert '@SpringBootApplication(scanBasePackages = {"egovframework.test"})' in body
    assert report['patched'].get('boot_application_final') == 'src/main/java/egovframework/test/EgovBootApplication.java'


def test_local_contract_repair_canonicalizes_boot_application_target(tmp_path: Path):
    boot_path = tmp_path / 'src/main/java/egovframework/test/EgovBootApplication.java'
    boot_path.parent.mkdir(parents=True, exist_ok=True)
    boot_path.write_text(
        'package egovframework.test;\n\n'
        'import broken.Missing;\n\n'
        '@SpringBootApplication(scanBasePackages = {egovframework.test})\n'
        'public class EgovBootApplication {\n'
        '    public static void main(String[] args) {\n'
        '        SpringApplication.run(Missing.class, args);\n'
        '    }\n'
        '}\n',
        encoding='utf-8',
    )

    changed = _local_contract_repair(
        tmp_path,
        SimpleNamespace(project_name='test'),
        {},
        ['src/main/java/egovframework/test/EgovBootApplication.java'],
        {'compile': {'errors': [{'path': 'src/main/java/egovframework/test/EgovBootApplication.java', 'code': 'cannot_find_symbol'}]}},
    )

    body = _read(boot_path)
    assert any(item.get('reason') == 'boot application canonicalized after compile failure' for item in changed)
    assert 'broken.Missing' not in body
    assert 'SpringApplication.run(EgovBootApplication.class, args);' in body
