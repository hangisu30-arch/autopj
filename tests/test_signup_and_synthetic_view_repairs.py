from pathlib import Path

from app.validation.generated_project_validator import _scan_form_fields_cover_all_columns
from app.validation.project_auto_repair import (
    _repair_form_fields_incomplete,
    _repair_jsp_missing_route_reference,
    _repair_malformed_jsp_structure,
)


def _write(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding='utf-8')


SIGNUP_CONTROLLER = """
package egovframework.test.signup.web;

import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.ui.Model;

@Controller
@RequestMapping("/signup")
public class SignupController {
    @GetMapping("/form.do")
    public String form(Model model) { return "signup/signupForm"; }

    @PostMapping("/save.do")
    public String save(Model model) { return "redirect:/login/login.do"; }

    @GetMapping("/checkLoginId.do")
    public String check(Model model) { return "signup/signupForm"; }
}
"""

SIGNUP_VO = """
package egovframework.test.signup.service.vo;

public class SignupVO {
    private String loginId;
    private String password;
    private String roleCd;
    private String useYn;
    private String createdBy;
    private String createdDt;
    private String lastModifiedBy;
    private String lastModifiedDt;
}
"""

MEMBER_CONTROLLER = """
package egovframework.test.member.web;

import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.ui.Model;

@Controller
@RequestMapping("/member")
public class MemberController {
    @GetMapping("/form.do")
    public String form(Model model) { return "member/memberForm"; }

    @GetMapping("/list.do")
    public String list(Model model) { return "member/memberList"; }

    @PostMapping("/save.do")
    public String save(Model model) { return "redirect:/member/list.do"; }
}
"""


def test_signup_form_repair_uses_domain_routes_and_hidden_system_fields(tmp_path: Path) -> None:
    _write(tmp_path / 'src/main/java/egovframework/test/signup/web/SignupController.java', SIGNUP_CONTROLLER)
    _write(tmp_path / 'src/main/java/egovframework/test/signup/service/vo/SignupVO.java', SIGNUP_VO)
    signup_jsp = tmp_path / 'src/main/webapp/WEB-INF/views/signup/signupForm.jsp'
    _write(signup_jsp, '<form action="<c:url value="/signupform/save.do"/>"></form>')

    changed = _repair_form_fields_incomplete(
        signup_jsp,
        issue={'details': {'missing_fields': ['loginId', 'password', 'roleCd', 'useYn', 'createdBy']}},
        project_root=tmp_path,
    )

    assert changed
    body = signup_jsp.read_text(encoding='utf-8')
    assert "/signup/save.do" in body
    assert "/signupform/save.do" not in body
    assert 'name="roleCd"' in body and 'type="hidden"' in body
    assert 'name="useYn"' in body and 'type="hidden"' in body
    assert 'name="createdBy"' in body and 'type="hidden"' in body
    assert 'name="loginId"' in body
    assert 'name="password"' in body



def test_unexpected_signup_calendar_is_redirected_to_signup_form(tmp_path: Path) -> None:
    _write(tmp_path / 'src/main/java/egovframework/test/signup/web/SignupController.java', SIGNUP_CONTROLLER)
    signup_calendar = tmp_path / 'src/main/webapp/WEB-INF/views/signup/signupCalendar.jsp'
    _write(signup_calendar, '<c:out value=""/><a href="<c:url value="/signup/list.do"/>">목록</a>')

    changed = _repair_malformed_jsp_structure(signup_calendar, project_root=tmp_path)

    assert changed
    body = signup_calendar.read_text(encoding='utf-8')
    assert '/signup/form.do' in body
    assert 'autopjCheckLoginId' not in body



def test_synthetic_views_form_routes_are_rebound_and_delete_removed(tmp_path: Path) -> None:
    _write(tmp_path / 'src/main/java/egovframework/test/member/web/MemberController.java', MEMBER_CONTROLLER)
    views_form = tmp_path / 'src/main/webapp/WEB-INF/views/views/viewsForm.jsp'
    _write(
        views_form,
        """
        <form action="<c:url value='/views/save.do'/>" method="post"></form>
        <a href="<c:url value='/views/list.do'/>">목록</a>
        <a href="<c:url value='/views/delete.do?id=1'/>">삭제</a>
        """,
    )

    changed = _repair_jsp_missing_route_reference(
        views_form,
        issue={
            'details': {
                'missing_routes': ['/views/save.do', '/views/list.do', '/views/delete.do?id=1'],
                'discovered_routes': ['/member/form.do', '/member/list.do', '/member/save.do'],
            }
        },
        project_root=tmp_path,
    )

    assert changed
    body = views_form.read_text(encoding='utf-8')
    assert '/member/save.do' in body
    assert '/member/list.do' in body
    assert '/views/delete.do' not in body



def test_validator_skips_signup_calendar_from_form_contract_enforcement(tmp_path: Path) -> None:
    _write(tmp_path / 'src/main/java/egovframework/test/signup/service/vo/SignupVO.java', SIGNUP_VO)
    _write(tmp_path / 'src/main/webapp/WEB-INF/views/signup/signupCalendar.jsp', '<html><body>redirect</body></html>')

    issues = _scan_form_fields_cover_all_columns(tmp_path)

    assert not any(item['path'].endswith('signup/signupCalendar.jsp') for item in issues)
