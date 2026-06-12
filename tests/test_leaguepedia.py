import pandas as pd

from moirai.sources.leaguepedia import build_team_where, normalize_games, opponents_for_team


def test_normalize_games_extracts_winner_and_loser():
    frame = normalize_games(
        [
            {
                "DateTime_UTC": "2024-01-01 12:00:00",
                "Region": "Korea",
                "Tournament": "LCK",
                "Patch": "14.1",
                "Team1": "Dplus KIA",
                "Team2": "T1",
                "WinTeam": "T1",
                "GameId": "game-1",
                "ScoreboardPage": "LCK/2024/Game 1",
            }
        ]
    )

    assert len(frame) == 1
    assert frame.loc[0, "winner"] == "T1"
    assert frame.loc[0, "loser"] == "Dplus KIA"
    assert pd.notna(frame.loc[0, "date"])


def test_opponents_for_team_returns_unique_opponents():
    matches = pd.DataFrame(
        [
            {"team1": "Dplus KIA", "team2": "T1"},
            {"team1": "Gen.G", "team2": "Dplus KIA"},
            {"team1": "Dplus KIA", "team2": "T1"},
        ]
    )

    assert opponents_for_team(matches, "Dplus KIA") == {"T1", "Gen.G"}


def test_normalize_games_canonicalizes_case_variants_from_observed_names():
    frame = normalize_games(
        [
            {
                "Team1": "Dplus Kia",
                "Team2": "KT Rolster",
                "WinTeam": "Dplus Kia",
                "GameId": "game-2",
                "ScoreboardPage": "LCK/2024/Game 2",
            },
            {
                "Team1": "Dplus KIA",
                "Team2": "T1",
                "WinTeam": "T1",
                "GameId": "game-3",
                "ScoreboardPage": "LCK/2024/Game 3",
            }
        ]
    )

    assert frame.loc[0, "team1"] == "Dplus KIA"
    assert frame.loc[0, "winner"] == "Dplus KIA"


def test_normalize_games_uses_preferred_team_name_when_source_has_one_variant():
    frame = normalize_games(
        [
            {
                "Team1": "Dplus Kia",
                "Team2": "KT Rolster",
                "WinTeam": "Dplus Kia",
                "GameId": "game-4",
                "ScoreboardPage": "LCK/2024/Game 4",
            }
        ],
        preferred_team_names=["Dplus KIA"],
    )

    assert frame.loc[0, "team1"] == "Dplus KIA"
    assert frame.loc[0, "winner"] == "Dplus KIA"


def test_build_team_where_includes_generic_case_variants():
    where = build_team_where("Dplus KIA")

    assert 'SG.Team1="Dplus KIA"' in where
    assert 'SG.Team1="Dplus Kia"' in where
    assert 'SG.Team1="DPLUS KIA"' in where


def test_normalize_games_strips_wrapping_quotes_from_team_names():
    frame = normalize_games(
        [
            {
                "Team1": "'Team WE'",
                "Team2": '"Anyone\'s Legend"',
                "WinTeam": "'Team WE'",
                "GameId": "game-5",
                "ScoreboardPage": "LPL/2026/Game 5",
            }
        ]
    )

    assert frame.loc[0, "team1"] == "Team WE"
    assert frame.loc[0, "team2"] == "Anyone's Legend"
    assert frame.loc[0, "winner"] == "Team WE"
