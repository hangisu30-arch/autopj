from pathlib import Path

from app.io.execution_core_apply import _rewrite_form_jsp_from_schema
from app.validation.post_generation_repair import _sanitize_frontend_ui_file
from app.validation.project_auto_repair import _rewrite_signup_jsp_to_safe_routes
from execution_core.builtin_crud import schema_for
from execution_core.feature_rules import FEATURE_KIND_CRUD


def test_member_form_keeps_useyn_visible(tmp_path: Path) -> None:
    rel = 'src/main/webapp/WEB-INF/views/member/memberForm.jsp'
    path = tmp_path / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('<html><body>broken</body></html>', encoding='utf-8')

    schema = schema_for(
        'Member',
        inferred_fields=[
            ('memberId', 'member_id', 'String'),
            ('memberNm', 'member_nm', 'String'),
            ('useYn', 'use_yn', 'String'),
            ('regDt', 'reg_dt', 'String'),
            ('createdAt', 'created_at', 'String'),
            ('updatedAt', 'updated_at', 'String'),
            ('createdBy', 'created_by', 'String'),
            ('roleCd', 'role_cd', 'String'),
        ],
        table='tb_member',
        feature_kind=FEATURE_KIND_CRUD,
        strict_fields=True,
    )

    assert _rewrite_form_jsp_from_schema(tmp_path, rel, schema) is True
    body = path.read_text(encoding='utf-8')
    assert 'name="useYn"' in body
    assert 'name="regDt"' in body
    assert 'name="createdAt"' in body
    assert 'name="updatedAt"' in body
    assert 'name="createdBy"' in body
    assert 'name="roleCd"' in body


def test_signup_rewrite_does_not_emit_empty_hidden_value(tmp_path: Path) -> None:
    signup_jsp = tmp_path / 'src/main/webapp/WEB-INF/views/signup/signupForm.jsp'
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
        '  @GetMapping("/signup.do") public String signup(){ return "signup/signupForm"; }\n'
        '  @PostMapping("/save.do") public String save(){ return "redirect:/login/login.do"; }\n'
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
        '  private String useYn;\n'
        '}\n',
        encoding='utf-8',
    )

    assert _rewrite_signup_jsp_to_safe_routes(signup_jsp, tmp_path) is True
    body = signup_jsp.read_text(encoding='utf-8')
    assert 'type="hidden" name="useYn"/>' in body
    assert 'type="hidden" name="useYn" value=""' not in body


def test_member_list_auth_sensitive_issue_rewrites_to_safe_list(tmp_path: Path) -> None:
    member_list = tmp_path / 'src/main/webapp/WEB-INF/views/member/memberList.jsp'
    member_list.parent.mkdir(parents=True, exist_ok=True)
    member_list.write_text(
        '<%@ taglib prefix="c" uri="http://java.sun.com/jsp/jstl/core"%>\n'
        '<table><thead><tr><th>password</th></tr></thead>'
        '<tbody><c:forEach var="row" items="${list}"><tr><td>${row.password}</td></tr></c:forEach></tbody></table>',
        encoding='utf-8',
    )

    vo = tmp_path / 'src/main/java/egovframework/test/member/service/vo/MemberVO.java'
    vo.parent.mkdir(parents=True, exist_ok=True)
    vo.write_text(
        'package egovframework.test.member.service.vo;\n'
        'public class MemberVO {\n'
        '  private String memberId;\n'
        '  private String memberNm;\n'
        '  private String password;\n'
        '  private String useYn;\n'
        '}\n',
        encoding='utf-8',
    )

    mapper = tmp_path / 'src/main/resources/egovframework/mapper/member/MemberMapper.xml'
    mapper.parent.mkdir(parents=True, exist_ok=True)
    mapper.write_text(
        '<mapper namespace="egovframework.test.member.service.mapper.MemberMapper">\n'
        '  <resultMap id="memberMap" type="egovframework.test.member.service.vo.MemberVO">\n'
        '    <id property="memberId" column="member_id"/>\n'
        '    <result property="memberNm" column="member_nm"/>\n'
        '    <result property="password" column="password"/>\n'
        '    <result property="useYn" column="use_yn"/>\n'
        '  </resultMap>\n'
        '</mapper>\n',
        encoding='utf-8',
    )

    changed = _sanitize_frontend_ui_file(member_list, 'non-auth UI must not expose auth-sensitive fields such as password/login_password')
    body = member_list.read_text(encoding='utf-8')
    assert changed is True
    lowered = body.lower()
    assert 'password' not in lowered
    assert 'login_password' not in lowered
    assert 'memberNm' in body or 'member_nm' in lowered
    assert 'useYn' in body or 'use_yn' in lowered
