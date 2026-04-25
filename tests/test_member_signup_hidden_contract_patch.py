from pathlib import Path

from app.io.execution_core_apply import _rewrite_form_jsp_from_schema
from app.validation.project_auto_repair import _rewrite_signup_jsp_to_safe_routes
from execution_core.builtin_crud import builtin_file, schema_for
from execution_core.feature_rules import FEATURE_KIND_CRUD


def test_rewrite_form_jsp_from_schema_adds_hidden_runtime_fields_and_skips_generation_metadata(tmp_path: Path) -> None:
    rel = 'src/main/webapp/WEB-INF/views/member/memberForm.jsp'
    path = tmp_path / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('<html><body>broken</body></html>', encoding='utf-8')

    schema = schema_for(
        'Member',
        inferred_fields=[
            ('memberId', 'member_id', 'String'),
            ('memberNm', 'member_nm', 'String'),
            ('password', 'password', 'String'),
            ('roleCd', 'role_cd', 'String'),
            ('useYn', 'use_yn', 'String'),
            ('createdBy', 'created_by', 'String'),
            ('db', 'db', 'String'),
            ('schemaName', 'schema_name', 'String'),
        ],
        table='tb_member',
        feature_kind=FEATURE_KIND_CRUD,
        strict_fields=True,
    )

    changed = _rewrite_form_jsp_from_schema(tmp_path, rel, schema)
    body = path.read_text(encoding='utf-8')

    assert changed is True
    assert 'name="memberId"' in body
    assert 'name="memberNm"' in body
    assert 'name="password"' in body
    assert 'type="password"' in body
    assert 'name="roleCd"' in body
    assert 'name="useYn"' in body
    assert 'name="createdBy"' in body
    assert 'name="db"' not in body
    assert 'name="schemaName"' not in body


def test_builtin_list_and_detail_do_not_render_generation_metadata_fields() -> None:
    schema = schema_for(
        'Member',
        inferred_fields=[
            ('memberId', 'member_id', 'String'),
            ('memberNm', 'member_nm', 'String'),
            ('roleCd', 'role_cd', 'String'),
            ('db', 'db', 'String'),
            ('schemaName', 'schema_name', 'String'),
            ('tableName', 'table_name', 'String'),
            ('packageName', 'package_name', 'String'),
        ],
        table='tb_member',
        feature_kind=FEATURE_KIND_CRUD,
        strict_fields=True,
    )

    list_jsp = builtin_file('jsp/member/memberList.jsp', 'egovframework.test', schema)
    detail_jsp = builtin_file('jsp/member/memberDetail.jsp', 'egovframework.test', schema)

    assert list_jsp is not None and detail_jsp is not None
    lowered_list = list_jsp.lower()
    lowered_detail = detail_jsp.lower()
    assert 'schema_name' not in lowered_list
    assert 'table_name' not in lowered_list
    assert 'package_name' not in lowered_list
    assert 'schema_name' not in lowered_detail
    assert 'table_name' not in lowered_detail
    assert 'package_name' not in lowered_detail


def test_signup_rewrite_uses_signup_vo_and_keeps_managed_fields_hidden(tmp_path: Path) -> None:
    signup_jsp = tmp_path / 'src/main/webapp/WEB-INF/views/login/signup.jsp'
    signup_jsp.parent.mkdir(parents=True, exist_ok=True)
    signup_jsp.write_text('<html><body>broken</body></html>', encoding='utf-8')

    controller = tmp_path / 'src/main/java/egovframework/test/member/web/MemberController.java'
    controller.parent.mkdir(parents=True, exist_ok=True)
    controller.write_text(
        'package egovframework.test.member.web;\n'
        'import org.springframework.stereotype.Controller;\n'
        'import org.springframework.web.bind.annotation.GetMapping;\n'
        'import org.springframework.web.bind.annotation.PostMapping;\n'
        'import org.springframework.web.bind.annotation.RequestMapping;\n'
        '@Controller\n@RequestMapping("/member")\n'
        'public class MemberController {\n'
        '  @GetMapping("/signup.do") public String signup(){ return "login/signup"; }\n'
        '  @PostMapping("/save.do") public String save(){ return "redirect:/login/login.do"; }\n'
        '  @GetMapping("/checkLoginId.do") public String check(){ return "jsonView"; }\n'
        '}\n',
        encoding='utf-8',
    )

    vo = tmp_path / 'src/main/java/egovframework/test/member/service/vo/SignupVO.java'
    vo.parent.mkdir(parents=True, exist_ok=True)
    vo.write_text(
        'package egovframework.test.member.service.vo;\n'
        'public class SignupVO {\n'
        '  private String memberId;\n'
        '  private String memberNm;\n'
        '  private String password;\n'
        '  private String roleCd;\n'
        '  private String useYn;\n'
        '  private String createdBy;\n'
        '  private String createdDt;\n'
        '  private String lastModifiedBy;\n'
        '  private String lastModifiedDt;\n'
        '}\n',
        encoding='utf-8',
    )

    changed = _rewrite_signup_jsp_to_safe_routes(signup_jsp, tmp_path)
    body = signup_jsp.read_text(encoding='utf-8')

    assert changed is True
    assert 'action="<c:url value=\'/member/save.do\'/>"' in body
    assert 'name="memberId"' in body
    assert 'name="memberNm"' in body
    assert 'name="password"' in body
    assert 'name="roleCd"' in body
    assert 'name="useYn"' in body
    assert 'name="createdBy"' in body
    assert 'name="createdDt"' in body
    assert 'name="lastModifiedBy"' in body
    assert 'name="lastModifiedDt"' in body
    assert '/member/checkLoginId.do' in body
    assert 'jwtLogin' not in body
