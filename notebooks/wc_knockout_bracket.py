"""Official FIFA World Cup 2026 knockout bracket slot layout."""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

FIFA_KNOCKOUT_LAYOUT: dict[int, tuple[str, str, int]] = {
    # Round of 32 — visual top-to-bottom slot per side
    73: ("Round of 32", "left", 3),
    74: ("Round of 32", "left", 1),
    75: ("Round of 32", "left", 4),
    76: ("Round of 32", "right", 1),
    77: ("Round of 32", "left", 2),
    78: ("Round of 32", "right", 2),
    79: ("Round of 32", "right", 3),
    80: ("Round of 32", "right", 4),
    81: ("Round of 32", "left", 7),
    82: ("Round of 32", "left", 8),
    83: ("Round of 32", "left", 5),
    84: ("Round of 32", "left", 6),
    85: ("Round of 32", "right", 7),
    86: ("Round of 32", "right", 5),
    87: ("Round of 32", "right", 8),
    88: ("Round of 32", "right", 6),
    # Round of 16
    89: ("Round of 16", "left", 1),
    90: ("Round of 16", "left", 2),
    91: ("Round of 16", "right", 1),
    92: ("Round of 16", "right", 2),
    93: ("Round of 16", "left", 3),
    94: ("Round of 16", "left", 4),
    95: ("Round of 16", "right", 3),
    96: ("Round of 16", "right", 4),
    # Quarter-finals
    97: ("Quarter-finals", "left", 1),
    98: ("Quarter-finals", "left", 2),
    99: ("Quarter-finals", "right", 1),
    100: ("Quarter-finals", "right", 2),
    # Semi-finals
    101: ("Semi-finals", "left", 1),
    102: ("Semi-finals", "right", 1),
}

FIFA_PAIR_TO_MATCH_NO: dict[frozenset[str], int] = {
    frozenset({"ZA", "CA"}): 73,
    frozenset({"DE", "PY"}): 74,
    frozenset({"NL", "MA"}): 75,
    frozenset({"BR", "JP"}): 76,
    frozenset({"FR", "SE"}): 77,
    frozenset({"CI", "NO"}): 78,
    frozenset({"MX", "EC"}): 79,
    frozenset({"EN", "CD"}): 80,
    frozenset({"US", "BA"}): 81,
    frozenset({"BE", "SN"}): 82,
    frozenset({"PT", "HR"}): 83,
    frozenset({"ES", "AT"}): 84,
    frozenset({"CH", "DZ"}): 85,
    frozenset({"AR", "CV"}): 86,
    frozenset({"CO", "GH"}): 87,
    frozenset({"AU", "EG"}): 88,
    frozenset({"PY", "FR"}): 89,
    frozenset({"CA", "MA"}): 90,
    frozenset({"BR", "NO"}): 91,
    frozenset({"MX", "EN"}): 92,
    frozenset({"PT", "ES"}): 93,
    frozenset({"HR", "AT"}): 93,
    frozenset({"US", "BE"}): 94,
    frozenset({"AR", "AU"}): 95,
    frozenset({"CV", "EG"}): 95,
    frozenset({"CH", "CO"}): 96,
    frozenset({"DZ", "GH"}): 96,
    frozenset({"AL", "GH"}): 96,
    frozenset({"CO", "DZ"}): 96,
}

POLYMARKET_ENRICH_FIELDS = (
    "event_slug",
    "event_start_time",
    "event_title",
    "poly_team1",
    "poly_team2",
    "team1_code",
    "team2_code",
    "polymarket_team1_win_price",
    "polymarket_draw_price",
    "polymarket_team2_win_price",
)

PRICE_ENRICH_FIELDS = (
    "polymarket_team1_win_price",
    "polymarket_draw_price",
    "polymarket_team2_win_price",
)

TEAM_SIDE_PAIRS = (
    ("poly_team1", "poly_team2"),
    ("team1_code", "team2_code"),
    ("team1_elo_pre", "team2_elo_pre"),
    ("polymarket_team1_win_price", "polymarket_team2_win_price"),
    ("elo_team1_win_prob", "elo_team2_win_prob"),
    ("team1_form", "team2_form"),
    ("team1_recent_matches", "team2_recent_matches"),
    ("team1_goals", "team2_goals"),
    ("team1_pen_goals", "team2_pen_goals"),
)

