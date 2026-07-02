"""Official FIFA World Cup 2026 knockout bracket slot layout."""

from __future__ import annotations

from typing import Any

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


def finalize_bracket_positions(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    positioned = [assign_fifa_bracket_position(dict(row)) for row in rows]
    return positioned
