from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from qualstocks.domain import SourceEvent, SourceTier
from qualstocks.research import SourceRanking


@dataclass(frozen=True)
class SourceWeight:
    source_id: str
    source_name: str
    observation_count: int
    speed_score: float
    uniqueness_score: float
    directionality_score: float
    outcome_score: float
    ranking_score: float
    confidence_multiplier: float
    defaulted: bool = False

    def effective_confidence(self, confidence: float) -> float:
        return _clamp(confidence * self.confidence_multiplier)

    def as_dict(self) -> dict[str, object]:
        return {
            "source_id": self.source_id,
            "source_name": self.source_name,
            "observation_count": self.observation_count,
            "speed_score": self.speed_score,
            "uniqueness_score": self.uniqueness_score,
            "directionality_score": self.directionality_score,
            "outcome_score": self.outcome_score,
            "ranking_score": self.ranking_score,
            "confidence_multiplier": self.confidence_multiplier,
            "defaulted": self.defaulted,
        }


@dataclass(frozen=True)
class SourceWeightBook:
    weights_by_source_id: Mapping[str, SourceWeight]
    default_trigger_multiplier: float = 0.9
    default_confirmation_multiplier: float = 0.8
    default_other_multiplier: float = 0.65

    @classmethod
    def from_rankings(
        cls,
        rankings: tuple[SourceRanking, ...],
        *,
        minimum_observations: int = 1,
    ) -> "SourceWeightBook":
        weights: dict[str, SourceWeight] = {}
        for ranking in rankings:
            if ranking.observation_count < minimum_observations:
                continue
            weights[ranking.source_id] = source_weight_from_ranking(ranking)
        return cls(weights_by_source_id=weights)

    def weight_for_event(self, event: SourceEvent) -> SourceWeight:
        if event.source_id and event.source_id in self.weights_by_source_id:
            return self.weights_by_source_id[event.source_id]
        return self._default_for_event(event)

    def _default_for_event(self, event: SourceEvent) -> SourceWeight:
        if event.source_tier == SourceTier.TRIGGER:
            multiplier = self.default_trigger_multiplier
        elif event.source_tier == SourceTier.CONFIRMATION:
            multiplier = self.default_confirmation_multiplier
        else:
            multiplier = self.default_other_multiplier
        return SourceWeight(
            source_id=event.source_id or event.source,
            source_name=event.source,
            observation_count=0,
            speed_score=0.5,
            uniqueness_score=0.0,
            directionality_score=0.5,
            outcome_score=0.5,
            ranking_score=0.0,
            confidence_multiplier=multiplier,
            defaulted=True,
        )


def source_weight_from_ranking(ranking: SourceRanking) -> SourceWeight:
    speed_score = _speed_score(ranking.avg_lead_lag_seconds)
    uniqueness_score = _clamp(ranking.uniqueness_score)
    directionality_score = _clamp(ranking.hit_rate)
    outcome_score = _outcome_score(ranking.avg_post_cost_directional_return_pct)
    weighted_score = (
        speed_score * 0.25
        + uniqueness_score * 0.25
        + directionality_score * 0.25
        + outcome_score * 0.25
    )
    confidence_multiplier = 0.75 + (weighted_score * 0.5)
    return SourceWeight(
        source_id=ranking.source_id,
        source_name=ranking.source_name,
        observation_count=ranking.observation_count,
        speed_score=speed_score,
        uniqueness_score=uniqueness_score,
        directionality_score=directionality_score,
        outcome_score=outcome_score,
        ranking_score=ranking.ranking_score,
        confidence_multiplier=confidence_multiplier,
    )


def _speed_score(avg_lead_lag_seconds: float) -> float:
    return _clamp(1 / (1 + max(avg_lead_lag_seconds, 0) / 300))


def _outcome_score(avg_post_cost_directional_return_pct: float) -> float:
    return _clamp(0.5 + avg_post_cost_directional_return_pct / 10)


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))
