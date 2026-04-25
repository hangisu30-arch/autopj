from app.validation.project_auto_repair import _sanitize_selectorless_style_blocks


def test_selectorless_style_block_is_wrapped_or_removed():
    src = '''<style>
width: 100%;
color: #333;
.table { border-collapse: collapse; }
</style>'''
    out = _sanitize_selectorless_style_blocks(src)
    assert 'width: 100%;' not in out
    assert '<style>' in out and '</style>' in out
    assert '.table { border-collapse: collapse; }' in out


def test_selectorless_style_only_declarations_wraps_to_body():
    src = '''<style>
padding: 16px;
background: #fff;
</style>'''
    out = _sanitize_selectorless_style_blocks(src)
    assert 'body {' in out
    assert 'padding: 16px;' in out
    assert 'background: #fff;' in out
