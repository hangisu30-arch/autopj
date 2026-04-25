from pathlib import Path
import urllib.error

from app.validation.runtime_smoke import run_backend_runtime_validation, smoke_test_endpoints


def test_smoke_test_endpoints_retries_connection_refused_once(monkeypatch):
    calls = []

    class DummyResponse:
        status = 200
        def geturl(self):
            return "http://127.0.0.1:18080/login/login.do"
        def read(self, size=-1):
            return b"ok"
        def __enter__(self):
            return self
        def __exit__(self, exc_type, exc, tb):
            return False

    def fake_urlopen(req, timeout=0):
        calls.append((req.full_url, timeout))
        if len(calls) == 1:
            raise urllib.error.URLError(ConnectionRefusedError(10061, 'target machine actively refused'))
        return DummyResponse()

    monkeypatch.setattr('urllib.request.urlopen', fake_urlopen)
    monkeypatch.setattr('app.validation.runtime_smoke.time.sleep', lambda seconds: None)

    report = smoke_test_endpoints('http://127.0.0.1:18080', ['/login/login.do'], timeout_seconds=3)

    assert report['status'] == 'ok'
    assert report['failed_count'] == 0
    assert report['results'][0]['attempts'] == 2
    assert calls == [
        ('http://127.0.0.1:18080/login/login.do', 3),
        ('http://127.0.0.1:18080/login/login.do', 90),
    ]


def test_run_backend_runtime_validation_retries_global_smoke_after_connection_refused(monkeypatch, tmp_path: Path):
    events = []

    class DummyProc:
        def terminate(self):
            events.append('terminate')
        def wait(self, timeout=None):
            events.append(f'wait:{timeout}')
            return 0
        def kill(self):
            events.append('kill')
        @property
        def stdout(self):
            return None

    monkeypatch.setattr(
        'app.validation.runtime_smoke.run_compile_smoke',
        lambda project_root, timeout=180: {'status': 'ok', 'tool': 'maven'},
    )
    monkeypatch.setattr(
        'app.validation.runtime_smoke._start_backend',
        lambda candidate, project_root, startup_timeout_seconds=120: (
            {
                'status': 'ok',
                'tool': 'maven',
                'base_url': 'http://127.0.0.1:18080',
                'port': 18080,
                'errors': [],
            },
            DummyProc(),
        ),
    )
    wait_calls = []
    monkeypatch.setattr(
        'app.validation.runtime_smoke._wait_for_endpoint_smoke_ready',
        lambda port, base_url, routes, grace_seconds=20: wait_calls.append((port, tuple(routes), grace_seconds)) or True,
    )
    monkeypatch.setattr('app.validation.runtime_smoke.time.sleep', lambda seconds: None)

    smoke_calls = []
    def fake_run_endpoint_smoke(base_url, endpoints, timeout=8):
        smoke_calls.append((base_url, tuple(item['path'] for item in endpoints), timeout))
        if len(smoke_calls) == 1:
            return {
                'status': 'failed',
                'results': [
                    {'route': '/login/login.do', 'ok': False, 'error': '<urlopen error [WinError 10061] actively refused>'},
                    {'route': '/member/list.do', 'ok': False, 'error': '<urlopen error [WinError 10061] actively refused>'},
                ],
                'connection_refused_only': True,
            }
        return {
            'status': 'ok',
            'results': [{'route': '/login/login.do', 'ok': True}],
            'connection_refused_only': False,
        }

    monkeypatch.setattr('app.validation.runtime_smoke.run_endpoint_smoke', fake_run_endpoint_smoke)

    manifest = {'routes': [{'method': 'GET', 'path': '/login/login.do'}, {'method': 'GET', 'path': '/member/list.do'}]}
    report = run_backend_runtime_validation(tmp_path, manifest=manifest, startup_timeout_seconds=30)

    assert report['status'] == 'ok'
    assert report['endpoint_smoke']['status'] == 'ok'
    assert len(smoke_calls) == 2
    assert wait_calls
    assert 'terminate' in events


def test_runtime_validation_restarts_backend_when_process_exits_before_smoke_ready(monkeypatch, tmp_path: Path):
    events = []

    class DummyProc:
        def __init__(self, exited=False):
            self._exited = exited
        def poll(self):
            return 0 if self._exited else None
        def terminate(self):
            events.append('terminate')
        def wait(self, timeout=None):
            events.append(f'wait:{timeout}')
            return 0
        def kill(self):
            events.append('kill')
        @property
        def stdout(self):
            return None

    monkeypatch.setattr(
        'app.validation.runtime_smoke.run_compile_smoke',
        lambda project_root, timeout=180: {'status': 'ok', 'tool': 'maven'},
    )

    starts = []
    def fake_start_backend(candidate, project_root, startup_timeout_seconds=120):
        starts.append('start')
        if len(starts) == 1:
            return ({'status': 'ok', 'tool': 'maven', 'base_url': 'http://127.0.0.1:18080', 'port': 18080, 'errors': []}, DummyProc(exited=True))
        return ({'status': 'ok', 'tool': 'maven', 'base_url': 'http://127.0.0.1:18081', 'port': 18081, 'errors': []}, DummyProc(exited=False))

    monkeypatch.setattr('app.validation.runtime_smoke._start_backend', fake_start_backend)
    monkeypatch.setattr('app.validation.runtime_smoke._wait_for_endpoint_smoke_ready', lambda *args, **kwargs: False)
    monkeypatch.setattr('app.validation.runtime_smoke.time.sleep', lambda seconds: None)

    smoke_calls = []
    def fake_run_endpoint_smoke(base_url, endpoints, timeout=8):
        smoke_calls.append((base_url, tuple(item['path'] for item in endpoints), timeout))
        if len(smoke_calls) == 1:
            return {
                'status': 'failed',
                'results': [{'route': '/login/login.do', 'ok': False, 'error': '<urlopen error [WinError 10061] actively refused>'}],
                'failed_count': 1,
                'connection_refused_only': True,
            }
        return {
            'status': 'ok',
            'results': [{'route': '/login/login.do', 'ok': True}],
            'failed_count': 0,
            'connection_refused_only': False,
        }

    monkeypatch.setattr('app.validation.runtime_smoke.run_endpoint_smoke', fake_run_endpoint_smoke)

    manifest = {'routes': [{'method': 'GET', 'path': '/login/login.do'}]}
    report = run_backend_runtime_validation(tmp_path, manifest=manifest, startup_timeout_seconds=30)

    assert report['status'] == 'ok'
    assert report['startup']['port'] == 18081
    assert len(starts) == 2
    assert len(smoke_calls) == 2
