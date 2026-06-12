"""LoL Esports API access for upcoming schedules and tournament context."""

from __future__ import annotations

from typing import Any

import httpx
import pandas as pd

from moirai.config import LOLESPORTS_API_KEY, LOLESPORTS_API_URL


class LolesportsClient:
    """Client for Riot's public, unofficial LoL Esports persisted endpoints."""

    def __init__(
        self,
        base_url: str = LOLESPORTS_API_URL,
        api_key: str = LOLESPORTS_API_KEY,
        hl: str = "en-US",
        timeout: float = 30.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.hl = hl
        self._client = httpx.Client(
            timeout=timeout,
            headers={
                "x-api-key": api_key,
                "User-Agent": "moirai-lol-analysis/0.1",
            },
            follow_redirects=True,
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "LolesportsClient":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def get_leagues(self) -> dict[str, Any]:
        return self._get("getLeagues")

    def get_tournaments_for_league(self, league_id: str) -> dict[str, Any]:
        return self._get("getTournamentsForLeague", leagueId=league_id)

    def get_schedule(self, *, league_id: str | None = None, page_token: str | None = None) -> dict[str, Any]:
        params = {}
        if league_id:
            params["leagueId"] = league_id
        if page_token:
            params["pageToken"] = page_token
        return self._get("getSchedule", **params)

    def upcoming_events(self, *, league_id: str | None = None) -> pd.DataFrame:
        payload = self.get_schedule(league_id=league_id)
        events = payload.get("data", {}).get("schedule", {}).get("events", [])
        records = [normalize_event(event) for event in events if event.get("state") != "completed"]
        return pd.DataFrame.from_records(records)

    def _get(self, endpoint: str, **params: str) -> dict[str, Any]:
        response = self._client.get(
            f"{self.base_url}/{endpoint}",
            params={"hl": self.hl, **params},
        )
        response.raise_for_status()
        return response.json()


def normalize_event(event: dict[str, Any]) -> dict[str, Any]:
    match = event.get("match") or {}
    teams = match.get("teams") or []
    team_a = teams[0] if len(teams) > 0 else {}
    team_b = teams[1] if len(teams) > 1 else {}
    strategy = match.get("strategy") or {}
    league = event.get("league") or {}

    return {
        "event_id": event.get("id"),
        "start_time": pd.to_datetime(event.get("startTime"), errors="coerce", utc=True),
        "state": event.get("state"),
        "league": league.get("name"),
        "league_slug": league.get("slug"),
        "tournament": event.get("blockName"),
        "match_id": match.get("id"),
        "team_a": team_a.get("name"),
        "team_a_code": team_a.get("code"),
        "team_b": team_b.get("name"),
        "team_b_code": team_b.get("code"),
        "best_of": _best_of(strategy),
    }


def normalize_leagues(payload: dict[str, Any]) -> pd.DataFrame:
    leagues = payload.get("data", {}).get("leagues", [])
    return pd.DataFrame.from_records(
        {
            "league_id": league.get("id"),
            "name": league.get("name"),
            "slug": league.get("slug"),
            "region": league.get("region"),
        }
        for league in leagues
    )


def _best_of(strategy: dict[str, Any]) -> int | None:
    count = strategy.get("count")
    if count is None:
        return None
    try:
        return int(count)
    except (TypeError, ValueError):
        return None
