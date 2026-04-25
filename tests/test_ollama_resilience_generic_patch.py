from app.ui.ollama_client import call_ollama
from app.ui.ollama_resilience import is_execution_core_managed_schema_sql, should_defer_ollama_file_generation


def test_call_ollama_retries_transient_readiness_timeout_then_succeeds(monkeypatch):
    calls = []

    def fake_ready(*, restart_if_running=True, wait_s=20.0):
        calls.append((restart_if_running, wait_s))
        if len(calls) == 1:
            raise TimeoutError('Ollama server did not become ready in time.')

    monkeypatch.setattr('app.ui.ollama_client.ensure_ollama_ready', fake_ready)
    monkeypatch.setattr('app.ui.ollama_client._stream_generate', lambda *args, **kwargs: 'ok')

    res = call_ollama('hello', restart_if_running=False, max_attempts=2, ready_wait_s=1.0)

    assert res.ok is True
    assert len(calls) == 2
    assert calls[0][0] is False
    assert calls[1][0] is True


def test_should_defer_schema_sql_generation_on_transient_ollama_failure():
    err = 'TimeoutError: Ollama server did not become ready in time.'
    assert should_defer_ollama_file_generation('src/main/resources/db/schema.sql', use_execution_core=True, error=err) is True
    assert should_defer_ollama_file_generation('src/main/resources/schema.sql', use_execution_core=True, error=err) is True
    assert should_defer_ollama_file_generation('src/main/java/egovframework/test/web/TestController.java', use_execution_core=True, error=err) is False


def test_is_execution_core_managed_schema_sql_accepts_variants():
    assert is_execution_core_managed_schema_sql('src/main/resources/schema.sql') is True
    assert is_execution_core_managed_schema_sql('src/main/resources/db/schema.sql') is True
    assert is_execution_core_managed_schema_sql('src/main/resources/schema-mysql.sql') is True
    assert is_execution_core_managed_schema_sql('src/main/resources/data.sql') is False
