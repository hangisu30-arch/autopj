from pathlib import Path

from app.io.execution_core_apply import _augment_schema_map_with_auth, _build_header_jsp, _build_leftnav_jsp
from app.validation.generated_project_validator import validate_generated_project
from app.validation.project_auto_repair import apply_generated_project_auto_repair
from execution_core.builtin_crud import schema_for
from execution_core.feature_rules import FEATURE_KIND_CRUD


class _Cfg:
    login_feature_enabled = True
    auth_unified_auth = False
    auth_cert_login = False
    auth_jwt_login = False
    frontend_key = 'jsp'
    database_key = 'mysql'
    database_type = 'mysql'


class _NavSchema:
    entity_var = 'member'
    routes = {
        'list': '/member/list.do',
        'form': '/member/form.do',
        'login': '/login/login.do',
    }


def test_build_navigation_assets_include_common_js_and_request_uri_active_binding():
    header = _build_header_jsp({'Member': _NavSchema()}, preferred_entity='Member', project_title='test')
    leftnav = _build_leftnav_jsp({'Member': _NavSchema()}, preferred_entity='Member')

    assert '/js/common.js' in header
    assert 'fn:endsWith(pageContext.request.requestURI' in header
    assert 'fn:endsWith(pageContext.request.requestURI' in leftnav
    assert 'autopj-leftnav__link' in leftnav


def test_augment_schema_map_with_auth_reuses_shared_account_table_for_login():
    member_schema = schema_for(
        'Member',
        [
            ('memberId', 'member_id', 'String'),
            ('loginId', 'login_id', 'String'),
            ('loginPassword', 'login_password', 'String'),
            ('memberName', 'member_name', 'String'),
            ('useYn', 'use_yn', 'String'),
        ],
        table='TB_MEMBER',
        feature_kind=FEATURE_KIND_CRUD,
        strict_fields=True,
    )
    out = _augment_schema_map_with_auth(
        {'Member': member_schema},
        [{'content': '회원가입 후 로그인 가능해야 하며 기존 로그인과 회원가입은 같은 테이블을 사용한다. 회원관리도 같은 테이블을 사용한다.'}],
        _Cfg(),
    )
    assert out['Member'].table.lower() == 'tb_member'
    assert out['Login'].table.lower() == 'tb_member'
    login_cols = [col for _prop, col, _jt in out['Login'].fields]
    assert 'login_id' in login_cols
    assert 'login_password' in login_cols
    assert 'password' not in login_cols


def test_validator_and_repair_fix_missing_common_nav_assets_and_broken_form(tmp_path: Path):
    header = tmp_path / 'src/main/webapp/WEB-INF/views/common/header.jsp'
    leftnav = tmp_path / 'src/main/webapp/WEB-INF/views/common/leftNav.jsp'
    form = tmp_path / 'src/main/webapp/WEB-INF/views/member/memberForm.jsp'
    controller = tmp_path / 'src/main/java/egovframework/test/member/web/MemberController.java'
    vo = tmp_path / 'src/main/java/egovframework/test/member/service/vo/MemberVO.java'

    header.parent.mkdir(parents=True, exist_ok=True)
    form.parent.mkdir(parents=True, exist_ok=True)
    controller.parent.mkdir(parents=True, exist_ok=True)
    vo.parent.mkdir(parents=True, exist_ok=True)

    header.write_text(
        '<%@ page contentType="text/html; charset=UTF-8" pageEncoding="UTF-8"%>\n'
        '<%@ taglib prefix="c" uri="http://java.sun.com/jsp/jstl/core"%>\n'
        '<div class="autopj-header"><a class="autopj-header__link" href="<c:url value="/member/list.do" />">목록</a></div>',
        encoding='utf-8',
    )
    leftnav.write_text(
        '<%@ page contentType="text/html; charset=UTF-8" pageEncoding="UTF-8"%>\n'
        '<%@ taglib prefix="c" uri="http://java.sun.com/jsp/jstl/core"%>\n'
        '<aside><a class="autopj-leftnav__link is-active" href="<c:url value="/member/list.do" />">목록</a></aside>',
        encoding='utf-8',
    )
    form.write_text(
        '<%@ page contentType="text/html; charset=UTF-8" pageEncoding="UTF-8"%>\n'
        '<%@ include file="/WEB-INF/views/common/header.jsp" %>\n'
        '<%@ include file="/WEB-INF/views/common/leftNav.jsp" %>\n'
        '<div class="autopj-form-actions"><button type="submit">저장</button></div>',
        encoding='utf-8',
    )
    controller.write_text(
        'package egovframework.test.member.web;\n'
        'import org.springframework.stereotype.Controller;\n'
        'import org.springframework.web.bind.annotation.GetMapping;\n'
        'import org.springframework.web.bind.annotation.PostMapping;\n'
        'import org.springframework.web.bind.annotation.RequestMapping;\n'
        '@Controller @RequestMapping("/member")\n'
        'public class MemberController {\n'
        '  @GetMapping("/list.do") public String list(){ return "member/memberList"; }\n'
        '  @GetMapping("/form.do") public String form(){ return "member/memberForm"; }\n'
        '  @PostMapping("/save.do") public String save(){ return "redirect:/member/list.do"; }\n'
        '}\n',
        encoding='utf-8',
    )
    vo.write_text(
        'package egovframework.test.member.service.vo;\n'
        'public class MemberVO { private String memberId; private String memberName;\n'
        'public String getMemberId(){return memberId;} public void setMemberId(String v){memberId=v;}\n'
        'public String getMemberName(){return memberName;} public void setMemberName(String v){memberName=v;}\n'
        '}\n',
        encoding='utf-8',
    )

    report = validate_generated_project(tmp_path, _Cfg(), include_runtime=False)
    issue_types = {(item.get('type') or item.get('code')) for item in report.get('issues') or []}
    assert 'common_nav_assets_missing' in issue_types
    assert 'broken_form_submission' in issue_types

    repair = apply_generated_project_auto_repair(tmp_path, report)
    assert repair.get('changed')

    header_body = header.read_text(encoding='utf-8')
    leftnav_body = leftnav.read_text(encoding='utf-8')
    form_body = form.read_text(encoding='utf-8')

    assert '/js/common.js' in header_body
    assert 'fn:endsWith(pageContext.request.requestURI' in header_body
    assert 'fn:endsWith(pageContext.request.requestURI' in leftnav_body
    assert '<form class="autopj-form-card form-card"' in form_body
    assert "/member/save.do" in form_body
