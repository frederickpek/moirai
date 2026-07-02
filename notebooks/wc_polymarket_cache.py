"""Polymarket World Cup event cache — in-memory pagination, compact JSON only."""

from __future__ import annotations

import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

POLYMARKET_EVENT_FIELDS = (
    "id",
    "slug",
    "title",
    "startTime",
    "endDate",
    "eventDate",
    "closed",
    "ended",
    "finishedTimestamp",
    "score",
)
PRIMARY_MATCH_SLUG_SKIP = (
    "more-markets",
    "halftime",
    "exact",
    "second-half",
    "first-to",
    "total-corners",
)

POLYMARKET_MARKET_FIELDS = (
    "id",
    "slug",
    "sportsMarketType",
    "clobTokenIds",
    "outcomes",
    "outcomePrices",
    "groupItemTitle",
    "question",
    "conditionId",
    "lastTradePrice",
    "bestBid",
    "bestAsk",
    "gameStartTime",
)


def legacy_event_page_pattern(series_slug: str) -> re.Pattern[str]:
    return re.compile(rf"^polymarket_events_{re.escape(series_slug)}_\d+_\d+\.json$")


def is_legacy_paginated_event_cache(name: str, series_slug: str) -> bool:
    return bool(legacy_event_page_pattern(series_slug).match(name))


def compact_polymarket_market(market: dict[str, Any]) -> dict[str, Any]:
    return {key: market.get(key) for key in POLYMARKET_MARKET_FIELDS if market.get(key) is not None}


def compact_polymarket_event(event: dict[str, Any]) -> dict[str, Any]:
    compact = {key: event.get(key) for key in POLYMARKET_EVENT_FIELDS if event.get(key) is not None}
    markets = [
        compact_polymarket_market(market)
        for market in (event.get("markets") or [])
        if market.get("sportsMarketType") == "moneyline"
    ]
    if markets:
        compact["markets"] = markets
    return compact


def save_compact_events_cache(
    cache_dir: Path,
    cache_name: str,
    events: list[dict[str, Any]],
    *,
    log: Callable[[str], None] | None = None,
) -> None:
    compact_events = [compact_polymarket_event(event) for event in events]
    path = cache_dir / cache_name
    path.write_text(
        json.dumps(compact_events, separators=(",", ":"), sort_keys=True),
        encoding="utf-8",
    )
    if log:
        log(f"[cache] wrote compact Polymarket events -> {cache_name}")


def load_compact_events_cache(
    cache_dir: Path,
    cache_name: str,
    *,
    log: Callable[[str], None] | None = None,
) -> list[dict[str, Any]] | None:
    path = cache_dir / cache_name
    if not path.exists():
        return None
    if log:
        log(f"[cache] {cache_name}")
    return json.loads(path.read_text(encoding="utf-8"))


def cleanup_legacy_paginated_event_caches(
    cache_dir: Path,
    series_slug: str,
    compact_cache_name: str,
    *,
    log: Callable[[str], None] | None = None,
) -> int:
    removed = 0
    pattern = legacy_event_page_pattern(series_slug)
    for legacy_path in cache_dir.glob("polymarket_events_*.json"):
        if legacy_path.name == compact_cache_name:
            continue
        if not pattern.match(legacy_path.name):
            continue
        legacy_path.unlink(missing_ok=True)
        removed += 1
        if log:
            log(f"[cache] removed legacy {legacy_path.name}")
    return removed


def migrate_legacy_paginated_event_caches(
    cache_dir: Path,
    series_slug: str,
    compact_cache_name: str,
    *,
    log: Callable[[str], None] | None = None,
) -> None:
    compact_path = cache_dir / compact_cache_name
    if compact_path.exists():
        cleanup_legacy_paginated_event_caches(cache_dir, series_slug, compact_cache_name, log=log)
        return

    pattern = legacy_event_page_pattern(series_slug)
    legacy_paths = sorted(
        path
        for path in cache_dir.glob("polymarket_events_*.json")
        if path.name != compact_cache_name and pattern.match(path.name)
    )
    if not legacy_paths:
        return

    all_events: list[dict[str, Any]] = []
    seen_event_ids: set[Any] = set()
    for legacy_path in legacy_paths:
        for event in json.loads(legacy_path.read_text(encoding="utf-8")):
            event_id = event.get("id")
            if event_id in seen_event_ids:
                continue
            seen_event_ids.add(event_id)
            all_events.append(event)

    save_compact_events_cache(cache_dir, compact_cache_name, all_events, log=log)
    cleanup_legacy_paginated_event_caches(cache_dir, series_slug, compact_cache_name, log=log)
    if log:
        log(f"[cache] migrated {len(all_events)} legacy Polymarket event(s) into {compact_cache_name}")


def fetch_events_from_api(
    *,
    gamma_url: str,
    series_slug: str,
    page_size: int = 100,
    sleep_seconds: float = 0.15,
    log: Callable[[str], None] | None = None,
) -> list[dict[str, Any]]:
    import requests

    all_events: list[dict[str, Any]] = []
    for offset in range(0, 5000, page_size):
        params = {"series_slug": series_slug, "limit": page_size, "offset": offset}
        if log:
            log(f"[download] {gamma_url}/events {params} (in memory only)")
        response = requests.get(f"{gamma_url}/events", params=params, timeout=60)
        response.raise_for_status()
        batch = response.json()
        if not batch:
            break
        all_events.extend(batch)
        if log:
            log(f"[events] loaded {len(all_events)} total Polymarket events")
        if len(batch) < page_size:
            break
        time.sleep(sleep_seconds)
    return all_events


