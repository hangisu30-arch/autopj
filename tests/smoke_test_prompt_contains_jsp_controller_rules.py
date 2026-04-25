from __future__ import annotations

import sys
import types

backend_contracts = types.ModuleType("app.engine.backend.backend_contracts")
class BackendPlanResult:
    def __init__(self, **kwargs):
        self._data = kwargs
    def to_dict(self):
        return dict(self._data)
backend_contracts.BackendPlanResult = BackendPlanResult
sys.modules["app.engine.backend.backend_contracts"] = backend_contracts

jsp_contracts = types.ModuleType("app.adapters.jsp.jsp_contracts")
class JspPlanResult:
    def __init__(self, **kwargs):
        self._data = kwargs
    def to_dict(self):
        return dict(self._data)
jsp_contracts.JspPlanResult = JspPlanResult
sys.modules["app.adapters.jsp.jsp_contracts"] = jsp_contracts

from app.engine.backend.backend_prompt_builder import backend_plan_to_prompt_text
from app.adapters.jsp.jsp_prompt_builder import jsp_plan_to_prompt_text


def main() -> None:
    backend_text = backend_plan_to_prompt_text({
        "project_name": "demo",
        "base_package": "egovframework.demo",
        "backend_mode": "egov_spring",
        "frontend_mode": "jsp",
        "database_type": "mysql",
        "domains": [],
    })
    jsp_text = jsp_plan_to_prompt_text({
        "project_name": "demo",
        "base_package": "egovframework.demo",
        "frontend_mode": "jsp",
        "view_root": "src/main/webapp/WEB-INF/views",
        "domains": [],
    })
    assert "Target JSP Controller size" in backend_text
    assert "Target JSP Controller size" in jsp_text
    assert "list/detail/form/save/delete" in jsp_text
    assert "MyBatisConfig must be valid Spring Boot Java" in backend_text
    assert "Mapper interface and Mapper XML must stay in XML-only MyBatis mode" in backend_text
    assert "Controller @ModelAttribute binding type must be <Entity>VO" in jsp_text
    assert "Mapper XML must be pure MyBatis mapper XML" in jsp_text
    print("OK: prompt rules include jsp controller and backend consistency guards")


if __name__ == "__main__":
    main()
