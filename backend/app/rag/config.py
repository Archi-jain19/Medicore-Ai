"""Transparent, configurable ranking parameters for evidence-aware retrieval.

Final score = w_sim * similarity + w_rel * source_reliability + w_rec * recency + w_clin * clinical_relevance
Every component is in [0, 1] and every value is returned to the client so the ranking can be inspected.

A high similarity score means the passage is *topically close* to the question. It is NOT evidence that
the passage is medically correct or applicable to the user.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass(frozen=True)
class RankingConfig:
    w_similarity: float = 0.55
    w_reliability: float = 0.20
    w_recency: float = 0.10
    w_clinical: float = 0.15
    # source reliability prior by (source, doc_type); heuristic, documented, adjustable
    reliability: dict = field(default_factory=lambda: {
        "WHO": 1.0, "CDC": 1.0, "MedlinePlus": 0.97, "NHS": 0.97, "Mayo Clinic": 0.92,
        "PubMed:guideline": 0.95, "PubMed:systematic_review": 0.90, "PubMed:review": 0.75, "PubMed:article": 0.6,
    })
    default_reliability: float = 0.5
    recency_half_life_years: float = 8.0
    unknown_date_recency: float = 0.5
    # retrieval thresholds
    min_similarity: float = 0.30          # below this a passage is treated as irrelevant
    min_best_similarity: float = 0.38     # if the best passage is below this, evidence is insufficient
    simple_k: int = 4
    complex_k_per_query: int = 6
    complex_final_k: int = 8
    candidate_pool: int = 30
    max_chunks_per_doc: int = 2

    def as_dict(self) -> dict:
        return asdict(self)

    def weights_sum(self) -> float:
        return self.w_similarity + self.w_reliability + self.w_recency + self.w_clinical


DEFAULT_RANKING = RankingConfig()
