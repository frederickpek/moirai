"""Matchup probability helpers."""

from __future__ import annotations

from dataclasses import dataclass
from math import exp, log

import pandas as pd

from moirai.config import EloConfig
from moirai.features.form import form_features
from moirai.models.elo import fit_elo, game_probability_from_ratings, series_probability


@dataclass(frozen=True)
class FormWeights:
    recent_form: float = 0.0
    streak: float = 0.0
    rest: float = 0.0


NO_FORM_WEIGHTS = FormWeights()
HEURISTIC_FORM_WEIGHTS = FormWeights(recent_form=0.35, streak=0.03, rest=0.01)
DEFAULT_FORM_WEIGHTS = NO_FORM_WEIGHTS


@dataclass(frozen=True)
class MatchupPrediction:
    team_a: str
    team_b: str
    best_of: int
    team_a_rating: float
    team_b_rating: float
    team_a_game_probability: float
    team_a_series_probability: float
    team_b_series_probability: float
    team_a_adjusted_game_probability: float
    team_a_adjusted_series_probability: float
    team_b_adjusted_series_probability: float
    features: dict[str, float | int | None]
    feature_adjustments: dict[str, float]


def predict_matchup(
    matches: pd.DataFrame,
    team_a: str,
    team_b: str,
    *,
    best_of: int = 1,
    elo_config: EloConfig | None = None,
    form_window: int = 10,
    form_weights: FormWeights = DEFAULT_FORM_WEIGHTS,
) -> MatchupPrediction:
    cfg = elo_config or EloConfig()
    result = fit_elo(matches, cfg)
    game_probability = game_probability_from_ratings(
        team_a,
        team_b,
        result.ratings,
        default_rating=cfg.initial_rating,
        scale=cfg.rating_scale,
    )
    team_a_series_probability = series_probability(game_probability, best_of=best_of)
    features = form_features(matches, team_a, team_b, window=form_window)
    adjusted_game_probability, adjustments = adjust_probability_with_form(
        game_probability,
        features,
        weights=form_weights,
    )
    adjusted_series_probability = series_probability(adjusted_game_probability, best_of=best_of)

    return MatchupPrediction(
        team_a=team_a,
        team_b=team_b,
        best_of=best_of,
        team_a_rating=result.ratings.get(team_a, cfg.initial_rating),
        team_b_rating=result.ratings.get(team_b, cfg.initial_rating),
        team_a_game_probability=game_probability,
        team_a_series_probability=team_a_series_probability,
        team_b_series_probability=1.0 - team_a_series_probability,
        team_a_adjusted_game_probability=adjusted_game_probability,
        team_a_adjusted_series_probability=adjusted_series_probability,
        team_b_adjusted_series_probability=1.0 - adjusted_series_probability,
        features=features,
        feature_adjustments=adjustments,
    )


def adjust_probability_with_form(
    base_probability: float,
    features: dict[str, float | int | None],
    *,
    weights: FormWeights = DEFAULT_FORM_WEIGHTS,
) -> tuple[float, dict[str, float]]:
    """Apply a small, transparent form adjustment to an Elo baseline.

    This is a heuristic until enough data exists to fit calibrated weights. The adjustment
    happens in log-odds space so it nudges probabilities without overwhelming Elo.
    """

    recent_win_rate_diff = float(features.get("recent_win_rate_diff") or 0.0)
    streak_diff = _clip(float(features.get("streak_diff") or 0.0), -5.0, 5.0)
    rest_diff = _rest_diff(features)

    adjustments = {
        "recent_form_logit": weights.recent_form * recent_win_rate_diff,
        "streak_logit": weights.streak * streak_diff,
        "rest_logit": weights.rest * rest_diff,
    }
    adjusted_logit = _logit(base_probability) + sum(adjustments.values())
    return _inverse_logit(adjusted_logit), adjustments


def _rest_diff(features: dict[str, float | int | None]) -> float:
    team_a_days = features.get("team_a_days_since_last_game")
    team_b_days = features.get("team_b_days_since_last_game")
    if team_a_days is None or team_b_days is None:
        return 0.0

    # Positive means team A has had more days off than team B. Cap noisy schedule effects.
    return _clip(float(team_a_days) - float(team_b_days), -7.0, 7.0)


def _logit(probability: float) -> float:
    probability = _clip(probability, 1e-6, 1 - 1e-6)
    return log(probability / (1 - probability))


def _inverse_logit(value: float) -> float:
    return 1 / (1 + exp(-value))


def _clip(value: float, lower: float, upper: float) -> float:
    return min(max(value, lower), upper)
