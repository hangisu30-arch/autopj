from app.ui.post_validation_logging import post_validation_diagnostic_lines, post_validation_failure_message
from app.validation.post_generation_repair import _build_startup_repair_round


def test_post_validation_failure_message_includes_startup_root_cause_and_log_path():
    message = post_validation_failure_message({
        'remaining_invalid_count': 1,
        'remaining_invalid_files': [{'reason': 'spring boot startup validation failed'}],
        'runtime_validation': {
            'compile': {'status': 'ok', 'errors': []},
            'startup': {
                'status': 'failed',
                'startup_root_cause': 'org.apache.ibatis.binding.BindingException: Invalid bound statement (not found): demo.mapper.insertThing',
                'startup_failure_signature': 'mybatis_binding|src/main/resources/egovframework/mapper/demo/DemoMapper.xml|invalid bound statement (not found): demo.mapper.insertthing',
                'log_path': '.autopj_debug/startup_raw.log',
            },
            'endpoint_smoke': {'status': 'skipped'},
        },
    })

    assert 'startup_root_cause=org.apache.ibatis.binding.BindingException: Invalid bound statement (not found): demo.mapper.insertThing' in message
    assert 'startup_signature=mybatis_binding|src/main/resources/egovframework/mapper/demo/DemoMapper.xml|' in message
    assert 'startup_log=.autopj_debug/startup_raw.log' in message


def test_post_validation_diagnostic_lines_include_final_startup_root_cause():
    lines = post_validation_diagnostic_lines({
        'runtime_validation': {
            'startup': {
                'status': 'failed',
                'startup_root_cause': 'Failed to execute SQL script statement #1 of class path resource [schema.sql]',
                'startup_failure_signature': 'sql_error|schema.sql|failed to execute sql script statement # of class path resource [schema.sql]',
                'log_path': '.autopj_debug/startup_raw.log',
            }
        }
    })

    assert '[STARTUP] root_cause=Failed to execute SQL script statement #1 of class path resource [schema.sql]' in lines
    assert '[STARTUP] signature=sql_error|schema.sql|failed to execute sql script statement # of class path resource [schema.sql]' in lines
    assert '[STARTUP] log=.autopj_debug/startup_raw.log' in lines


def test_build_startup_repair_round_only_marks_unchanged_when_signature_same():
    before_runtime = {
        'compile': {'status': 'ok', 'errors': []},
        'startup': {
            'status': 'failed',
            'startup_failure_signature': 'bean_creation|same',
            'startup_root_cause': 'same',
        },
        'endpoint_smoke': {'status': 'skipped'},
    }
    after_runtime = {
        'compile': {'status': 'ok', 'errors': []},
        'startup': {
            'status': 'failed',
            'startup_failure_signature': 'sql_error|different',
            'startup_root_cause': 'different',
        },
        'endpoint_smoke': {'status': 'skipped'},
    }

    round_info = _build_startup_repair_round(
        round_no=1,
        repair_report={'changed': [{'path': 'schema.sql'}], 'skipped': []},
        before_runtime=before_runtime,
        after_runtime=after_runtime,
    )

    assert round_info['terminal_failure'] == ''
    assert round_info['before_signature'] == 'bean_creation|same'
    assert round_info['after_signature'] == 'sql_error|different'
