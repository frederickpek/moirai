"""Chronological backtesting and calibration for form-adjusted Elo."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from math import exp, log

import pandas as pd

from moirai.config import EloConfig
from moirai.models.elo import expected_score, update_ratings
from moirai.predict import FormWeights


@dataclass(frozen=True)
class CalibrationResult:
    weights: FormWeights
    rows_used: int
    train_rows: int
    test_rows: int
    baseline_log_loss: float
    adjusted_log_loss: float
    baseline_accuracy: float
    adjusted_accuracy: float
    backtest: pd.DataFrame


def backtest_form_features(
    matches: pd.DataFrame,
    *,
    elo_config: EloConfig | None = None,
    form_window: int = 10,
    min_prior_games: int = 3,
) -> pd.DataFrame:
    """Create leakage-free per-game predictions from historical matches.

    Each row is predicted with Elo ratings and form state available before that game.
    Ratings and form are updated only after recording the prediction.
    """

    cfg = elo_config or EloConfig()
    ratings: dict[str, float] = {}
    team_history: dict[str, list[dict[str, object]]] = defaultdict(list)
    rows: list[dict[str, object]] = []

    ordered = matches.dropna(subset=["team1", "team2", "winner"]).copy()
    ordered["date"] = pd.to_datetime(ordered["date"], errors="coerce", utc=True)
    ordered = ordered.dropna(subset=["date"]).sort_values("date")

    for row in ordered.itertuples(index=False):
        team1 = str(row.team1)
        team2 = str(row.team2)
        winner = str(row.winner)
        if winner not in {team1, team2}:
            continue

        date = pd.Timestamp(row.date)
        rating1 = ratings.setdefault(team1, cfg.initial_rating)
        rating2 = ratings.setdefault(team2, cfg.initial_rating)
        base_probability = expected_score(rating1, rating2, scale=cfg.rating_scale)
        label = 1.0 if winner == team1 else 0.0

        features = _state_features(
            team_history[team1],
            team_history[team2],
            date=date,
            window=form_window,
        )
        if (
            features["team_a_recent_games"] >= min_prior_games
            and features["team_b_recent_games"] >= min_prior_games
        ):
            rows.append(
                {
                    "date": date,
                    "team1": team1,
                    "team2": team2,
                    "winner": winner,
                    "label": label,
                    "base_probability": base_probability,
                    "base_logit": _logit(base_probability),
                    **features,
                }
            )

        score1 = label
        after1, after2 = update_ratings(
            rating1,
            rating2,
            score1,
            k_factor=cfg.k_factor,
            scale=cfg.rating_scale,
        )
        ratings[team1] = after1
        ratings[team2] = after2
        team_history[team1].append({"date": date, "won": winner == team1})
        team_history[team2].append({"date": date, "won": winner == team2})

    return pd.DataFrame.from_records(rows)


def calibrate_form_weights(
    matches: pd.DataFrame,
    *,
    elo_config: EloConfig | None = None,
    form_window: int = 10,
    min_prior_games: int = 3,
    train_fraction: float = 0.7,
    epochs: int = 2500,
    learning_rate: float = 0.03,
    l2: float = 0.01,
) -> CalibrationResult:
    backtest = backtest_form_features(
        matches,
        elo_config=elo_config,
        form_window=form_window,
        min_prior_games=min_prior_games,
    )
    if backtest.empty:
        raise ValueError("Not enough historical games to calibrate form weights")

    split_index = max(1, min(len(backtest) - 1, int(len(backtest) * train_fraction)))
    train = backtest.iloc[:split_index]
    test = backtest.iloc[split_index:]
    if test.empty:
        test = train

    weights = _fit_weights(train, epochs=epochs, learning_rate=learning_rate, l2=l2)
    baseline_probability = test["base_probability"].tolist()
    adjusted_probability = predict_adjusted_probabilities(test, weights).tolist()
    labels = test["label"].tolist()

    return CalibrationResult(
        weights=weights,
        rows_used=len(backtest),
        train_rows=len(train),
        test_rows=len(test),
        baseline_log_loss=_log_loss(labels, baseline_probability),
        adjusted_log_loss=_log_loss(labels, adjusted_probability),
        baseline_accuracy=_accuracy(labels, baseline_probability),
        adjusted_accuracy=_accuracy(labels, adjusted_probability),
        backtest=backtest,
    )


def predict_adjusted_probabilities(backtest: pd.DataFrame, weights: FormWeights) -> pd.Series:
    logits = (
        backtest["base_logit"]
        + weights.recent_form * backtest["recent_win_rate_diff"]
        + weights.streak * backtest["streak_diff"].clip(-5, 5)
        + weights.rest * backtest["rest_diff"].clip(-7, 7)
    )
    return logits.map(_inverse_logit)


def _fit_weights(
    train: pd.DataFrame,
    *,
    epochs: int,
    learning_rate: float,
    l2: float,
) -> FormWeights:
    weights = [0.0, 0.0, 0.0]
    features = [
        train["recent_win_rate_diff"].tolist(),
        train["streak_diff"].clip(-5, 5).tolist(),
        train["rest_diff"].clip(-7, 7).tolist(),
    ]
    base_logits = train["base_logit"].tolist()
    labels = train["label"].tolist()
    n = len(labels)

    for _ in range(epochs):
        gradients = [0.0, 0.0, 0.0]
        for idx, label in enumerate(labels):
            logit = base_logits[idx] + sum(weights[j] * features[j][idx] for j in range(3))
            error = _inverse_logit(logit) - label
            for j in range(3):
                gradients[j] += error * features[j][idx]

        for j in range(3):
            gradients[j] = gradients[j] / n + l2 * weights[j]
            weights[j] -= learning_rate * gradients[j]

    return FormWeights(recent_form=weights[0], streak=weights[1], rest=weights[2])


def _state_features(
    team_a_history: list[dict[str, object]],
    team_b_history: list[dict[str, object]],
    *,
    date: pd.Timestamp,
    window: int,
) -> dict[str, float | int]:
    form_a = _team_state(team_a_history, date=date, window=window)
    form_b = _team_state(team_b_history, date=date, window=window)
    rest_diff = 0.0
    if form_a["days_since_last_game"] is not None and form_b["days_since_last_game"] is not None:
        rest_diff = float(form_a["days_since_last_game"]) - float(form_b["days_since_last_game"])

    return {
        "team_a_recent_games": form_a["games"],
        "team_b_recent_games": form_b["games"],
        "team_a_recent_win_rate": form_a["win_rate"],
        "team_b_recent_win_rate": form_b["win_rate"],
        "recent_win_rate_diff": form_a["win_rate"] - form_b["win_rate"],
        "team_a_current_streak": form_a["current_streak"],
        "team_b_current_streak": form_b["current_streak"],
        "streak_diff": form_a["current_streak"] - form_b["current_streak"],
        "team_a_days_since_last_game": form_a["days_since_last_game"],
        "team_b_days_since_last_game": form_b["days_since_last_game"],
        "rest_diff": rest_diff,
    }


def _team_state(
    history: list[dict[str, object]],
    *,
    date: pd.Timestamp,
    window: int,
) -> dict[str, float | int | None]:
    recent = history[-window:]
    if not recent:
        return {"games": 0, "win_rate": 0.0, "current_streak": 0, "days_since_last_game": None}

    results = [bool(game["won"]) for game in recent]
    last_date = pd.Timestamp(recent[-1]["date"])
    return {
        "games": len(recent),
        "win_rate": sum(results) / len(results),
        "current_streak": _current_streak(results),
        "days_since_last_game": max(0, int((date - last_date).days)),
    }


def _current_streak(results: list[bool]) -> int:
    latest = results[-1] if results else False
    count = 0
    for result in reversed(results):
        if result != latest:
            break
        count += 1
    return count if latest else -count


def _log_loss(labels: list[float], probabilities: list[float]) -> float:
    total = 0.0
    for label, probability in zip(labels, probabilities, strict=True):
        probability = _clip(probability, 1e-6, 1 - 1e-6)
        total += -(label * log(probability) + (1 - label) * log(1 - probability))
    return total / len(labels)


def _accuracy(labels: list[float], probabilities: list[float]) -> float:
    correct = 0
    for label, probability in zip(labels, probabilities, strict=True):
        correct += int((probability >= 0.5) == bool(label))
    return correct / len(labels)


def _logit(probability: float) -> float:
    probability = _clip(probability, 1e-6, 1 - 1e-6)
    return log(probability / (1 - probability))


def _inverse_logit(value: float) -> float:
    return 1 / (1 + exp(-value))


def _clip(value: float, lower: float, upper: float) -> float:
    return min(max(value, lower), upper)
