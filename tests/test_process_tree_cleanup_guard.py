from pathlib import Path

from app.validation import runtime_smoke


class _FakeProc:
    def __init__(self, pid=4321, returncode=0, output='[INFO] ok'):
        self.pid = pid
        self.returncode = returncode
        self._output = output
        self.terminate_calls = 0
        self.kill_calls = 0
        self.wait_calls = []

    def communicate(self, timeout=None):
        return self._output, None

    def poll(self):
        return self.returncode

    def wait(self, timeout=None):
        self.wait_calls.append(timeout)
        return self.returncode

    def terminate(self):
        self.terminate_calls += 1

    def kill(self):
        self.kill_calls += 1


class _LiveProc(_FakeProc):
    def __init__(self, pid=9876):
        super().__init__(pid=pid, returncode=None, output='')

    def poll(self):
        return None


def test_stop_process_uses_taskkill_tree_on_windows(monkeypatch):
    calls = []
    proc = _LiveProc(pid=2468)

    monkeypatch.setattr(runtime_smoke.os, 'name', 'nt', raising=False)

    def fake_run(cmd, stdout=None, stderr=None, check=False, timeout=None):
        calls.append((cmd, timeout))
        class _Done:
            returncode = 0
        return _Done()

    monkeypatch.setattr(runtime_smoke.subprocess, 'run', fake_run)

    runtime_smoke._stop_process(proc)

    assert calls
    assert calls[0][0][:4] == ['taskkill', '/PID', '2468', '/T']
    assert '/F' in calls[0][0]


def test_run_compile_always_cleans_process_tree(monkeypatch, tmp_path: Path):
    events = []
    fake_proc = _FakeProc(output='BUILD SUCCESS')

    def fake_popen(command, cwd=None, stdout=None, stderr=None, text=None, **kwargs):
        events.append(('popen', command, cwd, kwargs))
        return fake_proc

    def fake_stop(proc):
        events.append(('stop', proc.pid))

    monkeypatch.setattr(runtime_smoke.subprocess, 'Popen', fake_popen)
    monkeypatch.setattr(runtime_smoke, '_stop_process', fake_stop)

    candidate = {
        'command': ['mvn', '-q', '-DskipTests', 'clean', 'compile'],
        'tool': 'maven',
        'family': 'maven',
        'display': 'mvn -q -DskipTests clean compile',
    }
    result = runtime_smoke._run_compile(candidate, tmp_path, timeout_seconds=30)

    assert result['status'] == 'ok'
    assert ('stop', fake_proc.pid) in events
    assert events[0][0] == 'popen'
