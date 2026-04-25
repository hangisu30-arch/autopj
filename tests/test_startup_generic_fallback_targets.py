from pathlib import Path

from app.validation.post_generation_repair import _startup_runtime_to_static_issues


def test_startup_runtime_falls_back_to_project_initializer(tmp_path: Path):
    root = tmp_path
    init = root / 'src/main/java/egovframework/test/config/LoginDatabaseInitializer.java'
    init.parent.mkdir(parents=True, exist_ok=True)
    init.write_text('package egovframework.test.config; class LoginDatabaseInitializer {}', encoding='utf-8')
    (root / 'src/main/resources/schema.sql').parent.mkdir(parents=True, exist_ok=True)
    (root / 'src/main/resources/schema.sql').write_text('-- schema\n', encoding='utf-8')
    runtime = {
        'startup': {
            'status': 'failed',
            'errors': [
                {'code': 'application_run_failed', 'message': 'Spring Boot startup failed', 'snippet': 'BeanCreationException at org.springframework.beans.factory.support.AbstractAutowireCapableBeanFactory'},
                {'code': 'bean_creation', 'message': 'Spring bean creation failed', 'snippet': 'UnsatisfiedDependencyException'}
            ],
            'log_tail': 'Application run failed\norg.springframework.beans.factory.support.AbstractAutowireCapableBeanFactory\n'
        },
        'compile': {'status': 'ok'}
    }
    issues = _startup_runtime_to_static_issues(root, runtime)
    assert issues
    paths = {item['path'] for item in issues}
    assert 'src/main/java/egovframework/test/config/LoginDatabaseInitializer.java' in paths or 'src/main/resources/schema.sql' in paths
    assert all(item.get('repairable') for item in issues)
