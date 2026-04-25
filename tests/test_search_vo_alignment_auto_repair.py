from pathlib import Path

from app.validation.project_auto_repair import auto_repair_generated_project


def test_mapper_vo_mismatch_rebuilds_vo(tmp_path: Path):
    project_root = tmp_path
    vo_path = project_root / "src/main/java/egovframework/test/reservation/service/vo/ReservationVO.java"
    vo_path.parent.mkdir(parents=True, exist_ok=True)
    vo_path.write_text("package egovframework.test.reservation.service.vo;\n\npublic class ReservationVO {\n    private String roomName;\n    public String getRoomName() { return roomName; }\n    public void setRoomName(String roomName) { this.roomName = roomName; }\n}\n", encoding="utf-8")
    mapper_path = project_root / "src/main/resources/egovframework/mapper/reservation/ReservationMapper.xml"
    mapper_path.parent.mkdir(parents=True, exist_ok=True)
    mapper_path.write_text("<mapper></mapper>", encoding="utf-8")
    report = {"static_issues": [{"type": "mapper_vo_column_mismatch", "path": str(mapper_path.relative_to(project_root)).replace('\\','/'), "repairable": True, "details": {"vo_path": str(vo_path.relative_to(project_root)).replace('\\','/'), "mapper_columns": ["reservation_id", "room_id", "start_datetime"]}}]}
    result = auto_repair_generated_project(project_root, report)
    body = vo_path.read_text(encoding="utf-8")
    assert result["changed_count"] == 1
    assert "private String reservationId;" in body
    assert "private String roomId;" in body
    assert "private String startDatetime;" in body
    assert "roomName" not in body


def test_search_fields_incomplete_adds_missing_inputs(tmp_path: Path):
    project_root = tmp_path
    jsp_path = project_root / "src/main/webapp/WEB-INF/views/room/roomList.jsp"
    jsp_path.parent.mkdir(parents=True, exist_ok=True)
    jsp_path.write_text("<form><input type=\"text\" name=\"roomId\" /></form>", encoding="utf-8")
    report = {"static_issues": [{"type": "search_fields_incomplete", "path": str(jsp_path.relative_to(project_root)).replace('\\','/'), "repairable": True, "details": {"missing_fields": ["roomName", "regDt", "useYn"]}}]}
    result = auto_repair_generated_project(project_root, report)
    body = jsp_path.read_text(encoding="utf-8")
    assert result["changed_count"] == 1
    assert 'name="roomName"' in body
    assert 'name="regDt"' in body
    assert 'name="useYn"' in body
