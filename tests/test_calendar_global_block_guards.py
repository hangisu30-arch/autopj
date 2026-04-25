from pathlib import Path

from execution_core.feature_rules import is_forbidden_calendar_domain, should_generate_calendar_artifacts
from app.engine.analysis.artifact_planner import ArtifactPlanner
from app.engine.analysis.analysis_result import DomainAnalysis
from app.ui.fallback_builder import build_builtin_fallback_content
from app.validation.generated_project_validator import validate_generated_project
from app.validation.project_auto_repair import _repair_unexpected_calendar_artifact


class _Cfg:
    frontend_key = "jsp"
    backend_key = "egov_spring"
    database_key = "mysql"
    database_type = "mysql"


def _write(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


def test_calendar_helper_blocks_auth_and_structural_domains():
    assert is_forbidden_calendar_domain(domain="adminMember") is True
    assert is_forbidden_calendar_domain(domain="views") is True
    assert should_generate_calendar_artifacts("회원관리 시스템", domain="member") is False
    assert should_generate_calendar_artifacts("예약 달력 화면을 명시적으로 만든다", domain="reservation") is True


def test_artifact_planner_downgrades_forbidden_calendar_domain_to_crud():
    domain = DomainAnalysis(name="adminMember", entity_name="AdminMember", feature_kind="crud", feature_types=["crud"], source_table="tb_admin_member")
    domain.ir = {"classification": {"primaryPattern": "calendar", "featureTypes": ["crud"]}}
    domain.contracts = {"search": {"enabled": True}}
    planned = ArtifactPlanner().apply(domain, "jsp")
    assert "calendar" not in planned.pages
    assert all("/calendar" not in route for route in planned.api_endpoints)


def test_fallback_builder_refuses_forbidden_calendar_artifact():
    built = build_builtin_fallback_content(
        "src/main/webapp/WEB-INF/views/adminMember/adminMemberCalendar.jsp",
        "전자정부 프레임워크 기반 회원관리 시스템",
        project_name="demo",
    )
    assert built == ""


def test_validator_and_repair_remove_forbidden_calendar_artifacts_across_frontends(tmp_path: Path):
    jsp = tmp_path / "src/main/webapp/WEB-INF/views/adminMember/adminMemberCalendar.jsp"
    react = tmp_path / "frontend/react/src/pages/views/ViewsCalendarPage.jsx"
    controller = tmp_path / "src/main/java/egovframework/test/memberAdmin/web/MemberAdminController.java"
    _write(jsp, "<html></html>")
    _write(react, "export default function ViewsCalendarPage(){ return null; }")
    _write(controller, 'package egovframework.test.memberAdmin.web;\nimport org.springframework.stereotype.Controller;\nimport org.springframework.web.bind.annotation.GetMapping;\n@Controller public class MemberAdminController { @GetMapping("/calendar.do") public String calendar(){ return "memberAdmin/memberAdminCalendar"; } }')

    report = validate_generated_project(tmp_path, _Cfg(), manifest=None, include_runtime=False)
    codes = {item.get("code") or item.get("type") for item in report.get("issues") or []}
    assert "forbidden_calendar_artifact" in codes
    assert "forbidden_calendar_route" in codes

    assert _repair_unexpected_calendar_artifact(jsp, {"details": {"domain": "adminMember"}}, tmp_path) is True
    assert _repair_unexpected_calendar_artifact(react, {"details": {"domain": "views"}}, tmp_path) is True
    assert _repair_unexpected_calendar_artifact(controller, {"details": {"domain": "memberAdmin"}}, tmp_path) is True
    assert not jsp.exists()
    assert not react.exists()
    body = controller.read_text(encoding="utf-8")
    assert "/calendar.do" not in body
