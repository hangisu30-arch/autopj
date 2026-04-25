from pathlib import Path
from types import SimpleNamespace

from app.validation.generated_project_validator import validate_generated_project
from app.validation.project_auto_repair import apply_generated_project_auto_repair


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _cfg():
    return SimpleNamespace(frontend_key="jsp", backend_key="springboot")


def test_route_param_mismatch_is_detected_and_repaired(tmp_path: Path):
    controller = tmp_path / "src/main/java/egovframework/demo/room/web/RoomController.java"
    _write(
        controller,
        '''package egovframework.demo.room.web;
import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.*;
import org.springframework.ui.Model;
@Controller
@RequestMapping("/room")
public class RoomController {
  @GetMapping("/detail.do") public String detail(@RequestParam("id") Long id, Model model) { return "room/roomDetail"; }
  @GetMapping("/form.do") public String form(@RequestParam(value="id", required=false) Long id, Model model) { return "room/roomForm"; }
  @PostMapping("/delete.do") public String delete(@RequestParam("id") Long id) { return "redirect:/room/list.do"; }
}
''',
    )
    _write(tmp_path / "src/main/java/egovframework/demo/room/service/RoomService.java", "package egovframework.demo.room.service; public interface RoomService {}")
    _write(tmp_path / "src/main/java/egovframework/demo/room/service/impl/RoomServiceImpl.java", "package egovframework.demo.room.service.impl; public class RoomServiceImpl {}")
    _write(tmp_path / "src/main/resources/mapper/room/RoomMapper.xml", '<mapper namespace="egovframework.demo.room.service.mapper.RoomMapper"></mapper>')
    _write(tmp_path / "src/main/webapp/WEB-INF/views/room/roomDetail.jsp", "x")
    _write(
        tmp_path / "src/main/webapp/WEB-INF/views/room/roomList.jsp",
        '''<a href="<c:url value='/room/detail.do'/>?room_id=${row.room_id}">detail</a>
<a href="<c:url value='/room/form.do'/>?room_id=${row.room_id}">edit</a>
<form action="<c:url value='/room/delete.do'/>" method="post"><input type="hidden" name="room_id" value="${row.room_id}"/></form>
''',
    )
    report = validate_generated_project(tmp_path, _cfg(), include_runtime=False)
    assert any(i["type"] == "route_param_mismatch" for i in report["static_issues"])
    apply_generated_project_auto_repair(tmp_path, report)
    body = (tmp_path / "src/main/webapp/WEB-INF/views/room/roomList.jsp").read_text(encoding="utf-8")
    assert "?id=" in body
    assert 'name="id"' in body


def test_missing_detail_view_is_synthesized_from_form_fields(tmp_path: Path):
    _write(
        tmp_path / "src/main/java/egovframework/demo/room/web/RoomController.java",
        '''package egovframework.demo.room.web;
import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.*;
import org.springframework.ui.Model;
@Controller
@RequestMapping("/room")
public class RoomController {
  @GetMapping("/detail.do") public String detail(@RequestParam("roomId") Long roomId, Model model) { return "room/roomDetail"; }
}
''',
    )
    _write(tmp_path / "src/main/java/egovframework/demo/room/service/RoomService.java", "package egovframework.demo.room.service; public interface RoomService {}")
    _write(tmp_path / "src/main/java/egovframework/demo/room/service/impl/RoomServiceImpl.java", "package egovframework.demo.room.service.impl; public class RoomServiceImpl {}")
    _write(tmp_path / "src/main/resources/mapper/room/RoomMapper.xml", '<mapper namespace="egovframework.demo.room.service.mapper.RoomMapper"></mapper>')
    _write(
        tmp_path / "src/main/webapp/WEB-INF/views/room/roomForm.jsp",
        '<form><input name="roomId"/><input name="roomName"/><textarea name="remark"></textarea></form>',
    )
    report = validate_generated_project(tmp_path, _cfg(), include_runtime=False)
    assert any(i["type"] == "missing_view" for i in report["static_issues"])
    apply_generated_project_auto_repair(tmp_path, report)
    detail = tmp_path / "src/main/webapp/WEB-INF/views/room/roomDetail.jsp"
    assert detail.exists()
    body = detail.read_text(encoding="utf-8")
    assert "${item.roomId}" in body
    assert "${item.roomName}" in body
    assert "${item.remark}" in body


def test_calendar_mapping_is_added_for_calendar_view(tmp_path: Path):
    controller = tmp_path / "src/main/java/egovframework/demo/reservation/web/ReservationController.java"
    _write(
        controller,
        '''package egovframework.demo.reservation.web;
import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.*;
import org.springframework.ui.Model;
@Controller
@RequestMapping("/reservation")
public class ReservationController {
  @GetMapping("/list.do")
  public String list(Model model) throws Exception {
    model.addAttribute("list", java.util.Collections.emptyList());
    return "reservation/reservationList";
  }
}
''',
    )
    _write(tmp_path / "src/main/java/egovframework/demo/reservation/service/ReservationService.java", "package egovframework.demo.reservation.service; public interface ReservationService {}")
    _write(tmp_path / "src/main/java/egovframework/demo/reservation/service/impl/ReservationServiceImpl.java", "package egovframework.demo.reservation.service.impl; public class ReservationServiceImpl {}")
    _write(tmp_path / "src/main/resources/mapper/reservation/ReservationMapper.xml", '<mapper namespace="egovframework.demo.reservation.service.mapper.ReservationMapper"></mapper>')
    _write(tmp_path / "src/main/webapp/WEB-INF/views/reservation/reservationCalendar.jsp", "calendar")
    _write(tmp_path / "src/main/webapp/WEB-INF/views/reservation/reservationList.jsp", "list")
    report = validate_generated_project(tmp_path, _cfg(), include_runtime=False)
    assert any(i["type"] == "calendar_mapping_missing" for i in report["static_issues"])
    apply_generated_project_auto_repair(tmp_path, report)
    body = controller.read_text(encoding="utf-8")
    assert '@GetMapping("/calendar.do")' in body
    assert 'return "reservation/reservationCalendar";' in body


