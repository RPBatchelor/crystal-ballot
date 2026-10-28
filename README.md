# Prophecy

Bayesian, seat-level forecasts for Australian elections, plus a static website to explore
forecasts, polling and historical results. First target: the **Victorian state election,
28 November 2026** (Legislative Assembly, 88 seats).

```
pipeline/   Python package `prophecy`: ingest, Stan models, simulation, publish
data/       raw/ (downloads, git-ignored) · curated/ (hand-maintained) · processed/ (tidy CSVs)
web/        SvelteKit static site; reads JSON written to web/static/data/
```

## Setup

```sh
cd pipeline
uv sync
uv run python -c "import cmdstanpy; cmdstanpy.install_cmdstan(compiler=True)"   # Windows: adds RTools
cd ../web && npm install
```

## Pipeline

```sh
cd pipeline
uv run prophecy ingest-polls --election vic-2026   # Wikipedia poll tables -> data/processed
uv run prophecy ingest-results --year 2022         # VEC results, by-elections, preference distributions
uv run prophecy publish --election vic-2026        # JSON for the website
uv run pytest
```

Downloading from Wikipedia requires a User-Agent with contact details
([Wikimedia robot policy](https://w.wiki/4wJS)):
`PROPHECY_USER_AGENT="prophecy/0.1 (https://your-site; you@example.org)"`.
Use `--no-refresh` to re-parse the cached copy.

## Site

```sh
cd web
npm run dev      # http://localhost:5173
npm run build    # static output in web/build
```

## Data sources

| Data | Source |
|---|---|
| Vic Assembly results, 2CP, 2PP, by-elections | [VEC results](https://www.vec.vic.gov.au/results) |
| Full preference distributions (39 districts, 2022) | [VEC statistics](https://vec.vic.gov.au/results/electoral-statistics/state-election-statistics/full-preference-distributions) |
| Voting-intention polls | Pollster releases, indexed via [Wikipedia](https://en.wikipedia.org/wiki/Opinion_polling_for_the_2026_Victorian_state_election) |

Hand corrections live in `data/curated/` (`poll_corrections.csv`, `by_elections_vic.csv`).
