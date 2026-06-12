import pandas as pd

from moirai.models.backtest import calibrate_form_weights
from moirai.predict import HEURISTIC_FORM_WEIGHTS, adjust_probability_with_form, predict_matchup


def test_predict_matchup_handles_mixed_timezone_dates():
    matches = pd.DataFrame(
        [
            {
                "date": pd.Timestamp("2024-01-01"),
                "team1": "Dplus KIA",
                "team2": "KT Rolster",
                "winner": "Dplus KIA",
            },
            {
                "date": pd.Timestamp("2024-01-02", tz="UTC"),
                "team1": "KT Rolster",
                "team2": "Dplus KIA",
                "winner": "KT Rolster",
            },
        ]
    )

    prediction = predict_matchup(matches, "Dplus KIA", "KT Rolster", best_of=5)

    assert 0 <= prediction.team_a_series_probability <= 1
    assert 0 <= prediction.team_a_adjusted_series_probability <= 1
    assert prediction.features["team_a_days_since_last_game"] is not None


def test_adjust_probability_with_form_moves_toward_better_recent_form():
    adjusted, adjustments = adjust_probability_with_form(
        0.5,
        {
            "recent_win_rate_diff": 0.3,
            "streak_diff": 4,
            "team_a_days_since_last_game": 7,
            "team_b_days_since_last_game": 0,
        },
        weights=HEURISTIC_FORM_WEIGHTS,
    )

    assert adjusted > 0.5
    assert adjustments["recent_form_logit"] > 0
    assert adjustments["streak_logit"] > 0
    assert adjustments["rest_logit"] > 0


def test_calibrate_form_weights_runs_chronological_backtest():
    matches = pd.DataFrame(
        [
            {
                "date": pd.Timestamp(f"2024-01-{day:02d}", tz="UTC"),
                "team1": "Team A" if day % 2 else "Team B",
                "team2": "Team B" if day % 2 else "Team A",
                "winner": "Team A",
            }
            for day in range(1, 13)
        ]
    )

    result = calibrate_form_weights(
        matches,
        min_prior_games=1,
        epochs=10,
        learning_rate=0.01,
    )

    assert result.rows_used > 0
    assert result.train_rows > 0
    assert result.test_rows > 0
