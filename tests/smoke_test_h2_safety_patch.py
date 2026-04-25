from execution_core.project_patcher import patch_application_properties


def test_existing_h2_datasource_url_is_made_restart_safe(tmp_path):
    project_root = tmp_path / "demo"
    resources = project_root / "src/main/resources"
    resources.mkdir(parents=True, exist_ok=True)
    props = resources / "application.properties"
    props.write_text(
        "spring.datasource.url=jdbc:h2:file:./demo-db\n"
        "spring.datasource.hikari.maximum-pool-size=10\n"
        "spring.datasource.hikari.minimum-idle=2\n",
        encoding="utf-8",
    )

    patch_application_properties(project_root, "egovframework.demo", "react")

    text = props.read_text(encoding="utf-8")
    assert "jdbc:h2:file:./demo-db;MODE=MySQL;DB_CLOSE_ON_EXIT=FALSE;DB_CLOSE_DELAY=-1" in text
    assert "spring.datasource.hikari.maximum-pool-size=1" in text
    assert "spring.datasource.hikari.minimum-idle=1" in text
