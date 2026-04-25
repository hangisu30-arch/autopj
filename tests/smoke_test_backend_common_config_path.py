from __future__ import annotations

from app.ui.analysis_bridge import build_analysis_from_config
from app.ui.backend_bridge import build_backend_plan
from app.ui.state import ProjectConfig


def main() -> None:
    cfg = ProjectConfig(
        project_name='fulljsp',
        backend_key='egov_spring',
        backend_label='전자정부프레임워크 (Spring Boot)',
        frontend_key='jsp',
        frontend_label='jsp',
        database_key='mysql',
        database_label='MySQL',
        output_dir='.',
        extra_requirements=(
            '회원 관리 목록/상세/등록/수정/삭제 화면과 기능 생성.\n'
            '회원 엔티티 컬럼은 member_id, member_name, email 이다.\n'
            'member_id 는 기본키이다.'
        ),
    )
    analysis = build_analysis_from_config(cfg).to_dict()
    plan = build_backend_plan(analysis)
    artifacts = plan['domains'][0]['artifacts']
    config_paths = [a['target_path'] for a in artifacts if a['artifact_type'] == 'mybatis_config']
    assert config_paths == ['src/main/java/egovframework/fulljsp/config/MyBatisConfig.java'], config_paths
    print('Smoke test passed: common MyBatisConfig path fixed')


if __name__ == '__main__':
    main()
