from pathlib import Path

from app.io.execution_core_apply import apply_file_ops_with_execution_core
from app.ui.generated_content_validator import validate_generated_content
from app.ui.state import ProjectConfig


def _make_project_root(project_root: Path) -> None:
    (project_root / "src/main/resources").mkdir(parents=True, exist_ok=True)
    (project_root / "pom.xml").write_text(
        "<project><modelVersion>4.0.0</modelVersion><groupId>x</groupId><artifactId>x</artifactId></project>",
        encoding="utf-8",
    )
    (project_root / "src/main/resources/application.properties").write_text(
        "spring.datasource.url=jdbc:h2:file:./vuetest\n", encoding="utf-8"
    )
    (project_root / "src/main/java/egovframework/example").mkdir(parents=True, exist_ok=True)
    (project_root / "src/main/java/egovframework/example/EgovBootApplication.java").write_text(
        "package egovframework.example;\n\n"
        "import org.springframework.boot.SpringApplication;\n"
        "import org.springframework.boot.autoconfigure.SpringBootApplication;\n\n"
        "@SpringBootApplication\n"
        "public class EgovBootApplication {\n"
        "    public static void main(String[] args) {\n"
        "        SpringApplication.run(EgovBootApplication.class, args);\n"
        "    }\n"
        "}\n",
        encoding="utf-8",
    )


def test_vue_package_json_without_runtime_deps_is_rejected_and_baseline_kept(tmp_path):
    project_root = tmp_path / "vuetest"
    _make_project_root(project_root)

    broken_ops = [
        {"path": "frontend/vue/package.json", "content": '{"name":"frontend-vue","scripts":{"dev":"vite","build":"vite build","preview":"vite preview"},"dependencies":{"vue":"^3"},"devDependencies":{"vite":"^5","@vitejs/plugin-vue":"^5"}}'},
        {"path": "frontend/vue/src/main.js", "content": 'import { createApp } from "vue";\nimport App from "./App.vue";\nimport router from "./router";\ncreateApp(App).use(router).mount("#app");\n'},
    ]
    cfg = ProjectConfig(project_name="vuetest", frontend_key="vue", database_key="h2")
    report = apply_file_ops_with_execution_core(broken_ops, project_root, cfg, overwrite=True)
    assert any(e.get("reason") == "invalid_vue_runtime_content_kept_baseline" for e in report["errors"])
    pkg = (project_root / "frontend/vue/package.json").read_text(encoding="utf-8")
    ok, err = validate_generated_content("frontend/vue/package.json", pkg, frontend_key="vue")
    assert ok, err
    assert '"vue-router"' in pkg
    assert '"vite"' in pkg
    assert '"@vitejs/plugin-vue"' in pkg


def test_vue_main_js_with_pinia_is_rejected_by_validator():
    content = "import { createApp } from \"vue\";\nimport { createPinia } from \"pinia\";\nimport App from \"./App.vue\";\nimport router from \"./router\";\nconst app = createApp(App); app.use(createPinia()); app.use(router); app.mount(\"#app\");\n"
    ok, err = validate_generated_content("frontend/vue/src/main.js", content, frontend_key="vue")
    assert not ok
    assert "pinia" in err.lower()
