from app.adapters.react.react_task_builder import ReactTaskBuilder


def test_react_builder_prefers_ir_calendar_main_page():
    analysis_result = {
        'project': {'project_name': 'worktest', 'frontend_mode': 'react'},
        'domains': [{
            'name': 'schedule',
            'entity_name': 'Schedule',
            'feature_kind': 'schedule',
            'ir': {
                'classification': {'primaryPattern': 'calendar'},
                'mainEntry': {'route': '/schedule/calendar'},
                'frontendArtifacts': {
                    'mainPage': 'frontend/react/src/pages/schedule/ScheduleCalendarPage.jsx',
                    'detailPage': 'frontend/react/src/pages/schedule/ScheduleDetailPage.jsx',
                    'formPage': 'frontend/react/src/pages/schedule/ScheduleFormPage.jsx',
                    'apiService': 'frontend/react/src/api/services/schedule.js',
                },
            },
        }],
    }
    plan = ReactTaskBuilder().build(analysis_result).to_dict()
    domain = plan['domains'][0]
    artifacts = {a['artifact_type']: a for a in domain['artifacts']}
    assert artifacts['page_list']['target_path'].endswith('ScheduleCalendarPage.jsx')
    assert artifacts['page_list']['route_path'] == '/schedule/calendar'
    assert 'calendar' in artifacts['page_list']['purpose'].lower()
