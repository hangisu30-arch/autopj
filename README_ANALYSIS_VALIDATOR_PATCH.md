This patch updates only analysis and validator-related logic.

Changes:
- Prevent false upload classification from generic phrases like 'JSP 파일', 'Mapper.xml 파일', 'VO 파일'.
- Make CRUD actions win over stray upload/file wording during feature-kind classification.
- Make validation fail when feature_kind conflicts with CRUD pages/artifacts/views.
- Add targeted auto-repair action for feature-kind mismatch.

Validated with:
- python -m compileall app tests execution_core
- python tests/smoke_test_analysis.py
- python tests/smoke_test_analysis_upload_false_positive.py
- PYTHONPATH=. python tests/smoke_test_validation_engine.py
- PYTHONPATH=. python tests/smoke_test_validation_integration.py
- PYTHONPATH=. python tests/smoke_test_validation_feature_kind_mismatch.py
