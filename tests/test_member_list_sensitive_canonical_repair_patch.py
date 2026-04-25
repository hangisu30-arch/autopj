from pathlib import Path

from app.validation.post_generation_repair import _canonicalize_non_auth_sensitive_jsp
from app.ui.generated_content_validator import validate_generated_content


def test_member_list_auth_sensitive_issue_rewrites_to_clean_list(tmp_path: Path) -> None:
    root = tmp_path
    jsp = root / "src/main/webapp/WEB-INF/views/member/memberList.jsp"
    jsp.parent.mkdir(parents=True, exist_ok=True)
    jsp.write_text(
        """<%@ page contentType="text/html; charset=UTF-8" pageEncoding="UTF-8"%>
<table>
  <tr><th>비밀번호</th><td><c:out value="${row.password}"/></td></tr>
  <tr><th>회원명</th><td><c:out value="${row.memberName}"/></td></tr>
</table>
""",
        encoding="utf-8",
    )
    vo = root / "src/main/java/egovframework/demo/member/service/vo/MemberVO.java"
    vo.parent.mkdir(parents=True, exist_ok=True)
    vo.write_text(
        """package egovframework.demo.member.service.vo;

public class MemberVO {
    private String memberId;
    private String loginId;
    private String password;
    private String memberName;

    public String getMemberId() { return memberId; }
    public void setMemberId(String memberId) { this.memberId = memberId; }
    public String getLoginId() { return loginId; }
    public void setLoginId(String loginId) { this.loginId = loginId; }
    public String getPassword() { return password; }
    public void setPassword(String password) { this.password = password; }
    public String getMemberName() { return memberName; }
    public void setMemberName(String memberName) { this.memberName = memberName; }
}
""",
        encoding="utf-8",
    )

    changed = _canonicalize_non_auth_sensitive_jsp(root, "src/main/webapp/WEB-INF/views/member/memberList.jsp", "non-auth UI must not expose auth-sensitive fields such as password/login_password")
    assert changed is True
    body = jsp.read_text(encoding="utf-8").lower()
    assert 'password' not in body
    assert 'membername' in body
    ok, reason = validate_generated_content('src/main/webapp/WEB-INF/views/member/memberList.jsp', jsp.read_text(encoding="utf-8"), frontend_key='jsp')
    assert ok, reason
