from app.adapters.vue.vue_task_builder import VueTaskBuilder


def test_vue_task_builder_uses_api_and_plain_views():
    analysis_result = {
        "project": {"project_name": "demo", "frontend_mode": "vue"},
        "domains": [{"name": "member", "entity_name": "Member", "feature_kind": "crud"}],
    }
    plan = VueTaskBuilder().build(analysis_result).to_dict()
    domain = plan["domains"][0]
    assert domain["service_path"] == "frontend/vue/src/api/memberApi.js"
    paths = {a["target_path"] for a in domain["artifacts"]}
    assert "frontend/vue/src/views/member/MemberList.vue" in paths
    assert "frontend/vue/src/views/member/MemberDetail.vue" in paths
    assert "frontend/vue/src/views/member/MemberForm.vue" in paths
    assert all("ListView.vue" not in p and "DetailView.vue" not in p and "FormView.vue" not in p for p in paths)
    assert all("src/services/" not in p for p in paths)
