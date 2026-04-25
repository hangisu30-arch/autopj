from pathlib import Path

from app.ui.state import ProjectConfig
from app.validation.generated_project_validator import validate_generated_project
from app.validation.runtime_smoke import _route_timeout_sequence, _select_smoke_routes, parse_backend_log_errors, run_backend_runtime_validation, smoke_test_endpoints


def test_parse_backend_log_errors_detects_startup_failures():
    log_text = """
    Error starting ApplicationContext.
    org.springframework.beans.factory.UnsatisfiedDependencyException: Error creating bean with name 'x'
    org.springframework.beans.factory.BeanCreationException: boom
    org.apache.jasper.JasperException: /WEB-INF/views/test.jsp
    Application run failed
    """
    errors = parse_backend_log_errors(log_text)
    codes = {item["code"] for item in errors}
    assert "application_run_failed" in codes
    assert "unsatisfied_dependency" in codes
    assert "bean_creation" in codes
    assert "jsp_error" in codes


def test_run_backend_runtime_validation_orchestrates_compile_startup_and_smoke(monkeypatch, tmp_path: Path):
    manifest = {"routes": [{"method": "GET", "path": "/sample/list.do"}]}
    events = []

    class DummyProc:
        def terminate(self):
            events.append("terminate")
        def wait(self, timeout=None):
            events.append(f"wait:{timeout}")
            return 0
        def kill(self):
            events.append("kill")
        @property
        def stdout(self):
            return None

    monkeypatch.setattr(
        "app.validation.runtime_smoke.run_compile_smoke",
        lambda project_root, timeout=180: {"status": "ok", "tool": "maven"},
    )
    monkeypatch.setattr(
        "app.validation.runtime_smoke._start_backend",
        lambda candidate, project_root, startup_timeout_seconds=120: (
            {
                "status": "ok",
                "tool": "maven",
                "base_url": "http://127.0.0.1:18080",
                "port": 18080,
                "output": "Started DemoApplication",
                "errors": [],
            },
            DummyProc(),
        ),
    )
    monkeypatch.setattr("app.validation.runtime_smoke.time.sleep", lambda seconds: None)
    monkeypatch.setattr(
        "app.validation.runtime_smoke.run_endpoint_smoke",
        lambda base_url, endpoints, timeout=8: {"status": "ok", "results": [{"url": base_url + endpoints[0]["path"], "ok": True}]},
    )

    report = run_backend_runtime_validation(tmp_path, manifest=manifest)
    assert report["ok"] is True
    assert report["compile"]["status"] == "ok"
    assert report["startup"]["status"] == "ok"
    assert report["endpoint_smoke"]["status"] == "ok"
    assert "terminate" in events


def test_validate_generated_project_writes_runtime_report(monkeypatch, tmp_path: Path):
    controller = tmp_path / "src/main/java/egovframework/demo/sample/web/SampleController.java"
    controller.parent.mkdir(parents=True, exist_ok=True)
    controller.write_text(
        'package egovframework.demo.sample.web;\npublic class SampleController {\n  public String list(){ return "sample/sampleList"; }\n}\n',
        encoding="utf-8",
    )
    jsp = tmp_path / "src/main/webapp/WEB-INF/views/sample/sampleList.jsp"
    jsp.parent.mkdir(parents=True, exist_ok=True)
    jsp.write_text('<html><body><input name="startDate" type="date" /></body></html>', encoding="utf-8")

    monkeypatch.setattr(
        "app.validation.generated_project_validator.run_backend_runtime_validation",
        lambda project_root, manifest=None: {
            "ok": True,
            "compile": {"status": "skipped"},
            "startup": {"status": "skipped"},
            "endpoint_smoke": {"status": "skipped"},
        },
    )

    cfg = ProjectConfig(project_name="demo", frontend_key="jsp", database_key="mysql")
    report = validate_generated_project(tmp_path, cfg, manifest={"routes": []}, include_runtime=True)
    assert "runtime" in report
    assert (tmp_path / ".autopj_debug/generated_project_validation.json").exists()
    assert (tmp_path / ".autopj_debug/runtime_smoke.json").exists()


