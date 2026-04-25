from pathlib import Path

from app.validation.project_auto_repair import apply_generated_project_auto_repair, _repair_jsp_structural_views_artifact


def test_structural_views_artifact_handler_deletes_file(tmp_path: Path):
    jsp = tmp_path / "src/main/webapp/WEB-INF/views/views/viewsDetail.jsp"
    jsp.parent.mkdir(parents=True, exist_ok=True)
    jsp.write_text("broken", encoding="utf-8")
    assert _repair_jsp_structural_views_artifact(jsp, {}, tmp_path) is True
    assert not jsp.exists()


def test_apply_generated_project_auto_repair_maps_structural_views_issue(tmp_path: Path):
    jsp = tmp_path / "src/main/webapp/WEB-INF/views/views/viewsForm.jsp"
    jsp.parent.mkdir(parents=True, exist_ok=True)
    jsp.write_text("broken", encoding="utf-8")
    report = {
        "issues": [
            {
                "type": "jsp_structural_views_artifact",
                "path": "src/main/webapp/WEB-INF/views/views/viewsForm.jsp",
                "repairable": True,
                "details": {},
            }
        ]
    }
    result = apply_generated_project_auto_repair(tmp_path, report)
    assert result["changed_count"] == 1
    assert not jsp.exists()
