from app.ui.design_guides import build_design_guidance


def test_design_guidance_contains_certlogin_reference_and_css_merge_rules():
    guide = build_design_guidance('portal', 'https://example.com')
    assert 'EGOV CERTLOGIN INSPIRED' in guide
    assert 'common.css' in guide
    assert 'https://example.com' in guide
    assert '블루' in guide
