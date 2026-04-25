from pathlib import Path

from app.validation.generated_project_validator import validate_generated_project


class _Cfg:
    project_name = "test"
    frontend_key = "jsp"


def test_duplicate_request_mapping_scan_ignores_request_param_literals(tmp_path: Path):
    controller = tmp_path / "src/main/java/egovframework/test/memberAccount/web/MemberAccountController.java"
    controller.parent.mkdir(parents=True, exist_ok=True)
    controller.write_text(
        "package egovframework.test.memberAccount.web;\n"
        "import org.springframework.stereotype.Controller;\n"
        "import org.springframework.ui.Model;\n"
        "import org.springframework.web.bind.annotation.GetMapping;\n"
        "import org.springframework.web.bind.annotation.RequestMapping;\n"
        "import org.springframework.web.bind.annotation.RequestParam;\n"
        "import org.springframework.web.bind.annotation.ResponseBody;\n"
        "@Controller\n@RequestMapping(\"/memberAccount\")\n"
        "public class MemberAccountController {\n"
        "  @GetMapping(\"/detail.do\")\n"
        "  public String detail(@RequestParam(\"loginId\") String loginId, Model model) { return \"memberAccount/memberAccountDetail\"; }\n"
        "  @GetMapping(\"/checkLoginId.do\")\n"
        "  @ResponseBody\n"
        "  public String checkLoginId(@RequestParam(\"loginId\") String loginId) { return loginId; }\n"
        "}\n",
        encoding="utf-8",
    )

    report = validate_generated_project(tmp_path, _Cfg(), include_runtime=False)
    issues = [item for item in report.get("static_issues") or [] if item.get("type") == "ambiguous_request_mapping"]
    assert not issues
