from app.ui.design_reference_analyzer import get_design_reference_profile


class _Resp:
    def __init__(self, text: str):
        self.text = text
        self.encoding = 'utf-8'
        self.apparent_encoding = 'utf-8'

    def raise_for_status(self):
        return None


def _fake_requests_get(url, headers=None, timeout=None):
    if str(url).endswith('ref.css'):
        return _Resp('body { font-family: Arial, sans-serif; color: #123456; } .btn { border-radius: 12px; }')
    return _Resp('''
    <html>
      <head>
        <title>Reference Portal</title>
        <link rel="stylesheet" href="/assets/ref.css" />
        <style>.card { box-shadow: 0 4px 10px rgba(0,0,0,0.1); }</style>
      </head>
      <body>
        <button class="btn">Save</button>
      </body>
    </html>
    ''')


def test_design_reference_profile_works_without_bs4(monkeypatch):
    monkeypatch.setattr('app.ui.design_reference_analyzer.BeautifulSoup', None)
    monkeypatch.setattr('app.ui.design_reference_analyzer.requests.get', _fake_requests_get)
    profile = get_design_reference_profile('https://example.test/reference', force_refresh=True)
    assert profile is not None
    assert profile.page_title == 'Reference Portal'
    assert '#123456' in profile.colors
    assert any('ref.css' in url for url in profile.stylesheet_urls)
    assert profile.is_usable()
