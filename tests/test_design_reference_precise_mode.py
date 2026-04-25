from pathlib import Path

from app.ui.design_reference_analyzer import build_precise_design_reference_block, get_design_reference_profile
from app.ui.state import ProjectConfig
from app.io.execution_core_apply import _ensure_jsp_common_css, _ensure_react_runtime_baseline


class _Resp:
    def __init__(self, text: str):
        self.text = text
        self.encoding = 'utf-8'
        self.apparent_encoding = 'utf-8'

    def raise_for_status(self):
        return None


def _fake_requests_get(url, headers=None, timeout=None):
    if str(url).endswith('ref.css'):
        return _Resp('''
        :root { --brand: #2244aa; }
        body { font-family: "Pretendard", "Noto Sans KR", sans-serif; background: #f7f8fc; color: #223344; }
        .navbar { background: #103a7a; box-shadow: 0 12px 30px rgba(16, 58, 122, 0.18); }
        .btn-primary, button { background: #2244aa; color: #ffffff; border-radius: 18px; padding: 12px 18px; }
        .card { border-radius: 22px; box-shadow: 0 12px 32px rgba(15, 23, 42, 0.12); }
        .form-control, input, select, textarea { border-radius: 14px; border: 1px solid #d5deef; }
        .container { max-width: 1320px; }
        @media (max-width: 820px) { .navbar { padding: 12px; } }
        ''')
    return _Resp('''
    <html>
      <head>
        <title>Reference Portal</title>
        <link rel="stylesheet" href="/assets/ref.css" />
      </head>
      <body>
        <header class="navbar"></header>
        <button class="btn-primary">Save</button>
      </body>
    </html>
    ''')


def test_precise_design_reference_block_contains_tokens(monkeypatch):
    monkeypatch.setattr('app.ui.design_reference_analyzer.requests.get', _fake_requests_get)
    profile = get_design_reference_profile('https://example.test/reference', force_refresh=True)
    assert profile is not None
    assert profile.is_usable()
    assert '#2244aa' in profile.colors
    block = build_precise_design_reference_block('https://example.test/reference')
    assert '[DESIGN REFERENCE ANALYSIS - PRECISE MODE]' in block
    assert 'theme.primary = #2244aa' in block
    assert 'Pretendard' in block
    assert '1320px' in block


def test_jsp_common_css_uses_precise_design_profile(monkeypatch, tmp_path: Path):
    monkeypatch.setattr('app.ui.design_reference_analyzer.requests.get', _fake_requests_get)
    cfg = ProjectConfig(project_name='demo', design_url='https://example.test/reference')
    rel = _ensure_jsp_common_css(tmp_path, cfg=cfg)
    css = (tmp_path / rel).read_text(encoding='utf-8')
    assert '--autopj-primary: #2244aa;' in css
    assert '--autopj-font-family: Pretendard' in css
    assert '--autopj-content-max: 1320px;' in css


def test_react_runtime_baseline_uses_precise_design_profile(monkeypatch, tmp_path: Path):
    monkeypatch.setattr('app.ui.design_reference_analyzer.requests.get', _fake_requests_get)
    cfg = ProjectConfig(project_name='demo', design_url='https://example.test/reference')
    report = _ensure_react_runtime_baseline(tmp_path, cfg=cfg, overwrite=True)
    assert report['src/css/base.css'] == 'written'
    base_css = (tmp_path / 'frontend' / 'react' / 'src/css/base.css').read_text(encoding='utf-8')
    component_css = (tmp_path / 'frontend' / 'react' / 'src/css/component.css').read_text(encoding='utf-8')
    assert '--app-primary: #2244aa;' in base_css
    assert 'Pretendard' in base_css
    assert 'border-radius: var(--app-radius-sm);' in component_css