def test_smoke_test_endpoints_retries_timeout_once(monkeypatch):
    calls = []

    class DummyResponse:
        status = 200
        def geturl(self):
            return "http://127.0.0.1:18080/schedule/calendar.do"
        def read(self, size=-1):
            return b"ok"
        def __enter__(self):
            return self
        def __exit__(self, exc_type, exc, tb):
            return False

    def fake_urlopen(req, timeout=0):
        calls.append(timeout)
        if len(calls) == 1:
            raise TimeoutError("timed out")
        return DummyResponse()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    monkeypatch.setattr("app.validation.runtime_smoke.time.sleep", lambda seconds: None)

    report = smoke_test_endpoints("http://127.0.0.1:18080", ["/schedule/calendar.do"], timeout_seconds=3)
    assert report["status"] == "ok"
    assert report["routes_tested"] == 1
    assert report["results"][0]["route"] == "/schedule/calendar.do"
    assert report["results"][0]["attempts"] == 2
    assert calls == [3, 60]


def test_select_smoke_routes_collapses_auxiliary_auth_pages_to_login_entry():
    routes = [
        "/login/login.do",
        "/login/actionMain.do",
        "/login/integrationGuide.do",
        "/login/certLogin.do",
        "/login/jwtLogin.do",
        "/user/list.do",
    ]

    selected = _select_smoke_routes(routes, limit=6)

    assert "/login/login.do" in selected
    assert "/user/list.do" in selected
    assert "/login/actionMain.do" not in selected
    assert "/login/integrationGuide.do" not in selected
    assert "/login/certLogin.do" not in selected
    assert "/login/jwtLogin.do" not in selected


def test_route_timeout_sequence_gives_login_and_calendar_routes_longer_retry_budget():
    assert _route_timeout_sequence("/schedule/calendar.do", 3, None) == (3, 60)
    assert _route_timeout_sequence("/login/login.do", 3, None) == (3, 90)


def test_smoke_test_endpoints_keeps_timeout_only_secondary_failures_non_fatal(monkeypatch):
    calls = []

    class DummyResponse:
        status = 200
        def __init__(self, final_url):
            self._final_url = final_url
        def geturl(self):
            return self._final_url
        def read(self, size=-1):
            return b"ok"
        def __enter__(self):
            return self
        def __exit__(self, exc_type, exc, tb):
            return False

    def fake_urlopen(req, timeout=0):
        url = req.full_url
        calls.append((url, timeout))
        if url.endswith('/login/login.do'):
            return DummyResponse(url)
        raise TimeoutError('timed out')

    monkeypatch.setattr('urllib.request.urlopen', fake_urlopen)
    monkeypatch.setattr('app.validation.runtime_smoke.time.sleep', lambda seconds: None)

    report = smoke_test_endpoints(
        'http://127.0.0.1:18080',
        ['/login/login.do', '/schedule/calendar.do'],
        timeout_seconds=3,
    )
    assert report['status'] == 'ok'
    assert report['failed_count'] == 1
    assert report['results'][0]['ok'] is True
    assert report['results'][1]['ok'] is False


def test_select_smoke_routes_deprioritizes_root_when_more_specific_routes_exist():
    routes = [
        '/',
        '/login/login.do',
        '/schedule/calendar.do',
    ]

    selected = _select_smoke_routes(routes, limit=2)

    assert '/login/login.do' in selected
    assert '/schedule/calendar.do' in selected
    assert '/' not in selected


def test_smoke_test_endpoints_all_soft_timeout_routes_are_non_fatal(monkeypatch):
    calls = []

    def fake_urlopen(req, timeout=0):
        calls.append((req.full_url, timeout))
        raise TimeoutError('timed out')

    monkeypatch.setattr('urllib.request.urlopen', fake_urlopen)
    monkeypatch.setattr('app.validation.runtime_smoke.time.sleep', lambda seconds: None)

    report = smoke_test_endpoints(
        'http://127.0.0.1:18080',
        ['/', '/login/login.do', '/schedule/calendar.do'],
        timeout_seconds=3,
    )

    assert report['status'] == 'ok'
    assert report['soft_timeout_only'] is True
    assert report['failed_count'] == 2
    assert all(item['ok'] is False for item in report['results'])


