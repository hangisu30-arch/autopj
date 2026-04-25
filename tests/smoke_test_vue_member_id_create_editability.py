from pathlib import Path
from types import SimpleNamespace

from app.io.vue_builtin_repair import ensure_vue_frontend_crud


def test_vue_member_id_is_editable_on_create_and_readonly_only_on_edit(tmp_path: Path):
    project_root = tmp_path / "proj"
    schema = SimpleNamespace(
        id_prop="memberId",
        id_column="member_id",
        fields=[
            ("memberId", "member_id", "String"),
            ("memberName", "member_name", "String"),
            ("email", "email", "String"),
        ],
    )
    ensure_vue_frontend_crud(project_root, {"Member": schema})
    form = (project_root / "frontend/vue/src/views/member/MemberForm.vue").read_text(encoding="utf-8")
    assert 'v-model="form.memberId"' in form
    assert ':readonly="isEdit"' in form
    assert 'v-model="form.memberId" readonly' not in form
    assert 'v-model="form.memberId" disabled' not in form
