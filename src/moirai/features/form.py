"""Recent-form features for teams."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class TeamForm:
    team: str
    games: int
    wins: int
    losses: int
    win_rate: float
    current_streak: int
    days_since_last_game: int | None


def build_team_game_log(matches: pd.DataFrame) -> pd.DataFrame:
    """Expand match rows into one row per team per game."""

    records: list[dict[str, object]] = []
    for row in matches.dropna(subset=["team1", "team2", "winner"]).itertuples(index=False):
        for team, opponent in ((row.team1, row.team2), (row.team2, row.team1)):
            records.append(
                {
                    "date": row.date,
                    "team": team,
                    "opponent": opponent,
                    "tournament": getattr(row, "tournament", None),
                    "patch": getattr(row, "patch", None),
                    "won": row.winner == team,
                }
            )

    if not records:
        return pd.DataFrame(columns=["date", "team", "opponent", "tournament", "patch", "won"])

    frame = pd.DataFrame.from_records(records)
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce", utc=True)
    return frame.sort_values(["team", "date"]).reset_index(drop=True)


def team_form(
    matches: pd.DataFrame,
    team: str,
    *,
    window: int = 10,
    as_of: pd.Timestamp | str | None = None,
) -> TeamForm:
    log = build_team_game_log(matches)
    if as_of is not None and not log.empty:
        log = log[log["date"] <= _to_utc_timestamp(as_of)]

    games = log[log["team"] == team].sort_values("date").tail(window)
    if games.empty:
        return TeamForm(team=team, games=0, wins=0, losses=0, win_rate=0.0, current_streak=0, days_since_last_game=None)

    wins = int(games["won"].sum())
    losses = int(len(games) - wins)
    last_date = _to_utc_timestamp(games.iloc[-1]["date"])
    reference_date = _to_utc_timestamp(as_of) if as_of is not None else pd.Timestamp.now(tz="UTC")
    days_since = max(0, int((reference_date - last_date).days))

    return TeamForm(
        team=team,
        games=len(games),
        wins=wins,
        losses=losses,
        win_rate=wins / len(games),
        current_streak=_current_streak(games["won"].tolist()),
        days_since_last_game=days_since,
    )


def form_features(
    matches: pd.DataFrame,
    team_a: str,
    team_b: str,
    *,
    window: int = 10,
    as_of: pd.Timestamp | str | None = None,
) -> dict[str, float | int | None]:
    form_a = team_form(matches, team_a, window=window, as_of=as_of)
    form_b = team_form(matches, team_b, window=window, as_of=as_of)
    return {
        "team_a_recent_games": form_a.games,
        "team_b_recent_games": form_b.games,
        "team_a_recent_win_rate": form_a.win_rate,
        "team_b_recent_win_rate": form_b.win_rate,
        "recent_win_rate_diff": form_a.win_rate - form_b.win_rate,
        "team_a_current_streak": form_a.current_streak,
        "team_b_current_streak": form_b.current_streak,
        "streak_diff": form_a.current_streak - form_b.current_streak,
        "team_a_days_since_last_game": form_a.days_since_last_game,
        "team_b_days_since_last_game": form_b.days_since_last_game,
    }


def _current_streak(results: list[bool]) -> int:
    if not results:
        return 0
    latest = results[-1]
    count = 0
    for result in reversed(results):
        if result != latest:
            break
        count += 1
    return count if latest else -count


def _to_utc_timestamp(value: pd.Timestamp | str) -> pd.Timestamp:
    return pd.to_datetime(value, errors="coerce", utc=True)
