from app.ui.state import ProjectConfig


def test_frontend_branch_summary_and_effective_requirements_for_react():
    cfg = ProjectConfig(
        project_name="frontproj",
        frontend_key="react",
        frontend_label="react",
        extra_requirements="일정 관리 프로젝트를 만들어줘.",
    ).normalize()

    text = cfg.effective_extra_requirements()
    assert "[FRONTEND UI CONFIRMED SETTINGS - SOURCE OF TRUTH]" in text
    assert "- frontend_mode: react" in text
    assert "- React 선택: Spring Boot REST API + React 프론트 + axios/fetch + router" in text


def test_frontend_branch_summary_for_jsp_and_vue():
    jsp_cfg = ProjectConfig(frontend_key="jsp", frontend_label="jsp").normalize()
    vue_cfg = ProjectConfig(frontend_key="vue", frontend_label="vue").normalize()

    assert jsp_cfg.frontend_branch_summary() == "JSP 선택: Controller + JSP + MyBatis + 서버 렌더링"
    assert vue_cfg.frontend_branch_summary() == "Vue 선택: Spring Boot REST API + Vue 프론트 + router + axios"