def is_primary_moneyline_event(event: dict[str, Any]) -> bool:
    slug = event.get("slug") or ""
    if not slug.startswith("fifwc-"):
        return False
    if any(part in slug for part in PRIMARY_MATCH_SLUG_SKIP):
        return False
    markets = event.get("markets") or []
    if markets:
        return any(market.get("sportsMarketType") == "moneyline" for market in markets)
    return True


def event_start_time_iso(event: dict[str, Any]) -> str | None:
    start = event.get("startTime") or event.get("endDate")
    if not start:
        return None
    return str(start)


def build_polymarket_team_pair_lookup(
    events: list[dict[str, Any]],
    *,
    team_code_for_name: Callable[[str], str | None],
    split_teams: Callable[[str], tuple[str | None, str | None]],
) -> dict[frozenset[str], dict[str, Any]]:
    """Map Elo team-code pairs to primary Polymarket moneyline event metadata."""
    lookup: dict[frozenset[str], dict[str, Any]] = {}
    for event in events:
        if not is_primary_moneyline_event(event):
            continue
        title = (event.get("title") or "").strip()
        if not title:
            continue
        team1, team2 = split_teams(title)
        if not team1 or not team2:
            continue
        team1_code = team_code_for_name(team1)
        team2_code = team_code_for_name(team2)
        if not team1_code or not team2_code:
            continue

        entry = {
            "event_slug": event.get("slug") or "",
            "event_title": title,
            "event_start_time": event_start_time_iso(event) or "",
            "poly_team1": team1,
            "poly_team2": team2,
            "team1_code": team1_code,
            "team2_code": team2_code,
        }
        key = frozenset({team1_code, team2_code})
        existing = lookup.get(key)
        if existing is None:
            lookup[key] = entry
            continue

        existing_slug = existing.get("event_slug") or ""
        new_slug = entry.get("event_slug") or ""
        if len(new_slug) < len(existing_slug):
            lookup[key] = entry
        elif not existing.get("event_start_time") and entry.get("event_start_time"):
            lookup[key] = entry
    return lookup


def fetch_knockout_more_markets(
    gamma_url: str,
    event_slug: str,
    team1: str,
    team2: str,
    *,
    timeout: float = 30,
) -> dict[str, Any]:
    """Fetch knockout advancement / penalty-shootout flags from Polymarket more-markets."""
    import json as _json

    import requests

    if not event_slug:
        return {}

    slug = f"{event_slug}-more-markets"
    try:
        response = requests.get(f"{gamma_url}/events", params={"slug": slug}, timeout=timeout)
        response.raise_for_status()
        events = response.json()
    except Exception:
        return {}

    if not events:
        return {}

    extras: dict[str, Any] = {}
    for market in events[0].get("markets") or []:
        title = market.get("groupItemTitle") or market.get("question") or ""
        try:
            outcomes = _json.loads(market.get("outcomes") or "[]")
            prices = _json.loads(market.get("outcomePrices") or "[]")
        except _json.JSONDecodeError:
            continue

        if title == "Team to Advance":
            winner_idx = next((idx for idx, price in enumerate(prices) if price == "1"), None)
            if winner_idx is None or winner_idx >= len(outcomes):
                continue
            winner_name = outcomes[winner_idx]
            if winner_name == team1:
                extras["advance_winner"] = "team1"
            elif winner_name == team2:
                extras["advance_winner"] = "team2"
        elif "Penalty Shootout" in title:
            yes_idx = next((idx for idx, outcome in enumerate(outcomes) if outcome == "Yes"), None)
            if yes_idx is not None and prices[yes_idx] == "1":
                extras["went_to_penalties"] = True

    return extras


def fetch_penalty_score_from_skysports(
    team1: str,
    team2: str,
    team1_goals: int,
    team2_goals: int,
    *,
    article_id_start: int = 13558800,
    article_id_end: int = 13558950,
    timeout: float = 12,
) -> tuple[int | None, int | None]:
    """Best-effort penalty score lookup from Sky Sports match reports."""
    import re

    import requests

    headers = {"User-Agent": "Mozilla/5.0"}
    pattern = re.compile(
        rf"{re.escape(team1)}\s+{int(team1_goals)}-{int(team2_goals)}\s+{re.escape(team2)}.*?"
        rf"\((\d+)-(\d+)\s+on\s+penalties\)",
        re.IGNORECASE | re.DOTALL,
    )

    for article_id in range(article_id_start, article_id_end):
        url = f"https://www.skysports.com/football/news/17251/{article_id}/"
        try:
            response = requests.get(url, headers=headers, timeout=timeout)
        except Exception:
            continue
        if response.status_code != 200:
            continue
        match = pattern.search(response.text)
        if match:
            return int(match.group(1)), int(match.group(2))

    return None, None


def load_world_cup_events(
    *,
    cache_dir: Path,
    gamma_url: str,
    series_slug: str,
    compact_cache_name: str,
    force_refresh: bool,
    page_size: int = 100,
    sleep_seconds: float = 0.15,
    log: Callable[[str], None] | None = None,
) -> list[dict[str, Any]]:
    cleanup_legacy_paginated_event_caches(cache_dir, series_slug, compact_cache_name, log=log)

    if not force_refresh:
        cached = load_compact_events_cache(cache_dir, compact_cache_name, log=log)
        if cached is not None:
            return cached

    all_events = fetch_events_from_api(
        gamma_url=gamma_url,
        series_slug=series_slug,
        page_size=page_size,
        sleep_seconds=sleep_seconds,
        log=log,
    )
    save_compact_events_cache(cache_dir, compact_cache_name, all_events, log=log)
    cleanup_legacy_paginated_event_caches(cache_dir, series_slug, compact_cache_name, log=log)
    return load_compact_events_cache(cache_dir, compact_cache_name, log=log) or []
