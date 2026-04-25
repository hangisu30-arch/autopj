from pathlib import Path

from app.validation.generated_project_validator import (
    _scan_jsp_vo_property_mismatch,
    _scan_malformed_jsp_structure,
    _scan_unresolved_jsp_routes,
)
from app.validation.project_auto_repair import (
    _repair_jsp_missing_route_reference,
    _repair_jsp_vo_property_mismatch,
    _repair_malformed_jsp_structure,
)


def _write(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding='utf-8')


def test_sensitive_missing_vo_prop_rewrites_detail_generically(tmp_path: Path):
    _write(
        tmp_path / 'src/main/java/egovframework/test/signup/service/vo/SignupVO.java',
        'package egovframework.test.signup.service.vo;\n'
        'public class SignupVO {\n'
        '  private String loginId;\n'
        '  private String memberName;\n'
        '  public String getLoginId(){ return loginId; }\n'
        '  public void setLoginId(String v){ this.loginId=v; }\n'
        '  public String getMemberName(){ return memberName; }\n'
        '  public void setMemberName(String v){ this.memberName=v; }\n'
        '}\n',
    )
    _write(
        tmp_path / 'src/main/webapp/WEB-INF/views/signup/signupDetail.jsp',
        '<%@ page contentType="text/html; charset=UTF-8" pageEncoding="UTF-8"%>\n'
        '<div>${item.loginId}</div>\n'
        '<div>${item.password}</div>\n',
    )

    issues = _scan_jsp_vo_property_mismatch(tmp_path)
    assert any(issue['path'].endswith('signup/signupDetail.jsp') for issue in issues)
    issue = next(issue for issue in issues if issue['path'].endswith('signup/signupDetail.jsp'))
    assert _repair_jsp_vo_property_mismatch(tmp_path / issue['path'], issue, tmp_path)

    repaired = (tmp_path / 'src/main/webapp/WEB-INF/views/signup/signupDetail.jsp').read_text(encoding='utf-8')
    assert 'password' not in repaired.lower()
    assert not _scan_jsp_vo_property_mismatch(tmp_path)



def test_calendar_route_and_orphan_repairs_are_generic(tmp_path: Path):
    _write(
        tmp_path / 'src/main/java/egovframework/test/schedule/web/ScheduleController.java',
        'package egovframework.test.schedule.web;\n'
        'import org.springframework.stereotype.Controller;\n'
        'import org.springframework.web.bind.annotation.*;\n'
        '@Controller\n'
        '@RequestMapping("/schedule")\n'
        'public class ScheduleController {\n'
        '  @GetMapping("/calendar.do") public String calendar(){ return "schedule/scheduleCalendar"; }\n'
        '  @GetMapping("/list.do") public String list(){ return "schedule/scheduleList"; }\n'
        '  @GetMapping("/detail.do") public String detail(){ return "schedule/scheduleDetail"; }\n'
        '  @GetMapping("/form.do") public String form(){ return "schedule/scheduleForm"; }\n'
        '  @PostMapping("/delete.do") public String delete(){ return "redirect:/schedule/list.do"; }\n'
        '}\n',
    )
    _write(
        tmp_path / 'src/main/java/egovframework/test/signup/service/vo/SignupVO.java',
        'package egovframework.test.signup.service.vo;\n'
        'public class SignupVO {\n'
        '  private String title;\n'
        '  private String regDt;\n'
        '  public String getTitle(){ return title; }\n'
        '  public void setTitle(String v){ this.title=v; }\n'
        '  public String getRegDt(){ return regDt; }\n'
        '  public void setRegDt(String v){ this.regDt=v; }\n'
        '}\n',
    )
    bad_calendar = (
        '<%@ page contentType="text/html; charset=UTF-8" pageEncoding="UTF-8"%>\n'
        '</div>\n'
        '<a href="${pageContext.request.contextPath}/border/detail.do">상세</a>\n'
        '<a href="${pageContext.request.contextPath}/border/form.do">등록</a>\n'
        '<form action="${pageContext.request.contextPath}/border/delete.do" method="post"></form>\n'
    )
    _write(tmp_path / 'src/main/webapp/WEB-INF/views/signup/signupCalendar.jsp', bad_calendar)

    malformed = _scan_malformed_jsp_structure(tmp_path)
    unresolved = _scan_unresolved_jsp_routes(tmp_path)
    assert any(item['path'].endswith('signup/signupCalendar.jsp') for item in malformed)
    assert any(item['path'].endswith('signup/signupCalendar.jsp') for item in unresolved)

    for issue in unresolved:
        if issue['path'].endswith('signup/signupCalendar.jsp'):
            assert _repair_jsp_missing_route_reference(tmp_path / issue['path'], issue, tmp_path)
            break
    for issue in malformed:
        if issue['path'].endswith('signup/signupCalendar.jsp'):
            _repair_malformed_jsp_structure(tmp_path / issue['path'], issue, tmp_path)
            break

    repaired = (tmp_path / 'src/main/webapp/WEB-INF/views/signup/signupCalendar.jsp').read_text(encoding='utf-8')
    assert '/border/' not in repaired
    assert not repaired.lstrip().startswith('</div>')
    assert 'calendarCells' in repaired or 'calendarcells' in repaired.lower()
    assert not _scan_malformed_jsp_structure(tmp_path)
    assert not _scan_unresolved_jsp_routes(tmp_path)
