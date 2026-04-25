from __future__ import annotations

from .egov_spring_jsp import EgovSpringJspProfile
from .egov_spring_react import EgovSpringReactProfile
from .egov_spring_vue import EgovSpringVueProfile
from .egov_spring_nexacro import EgovSpringNexacroProfile


def get_profile(context):
    frontend = (getattr(context, "frontend", "jsp") or "jsp").strip().lower()
    if frontend == "react":
        return EgovSpringReactProfile(context)
    if frontend == "vue":
        return EgovSpringVueProfile(context)
    if frontend == "nexacro":
        return EgovSpringNexacroProfile(context)
    return EgovSpringJspProfile(context)
