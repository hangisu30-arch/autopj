from execution_core.builtin_crud import _temporal_write_value_expr, _jsp_input_type
from app.io.execution_core_apply import _autopj_input_type


def test_temporal_write_value_expr_accepts_datetime_with_seconds_for_persistence_fields():
    expr = _temporal_write_value_expr('regDt', 'reg_dt')
    assert "LENGTH(NULLIF(TRIM(REPLACE(#{regDt}, 'T', ' ')), '')) = 19" not in expr  # robust branch keeps ELSE for seconds
    assert "STR_TO_DATE(NULLIF(TRIM(REPLACE(#{regDt}, 'T', ' ')), ''), '%Y-%m-%d %H:%i:%s')" in expr or "%Y-%m-%d %H:%i:%s" in expr
    expr2 = _temporal_write_value_expr('modDt', 'mod_dt')
    assert "%Y-%m-%d %H:%i:%s" in expr2


def test_audit_temporal_inputs_are_date_only_in_generated_forms():
    assert _jsp_input_type('regDt', 'String') == 'date'
    assert _jsp_input_type('modDt', 'String') == 'date'
    assert _autopj_input_type('regDt', 'String') == 'date'
    assert _autopj_input_type('modDt', 'String') == 'date'
