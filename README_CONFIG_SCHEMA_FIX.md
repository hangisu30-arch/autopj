This patch fixes two issues:
1) MyBatisConfig.java path is now forced to the common config package:
   src/main/java/{base_package}/config/MyBatisConfig.java
2) When schema_text is empty, analysis now infers fields/pk from requirements text.
   - explicit columns phrases like "컬럼은 member_id, member_name, email"
   - explicit pk phrases like "member_id 는 기본키"
   - heuristic fallback when no explicit schema/columns are provided

Validated with:
- python -m compileall app tests execution_core
- python tests/smoke_test_analysis.py
- python tests/smoke_test_analysis_upload_false_positive.py
- python tests/smoke_test_analysis_schema_inference.py
- PYTHONPATH=. python tests/smoke_test_backend_engine.py
- PYTHONPATH=. python tests/smoke_test_backend_common_config_path.py
- PYTHONPATH=. python tests/smoke_test_validation_engine.py
