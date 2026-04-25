from app.adapters.jsp.jsp_task_builder import JspTaskBuilder


def test_jsp_builder_prefers_ir_main_jsp_path():
    analysis_result = {
        'project': {'project_name': 'worktest', 'base_package': 'egovframework.worktest', 'frontend_mode': 'jsp'},
        'domains': [{
            'name': 'schedule',
            'entity_name': 'Schedule',
            'feature_kind': 'schedule',
            'ir': {
                'classification': {'primaryPattern': 'calendar'},
                'mainEntry': {'route': '/schedule/calendar.do', 'jsp': '/WEB-INF/views/schedule/scheduleCalendar.jsp'},
                'frontendArtifacts': {
                    'mainJsp': 'src/main/webapp/WEB-INF/views/schedule/scheduleCalendar.jsp',
                    'detailJsp': 'src/main/webapp/WEB-INF/views/schedule/scheduleDetail.jsp',
                    'formJsp': 'src/main/webapp/WEB-INF/views/schedule/scheduleForm.jsp',
                },
            },
        }],
    }
    plan = JspTaskBuilder().build(analysis_result).to_dict()
    domain = plan['domains'][0]
    views = {v['artifact_type']: v for v in domain['views']}
    assert views['list_jsp']['target_path'].endswith('/schedule/scheduleCalendar.jsp')
    assert views['list_jsp']['view_name'] == 'schedule/scheduleCalendar'
    assert 'calendar' in views['list_jsp']['purpose'].lower()
