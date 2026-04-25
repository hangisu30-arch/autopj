from pathlib import Path

from app.io.execution_core_apply import (
    _rewrite_detail_jsp_from_schema,
    _rewrite_form_jsp_from_schema,
    _rewrite_list_jsp_from_schema,
)
from app.ui.generated_content_validator import validate_generated_content
from app.validation.backend_compile_repair import enforce_generated_project_invariants
from execution_core.builtin_crud import schema_for
from execution_core.feature_rules import FEATURE_KIND_CRUD


def _member_schema_with_metadata():
    return schema_for(
        'Member',
        inferred_fields=[
            ('memberId', 'member_id', 'String'),
            ('memberName', 'member_name', 'String'),
            ('useYn', 'use_yn', 'String'),
            ('regDt', 'reg_dt', 'String'),
            ('db', 'db', 'String'),
            ('schemaName', 'schema_name', 'String'),
            ('tableName', 'table_name', 'String'),
            ('packageName', 'package_name', 'String'),
        ],
        table='tb_member',
        feature_kind=FEATURE_KIND_CRUD,
        strict_fields=True,
    )


def test_jsp_schema_rewriters_exclude_generation_metadata_fields(tmp_path: Path) -> None:
    schema = _member_schema_with_metadata()
    rels = [
        'src/main/webapp/WEB-INF/views/member/memberList.jsp',
        'src/main/webapp/WEB-INF/views/member/memberForm.jsp',
        'src/main/webapp/WEB-INF/views/member/memberDetail.jsp',
    ]
    rewriters = {
        'memberList.jsp': _rewrite_list_jsp_from_schema,
        'memberForm.jsp': _rewrite_form_jsp_from_schema,
        'memberDetail.jsp': _rewrite_detail_jsp_from_schema,
    }

    for rel in rels:
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('<html><body>broken</body></html>', encoding='utf-8')
        changed = rewriters[path.name](tmp_path, rel, schema)
        assert changed is True
        body = path.read_text(encoding='utf-8')
        lowered = body.lower()
        assert 'schemaname' not in lowered
        assert 'tablename' not in lowered
        assert 'packagename' not in lowered
        assert '>db<' not in lowered
        assert 'membername' in lowered
        ok, reason = validate_generated_content(rel, body, frontend_key='jsp')
        assert ok, reason


def test_invariants_normalize_boot_application_to_symbol_safe_minimal_entry(tmp_path: Path) -> None:
    boot_path = tmp_path / 'src/main/java/egovframework/test/EgovBootApplication.java'
    boot_path.parent.mkdir(parents=True, exist_ok=True)
    boot_path.write_text(
        'package egovframework.test;\n\n'
        'import org.springframework.boot.SpringApplication;\n'
        'import org.springframework.boot.autoconfigure.SpringBootApplication;\n\n'
        '@SpringBootApplication\n'
        'public class EgovBootApplication {\n'
        '    public static void main(String[] args) {\n'
        '        SpringApplication.run(TestBootApplication.class, args);\n'
        '    }\n'
        '}\n',
        encoding='utf-8',
    )
    member_controller = tmp_path / 'src/main/java/egovframework/test/member/web/MemberController.java'
    member_controller.parent.mkdir(parents=True, exist_ok=True)
    member_controller.write_text(
        'package egovframework.test.member.web;\n\n'
        'public class MemberController {}\n',
        encoding='utf-8',
    )

    report = enforce_generated_project_invariants(tmp_path)

    body = boot_path.read_text(encoding='utf-8')
    assert report['changed_count'] >= 1
    assert 'SpringApplication.run(EgovBootApplication.class, args);' in body
    assert '@SpringBootApplication(scanBasePackages = {"egovframework.test"})' in body
    assert 'TestBootApplication.class' not in body
