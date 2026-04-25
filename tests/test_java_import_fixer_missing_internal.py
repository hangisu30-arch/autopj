from pathlib import Path

from app.ui.java_import_fixer import fix_project_java_imports


def test_fix_project_java_imports_adds_missing_internal_import_without_existing_import_block(tmp_path: Path):
    vo = tmp_path / "src/main/java/egovframework/demo/schedule/service/vo/ScheduleVO.java"
    svc = tmp_path / "src/main/java/egovframework/demo/schedule/service/ScheduleService.java"
    vo.parent.mkdir(parents=True, exist_ok=True)
    svc.parent.mkdir(parents=True, exist_ok=True)

    vo.write_text(
        "package egovframework.demo.schedule.service.vo;\n\npublic class ScheduleVO {}\n",
        encoding="utf-8",
    )
    svc.write_text(
        "package egovframework.demo.schedule.service;\n\nimport java.util.List;\n\npublic interface ScheduleService {\n    List<ScheduleVO> selectScheduleList() throws Exception;\n    ScheduleVO selectSchedule(Long scheduleId) throws Exception;\n}\n",
        encoding="utf-8",
    )

    changed = fix_project_java_imports(tmp_path)
    text = svc.read_text(encoding="utf-8")

    assert svc in changed
    assert "import egovframework.demo.schedule.service.vo.ScheduleVO;" in text


def test_fix_project_java_imports_adds_missing_standard_import(tmp_path: Path):
    vo = tmp_path / "src/main/java/egovframework/demo/schedule/service/vo/ScheduleVO.java"
    vo.parent.mkdir(parents=True, exist_ok=True)
    vo.write_text(
        "package egovframework.demo.schedule.service.vo;\n\npublic class ScheduleVO {\n    private LocalDateTime startDatetime;\n}\n",
        encoding="utf-8",
    )

    changed = fix_project_java_imports(tmp_path)
    text = vo.read_text(encoding="utf-8")

    assert vo in changed
    assert "import java.time.LocalDateTime;" in text