def test_smoke_test_endpoints_keeps_non_soft_timeout_failures_fatal(monkeypatch):
    def fake_urlopen(req, timeout=0):
        raise TimeoutError('timed out')

    monkeypatch.setattr('urllib.request.urlopen', fake_urlopen)
    monkeypatch.setattr('app.validation.runtime_smoke.time.sleep', lambda seconds: None)

    report = smoke_test_endpoints(
        'http://127.0.0.1:18080',
        ['/api/ping'],
        timeout_seconds=3,
    )

    assert report['status'] == 'failed'
    assert report['soft_timeout_only'] is False


def test_start_backend_accepts_live_port_when_startup_log_is_missing(monkeypatch, tmp_path: Path):
    class DummyStdout:
        def readline(self):
            return ''
        def read(self):
            return ''

    class DummyProc:
        def __init__(self):
            self.stdout = DummyStdout()
        def poll(self):
            return None
        def terminate(self):
            return None
        def wait(self, timeout=None):
            return 0
        def kill(self):
            return None

    monkeypatch.setattr('app.validation.runtime_smoke._pick_free_port', lambda: 18081)
    monkeypatch.setattr('subprocess.Popen', lambda *args, **kwargs: DummyProc())
    monkeypatch.setattr('app.validation.runtime_smoke._read_startup_output', lambda proc, startup_timeout_seconds: (False, '', []))
    monkeypatch.setattr('app.validation.runtime_smoke._wait_for_startup_probe', lambda port, base_url, grace_seconds=20: True)

    result, proc = __import__('app.validation.runtime_smoke', fromlist=['_start_backend'])._start_backend({'tool': 'maven', 'family': 'maven'}, tmp_path, startup_timeout_seconds=12)

    assert proc is not None
    assert result['status'] == 'ok'
    assert result['startup_probe'] == 'port_or_http_ready'
    assert result['port'] == 18081


def test_start_backend_still_fails_when_fatal_startup_errors_exist(monkeypatch, tmp_path: Path):
    class DummyStdout:
        def readline(self):
            return ''
        def read(self):
            return ''

    class DummyProc:
        def __init__(self):
            self.stdout = DummyStdout()
        def poll(self):
            return None
        def terminate(self):
            return None
        def wait(self, timeout=None):
            return 0
        def kill(self):
            return None

    monkeypatch.setattr('app.validation.runtime_smoke._pick_free_port', lambda: 18082)
    monkeypatch.setattr('subprocess.Popen', lambda *args, **kwargs: DummyProc())
    monkeypatch.setattr(
        'app.validation.runtime_smoke._read_startup_output',
        lambda proc, startup_timeout_seconds: (False, 'BeanCreationException: boom', [{'code': 'bean_creation', 'message': 'Spring bean creation failed', 'snippet': 'boom'}]),
    )
    wait_calls = []
    monkeypatch.setattr('app.validation.runtime_smoke._wait_for_startup_probe', lambda port, base_url, grace_seconds=20: wait_calls.append((port, base_url, grace_seconds)) or True)

    result, proc = __import__('app.validation.runtime_smoke', fromlist=['_start_backend'])._start_backend({'tool': 'maven', 'family': 'maven'}, tmp_path, startup_timeout_seconds=12)

    assert proc is None
    assert result['status'] == 'failed'
    assert result['errors'][0]['code'] == 'bean_creation'
    assert wait_calls == []


def test_smoke_test_endpoints_list_and_form_timeouts_are_soft_when_startup_is_ok(monkeypatch):
    def fake_urlopen(req, timeout=0):
        raise TimeoutError('timed out')

    monkeypatch.setattr('urllib.request.urlopen', fake_urlopen)
    monkeypatch.setattr('app.validation.runtime_smoke.time.sleep', lambda seconds: None)

    report = smoke_test_endpoints(
        'http://127.0.0.1:18080',
        ['/login/login.do', '/if/list.do', '/if/form.do'],
        timeout_seconds=3,
    )

    assert report['status'] == 'ok'
    assert report['soft_timeout_only'] is True
    assert report['failed_count'] == 3
