"""Transparent Elo ratings for professional League of Legends teams."""

from __future__ import annotations

from dataclasses import dataclass
from math import comb

import pandas as pd

from moirai.config import EloConfig


@dataclass(frozen=True)
class EloResult:
    ratings: dict[str, float]
    history: pd.DataFrame


def expected_score(rating_a: float, rating_b: float, *, scale: float = 400.0) -> float:
    return 1.0 / (1.0 + 10.0 ** ((rating_b - rating_a) / scale))


def update_ratings(
    rating_a: float,
    rating_b: float,
    score_a: float,
    *,
    k_factor: float = 32.0,
    scale: float = 400.0,
) -> tuple[float, float]:
    expected_a = expected_score(rating_a, rating_b, scale=scale)
    delta = k_factor * (score_a - expected_a)
    return rating_a + delta, rating_b - delta


def fit_elo(matches: pd.DataFrame, config: EloConfig | None = None) -> EloResult:
    """Fit Elo ratings from one row per completed game."""

    cfg = config or EloConfig()
    ratings: dict[str, float] = {}
    history: list[dict[str, object]] = []

    if matches.empty:
        return EloResult(ratings=ratings, history=pd.DataFrame())

    ordered = matches.dropna(subset=["team1", "team2", "winner"]).copy()
    ordered["date"] = pd.to_datetime(ordered["date"], errors="coerce", utc=True)
    ordered = ordered.sort_values("date")
    for row in ordered.itertuples(index=False):
        team1 = str(row.team1)
        team2 = str(row.team2)
        winner = str(row.winner)

        before_1 = ratings.setdefault(team1, cfg.initial_rating)
        before_2 = ratings.setdefault(team2, cfg.initial_rating)
        score_1 = 1.0 if winner == team1 else 0.0
        probability_1 = expected_score(before_1, before_2, scale=cfg.rating_scale)
        after_1, after_2 = update_ratings(
            before_1,
            before_2,
            score_1,
            k_factor=cfg.k_factor,
            scale=cfg.rating_scale,
        )
        ratings[team1] = after_1
        ratings[team2] = after_2

        history.append(
            {
                "date": row.date,
                "team1": team1,
                "team2": team2,
                "winner": winner,
                "team1_rating_before": before_1,
                "team2_rating_before": before_2,
                "team1_win_probability": probability_1,
                "team1_rating_after": after_1,
                "team2_rating_after": after_2,
            }
        )

    return EloResult(ratings=ratings, history=pd.DataFrame.from_records(history))


def game_probability_from_ratings(
    team_a: str,
    team_b: str,
    ratings: dict[str, float],
    *,
    default_rating: float = 1500.0,
    scale: float = 400.0,
) -> float:
    return expected_score(
        ratings.get(team_a, default_rating),
        ratings.get(team_b, default_rating),
        scale=scale,
    )


def series_probability(game_probability: float, best_of: int = 1) -> float:
    """Convert a per-game win probability to a Bo1/Bo3/Bo5 series probability."""

    if best_of < 1 or best_of % 2 == 0:
        raise ValueError("best_of must be a positive odd integer such as 1, 3, or 5")
    if not 0.0 <= game_probability <= 1.0:
        raise ValueError("game_probability must be between 0 and 1")

    wins_needed = best_of // 2 + 1
    probability = 0.0
    for wins in range(wins_needed, best_of + 1):
        probability += comb(best_of, wins) * game_probability**wins * (1 - game_probability) ** (
            best_of - wins
        )
    return probability
