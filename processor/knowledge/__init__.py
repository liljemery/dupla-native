"""
Knowledge layer for continuous learning infrastructure.
"""

from .bc3_embeddings import (
    EmbeddingIndex,
    build_bc3_embeddings,
    build_query_from_takeoff,
    load_or_build_embeddings,
    search_bc3,
)
from .feedback_store import Correction, FeedbackStore, apply_corrections_to_rules
from .methodology_generator import generate_methodology_context
from .pres_expansion import inject_pres_reference_candidates, synthetic_takeoffs_from_pres
from .training_data import (
    LevelTemplate,
    TrainingPair,
    extract_level_templates,
    extract_training_pairs,
    generate_few_shot_examples,
)

__all__ = [
    "Correction",
    "EmbeddingIndex",
    "FeedbackStore",
    "LevelTemplate",
    "TrainingPair",
    "apply_corrections_to_rules",
    "build_bc3_embeddings",
    "build_query_from_takeoff",
    "extract_level_templates",
    "extract_training_pairs",
    "generate_few_shot_examples",
    "generate_methodology_context",
    "inject_pres_reference_candidates",
    "load_or_build_embeddings",
    "search_bc3",
    "synthetic_takeoffs_from_pres",
]
