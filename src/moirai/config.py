"""Project-wide defaults for data collection and modeling."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
RAW_DATA_DIR = DATA_DIR / "raw"
PROCESSED_DATA_DIR = DATA_DIR / "processed"

LEAGUEPEDIA_API_URL = "https://lol.fandom.com/api.php"
LOLESPORTS_API_URL = "https://esports-api.lolesports.com/persisted/gw"
LOLESPORTS_API_KEY = "0TvQnueqKa5mxJntVWt0w4LpLfEkrV1Ta8rQBb9Z"


@dataclass(frozen=True)
class EloConfig:
    initial_rating: float = 1500.0
    k_factor: float = 32.0
    rating_scale: float = 400.0


@dataclass(frozen=True)
class CrawlConfig:
    seed_teams: tuple[str, ...]
    max_depth: int = 1
    start_date: str | None = None
    end_date: str | None = None
    limit_per_team: int = 500
    request_delay_seconds: float = 0.5
