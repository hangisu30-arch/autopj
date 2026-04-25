from app.ui.options import DESIGN_STYLES
from app.ui.prompt_templates import build_gemini_json_fileops_prompt, _design_style_guidance
from app.ui.state import ProjectConfig


def test_design_styles_include_richer_variants():
    keys = {opt.key for opt in DESIGN_STYLES}
    assert {"portal", "enterprise_portal", "rich_cards", "dashboard", "soft_dark"}.issubset(keys)


def test_design_guidance_mentions_certlogin_for_portal_style():
    cfg = ProjectConfig(design_style_key="portal", design_style_label="포털형", frontend_key="jsp", frontend_label="jsp")
    text = _design_style_guidance(cfg)
    assert "certlogin" in text
    assert "main_portal.css" in text


def test_prompt_includes_high_design_richness_and_common_css_merge_rules():
    cfg = ProjectConfig(
        project_name="worktest",
        frontend_key="jsp",
        frontend_label="jsp",
        design_style_key="enterprise_portal",
        design_style_label="업무포털 고급형",
        design_url="https://example.com/ref",
        extra_requirements="일정관리 화면"
    )
    prompt = build_gemini_json_fileops_prompt(cfg)
    assert "- design_richness: high" in prompt
    assert "common.css" in prompt
    assert "카드형 패널" in prompt
    assert "업무포털 고급형" in prompt
    assert "https://example.com/ref" in prompt
