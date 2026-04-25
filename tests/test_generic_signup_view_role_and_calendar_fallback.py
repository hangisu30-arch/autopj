from pathlib import Path

from app.io.execution_core_apply import _is_auth_ui_rel_path
from app.ui.generated_content_validator import _is_auth_ui_path
from app.ui.ui_sanitize_common import is_auth_ui_file_path
from app.validation.generated_project_validator import _scan_jsp_vo_property_mismatch, _scan_unresolved_jsp_routes
from app.validation.project_auto_repair import _repair_jsp_missing_route_reference, _repair_jsp_vo_property_mismatch


def _write(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding='utf-8')


def test_auth_ui_detection_is_role_aware_for_signup_named_views():
    assert _is_auth_ui_rel_path('src/main/webapp/WEB-INF/views/member/memberSignup.jsp')
    assert _is_auth_ui_path('src/main/webapp/WEB-INF/views/member/memberSignup.jsp')
    assert is_auth_ui_file_path('src/main/webapp/WEB-INF/views/member/memberSignup.jsp')

    assert not _is_auth_ui_rel_path('src/main/webapp/WEB-INF/views/signup/signupList.jsp')
    assert not _is_auth_ui_path('src/main/webapp/WEB-INF/views/signup/signupList.jsp')
    assert not is_auth_ui_file_path('src/main/webapp/WEB-INF/views/signup/signupList.jsp')

    assert not _is_auth_ui_rel_path('src/main/webapp/WEB-INF/views/signup/signupDetail.jsp')
    assert not _is_auth_ui_path('src/main/webapp/WEB-INF/views/signup/signupDetail.jsp')
    assert not is_auth_ui_file_path('src/main/webapp/WEB-INF/views/signup/signupDetail.jsp')

    assert not _is_auth_ui_rel_path('src/main/webapp/WEB-INF/views/signup/signupCalendar.jsp')
    assert not _is_auth_ui_path('src/main/webapp/WEB-INF/views/signup/signupCalendar.jsp')
    assert not is_auth_ui_file_path('src/main/webapp/WEB-INF/views/signup/signupCalendar.jsp')


def test_signup_named_list_and_detail_repair_do_not_reintroduce_id_or_password(tmp_path: Path):
    _write(
        tmp_path / 'src/main/java/egovframework/test/signup/service/vo/SignupVO.java',
        'package egovframework.test.signup.service.vo;\n'
        'public class SignupVO {\n'
        '  private String loginId;\n'
        '  private String memberName;\n'
        '  public String getLoginId(){ return loginId; }\n'
        '  public String getMemberName(){ return memberName; }\n'
        '}\n',
    )
    _write(
        tmp_path / 'src/main/webapp/WEB-INF/views/signup/signupList.jsp',
        '<div>${row.id}</div>\n<div>${row.loginId}</div>\n',
    )
    _write(
        tmp_path / 'src/main/webapp/WEB-INF/views/signup/signupDetail.jsp',
        '<div>${item.password}</div>\n<div>${item.memberName}</div>\n',
    )

    issues = _scan_jsp_vo_property_mismatch(tmp_path)
    for issue in issues:
        _repair_jsp_vo_property_mismatch(tmp_path / issue['path'], issue, tmp_path)

    list_body = (tmp_path / 'src/main/webapp/WEB-INF/views/signup/signupList.jsp').read_text(encoding='utf-8').lower()
    detail_body = (tmp_path / 'src/main/webapp/WEB-INF/views/signup/signupDetail.jsp').read_text(encoding='utf-8').lower()

    assert '${row.id}' not in list_body
    assert 'password' not in detail_body
    assert not _scan_jsp_vo_property_mismatch(tmp_path)


def test_calendar_route_falls_back_to_list_when_calendar_mapping_is_missing(tmp_path: Path):
    _write(
        tmp_path / 'src/main/java/egovframework/test/egovIndex/web/EgovIndexController.java',
        'package egovframework.test.egovIndex.web;\n'
        'import org.springframework.stereotype.Controller;\n'
        'import org.springframework.web.bind.annotation.*;\n'
        '@Controller\n'
        '@RequestMapping("/egovIndex")\n'
        'public class EgovIndexController {\n'
        '  @GetMapping("/list.do") public String list(){ return "egovIndex/egovIndexList"; }\n'
        '  @GetMapping("/detail.do") public String detail(){ return "egovIndex/egovIndexDetail"; }\n'
        '  @GetMapping("/form.do") public String form(){ return "egovIndex/egovIndexForm"; }\n'
        '  @PostMapping("/delete.do") public String delete(){ return "redirect:/egovIndex/list.do"; }\n'
        '}\n',
    )
    _write(
        tmp_path / 'src/main/java/egovframework/test/egovIndex/service/vo/EgovIndexVO.java',
        'package egovframework.test.egovIndex.service.vo;\n'
        'public class EgovIndexVO {\n'
        '  private String title;\n'
        '  public String getTitle(){ return title; }\n'
        '}\n',
    )
    _write(
        tmp_path / 'src/main/webapp/WEB-INF/views/egovIndex/egovIndexCalendar.jsp',
        '<a href="${pageContext.request.contextPath}/egovIndex/calendar.do">달력</a>\n'
        '<a href="${pageContext.request.contextPath}/border/detail.do">상세</a>\n'
        '<a href="${pageContext.request.contextPath}/border/form.do">폼</a>\n',
    )

    issues = _scan_unresolved_jsp_routes(tmp_path)
    issue = next(item for item in issues if item['path'].endswith('egovIndex/egovIndexCalendar.jsp'))
    assert _repair_jsp_missing_route_reference(tmp_path / issue['path'], issue, tmp_path)

    repaired = (tmp_path / 'src/main/webapp/WEB-INF/views/egovIndex/egovIndexCalendar.jsp').read_text(encoding='utf-8')
    assert '/egovIndex/calendar.do' not in repaired
    assert '/egovIndex/list.do' in repaired
    assert '/border/' not in repaired
    assert not _scan_unresolved_jsp_routes(tmp_path)
