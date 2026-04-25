from pathlib import Path

from app.validation.generated_project_validator import validate_generated_project
from app.validation.project_auto_repair import apply_generated_project_auto_repair
from app.validation.post_generation_repair import _repair_timed_out_edit_endpoints
from app.io.execution_core_apply import _rewrite_list_jsp_from_schema


class _Cfg:
    frontend_key = "jsp"


def _write(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


def test_validator_sanitizes_room_mapper_alignment_noise(tmp_path: Path):
    _write(
        tmp_path / 'src/main/resources/schema.sql',
        """
CREATE TABLE IF NOT EXISTS room (
  room_id varchar(50) COMMENT 'ID',
  location varchar(200) COMMENT '위치',
  capacity varchar(50) COMMENT '정원',
  room_desc varchar(400) COMMENT '설명',
  upd_dt datetime COMMENT '수정일시'
);
""".strip(),
    )
    _write(
        tmp_path / 'src/main/resources/egovframework/mapper/room/RoomMapper.xml',
        """
<mapper namespace="egovframework.test.room.service.mapper.RoomMapper">
  <resultMap id="RoomMap" type="egovframework.test.room.service.vo.RoomVO">
    <id property="roomId" column="room_id"/>
    <result property="location" column="location"/>
    <result property="capacity" column="capacity"/>
    <result property="roomDesc" column="room_desc"/>
    <result property="updDt" column="upd_dt"/>
    <result property="text" column="text"/>
    <result property="string" column="string"/>
  </resultMap>
</mapper>
""".strip(),
    )
    _write(
        tmp_path / 'src/main/java/egovframework/test/room/service/vo/RoomVO.java',
        """
package egovframework.test.room.service.vo;
public class RoomVO {
  private String roomId;
  private String location;
  private String capacity;
  private String roomDesc;
  private String updDt;
}
""".strip(),
    )
    report = validate_generated_project(tmp_path, _Cfg(), include_runtime=False)
    msgs = [i.get('message') or i.get('reason') or '' for i in report.get('static_issues') or []]
    assert not any('text' in msg or 'string' in msg for msg in msgs)


def test_auto_repair_adds_room_calendar_method_with_contract(tmp_path: Path):
    controller = tmp_path / 'src/main/java/egovframework/test/room/web/RoomController.java'
    _write(
        controller,
        """
package egovframework.test.room.web;
import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.ui.Model;
@Controller
@RequestMapping("/room")
public class RoomController {
  @GetMapping("/list.do")
  public String list(Model model) { return "room/roomList"; }
}
""".strip(),
    )
    report = {
        'issues': [
            {
                'type': 'calendar_mapping_missing',
                'path': 'src/main/java/egovframework/test/room/web/RoomController.java',
                'repairable': True,
                'details': {'domain': 'room', 'expected_view': 'room/roomCalendar'},
            }
        ]
    }
    result = apply_generated_project_auto_repair(tmp_path, report)
    body = controller.read_text(encoding='utf-8')
    assert result['changed_count'] == 1
    assert '@GetMapping("/calendar.do")' in body
    assert 'model.addAttribute("calendarcells"' in body
    assert 'return "room/roomCalendar";' in body


def test_list_rewrite_includes_all_search_fields(tmp_path: Path):
    jsp = tmp_path / 'src/main/webapp/WEB-INF/views/room/roomList.jsp'
    _write(jsp, '<html><body>list</body></html>')

    class _Schema:
        entity = 'Room'
        id_prop = 'roomId'
        routes = {'form': '/room/edit.do', 'detail': '/room/detail.do', 'delete': '/room/remove.do'}
        fields = [
            ('roomId', 'room_id', 'String'),
            ('location', 'location', 'String'),
            ('capacity', 'capacity', 'String'),
            ('regDt', 'reg_dt', 'String'),
            ('updDt', 'upd_dt', 'String'),
            ('useYn', 'use_yn', 'String'),
        ]

    assert _rewrite_list_jsp_from_schema(tmp_path, str(jsp.relative_to(tmp_path)).replace('\\', '/'), _Schema())
    body = jsp.read_text(encoding='utf-8')
    assert 'id="searchForm"' in body
    assert 'name="regDt"' in body
    assert 'name="updDt"' in body
    assert 'name="useYn"' in body


def test_edit_timeout_repair_writes_safe_jsp_and_controller(tmp_path: Path):
    controller = tmp_path / 'src/main/java/egovframework/test/reservation/web/ReservationController.java'
    _write(
        controller,
        """
package egovframework.test.reservation.web;
import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.ui.Model;
@Controller
@RequestMapping("/reservation")
public class ReservationController {
  @GetMapping("/edit.do")
  public String edit(Model model) throws Exception {
    while(true) {}
  }
}
""".strip(),
    )
    runtime = {'endpoint_smoke': {'status': 'failed', 'results': [{'route': '/reservation/edit.do', 'ok': False, 'error': 'timed out'}]}}
    changed = _repair_timed_out_edit_endpoints(tmp_path, runtime)
    body = controller.read_text(encoding='utf-8')
    jsp = tmp_path / 'src/main/webapp/WEB-INF/views/reservation/reservationForm.jsp'
    assert changed
    assert 'return "reservation/reservationForm";' in body
    assert jsp.exists()
    assert 'AUTOPJ smoke-safe edit page' in jsp.read_text(encoding='utf-8')
