from pathlib import Path

from app.validation.backend_compile_repair import enforce_generated_project_invariants


def test_invariants_relocate_reserved_java_package_segments(tmp_path: Path):
    root = tmp_path
    vo = root / "src/main/java/egovframework/test/if/service/vo/IfVO.java"
    svc = root / "src/main/java/egovframework/test/if/service/impl/IfServiceImpl.java"
    mapper_xml = root / "src/main/resources/egovframework/mapper/if/IfMapper.xml"
    vo.parent.mkdir(parents=True, exist_ok=True)
    svc.parent.mkdir(parents=True, exist_ok=True)
    mapper_xml.parent.mkdir(parents=True, exist_ok=True)
    vo.write_text("""package egovframework.test.if.service.vo;
public class IfVO {}
""", encoding="utf-8")
    svc.write_text("""package egovframework.test.if.service.impl;
import egovframework.test.if.service.vo.IfVO;
public class IfServiceImpl { private IfVO vo; }
""", encoding="utf-8")
    mapper_xml.write_text('<mapper namespace="egovframework.test.if.service.mapper.IfMapper"></mapper>', encoding="utf-8")

    report = enforce_generated_project_invariants(root)

    assert (root / "src/main/java/egovframework/test/if_/service/vo/IfVO.java").exists()
    assert (root / "src/main/java/egovframework/test/if_/service/impl/IfServiceImpl.java").exists()
    assert not vo.exists()
    assert not svc.exists()
    svc_body = (root / "src/main/java/egovframework/test/if_/service/impl/IfServiceImpl.java").read_text(encoding="utf-8")
    assert "package egovframework.test.if_.service.impl;" in svc_body
    assert "import egovframework.test.if_.service.vo.IfVO;" in svc_body
    xml_body = mapper_xml.read_text(encoding="utf-8")
    assert "egovframework.test.if_.service.mapper.IfMapper" in xml_body
    assert report["changed_count"] >= 3
