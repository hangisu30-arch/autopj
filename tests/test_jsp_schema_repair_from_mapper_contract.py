from pathlib import Path

from app.validation.generated_project_validator import _scan_malformed_jsp_structure
from app.validation.project_auto_repair import _repair_malformed_jsp_structure


def _write(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


def _bootstrap_member_project(root: Path) -> None:
    _write(
        root / "src/main/java/egovframework/test/member/service/vo/MemberVO.java",
        """package egovframework.test.member.service.vo;
public class MemberVO {
    private String memberId;
    private String loginId;
    private String memberName;
    private String email;
    private String useYn;
    public String getMemberId() { return memberId; }
    public void setMemberId(String memberId) { this.memberId = memberId; }
    public String getLoginId() { return loginId; }
    public void setLoginId(String loginId) { this.loginId = loginId; }
    public String getMemberName() { return memberName; }
    public void setMemberName(String memberName) { this.memberName = memberName; }
    public String getEmail() { return email; }
    public void setEmail(String email) { this.email = email; }
    public String getUseYn() { return useYn; }
    public void setUseYn(String useYn) { this.useYn = useYn; }
}
""",
    )
    _write(
        root / "src/main/resources/egovframework/mapper/member/MemberMapper.xml",
        """<?xml version=\"1.0\" encoding=\"UTF-8\"?>
<!DOCTYPE mapper PUBLIC \"-//mybatis.org//DTD Mapper 3.0//EN\" \"http://mybatis.org/dtd/mybatis-3-mapper.dtd\">
<mapper namespace=\"egovframework.test.member.service.mapper.MemberMapper\">
  <resultMap id=\"memberMap\" type=\"egovframework.test.member.service.vo.MemberVO\">
    <id property=\"memberId\" column=\"member_id\"/>
    <result property=\"loginId\" column=\"login_id\"/>
    <result property=\"memberName\" column=\"member_name\"/>
    <result property=\"email\" column=\"email\"/>
    <result property=\"useYn\" column=\"use_yn\"/>
  </resultMap>
  <insert id=\"insertMember\" parameterType=\"egovframework.test.member.service.vo.MemberVO\">
    INSERT INTO tb_member (member_id, login_id, member_name, email, use_yn)
    VALUES (#{memberId}, #{loginId}, #{memberName}, #{email}, #{useYn})
  </insert>
</mapper>
""",
    )
    _write(
        root / "src/main/resources/schema.sql",
        """CREATE TABLE tb_member (
  member_id VARCHAR(64) PRIMARY KEY COMMENT '회원ID',
  login_id VARCHAR(64) COMMENT '로그인ID',
  member_name VARCHAR(100) COMMENT '회원명',
  email VARCHAR(200) COMMENT '이메일',
  use_yn CHAR(1) COMMENT '사용여부'
);
""",
    )


def test_member_form_with_orphan_layout_and_id_only_is_rebuilt_from_mapper_contract(tmp_path: Path):
    _bootstrap_member_project(tmp_path)
    _write(
        tmp_path / "src/main/webapp/WEB-INF/views/member/memberForm.jsp",
        """<%@ page contentType=\"text/html; charset=UTF-8\" pageEncoding=\"UTF-8\"%>
<%@ taglib prefix=\"c\" uri=\"http://java.sun.com/jsp/jstl/core\"%>
<!DOCTYPE html><html><body>
<%@ include file=\"/WEB-INF/views/common/header.jsp\" %>
<%@ include file=\"/WEB-INF/views/common/leftNav.jsp\" %>
      </div>
    </div>
    <div class=\"autopj-form-grid\">
      <label class=\"autopj-field\">
        <input type=\"text\" name=\"memberId\" value=\"<c:out value='${item.memberId}'/>\"/>
      </label>
    </div>
    <div class=\"autopj-form-actions\"><button type=\"submit\">저장</button></div>
  </form>
</body></html>
""",
    )

    issues = _scan_malformed_jsp_structure(tmp_path)
    issue = next(i for i in issues if i["path"].endswith("member/memberForm.jsp"))
    assert _repair_malformed_jsp_structure(tmp_path / issue["path"], issue, tmp_path)

    body = (tmp_path / "src/main/webapp/WEB-INF/views/member/memberForm.jsp").read_text(encoding="utf-8")
    assert '<form class="autopj-form-card form-card"' in body
    assert 'name="memberId"' in body
    assert 'name="loginId"' in body
    assert 'name="memberName"' in body
    assert 'name="email"' in body
    assert '</form>' in body


def test_member_detail_with_empty_grid_is_rebuilt_from_mapper_contract(tmp_path: Path):
    _bootstrap_member_project(tmp_path)
    _write(
        tmp_path / "src/main/webapp/WEB-INF/views/member/memberDetail.jsp",
        """<%@ page contentType=\"text/html; charset=UTF-8\" pageEncoding=\"UTF-8\"%>
<%@ taglib prefix=\"c\" uri=\"http://java.sun.com/jsp/jstl/core\"%>
<!DOCTYPE html><html><body>
<%@ include file=\"/WEB-INF/views/common/header.jsp\" %>
<%@ include file=\"/WEB-INF/views/common/leftNav.jsp\" %>
        </div>
      </div>
      <div class=\"autopj-form-grid\"></div>
      <div class=\"autopj-form-actions\">
        <a class=\"btn\" href=\"<c:url value='/member/form.do'/>?memberId=${item.memberId}\">수정</a>
      </div>
    </div>
  </c:if>
</body></html>
""",
    )

    issues = _scan_malformed_jsp_structure(tmp_path)
    issue = next(i for i in issues if i["path"].endswith("member/memberDetail.jsp"))
    assert _repair_malformed_jsp_structure(tmp_path / issue["path"], issue, tmp_path)

    body = (tmp_path / "src/main/webapp/WEB-INF/views/member/memberDetail.jsp").read_text(encoding="utf-8")
    assert 'memberId' in body
    assert 'loginId' in body
    assert 'memberName' in body
    assert 'email' in body
    assert '상세 정보' in body
    assert '/member/list.do' in body or '목록으로' in body
