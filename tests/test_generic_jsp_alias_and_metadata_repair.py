from pathlib import Path

from app.validation.generated_project_validator import _suggest_property_replacement
from app.validation.project_auto_repair import _repair_jsp_vo_property_mismatch, _sanitize_ui_metadata_and_sensitive_refs


def test_suggest_property_replacement_prefers_semantic_aliases():
    available = [
        'scheduleTitle',
        'startDatetime',
        'endDatetime',
        'locationText',
        'memberNo',
    ]
    assert _suggest_property_replacement('title', available) == 'scheduleTitle'
    assert _suggest_property_replacement('startDate', available) == 'startDatetime'
    assert _suggest_property_replacement('endDate', available) == 'endDatetime'
    assert _suggest_property_replacement('location', available) == 'locationText'
    assert _suggest_property_replacement('memberNo_2', available) == 'memberNo'


def test_repair_jsp_vo_property_mismatch_rewrites_numbered_alias_fields(tmp_path: Path):
    jsp = tmp_path / 'sample.jsp'
    jsp.write_text(
        '\n'.join([
            '<input name="title_2" value="${item.title_2}"/>',
            '<input name="startDate_2" value="${item.startDate_2}"/>',
            '<input name="endDate_3" value="${item.endDate_3}"/>',
            '<input name="location_3" value="${item.location_3}"/>',
        ]) + '\n',
        encoding='utf-8',
    )
    issue = {
        'details': {
            'available_props': ['scheduleTitle', 'startDatetime', 'endDatetime', 'locationText'],
            'mapper_props': ['scheduleTitle', 'startDatetime', 'endDatetime', 'locationText'],
            'missing_props': ['title_2', 'startDate_2', 'endDate_3', 'location_3'],
            'missing_props_by_var': {'item': ['title_2', 'startDate_2', 'endDate_3', 'location_3']},
            'suggested_replacements': {},
        }
    }
    assert _repair_jsp_vo_property_mismatch(jsp, issue, tmp_path)
    body = jsp.read_text(encoding='utf-8')
    assert 'item.scheduleTitle' in body
    assert 'item.startDatetime' in body
    assert 'item.endDatetime' in body
    assert 'item.locationText' in body
    assert 'title_2' not in body
    assert 'startDate_2' not in body


def test_sanitize_ui_metadata_and_sensitive_refs_removes_table_headers_and_labels():
    body = '''
    <th>db</th>
    <label for="schemaName">schema</label>
    <input name="tableName" value="${item.tableName}"/>
    <div>${item.packageName}</div>
    '''
    cleaned = _sanitize_ui_metadata_and_sensitive_refs(body, ['db', 'schemaName', 'tableName', 'packageName'])
    assert 'tableName' not in cleaned
    assert 'packageName' not in cleaned
    assert '<th>db</th>' not in cleaned.lower()
    assert 'schemaName' not in cleaned
