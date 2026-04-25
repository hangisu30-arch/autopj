from pathlib import Path
from types import SimpleNamespace

from app.ui.fallback_builder import build_builtin_fallback_content
from app.validation.backend_compile_repair import _local_contract_repair


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')


def test_fallback_builder_preserves_long_id_from_controller_spec():
    path = 'src/main/java/egovframework/fff/room/web/RoomController.java'
    spec = '''
package egovframework.fff.room.web;
@Controller
@RequestMapping("/room")
public class RoomController {
  @GetMapping("/detail.do")
  public String detail(@RequestParam("roomId") Long roomId, Model model) throws Exception {
    model.addAttribute("item", roomService.selectRoom(roomId));
    return "room/roomDetail";
  }
}
'''
    content = build_builtin_fallback_content(path, spec, project_name='fff')
    assert '@RequestParam("roomId") Long roomId' in content
    assert 'roomService.selectRoom(roomId)' in content
    assert '@RequestParam(value="roomId", required=false) Long roomId' in content


def test_local_contract_repair_uses_bundle_schema_to_fix_room_controller_id_type(tmp_path: Path):
    controller = tmp_path / 'src/main/java/egovframework/fff/room/web/RoomController.java'
    service = tmp_path / 'src/main/java/egovframework/fff/room/service/RoomService.java'
    service_impl = tmp_path / 'src/main/java/egovframework/fff/room/service/impl/RoomServiceImpl.java'
    vo = tmp_path / 'src/main/java/egovframework/fff/room/service/vo/RoomVO.java'
    mapper = tmp_path / 'src/main/java/egovframework/fff/room/service/mapper/RoomMapper.java'
    mapper_xml = tmp_path / 'src/main/resources/egovframework/mapper/room/RoomMapper.xml'

    _write(controller, '''package egovframework.fff.room.web;
import javax.annotation.Resource;
import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.web.bind.annotation.*;
import egovframework.fff.room.service.RoomService;
@Controller @RequestMapping("/room")
public class RoomController {
  @Resource(name="roomService") private RoomService roomService;
  @GetMapping("/detail.do") public String detail(@RequestParam("roomId") String roomId, Model model) throws Exception { model.addAttribute("item", roomService.selectRoom(roomId)); return "room/roomDetail"; }
}
''')
    _write(service, 'package egovframework.fff.room.service; import java.util.List; import egovframework.fff.room.service.vo.RoomVO; public interface RoomService { List<RoomVO> selectRoomList() throws Exception; RoomVO selectRoom(Long roomId) throws Exception; int insertRoom(RoomVO vo) throws Exception; int updateRoom(RoomVO vo) throws Exception; int deleteRoom(Long roomId) throws Exception; }')
    _write(service_impl, 'package egovframework.fff.room.service.impl; import java.util.List; import egovframework.fff.room.service.RoomService; import egovframework.fff.room.service.mapper.RoomMapper; import egovframework.fff.room.service.vo.RoomVO; public class RoomServiceImpl implements RoomService { private RoomMapper roomMapper; public List<RoomVO> selectRoomList() throws Exception { return null; } public RoomVO selectRoom(Long roomId) throws Exception { return null; } public int insertRoom(RoomVO vo) throws Exception { return 0; } public int updateRoom(RoomVO vo) throws Exception { return 0; } public int deleteRoom(Long roomId) throws Exception { return 0; } }')
    _write(vo, 'package egovframework.fff.room.service.vo; public class RoomVO { private Long roomId; private String roomName; public Long getRoomId(){ return roomId; } public void setRoomId(Long roomId){ this.roomId = roomId; } }')
    _write(mapper, 'package egovframework.fff.room.service.mapper; import org.apache.ibatis.annotations.Mapper; import org.apache.ibatis.annotations.Param; import egovframework.fff.room.service.vo.RoomVO; @Mapper public interface RoomMapper { RoomVO selectRoom(@Param("roomId") Long roomId); int deleteRoom(@Param("roomId") Long roomId); }')
    _write(mapper_xml, '<mapper namespace="egovframework.fff.room.service.mapper.RoomMapper"><resultMap id="RoomMap" type="egovframework.fff.room.service.vo.RoomVO"><id property="roomId" column="room_id"/></resultMap><select id="selectRoom" parameterType="long" resultMap="RoomMap">SELECT room_id, room_name FROM room WHERE room_id = #{roomId}</select></mapper>')

    runtime_report = {'compile': {'errors': [{'code': 'cannot_find_symbol', 'message': 'cannot find symbol'}]}}
    cfg = SimpleNamespace(project_name='fff')

    changed = _local_contract_repair(tmp_path, cfg, {}, [str(controller.relative_to(tmp_path)).replace('\\', '/')], runtime_report)
    assert changed
    repaired = controller.read_text(encoding='utf-8')
    assert '@RequestParam("roomId") Long roomId' in repaired
    assert '@RequestParam(value="roomId", required=false) Long roomId' in repaired
    assert 'roomService.selectRoom(roomId)' in repaired
    assert 'roomService.deleteRoom(roomId)' in repaired
