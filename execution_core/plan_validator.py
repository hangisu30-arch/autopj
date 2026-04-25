class PlanValidationError(Exception):
    pass


def validate_plan(plan: dict):
    if "tasks" not in plan:
        raise PlanValidationError("Plan must contain tasks")

    if not isinstance(plan["tasks"], list):
        raise PlanValidationError("tasks must be list")

    for task in plan["tasks"]:
        if "path" not in task:
            raise PlanValidationError("task missing path")
        if "purpose" not in task:
            raise PlanValidationError("task missing purpose")