FIXTURE_SIDE_PAIRS = (
    ("team1_elo_pre", "team2_elo_pre"),
    ("elo_team1_win_prob", "elo_team2_win_prob"),
    ("team1_form", "team2_form"),
    ("team1_recent_matches", "team2_recent_matches"),
    ("team1_goals", "team2_goals"),
    ("team1_pen_goals", "team2_pen_goals"),
)


def team_pair_key(team1_code: str, team2_code: str) -> frozenset[str]:
    return frozenset({str(team1_code).strip(), str(team2_code).strip()})


def lookup_fifa_match_no(team1_code: str, team2_code: str) -> int | None:
    return FIFA_PAIR_TO_MATCH_NO.get(team_pair_key(team1_code, team2_code))


def bracket_position_for_match(match_no: int) -> dict[str, Any] | None:
    layout = FIFA_KNOCKOUT_LAYOUT.get(match_no)
    if layout is None:
        return None
    round_name, side, slot = layout
    return {
        "fifa_match_no": match_no,
        "round": round_name,
        "bracket_side": side,
        "bracket_slot": slot,
    }


def assign_fifa_bracket_position(row: dict[str, Any]) -> dict[str, Any]:
    team1_code = row.get("team1_code") or ""
    team2_code = row.get("team2_code") or ""
    match_no = lookup_fifa_match_no(team1_code, team2_code)
    if match_no is None:
        return row

    position = bracket_position_for_match(match_no)
    if position is None:
        return row

    return {**row, **position}


def _is_blank(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str) and not value.strip():
        return True
    if isinstance(value, float) and math.isnan(value):
        return True
    return False


def enrich_from_polymarket(
    row: dict[str, Any],
    lookup: dict[frozenset[str], dict[str, Any]] | None,
) -> dict[str, Any]:
    if not lookup:
        return row

    team1_code = row.get("team1_code") or ""
    team2_code = row.get("team2_code") or ""
    if not team1_code or not team2_code:
        return row

    polymarket_row = lookup.get(team_pair_key(team1_code, team2_code))
    if not polymarket_row:
        return row

    merged = dict(row)
    for field in POLYMARKET_ENRICH_FIELDS:
        polymarket_value = polymarket_row.get(field)
        if _is_blank(polymarket_value):
            continue
        merged[field] = polymarket_value
    return merged


def build_polymarket_price_lookup(
    records: list[dict[str, Any]],
) -> dict[frozenset[str], dict[str, Any]]:
    lookup: dict[frozenset[str], dict[str, Any]] = {}
    for record in records:
        team1_code = record.get("team1_code")
        team2_code = record.get("team2_code")
        if not team1_code or not team2_code:
            continue
        prices = {field: record.get(field) for field in PRICE_ENRICH_FIELDS}
        if all(_is_blank(value) for value in prices.values()):
            continue
        lookup[team_pair_key(team1_code, team2_code)] = prices
    return lookup


def enrich_from_polymarket_prices(
    row: dict[str, Any],
    lookup: dict[frozenset[str], dict[str, Any]] | None,
) -> dict[str, Any]:
    if not lookup:
        return row

    team1_code = row.get("team1_code") or ""
    team2_code = row.get("team2_code") or ""
    if not team1_code or not team2_code:
        return row

    price_row = lookup.get(team_pair_key(team1_code, team2_code))
    if not price_row:
        return row

    merged = dict(row)
    for field in PRICE_ENRICH_FIELDS:
        if _is_blank(merged.get(field)) and not _is_blank(price_row.get(field)):
            merged[field] = price_row[field]
    return merged


def swap_fixture_sides(row: dict[str, Any]) -> dict[str, Any]:
    merged = dict(row)
    for field1, field2 in FIXTURE_SIDE_PAIRS:
        merged[field1], merged[field2] = row.get(field2), row.get(field1)
    return merged


def swap_team_sides(row: dict[str, Any]) -> dict[str, Any]:
    merged = dict(row)
    for field1, field2 in TEAM_SIDE_PAIRS:
        merged[field1], merged[field2] = row.get(field2), row.get(field1)
    return merged


def _fixture_team1_code_from_row(row: dict[str, Any]) -> str | None:
    code = row.get("_fixture_team1_code")
    if _is_blank(code):
        return None
    return str(code).strip()


