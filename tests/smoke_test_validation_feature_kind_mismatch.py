from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.validation.global_validator import validate_generation_context
from app.validation.repair_dispatcher import build_repair_plan


FIXTURE_DIR = ROOT / 'tests' / 'fixtures'


def main() -> None:
    analysis = json.loads((FIXTURE_DIR / 'analysis_result_upload_mismatch.json').read_text(encoding='utf-8'))
    backend = json.loads((FIXTURE_DIR / 'backend_plan_upload_mismatch.json').read_text(encoding='utf-8'))
    jsp = json.loads((FIXTURE_DIR / 'jsp_plan_upload_mismatch.json').read_text(encoding='utf-8'))

    report = validate_generation_context(
        analysis_result=analysis,
        backend_plan=backend,
        jsp_plan=jsp,
        frontend_key='jsp',
    )
    repair = build_repair_plan(report)

    out = {'report': report, 'repair': repair}
    Path('tests/smoke_test_validation_feature_kind_mismatch_output.json').write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding='utf-8'
    )

    assert report['ok'] is False, report
    assert any('feature_kind upload conflicts' in err for err in report['errors']), report
    assert repair['repair_mode'] == 'targeted', repair
    assert any(a['action_type'] == 'recompute_feature_kind_and_revalidate' for a in repair['actions']), repair
    print('Smoke test passed: validation catches feature-kind mismatch')


if __name__ == '__main__':
    main()
