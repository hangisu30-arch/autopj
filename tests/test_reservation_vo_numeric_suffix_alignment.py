from pathlib import Path

from app.validation.generated_project_validator import validate_generated_project
from app.validation.post_generation_repair import apply_generated_project_auto_repair
from execution_core.builtin_crud import _camel_from_snake


class _Cfg:
    frontend_key = "jsp"
    backend_key = "spring"


def _write(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


def test_numeric_suffix_column_keeps_underscore_in_property_name():
    assert _camel_from_snake("repeat_3") == "repeat_3"
    assert _camel_from_snake("repeat_7") == "repeat_7"
    assert _camel_from_snake("sans_serif") == "sansSerif"


def test_mapper_vo_mismatch_with_numeric_suffix_columns_is_fully_repaired(tmp_path: Path):
    project = tmp_path
    _write(project / "src/main/resources/schema.sql", """
CREATE TABLE IF NOT EXISTS reservation (
  sans_serif varchar(50) COMMENT 'sans',
  repeat_3 varchar(50) COMMENT 'repeat3',
  repeat_7 varchar(50) COMMENT 'repeat7',
  date varchar(50) COMMENT 'date',
  status varchar(50) COMMENT 'status',
  reservation_id varchar(50) COMMENT 'id'
);
""".strip())
    _write(project / "src/main/resources/egovframework/mapper/reservation/ReservationMapper.xml", """
<mapper namespace="egovframework.test.reservation.service.mapper.ReservationMapper">
  <resultMap id="reservationMap" type="egovframework.test.reservation.service.vo.ReservationVO">
    <result property="sansSerif" column="sans_serif"/>
    <result property="repeat_3" column="repeat_3"/>
    <result property="repeat_7" column="repeat_7"/>
    <result property="date" column="date"/>
    <result property="status" column="status"/>
    <id property="reservationId" column="reservation_id"/>
  </resultMap>
  <select id="selectReservationList" resultMap="reservationMap">
    SELECT sans_serif, repeat_3, repeat_7, date, status, reservation_id FROM reservation
  </select>
</mapper>
""".strip())
    _write(project / "src/main/java/egovframework/test/reservation/service/vo/ReservationVO.java", """
package egovframework.test.reservation.service.vo;

public class ReservationVO {
    private String roomName;
}
""".strip())

    report_before = validate_generated_project(project, _Cfg(), include_runtime=False)
    kinds_before = {issue.get("type") for issue in report_before.get("static_issues") or []}
    assert "mapper_vo_column_mismatch" in kinds_before

    repair = apply_generated_project_auto_repair(project, report_before)
    assert repair["changed_count"] >= 1

    vo_body = (project / "src/main/java/egovframework/test/reservation/service/vo/ReservationVO.java").read_text(encoding="utf-8")
    assert "private String repeat_3;" in vo_body
    assert "private String repeat_7;" in vo_body
    assert "private String sansSerif;" in vo_body

    report_after = validate_generated_project(project, _Cfg(), include_runtime=False)
    kinds_after = {issue.get("type") for issue in report_after.get("static_issues") or []}
    assert "mapper_vo_column_mismatch" not in kinds_after
