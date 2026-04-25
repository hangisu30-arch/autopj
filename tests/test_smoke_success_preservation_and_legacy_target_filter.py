from app.validation.post_generation_repair import _preserve_previous_runtime_if_smoke_regressed
from app.validation.runtime_smoke import _select_smoke_routes


def test_preserve_previous_runtime_when_only_smoke_regresses_with_connection_refused():
    before = {
        'compile': {'status': 'ok'},
        'startup': {'status': 'ok'},
        'endpoint_smoke': {'status': 'ok', 'results': [{'route': '/member/list.do', 'ok': True}]},
    }
    after = {
        'compile': {'status': 'ok'},
        'startup': {'status': 'ok'},
        'endpoint_smoke': {
            'status': 'failed',
            'connection_refused_only': True,
            'results': [
                {'route': '/login/login.do', 'ok': False, 'error': '<urlopen error [WinError 10061] actively refused>'},
                {'route': '/tbMember/list.do', 'ok': False, 'error': '<urlopen error [WinError 10061] actively refused>'},
            ],
        },
    }

    preserved = _preserve_previous_runtime_if_smoke_regressed(before, after)

    assert preserved is before
    assert preserved['endpoint_smoke']['status'] == 'ok'


def test_preserve_previous_runtime_does_not_mask_real_http_failure():
    before = {
        'compile': {'status': 'ok'},
        'startup': {'status': 'ok'},
        'endpoint_smoke': {'status': 'ok', 'results': [{'route': '/member/list.do', 'ok': True}]},
    }
    after = {
        'compile': {'status': 'ok'},
        'startup': {'status': 'ok'},
        'endpoint_smoke': {
            'status': 'failed',
            'results': [
                {'route': '/member/list.do', 'ok': False, 'status_code': 500, 'response_excerpt': 'boom'},
            ],
        },
    }

    preserved = _preserve_previous_runtime_if_smoke_regressed(before, after)

    assert preserved is after
    assert preserved['endpoint_smoke']['status'] == 'failed'


def test_select_smoke_routes_prefers_non_tb_alias_when_logical_route_exists():
    selected = _select_smoke_routes([
        '/login/login.do',
        '/tbMember/list.do',
        '/member/list.do',
        '/tbMember/detail.do',
        '/member/detail.do',
    ], limit=6)

    assert '/member/list.do' in selected
    assert '/member/detail.do' in selected
    assert '/tbMember/list.do' not in selected
    assert '/tbMember/detail.do' not in selected
