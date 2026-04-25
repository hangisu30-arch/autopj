from pathlib import Path

from app.io.execution_core_apply import _normalize_out_path, _repair_content_by_path


def test_jsp_paths_and_crud_repair():
    base_package = "egovframework.fulljsp"

    jsp_path = _normalize_out_path(
        "src/main/webapp/WEB-INF/views/memberList.jsp",
        base_package=base_package,
        preferred_entity="Member",
        content="",
        extra_text="member crud jsp",
    )
    assert jsp_path == "src/main/webapp/WEB-INF/views/member/memberList.jsp"

    broken_controller = """package egovframework.fulljsp.member.web;

import javax.annotation.Resource;
import javax.servlet.http.HttpSession;
import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import egovframework.fulljsp.member.service.MemberService;
import egovframework.fulljsp.member.service.vo.MemberVO;

@Controller
@RequestMapping("/member")
public class MemberController {

    @Resource(name = "memberService")
    private MemberService memberService;

    @GetMapping("/login.do")
    public String loginForm(Model model) {
        model.addAttribute("item", new MemberVO());
        return "memberForm";
    }

    @PostMapping("/process.do")
    public String process(MemberVO vo, HttpSession session, Model model) throws Exception {
        MemberVO authUser = memberService.authenticate(vo);
        if (authUser == null) {
            model.addAttribute("loginError", true);
            model.addAttribute("item", vo);
            return "memberForm";
        }
        session.setAttribute("loginUser", authUser);
        return "redirect:/";
    }
}
"""

    repaired = _repair_content_by_path(
        "src/main/java/egovframework/fulljsp/member/web/MemberController.java",
        broken_controller,
        base_package=base_package,
        preferred_entity="Member",
        schema_map=None,
    )
    lowered = repaired.lower()
    assert '@getmapping("/list.do")' in lowered
    assert '@postmapping("/save.do")' in lowered
    assert 'authenticate(' not in lowered
    assert 'return "member/memberlist";' in lowered
