from __future__ import annotations

import json
from pathlib import Path

from .analysis_context import AnalysisContext
from .analysis_result import AnalysisResult, ProjectAnalysis
from .artifact_planner import ArtifactPlanner
from .domain_classifier import DomainClassifier
from .ir_builder import IRBuilder
from .naming_rules import build_domain_naming
from .requirement_parser import RequirementParser
from .schema_parser import SchemaParser


class AnalysisEngine:
    def __init__(self) -> None:
        self.requirement_parser = RequirementParser()
        self.schema_parser = SchemaParser()
        self.domain_classifier = DomainClassifier()
        self.ir_builder = IRBuilder()
        self.artifact_planner = ArtifactPlanner()

    def run(self, ctx: AnalysisContext) -> AnalysisResult:
        hints = self.requirement_parser.parse(ctx.requirements_text)
        warnings = []

        tables = self.schema_parser.parse(ctx.schema_text)
        if not tables:
            tables = self.schema_parser.infer_from_requirements(
                ctx.requirements_text,
                hints.domain_candidates,
                auth_intent=hints.auth_intent and not any(action in hints.actions for action in {'list', 'detail', 'create', 'update', 'delete'}),
            )
            if tables:
                warnings.append('schema_text missing or empty: inferred fields/pk from requirements heuristics')

        domains = self.domain_classifier.classify(hints, tables)

        for domain in domains:
            domain.naming = build_domain_naming(
                base_package=ctx.base_package,
                domain_name=domain.name,
                frontend_mode=ctx.frontend_mode,
            )
            self.ir_builder.apply(domain, ctx.frontend_mode, ctx.requirements_text)
            self.artifact_planner.apply(domain, ctx.frontend_mode)

        return AnalysisResult(
            project=ProjectAnalysis(
                project_root=ctx.project_root,
                project_name=ctx.project_name,
                base_package=ctx.base_package,
                backend_mode=ctx.backend_mode,
                frontend_mode=ctx.frontend_mode,
                database_type=ctx.database_type,
            ),
            requirements_text=ctx.requirements_text,
            schema_text=ctx.schema_text,
            domains=domains,
            warnings=warnings,
            generation_policy={
                'modifyExistingOnly': True,
                'relatedFilesOnly': True,
                'preserveCommonAssets': True,
                'mergeCommonCss': True,
            },
            ir_version='1.0',
        )

    def dump_json(self, result: AnalysisResult, out_path: str) -> str:
        path = Path(out_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(result.to_dict(), ensure_ascii=False, indent=2), encoding='utf-8')
        return str(path)
