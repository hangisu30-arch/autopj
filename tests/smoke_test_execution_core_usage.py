from app.ui.apply_strategy import should_use_execution_core_apply
from app.ui.state import ProjectConfig


def test_execution_core_apply_is_used_for_egov_jsp_even_without_mysql():
    cfg = ProjectConfig(project_name="fulljsp", backend_key="egov_spring", frontend_key="jsp", database_key="sqlite")
    assert should_use_execution_core_apply(cfg) is True


def test_execution_core_apply_is_used_for_all_egov_frontends():
    for frontend in ("jsp", "react", "vue", "nexacro"):
        cfg = ProjectConfig(project_name="demo", backend_key="egov_spring", frontend_key=frontend, database_key="oracle")
        assert should_use_execution_core_apply(cfg) is True


def test_execution_core_apply_is_not_used_for_non_egov_backend():
    cfg = ProjectConfig(project_name="demo", backend_key="python_fastapi", frontend_key="jsp", database_key="sqlite")
    assert should_use_execution_core_apply(cfg) is False
