from pathlib import Path

from execution_core.project_patcher import patch_boot_application


def test_duplicate_boot_application_cleanup(tmp_path: Path):
    project_root = tmp_path / "fulljsp"
    java_root = project_root / "src/main/java"
    canonical = java_root / "egovframework/fulljsp/EgovBootApplication.java"
    stale = java_root / "egovframework/fulljsp/spring/EgovBootApplication.java"
    canonical.parent.mkdir(parents=True, exist_ok=True)
    stale.parent.mkdir(parents=True, exist_ok=True)

    canonical.write_text(
        "package egovframework.fulljsp;\n\n"
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
    stale.write_text(
        "package egovframework.fulljsp.spring;\n\n"
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

    stale_class = project_root / "target/classes/egovframework/fulljsp/spring/EgovBootApplication.class"
    stale_class.parent.mkdir(parents=True, exist_ok=True)
    stale_class.write_bytes(b"dummy")

    boot_path = patch_boot_application(project_root, "egovframework.fulljsp")

    assert boot_path == canonical
    assert canonical.exists()
    assert not stale.exists()
    assert not stale_class.exists()

    content = canonical.read_text(encoding="utf-8")
    assert "package egovframework.fulljsp;" in content
    assert content.count("@SpringBootApplication") == 1
