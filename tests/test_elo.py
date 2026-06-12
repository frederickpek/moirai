import pandas as pd
import pytest

from moirai.models.elo import expected_score, fit_elo, series_probability


def test_expected_score_is_balanced_for_equal_ratings():
    assert expected_score(1500, 1500) == pytest.approx(0.5)


def test_fit_elo_rewards_winner():
    matches = pd.DataFrame(
        [
            {
                "date": pd.Timestamp("2024-01-01", tz="UTC"),
                "team1": "Dplus KIA",
                "team2": "T1",
                "winner": "Dplus KIA",
            }
        ]
    )

    result = fit_elo(matches)

    assert result.ratings["Dplus KIA"] > 1500
    assert result.ratings["T1"] < 1500
    assert result.history.loc[0, "team1_win_probability"] == pytest.approx(0.5)


def test_series_probability_for_best_of_three():
    assert series_probability(0.5, best_of=3) == pytest.approx(0.5)
    assert series_probability(0.6, best_of=3) == pytest.approx(0.648)
