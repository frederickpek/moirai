"""Leaguepedia/Fandom Cargo access for historical League of Legends matches."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from time import sleep
from typing import Any

import httpx
import pandas as pd

from moirai.config import LEAGUEPEDIA_API_URL

DEFAULT_FIELDS = [
    "SG.DateTime_UTC=DateTime_UTC",
    "IT.Region=Region",
    "IT.StandardName=Tournament",
    "SG.OverviewPage=OverviewPage",
    "SG.Patch=Patch",
    "SG.Team1=Team1",
    "SG.Team2=Team2",
    "SG.WinTeam=WinTeam",
    "SG.Gamelength=Gamelength",
    "SG.Team1Kills=Team1Kills",
    "SG.Team2Kills=Team2Kills",
    "SG.Team1Gold=Team1Gold",
    "SG.Team2Gold=Team2Gold",
    "SG.MatchHistory=MatchHistory",
    "SG.VOD=VOD",
    "SG.GameId=GameId",
    "SG._pageName=ScoreboardPage",
]

class LeaguepediaClient:
    """Small Cargo API client scoped to the fields needed by the notebooks."""

    def __init__(
        self,
        api_url: str = LEAGUEPEDIA_API_URL,
        timeout: float = 30.0,
        user_agent: str = "moirai-lol-analysis/0.1",
    ) -> None:
        self.api_url = api_url
        self._client = httpx.Client(
            timeout=timeout,
            headers={"User-Agent": user_agent},
            follow_redirects=True,
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "LeaguepediaClient":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def cargo_query(
        self,
        *,
        tables: Iterable[str],
        fields: Iterable[str],
        where: str | None = None,
        join_on: Iterable[str] | None = None,
        order_by: str | None = None,
        limit: int = 500,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {
            "action": "cargoquery",
            "format": "json",
            "tables": ",".join(tables),
            "fields": ",".join(fields),
            "limit": limit,
            "offset": offset,
        }
        if where:
            params["where"] = where
        if join_on:
            params["join_on"] = ",".join(join_on)
        if order_by:
            params["order_by"] = order_by

        response = self._client.get(self.api_url, params=params)
        response.raise_for_status()
        payload = response.json()
        return [item["title"] for item in payload.get("cargoquery", [])]

    def fetch_team_games(
        self,
        team: str,
        *,
        start_date: str | None = None,
        end_date: str | None = None,
        limit: int = 500,
    ) -> list[dict[str, Any]]:
        """Fetch all known games for one team, paginating until Cargo has no more rows."""

        where = build_team_where(team, start_date=start_date, end_date=end_date)
        rows = self._fetch_games_where(where, limit=limit)
        if rows:
            return rows

        fallback_rows = self.search_scoreboard_games(
            team,
            start_date=start_date,
            end_date=end_date,
            limit=limit,
        )
        team_terms = _search_terms(team)
        return [
            row
            for row in fallback_rows
            if _matches_terms(canonical_team_name(row.get("Team1")) or "", team_terms)
            or _matches_terms(canonical_team_name(row.get("Team2")) or "", team_terms)
        ]

    def _fetch_games_where(self, where: str, *, limit: int) -> list[dict[str, Any]]:
        return self._fetch_games_where_once(where, limit=limit) or self._fetch_games_where_once(
            where,
            limit=limit,
            retry_delay_seconds=1.0,
        )

    def _fetch_games_where_once(
        self,
        where: str,
        *,
        limit: int,
        retry_delay_seconds: float = 0.0,
    ) -> list[dict[str, Any]]:
        if retry_delay_seconds:
            sleep(retry_delay_seconds)

        rows: list[dict[str, Any]] = []
        offset = 0

        while True:
            batch = self.cargo_query(
                tables=["ScoreboardGames=SG", "Tournaments=IT"],
                fields=DEFAULT_FIELDS,
                where=where,
                join_on=["SG.OverviewPage=IT.OverviewPage"],
                order_by="SG.DateTime_UTC DESC",
                limit=limit,
                offset=offset,
            )
            rows.extend(batch)
            if len(batch) < limit:
                break
            offset += limit

        return rows

    def find_team_names(
        self,
        query: str,
        *,
        start_date: str | None = None,
        end_date: str | None = None,
        limit: int = 500,
    ) -> pd.DataFrame:
        """Find scoreboard team names that match a human-entered query."""

        rows = self.search_scoreboard_games(
            query,
            start_date=start_date,
            end_date=end_date,
            limit=limit,
        )
        records: dict[str, dict[str, Any]] = {}
        query_terms = _search_terms(query)
        for row in rows:
            for field in ("Team1", "Team2"):
                team = canonical_team_name(row.get(field))
                if not team or not _matches_terms(team, query_terms):
                    continue
                record = records.setdefault(
                    team,
                    {"team": team, "games_seen": 0, "latest_game": pd.NaT},
                )
                record["games_seen"] += 1
                date = _parse_datetime(row.get("DateTime UTC") or row.get("DateTime_UTC"))
                if pd.isna(record["latest_game"]) or date > record["latest_game"]:
                    record["latest_game"] = date

        frame = pd.DataFrame.from_records(list(records.values()))
        if frame.empty:
            return pd.DataFrame(columns=["team", "games_seen", "latest_game"])
        return frame.sort_values(["games_seen", "latest_game"], ascending=False).reset_index(drop=True)

    def search_scoreboard_games(
        self,
        query: str,
        *,
        start_date: str | None = None,
        end_date: str | None = None,
        limit: int = 500,
    ) -> list[dict[str, Any]]:
        rows_by_key: dict[tuple[str | None, str | None], dict[str, Any]] = {}
        for term in _search_terms(query):
            where = build_team_like_where(term, start_date=start_date, end_date=end_date)
            for row in self._fetch_games_where(where, limit=limit):
                key = (_clean(row.get("GameId")), _clean(row.get("ScoreboardPage")))
                rows_by_key[key] = row
        return list(rows_by_key.values())

    def fetch_team_games_frame(
        self,
        team: str,
        *,
        start_date: str | None = None,
        end_date: str | None = None,
        limit: int = 500,
    ) -> pd.DataFrame:
        rows = self.fetch_team_games(
            team,
            start_date=start_date,
            end_date=end_date,
            limit=limit,
        )
        return normalize_games(rows, preferred_team_names=[team])


def build_team_where(
    team: str,
    *,
    start_date: str | None = None,
    end_date: str | None = None,
) -> str:
    team_clauses = []
    for query_name in team_query_names(team):
        escaped_team = _cargo_quote(query_name)
        team_clauses.append(f'SG.Team1="{escaped_team}"')
        team_clauses.append(f'SG.Team2="{escaped_team}"')

    clauses = [f"({' OR '.join(team_clauses)})"]
    if start_date:
        clauses.append(f'SG.DateTime_UTC >= "{_cargo_quote(start_date)}"')
    if end_date:
        clauses.append(f'SG.DateTime_UTC <= "{_cargo_quote(end_date)}"')
    return " AND ".join(clauses)


def build_team_like_where(
    team: str,
    *,
    start_date: str | None = None,
    end_date: str | None = None,
) -> str:
    team_clauses = []
    for term in _search_terms(team):
        escaped_term = _cargo_quote(term)
        team_clauses.append(f'SG.Team1 LIKE "%{escaped_term}%"')
        team_clauses.append(f'SG.Team2 LIKE "%{escaped_term}%"')

    clauses = [f"({' OR '.join(team_clauses)})"]
    if start_date:
        clauses.append(f'SG.DateTime_UTC >= "{_cargo_quote(start_date)}"')
    if end_date:
        clauses.append(f'SG.DateTime_UTC <= "{_cargo_quote(end_date)}"')
    return " AND ".join(clauses)


def normalize_games(
    rows: Iterable[dict[str, Any]],
    *,
    preferred_team_names: Iterable[str] = (),
) -> pd.DataFrame:
    """Normalize Cargo rows into a stable tabular schema."""

    row_list = list(rows)
    team_name_map = build_team_name_map(row_list, preferred_team_names=preferred_team_names)
    records = [normalize_game(row, team_name_map=team_name_map) for row in row_list]
    frame = pd.DataFrame.from_records(records)
    if frame.empty:
        return pd.DataFrame(columns=list(_empty_game_record().keys()))

    frame = frame.drop_duplicates(subset=["game_id", "scoreboard_page"], keep="first")
    frame = canonicalize_match_teams(frame)
    frame = frame.sort_values("date", ascending=True, na_position="last").reset_index(drop=True)
    return frame


def normalize_game(
    row: dict[str, Any],
    *,
    team_name_map: dict[str, str] | None = None,
) -> dict[str, Any]:
    team1 = canonical_team_name(row.get("Team1"), team_name_map=team_name_map)
    team2 = canonical_team_name(row.get("Team2"), team_name_map=team_name_map)
    winner = canonical_team_name(row.get("WinTeam"), team_name_map=team_name_map)

    return {
        "date": _parse_datetime(row.get("DateTime UTC") or row.get("DateTime_UTC")),
        "region": _clean(row.get("Region")),
        "tournament": _clean(row.get("Tournament")),
        "overview_page": _clean(row.get("OverviewPage")),
        "patch": _clean(row.get("Patch")),
        "team1": team1,
        "team2": team2,
        "winner": winner,
        "loser": _loser(team1, team2, winner),
        "game_length": _clean(row.get("Gamelength")),
        "team1_kills": _to_number(row.get("Team1Kills")),
        "team2_kills": _to_number(row.get("Team2Kills")),
        "team1_gold": _to_number(row.get("Team1Gold")),
        "team2_gold": _to_number(row.get("Team2Gold")),
        "match_history_url": _clean(row.get("MatchHistory")),
        "vod_url": _clean(row.get("VOD")),
        "game_id": _clean(row.get("GameId")),
        "scoreboard_page": _clean(row.get("ScoreboardPage")),
    }


def opponents_for_team(matches: pd.DataFrame, team: str) -> set[str]:
    if matches.empty:
        return set()

    matches = canonicalize_match_teams(matches)
    team_name_map = build_team_name_map(
        {"Team1": row.get("team1"), "Team2": row.get("team2"), "WinTeam": None}
        for row in matches.to_dict("records")
    )
    team = canonical_team_name(team, team_name_map=team_name_map) or team
    team_games = matches[(matches["team1"] == team) | (matches["team2"] == team)]
    opponents = set(team_games.loc[team_games["team1"] == team, "team2"])
    opponents.update(team_games.loc[team_games["team2"] == team, "team1"])
    return {opponent for opponent in opponents if isinstance(opponent, str) and opponent}


def canonical_team_name(
    value: Any,
    *,
    team_name_map: dict[str, str] | None = None,
) -> str | None:
    """Normalize whitespace and apply observed casing canonicalization when available."""

    cleaned = _clean(value)
    if cleaned is None:
        return None

    if team_name_map:
        canonical = team_name_map.get(team_name_key(cleaned))
        if canonical:
            return canonical
    return cleaned


def team_query_names(team: str) -> tuple[str, ...]:
    canonical = canonical_team_name(team) or team
    variants = (canonical, canonical.title(), canonical.upper(), team)
    return tuple(dict.fromkeys(variants))


def build_team_name_map(
    rows: Iterable[dict[str, Any]],
    *,
    preferred_team_names: Iterable[str] = (),
) -> dict[str, str]:
    variants_by_key: dict[str, list[str]] = {}
    for row in rows:
        for field in ("Team1", "Team2", "WinTeam"):
            cleaned = _clean(row.get(field))
            if cleaned:
                variants_by_key.setdefault(team_name_key(cleaned), []).append(cleaned)

    team_name_map = {
        key: max(variants, key=_team_name_preference_score)
        for key, variants in variants_by_key.items()
    }
    for preferred_name in preferred_team_names:
        cleaned = _clean(preferred_name)
        if cleaned:
            team_name_map[team_name_key(cleaned)] = cleaned
    return team_name_map


def canonicalize_match_teams(matches: pd.DataFrame) -> pd.DataFrame:
    """Merge casing-only variants across an already-normalized match frame."""

    if matches.empty:
        return matches

    team_name_map = build_team_name_map(
        {
            "Team1": row.get("team1"),
            "Team2": row.get("team2"),
            "WinTeam": row.get("winner"),
        }
        for row in matches.to_dict("records")
    )
    frame = matches.copy()
    for column in ("team1", "team2", "winner", "loser"):
        if column not in frame.columns:
            continue
        frame[column] = frame[column].map(
            lambda value: canonical_team_name(value, team_name_map=team_name_map)
        )
    return frame


def team_name_key(value: str) -> str:
    return " ".join(value.split()).casefold()


def _team_name_preference_score(value: str) -> tuple[int, int, int, str]:
    tokens = value.replace(".", " ").replace("-", " ").split()
    acronym_tokens = sum(1 for token in tokens if len(token) > 1 and token.isupper())
    uppercase_chars = sum(1 for char in value if char.isupper())
    lowercase_chars = sum(1 for char in value if char.islower())
    return (value.count(" "), acronym_tokens, uppercase_chars, lowercase_chars, value)


def _empty_game_record() -> dict[str, Any]:
    return {
        "date": pd.NaT,
        "region": None,
        "tournament": None,
        "overview_page": None,
        "patch": None,
        "team1": None,
        "team2": None,
        "winner": None,
        "loser": None,
        "game_length": None,
        "team1_kills": None,
        "team2_kills": None,
        "team1_gold": None,
        "team2_gold": None,
        "match_history_url": None,
        "vod_url": None,
        "game_id": None,
        "scoreboard_page": None,
    }


def _cargo_quote(value: str) -> str:
    return value.replace('"', r"\"")


def _clean(value: Any) -> str | None:
    if value is None:
        return None
    if pd.isna(value):
        return None
    text = str(value).strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in {"'", '"'}:
        text = text[1:-1].strip()
    return text or None


def _search_terms(value: str) -> tuple[str, ...]:
    terms = [term for term in value.replace("_", " ").split() if len(term) > 1]
    return tuple(dict.fromkeys(terms or [value]))


def _matches_terms(value: str, terms: tuple[str, ...]) -> bool:
    key = team_name_key(value)
    return all(term.casefold() in key for term in terms)


def _loser(team1: str | None, team2: str | None, winner: str | None) -> str | None:
    if winner == team1:
        return team2
    if winner == team2:
        return team1
    return None


def _parse_datetime(value: Any) -> pd.Timestamp:
    if not value:
        return pd.NaT
    try:
        return pd.Timestamp(datetime.fromisoformat(str(value).replace("Z", "+00:00")))
    except ValueError:
        return pd.to_datetime(value, errors="coerce", utc=True)


def _to_number(value: Any) -> float | None:
    if value in (None, ""):
        return None
    text = str(value).replace(",", "")
    try:
        return float(text)
    except ValueError:
        return None
