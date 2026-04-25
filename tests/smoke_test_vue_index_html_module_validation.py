from app.ui.generated_content_validator import validate_generated_content


def test_vue_index_html_requires_module_entry():
    ok, err = validate_generated_content(
        "frontend/vue/index.html",
        "<html><body><div id=\"app\"></div><script src=\"/src/main.js\"></script></body></html>",
        frontend_key="vue",
    )
    assert not ok
    assert "module script" in err


def test_vue_index_html_valid_module_entry():
    ok, err = validate_generated_content(
        "frontend/vue/index.html",
        "<!doctype html><html><body><div id=\"app\"></div><script type=\"module\" src=\"/src/main.js\"></script></body></html>",
        frontend_key="vue",
    )
    assert ok, err
