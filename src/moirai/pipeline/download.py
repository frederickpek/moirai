"""Bounded recursive downloads for historical team match history."""

from __future__ import annotations

from collections import deque
from time import sleep
from typing import Any

import pandas as pd

from moirai.config import CrawlConfig
from moirai.pipeline.store import load_raw_json, save_matches, save_raw_json
from moirai.sources.leaguepedia import (
    LeaguepediaClient,
    canonical_team_name,
    normalize_games,
    opponents_for_team,
)


def crawl_match_history(
    config: CrawlConfig,
    *,
    use_cache: bool = True,
    verbose: bool = True,
) -> pd.DataFrame:
    """Download seed teams and their opponents up to ``config.max_depth``.

    Depth 0 is the seed team set. Depth 1 adds every opponent found in the seed teams'
    downloaded matches, and so on. A visited set prevents unbounded loops across leagues.
    """

    visited: set[str] = set()
    queued = deque((canonical_team_name(team) or team, 0) for team in config.seed_teams)
    raw_rows: list[dict[str, Any]] = []

    with LeaguepediaClient() as client:
        while queued:
            team, depth = queued.popleft()
            team = canonical_team_name(team) or team
            if team in visited or depth > config.max_depth:
                continue

            visited.add(team)
            _log(verbose, f"[crawl] depth={depth}/{config.max_depth} team={team}")
            rows, source = _load_or_fetch_team_rows(
                client, team, config=config, use_cache=use_cache
            )
            raw_rows.extend(rows)

            team_matches = normalize_games(rows, preferred_team_names=[team])
            queued_count = 0
            if depth < config.max_depth:
                for opponent in sorted(opponents_for_team(team_matches, team)):
                    if opponent not in visited:
                        queued.append((opponent, depth + 1))
                        queued_count += 1

            _log(
                verbose,
                (
                    f"[crawl] depth={depth}/{config.max_depth} team={team} "
                    f"source={source} rows={len(rows)} queued_opponents={queued_count} "
                    f"visited={len(visited)} remaining={len(queued)}"
                ),
            )

            if config.request_delay_seconds:
                sleep(config.request_delay_seconds)

    matches = normalize_games(raw_rows, preferred_team_names=config.seed_teams)
    save_matches(matches)
    _log(
        verbose,
        (
            f"[crawl] complete teams_visited={len(visited)} games={len(matches)} "
            "saved=data/processed/matches.parquet"
        ),
    )
    return matches


def _load_or_fetch_team_rows(
    client: LeaguepediaClient,
    team: str,
    *,
    config: CrawlConfig,
    use_cache: bool,
) -> tuple[list[dict[str, Any]], str]:
    cache_key = _cache_key(team, config)
    if use_cache:
        cached = load_raw_json(cache_key)
        if cached is not None:
            cached_rows = list(cached)
            if cached_rows:
                return cached_rows, "cache"

    rows = client.fetch_team_games(
        team,
        start_date=config.start_date,
        end_date=config.end_date,
        limit=config.limit_per_team,
    )
    save_raw_json(cache_key, rows)
    return rows, "network"


def _cache_key(team: str, config: CrawlConfig) -> str:
    date_bits = [
        config.start_date or "all-start",
        config.end_date or "all-end",
        str(config.limit_per_team),
    ]
    return f"leaguepedia-{team}-{'-'.join(date_bits)}"


def _log(verbose: bool, message: str) -> None:
    if verbose:
        print(message, flush=True)
