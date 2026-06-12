# moirai

Notebook-first League of Legends esports match probability analysis.

Moirai downloads professional match history, builds transparent team Elo ratings,
adds recent-form context, and estimates Bo1/Bo3/Bo5 win probabilities for selected
teams. The notebooks are the main interface; reusable code lives in `src/moirai`.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
python -m ipykernel install --user --name moirai --display-name "moirai"
```

## Data Sources

- Historical games: Leaguepedia/Fandom Cargo tables, especially `ScoreboardGames`
  joined with `Tournaments`.
- Upcoming matches: Riot's public LoL Esports persisted schedule endpoints.

Both sources are public and unofficial. The pipeline caches raw responses under
`data/raw/` and processed Parquet datasets under `data/processed/`; these paths are
ignored by git.

## Notebook Workflow

1. `notebooks/01_download_match_history.ipynb`: choose seed teams, crawl opponent
   histories with bounded depth, and save processed matches.
2. `notebooks/02_build_elo_ratings.ipynb`: fit Elo ratings and inspect rating history.
3. `notebooks/03_predict_matchup.ipynb`: select two teams and a best-of format to
   estimate matchup probabilities.
4. `notebooks/04_upcoming_matches.ipynb`: fetch upcoming matches and tournament
   context from LoL Esports.

## Python API Example

```python
from moirai.config import CrawlConfig
from moirai.pipeline.download import crawl_match_history
from moirai.predict import predict_matchup

matches = crawl_match_history(
    CrawlConfig(seed_teams=("Dplus KIA",), max_depth=1, start_date="2024-01-01")
)

prediction = predict_matchup(matches, "Dplus KIA", "T1", best_of=3)
prediction.team_a_series_probability
```

## Modeling Notes

The first model is intentionally interpretable:

- Fit one Elo timeline from completed games.
- Convert per-game probability to Bo-series probability with binomial math.
- Report recent win rate, current streak, and rest days as separate context.

Roster-aware ratings, calibrated logistic models, and patch-specific adjustments are
natural next steps once enough historical data has been collected.