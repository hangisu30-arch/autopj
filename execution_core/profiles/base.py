from pathlib import Path


class BaseProfile:

    def __init__(self, context):
        self.context = context

    def enforce_structure(self, plan: dict) -> dict:
        return plan

    def resolve_path(self, logical_path: str) -> Path:
        raise NotImplementedError

    def build_prompt(self, task: dict) -> str:
        raise NotImplementedError

    def post_process(self, path: Path, content: str) -> str:
        return content