from pathlib import Path

from app.io.execution_core_apply import apply_file_ops_with_execution_core
from app.ui.state import ProjectConfig


def test_react_fullstack_repair_rebuilds_backend_and_frontend(tmp_path):
    project_root = tmp_path / "reacttest"
    (project_root / "src/main/resources").mkdir(parents=True, exist_ok=True)
    (project_root / "pom.xml").write_text(
        "<project><modelVersion>4.0.0</modelVersion><groupId>x</groupId><artifactId>x</artifactId></project>",
        encoding="utf-8",
    )
    (project_root / "src/main/resources/application.properties").write_text(
        "spring.datasource.url=jdbc:h2:file:./reacttest\n", encoding="utf-8"
    )
    (project_root / "src/main/java/egovframework/example").mkdir(parents=True, exist_ok=True)
    (project_root / "src/main/java/egovframework/example/EgovBootApplication.java").write_text(
        "package egovframework.example;\n\n"
        "import org.springframework.boot.SpringApplication;\n"
        "import org.springframework.boot.autoconfigure.SpringBootApplication;\n\n"
        "@SpringBootApplication\n"
        "public class EgovBootApplication {\n"
        "    public static void main(String[] args) {\n"
        "        SpringApplication.run(EgovBootApplication.class, args);\n"
        "    }\n"
        "}\n",
        encoding="utf-8",
    )

    broken_ops = [
        {
            "path": "src/main/java/egovframework/fulljsp/member/service/MemberService.java",
            "content": "package egovframework.fulljsp.member.service;\n\npublic interface MemberService {}\n",
        },
        {
            "path": "src/main/java/egovframework/fulljsp/member/web/MemberController.java",
            "content": "package egovframework.fulljsp.member.web;\n\n"
                       "import org.springframework.stereotype.Controller;\n"
                       "@Controller public class MemberController {}\n",
        },
        {
            "path": "src/main/resources/egovframework/mapper/member/MemberMapper.xml",
            "content": "<beans><sqlMap><select id=\"x\">SELECT 1</select></sqlMap></beans>",
        },
        {
            "path": "src/main/webapp/WEB-INF/views/member/memberList.jsp",
            "content": "<html>bad jsp</html>",
        },
        {
            "path": "frontend/react/src/routes/index.jsx",
            "content": "import { createBrowserRouter } from 'react-router-dom';\n"
                       "import MainPage from '../pages/main/MainPage';\n"
                       "const router = createBrowserRouter([{ path: '/', element: <MainPage /> }]);\n"
                       "export default router;\n",
        },
        {
            "path": "frontend/react/src/constants/routes.js",
            "content": "const ROUTES = { MAIN: '/' }; export default ROUTES;\n",
        },
        {
            "path": "frontend/react/src/pages/main/MainPage.jsx",
            "content": "export default function MainPage(){return <p>Main Page</p>}\n",
        },
        {
            "path": "frontend/react/src/api/services/member.js",
            "content": "import axios from '../client';\nexport default { fetchMembers: () => axios.get('/') };\n",
        },
        {
            "path": "frontend/react/src/pages/member/MemberListPage.jsx",
            "content": "import { fetchMembers } from '../api/MemberApi';\nexport default function MemberListPage(){return null;}\n",
        },
        {
            "path": "frontend/react/src/pages/member/MemberDetailPage.jsx",
            "content": "import axios from 'axios';\nexport default function MemberDetailPage(){return null;}\n",
        },
        {
            "path": "frontend/react/src/pages/member/MemberFormPage.jsx",
            "content": "import { useHistory } from 'react-router-dom';\nexport default function MemberFormPage(){return null;}\n",
        },
        {
            "path": "src/main/java/egovframework/reacttest/member/service/vo/MemberVO.java",
            "content": "package egovframework.reacttest.member.service.vo;\n\n"
                       "public class MemberVO {\n"
                       "  private String memberId;\n"
                       "  private String memberName;\n"
                       "  private String email;\n"
                       "  public String getMemberId(){ return memberId; }\n"
                       "  public void setMemberId(String memberId){ this.memberId = memberId; }\n"
                       "  public String getMemberName(){ return memberName; }\n"
                       "  public void setMemberName(String memberName){ this.memberName = memberName; }\n"
                       "  public String getEmail(){ return email; }\n"
                       "  public void setEmail(String email){ this.email = email; }\n"
                       "}\n",
        },
    ]

    cfg = ProjectConfig(project_name="reacttest", frontend_key="react", database_key="h2")
    report = apply_file_ops_with_execution_core(broken_ops, project_root, cfg, overwrite=True)
    assert not report["errors"]

    controller = (project_root / "src/main/java/egovframework/reacttest/member/web/MemberRestController.java").read_text(encoding="utf-8")
    assert "@RestController" in controller
    assert '@RequestMapping("/api/member")' in controller
    assert "MemberController" not in controller

    mapper_xml = (project_root / "src/main/resources/egovframework/mapper/member/MemberMapper.xml").read_text(encoding="utf-8")
    assert "<mapper namespace=\"egovframework.reacttest.member.service.mapper.MemberMapper\">" in mapper_xml
    assert "<resultMap id=\"MemberMap\" type=\"egovframework.reacttest.member.service.vo.MemberVO\">" in mapper_xml
    assert "<beans" not in mapper_xml
    assert "member_email" not in mapper_xml.lower()

    assert not (project_root / "src/main/webapp/WEB-INF/views/member").exists()

    routes = (project_root / "frontend/react/src/constants/routes.js").read_text(encoding="utf-8")
    assert "MEMBER_LIST" in routes and "MEMBER_CREATE" in routes and "MEMBER_EDIT" in routes

    router = (project_root / "frontend/react/src/routes/index.jsx").read_text(encoding="utf-8")
    assert "Navigate" in router
    assert "MemberListPage" in router and "MemberDetailPage" in router and "MemberFormPage" in router
    assert "ROUTES.MEMBER_LIST" in router

    service = (project_root / "frontend/react/src/api/services/member.js").read_text(encoding="utf-8")
    assert 'import { apiRequest } from "@/api/client";' in service
    assert "axios" not in service
    assert "API_BASE = \"/api/member\"" in service
    assert "listMember" in service and "getMember" in service and "createMember" in service

    list_page = (project_root / "frontend/react/src/pages/member/MemberListPage.jsx").read_text(encoding="utf-8")
    assert "@/api/services/member" in list_page
    assert "../api/MemberApi" not in list_page
    assert "ROUTES.MEMBER_CREATE" in list_page
    assert "memberId" in list_page and "memberName" in list_page and "email" in list_page

    detail_page = (project_root / "frontend/react/src/pages/member/MemberDetailPage.jsx").read_text(encoding="utf-8")
    assert "deleteMember" in detail_page and "getMember" in detail_page
    assert "axios" not in detail_page

    form_page = (project_root / "frontend/react/src/pages/member/MemberFormPage.jsx").read_text(encoding="utf-8")
    assert "useNavigate" in form_page
    assert "useHistory" not in form_page
    assert "createMember" in form_page and "updateMember" in form_page

    vite = (project_root / "frontend/react/vite.config.js").read_text(encoding="utf-8")
    assert "/api" in vite and "localhost:8080" in vite and "5173" in vite