def reconcile_fixture_elo_sides(
    row: dict[str, Any],
    *,
    fixture_team1_code: str | None = None,
) -> dict[str, Any]:
    merged = dict(row)
    merged.pop("_fixture_team1_code", None)
    if _is_blank(fixture_team1_code):
        return merged

    if str(fixture_team1_code) == str(merged.get("team1_code")):
        return merged
    if str(fixture_team1_code) == str(merged.get("team2_code")):
        return swap_fixture_sides(merged)
    return merged


def finalize_bracket_positions(
    rows: list[dict[str, Any]],
    *,
    polymarket_lookup: dict[frozenset[str], dict[str, Any]] | None = None,
    price_lookup: dict[frozenset[str], dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    positioned = []
    for row in rows:
        working = dict(row)
        fixture_team1_code = _fixture_team1_code_from_row(working)
        if fixture_team1_code is None:
            pre_enrich_team1 = working.get("team1_code")
            fixture_team1_code = None if _is_blank(pre_enrich_team1) else str(pre_enrich_team1)
        working.pop("_fixture_team1_code", None)
        working = enrich_from_polymarket(working, polymarket_lookup)
        working = enrich_from_polymarket_prices(working, price_lookup)
        working = reconcile_fixture_elo_sides(
            working,
            fixture_team1_code=fixture_team1_code,
        )
        working = assign_fifa_bracket_position(working)
        positioned.append(working)
    return positioned


def _kickoff_instant(row: dict[str, Any]) -> datetime | None:
    raw = row.get("event_start_time")
    if _is_blank(raw):
        return None
    try:
        instant = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return None
    if instant.tzinfo is None:
        instant = instant.replace(tzinfo=timezone.utc)
    return instant


def _local_match_date(instant: datetime, tz_name: str):
    return instant.astimezone(ZoneInfo(tz_name)).date()


def _is_upcoming_row(row: dict[str, Any]) -> bool:
    return _is_blank(row.get("team1_goals")) or _is_blank(row.get("team2_goals"))


def build_next_up_slug_pair_sets(
    records: list[dict[str, Any]],
    *,
    display_timezone: str = "Asia/Singapore",
) -> tuple[set[str], set[frozenset[str]]]:
    """Slugs and team pairs for upcoming fixtures on the next match day only."""
    upcoming = [row for row in records if _is_upcoming_row(row)]
    slugs: set[str] = set()
    pairs: set[frozenset[str]] = set()
    if not upcoming:
        return slugs, pairs

    kickoffs: list[tuple[datetime, dict[str, Any]]] = []
    for row in upcoming:
        instant = _kickoff_instant(row)
        if instant is not None:
            kickoffs.append((instant, row))
    if not kickoffs:
        return slugs, pairs

    earliest = min(kickoffs, key=lambda item: item[0])[0]
    next_match_day = _local_match_date(earliest, display_timezone)
    for instant, row in kickoffs:
        if _local_match_date(instant, display_timezone) != next_match_day:
            continue
        slug = str(row.get("event_slug") or "").strip()
        if slug:
            slugs.add(slug)
        team1_code = row.get("team1_code")
        team2_code = row.get("team2_code")
        if not _is_blank(team1_code) and not _is_blank(team2_code):
            pairs.add(team_pair_key(str(team1_code), str(team2_code)))
    return slugs, pairs


def tag_next_up_flags(
    rows: list[dict[str, Any]],
    *,
    next_up_slugs: set[str],
    next_up_pairs: set[frozenset[str]],
) -> list[dict[str, Any]]:
    """Mark upcoming rows that also appear on the main matches page (next match day)."""
    tagged: list[dict[str, Any]] = []
    for row in rows:
        if not _is_truthy(row.get("is_upcoming")):
            tagged.append({**row, "is_next_up": False})
            continue

        slug = str(row.get("event_slug") or "").strip()
        pair = team_pair_key(row.get("team1_code", ""), row.get("team2_code", ""))
        is_next_up = (slug in next_up_slugs) or (pair in next_up_pairs)
        tagged.append({**row, "is_next_up": is_next_up})
    return tagged


def _is_truthy(value: Any) -> bool:
    if value is True or value == 1:
        return True
    if isinstance(value, str):
        return value.strip().lower() in {"true", "1", "yes"}
    return False
