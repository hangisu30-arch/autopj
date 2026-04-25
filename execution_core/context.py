from pathlib import Path


class ExecutionContext:
    def __init__(
        self,
        project_root: str,
        backend: str,
        frontend: str,
        base_package: str,
        config: dict,
        overwrite: bool = False,
        db_apply: bool = False,
        dry_run: bool = False,
    ):
        self.project_root = Path(project_root)
        self.backend = backend
        self.frontend = frontend
        self.base_package = base_package
        self.config = config
        self.overwrite = overwrite
        self.db_apply = db_apply
        self.dry_run = dry_run

        if not self.project_root.exists():
            raise ValueError(f"project_root does not exist: {project_root}")