from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ContextTrimPlan:
    name: str
    drop_sections: tuple[str, ...] = ()


DEFAULT_CONTEXT_TRIM_PLANS: tuple[ContextTrimPlan, ...] = (
    ContextTrimPlan(name="full"),
    ContextTrimPlan(name="trim_skills_catalog", drop_sections=("skills_catalog",)),
    ContextTrimPlan(name="trim_memes", drop_sections=("skills_catalog", "memes")),
    ContextTrimPlan(
        name="trim_long_term_memory",
        drop_sections=("skills_catalog", "memes", "long_term_memory"),
    ),
    ContextTrimPlan(
        name="trim_retrieved_memory",
        drop_sections=(
            "skills_catalog",
            "memes",
            "long_term_memory",
            "retrieved_memory",
        ),
    ),
)