def test_duplicate_schema_initializer_is_removed_and_variants_synced(tmp_path: Path):
    _write(tmp_path / "src/main/resources/application.properties", "spring.sql.init.mode=always\n")
    init = tmp_path / "src/main/java/egovframework/demo/config/DatabaseInitializer.java"
    _write(init, "package egovframework.demo.config; public class DatabaseInitializer {}")
    _write(tmp_path / "src/main/resources/schema.sql", "CREATE TABLE room (room_id BIGINT);\n")
    variant = tmp_path / "src/main/resources/db/schema-mysql.sql"
    _write(variant, "CREATE TABLE room (reservation_id BIGINT);\n")
    _write(
        tmp_path / "src/main/java/egovframework/demo/reservation/service/ReservationVO.java",
        "package egovframework.demo.reservation.service; public class ReservationVO { private String reservationId; }",
    )
    report = validate_generated_project(tmp_path, _cfg(), include_runtime=False)
    types = {i["type"] for i in report["static_issues"]}
    assert "duplicate_schema_initializer" in types
    assert "schema_variant_conflict" in types
    apply_generated_project_auto_repair(tmp_path, report)
    assert not init.exists()
    assert variant.read_text(encoding="utf-8") == (tmp_path / "src/main/resources/schema.sql").read_text(encoding="utf-8")


def test_calendar_data_contract_missing_is_repaired_with_model_aliases(tmp_path: Path):
    controller = tmp_path / "src/main/java/egovframework/demo/reservation/web/ReservationController.java"
    _write(
        controller,
        """package egovframework.demo.reservation.web;
import java.util.Collections;
import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
@Controller
@RequestMapping("/reservation")
public class ReservationController {
  @GetMapping("/calendar.do")
  public String calendar(Model model) {
    model.addAttribute("selectedDate", "2026-04-01");
    return "reservation/reservationCalendar";
  }
}
""",
    )
    _write(
        tmp_path / "src/main/webapp/WEB-INF/views/reservation/reservationCalendar.jsp",
        '<c:forEach var="cell" items="${calendarCells}"></c:forEach><c:forEach var="row" items="${selectedDateSchedules}"></c:forEach>',
    )
    report = validate_generated_project(tmp_path, _cfg(), include_runtime=False)
    assert any(i["type"] == "calendar_data_contract_missing" for i in report["static_issues"])
    apply_generated_project_auto_repair(tmp_path, report)
    body = controller.read_text(encoding="utf-8")
    assert 'model.addAttribute("calendarcells",' in body
    assert 'model.addAttribute("selecteddateschedules",' in body
    repaired = validate_generated_project(tmp_path, _cfg(), include_runtime=False)
    assert not any(i["type"] == "calendar_data_contract_missing" for i in repaired["static_issues"])


def test_schema_primary_updates_are_propagated_to_variants(tmp_path: Path):
    mapper = tmp_path / "src/main/resources/mapper/reservation/ReservationMapper.xml"
    _write(
        mapper,
        """<mapper namespace="egovframework.demo.reservation.service.mapper.ReservationMapper">
  <resultMap id="reservationMap" type="egovframework.demo.reservation.service.ReservationVO">
    <id property="reservationId" column="reservation_id"/>
    <result property="eventDate" column="event_date"/>
    <result property="roomList" column="room_list"/>
    <result property="checkResult" column="check_result"/>
  </resultMap>
  <select id="selectReservationList" resultMap="reservationMap">
    SELECT reservation_id, event_date, room_list, check_result FROM reservation
  </select>
</mapper>
""",
    )
    _write(
        tmp_path / "src/main/resources/schema.sql",
        'CREATE TABLE reservation (\n    reservation_id VARCHAR(255)\n);\n',
    )
    _write(
        tmp_path / "src/main/resources/db/schema-mysql.sql",
        'CREATE TABLE reservation (\n    stale_col VARCHAR(255)\n);\n',
    )
    _write(
        tmp_path / "src/main/java/egovframework/demo/reservation/service/ReservationVO.java",
        "package egovframework.demo.reservation.service; public class ReservationVO { private String reservationId; }",
    )
    report = validate_generated_project(tmp_path, _cfg(), include_runtime=False)
    types = {i["type"] for i in report["static_issues"]}
    assert "mapper_table_column_mismatch" in types
    assert "schema_column_comment_missing" in types
    assert "schema_variant_conflict" in types
    apply_generated_project_auto_repair(tmp_path, report)
    primary = (tmp_path / "src/main/resources/schema.sql").read_text(encoding="utf-8")
    variant = (tmp_path / "src/main/resources/db/schema-mysql.sql").read_text(encoding="utf-8")
    assert 'event_date' in primary and 'room_list' in primary and 'check_result' in primary
    assert "event_date VARCHAR(255) COMMENT '행사일자'" in primary
    assert 'COMMENT ON COLUMN' not in primary
    assert variant == primary
