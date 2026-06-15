from .inventory_builder import build_json_inventory, build_level_inventory
from .schemas import (
    BudgetCandidate,
    BudgetChapter,
    BudgetLine,
    BudgetRow,
    Door,
    Fixture,
    Kitchen,
    LevelInventory,
    Opening,
    ProjectContext,
    QuantityTakeoff,
    QuantityTrace,
    Stair,
    StructuralElement,
    Wall,
    WetArea,
    Window,
    level_inventory_from_dict,
    project_context_from_dict,
)


def bootstrap_pipeline_inputs(*args, **kwargs):
    from .pipeline import bootstrap_pipeline_inputs as _bootstrap_pipeline_inputs

    return _bootstrap_pipeline_inputs(*args, **kwargs)


def build_budget_from_inventory(*args, **kwargs):
    from .pipeline import build_budget_from_inventory as _build_budget_from_inventory

    return _build_budget_from_inventory(*args, **kwargs)


def build_budget_from_sources(*args, **kwargs):
    from .pipeline import build_budget_from_sources as _build_budget_from_sources

    return _build_budget_from_sources(*args, **kwargs)


def build_hybrid_inventory(*args, **kwargs):
    from .pipeline import build_hybrid_inventory as _build_hybrid_inventory

    return _build_hybrid_inventory(*args, **kwargs)


def build_takeoffs_from_sources(*args, **kwargs):
    from .pipeline import build_takeoffs_from_sources as _build_takeoffs_from_sources

    return _build_takeoffs_from_sources(*args, **kwargs)


def build_expanded_takeoffs_from_inventory(*args, **kwargs):
    from .pipeline import build_expanded_takeoffs_from_inventory as _build_expanded_takeoffs_from_inventory

    return _build_expanded_takeoffs_from_inventory(*args, **kwargs)


def build_expanded_takeoffs_from_sources(*args, **kwargs):
    from .pipeline import build_expanded_takeoffs_from_sources as _build_expanded_takeoffs_from_sources

    return _build_expanded_takeoffs_from_sources(*args, **kwargs)


def build_final_budget(*args, **kwargs):
    from .pipeline import build_final_budget as _build_final_budget

    return _build_final_budget(*args, **kwargs)

__all__ = [
    "bootstrap_pipeline_inputs",
    "build_budget_from_inventory",
    "build_budget_from_sources",
    "build_expanded_takeoffs_from_inventory",
    "build_expanded_takeoffs_from_sources",
    "build_final_budget",
    "build_json_inventory",
    "build_level_inventory",
    "build_hybrid_inventory",
    "build_takeoffs_from_sources",
    "BudgetCandidate",
    "BudgetChapter",
    "BudgetLine",
    "BudgetRow",
    "Door",
    "Fixture",
    "Kitchen",
    "LevelInventory",
    "Opening",
    "ProjectContext",
    "QuantityTakeoff",
    "QuantityTrace",
    "Stair",
    "StructuralElement",
    "Wall",
    "WetArea",
    "Window",
    "level_inventory_from_dict",
    "project_context_from_dict",
]
