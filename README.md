# Crystal Ballot

The public site is **Crystal Ballot** (https://crystalballot.netlify.app); the site name is
set in `web/src/lib/site.ts`. The code and pipeline keep the name `prophecy`.

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
uv run prophecy ingest-polls --jurisdiction VIC    # every cycle's polls + election results
uv run prophecy ingest-results --year 2022         # VEC results (also 2014, 2018), by-elections, DoPs
uv run prophecy poll-error                         # historical final-poll error table
uv run prophecy backtest --election vic-2018       # blind forecast of 2018, scored
uv run prophecy aggregate --election vic-2026      # Bayesian poll aggregate (Stan, ~6 min)
uv run prophecy forecast --election vic-2026       # seat simulation (needs aggregate + AEC/Vicmap raw data)
uv run prophecy publish --election vic-2026        # JSON for the website
uv run pytest
```

New South Wales (results 2015-2023 and a blind forecast of 2023):

```sh
uv run prophecy ingest-polls --jurisdiction NSW    # 2011-2027 cycles (2015/2019 from pinned revisions)
uv run prophecy ingest-nswec                       # NSWEC 2015, 2019, 2023 + statewide results
uv run prophecy notional --election nsw-2023   # 2019 result re-cut onto the 2021 boundaries
uv run prophecy poll-error --jurisdiction NSW
uv run prophecy backtest --election nsw-2023
uv run prophecy publish --election nsw-2027
uv run prophecy ingest-boundaries --boundaries nsw-2021,nsw-2013   # districts (~45 MB each)
uv run prophecy publish-geo --jurisdiction NSW --boundaries nsw-2021,nsw-2013   # seat maps
```

Queensland (results 2012-2024 and a blind forecast of 2024):

```sh
uv run prophecy ingest-polls --jurisdiction QLD    # 2012-2028 cycles
uv run prophecy ingest-ecq --years 2012,2015,2017,2020,2024   # legacy site to 2017, XML feed after
uv run prophecy poll-error --jurisdiction QLD
uv run prophecy backtest --election qld-2024
uv run prophecy publish --election qld-2028
uv run prophecy ingest-boundaries --boundaries qld-2017,qld-2008
uv run prophecy publish-geo --jurisdiction QLD --boundaries qld-2017,qld-2008
```

South Australia (results 2014-2026):

```sh
uv run prophecy ingest-polls --jurisdiction SA     # 2010-2026 cycles
uv run prophecy ingest-ecsa                        # ECSA 2014, 2018 (site pages), 2022, 2026 (results API)
uv run prophecy poll-error --jurisdiction SA
uv run prophecy notional --election sa-2026        # 2022 result re-cut onto the 2024 boundaries
uv run prophecy backtest --election sa-2026        # blind forecast of the 2026 election
uv run prophecy publish --election sa-2030
uv run prophecy ingest-boundaries --boundaries sa-2012,sa-2016,sa-2020,sa-2024
uv run prophecy publish-geo --jurisdiction SA --boundaries sa-2012,sa-2016,sa-2020,sa-2024
```

Western Australia (results 2008-2025 and a blind forecast of 2025):

```sh
uv run prophecy ingest-polls --jurisdiction WA     # 2008-2025 cycles
uv run prophecy ingest-waec                        # WAEC 2008-2025 (results API)
uv run prophecy notional --election wa-2025    # 2021 result re-cut onto the 2023 boundaries
uv run prophecy poll-error --jurisdiction WA
uv run prophecy backtest --election wa-2025
uv run prophecy publish --election wa-2029
```

Tasmania (results 2018-2025 and blind forecasts of 2024 and 2025; Hare-Clark, see below):

```sh
uv run prophecy ingest-polls --jurisdiction TAS    # 2014-2025 cycles (2025 from its own polling page)
uv run prophecy ingest-tec                         # TEC 2018, 2021, 2024, 2025
uv run prophecy poll-error --jurisdiction TAS
uv run prophecy backtest --election tas-2024       # also tas-2025
```

ACT (results 2016-2024 and a blind forecast of 2024; Hare-Clark, as for Tasmania):

```sh
uv run prophecy ingest-polls --jurisdiction ACT    # only 2020 has polls
uv run prophecy ingest-elections-act               # Elections ACT 2016, 2020, 2024
uv run prophecy backtest --election act-2024       # no polls: previous result plus historical swing
```

Northern Territory (results 2016-2024 and a blind forecast of 2024):

```sh
uv run prophecy ingest-polls --jurisdiction NT
uv run prophecy ingest-nt                          # Wikipedia's per-division NTEC results, and the 2024 notional
uv run prophecy poll-error --jurisdiction NT
uv run prophecy backtest --election nt-2024
```

### Estimated settings and the backtest set

Backtests take every model setting from elections before the one forecast:

- **Seat swing** (`prophecy.model.swing_fit`): Student-t seat noise, regression to the
  mean and retirement / first-term effects, fitted on pairs of consecutive elections on
  the same (or notionally re-cut) boundaries; the noise scale is the jurisdiction's own,
  shrunk toward the pooled one. Victoria 2018 has too few earlier pairs and keeps the
  hand-set values. Hare-Clark divisions keep their own.
- **Polling error** (`pooled_poll_error`): final-month poll errors from all nine
  jurisdictions, each jurisdiction shrunk toward the pool, with correlated party errors.
- **First-time independents and new parties** (`prophecy.model.new_candidates`,
  `prophecy.model.hareclark_pools`): drawn from what such candidates polled before.
- **One Nation geography** in the states: the last federal election's polling places
  mapped onto state districts where One Nation did not contest most seats last time.
- **No-polls prior**: the governing party's centre falls by the (shrunk) average loss of
  governments at earlier elections.

`--hand-set` reruns a backtest with the settings from before the October 2026 review, for
comparison (output in `backtest-<id>-handset`); `--aggregator poll_aggregator_corr` uses the
poll model with correlated party trends and drifting house effects (`backtest-<id>-corr`).
Each backtest writes `manifest.json` (git commit, input file hashes, full settings) and
scores seat votes (CRPS, PIT histogram, interval coverage) and a Mackerras pendulum baseline
as well as seat winners. Earlier elections backtested the same way: Queensland 2015, 2017
and 2020, NSW 2019, SA 2018 and 2022, WA 2017 and 2021, NT 2020 (notionals with
`prophecy notional --election <id>`).

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
| NSW Assembly results, preferences, venue counts, 2CP/2PP | [NSWEC past results](https://pastvtr.elections.nsw.gov.au/) |
| NSW district boundaries (2013, 2021 redistributions) | [NSW Spatial Services](https://data.nsw.gov.au/data/dataset/900b8e44-d4af-4799-94f7-8ef70bbcf20c) (Administrative Boundaries Theme; [2013 snapshot](https://data.gov.au/data/dataset/c4a5ab74-066f-4af6-b6e8-6e46fa8d6469)) |
| Qld Assembly results, booth votes, preferences, 2CP | [ECQ results](https://results.elections.qld.gov.au/) (XML media feed, 2020 on); [ECQ legacy results](https://results.ecq.qld.gov.au/elections/state/State2017/results/summary.html) (2012-2017) |
| Qld district boundaries (2017 redistribution) | [Queensland Spatial](https://spatial-gis.information.qld.gov.au/arcgis/rest/services/Boundaries/AdminBoundariesFramework/MapServer/139) (Administrative Boundaries Framework; the same data as the QSpatial catalogue download), clipped for the maps to the [ABS state outline](https://geo.abs.gov.au/arcgis/rest/services/ASGS2021/STE/MapServer/0) (ASGS 2021) because the districts extend out to sea |
| SA Assembly results, polling-place votes, 2CP; preferences from 2022 | [ECSA results](https://result.ecsa.sa.gov.au/) (2022, 2026); [ECSA past results](https://www.ecsa.sa.gov.au/elections/past-state-election-results) (2014, 2018) |
| SA district boundaries (each election) | [State Electorates, data.sa.gov.au](https://data.sa.gov.au/data/dataset/state-electorates) (Location SA) |
| WA Assembly results, polling-place votes, 2CP, preferences | [WAEC results](https://www.elections.wa.gov.au/elections/state/sgelection) (the app's API, `eis.waec.wa.gov.au`) |
| Tas House of Assembly results (Hare-Clark), polling-place first preferences | [TEC results](https://www.tec.tas.gov.au/house-of-assembly/index.html) (final distribution fragments; first preferences by polling place workbooks, 2021 on) |
| ACT Assembly results (Hare-Clark) | [Elections ACT](https://www.elections.act.gov.au/elections/previous-assembly-elections) (distribution of preferences workbooks 2016, 2020; 2024 statistics book; lists of elected candidates) |
| NT Assembly results | NTEC counts as transcribed in Wikipedia's [Results of the 2024 Northern Territory general election](https://en.wikipedia.org/wiki/Results_of_the_2024_Northern_Territory_general_election) (and 2016, 2020); the NTEC site refuses automated requests |
| Voting-intention polls | Pollster releases, indexed via [Wikipedia](https://en.wikipedia.org/wiki/Opinion_polling_for_the_2026_Victorian_state_election) |

Hand corrections live in `data/curated/` (`poll_corrections.csv`, `by_elections_vic.csv`,
`by_elections_nsw.csv`, `by_elections_qld.csv`, `by_elections_wa.csv`, `by_elections_sa.csv`, `by_elections_nt.csv`); the `regions_*.csv` files group districts into regions. `results_sa_supplement.csv` fills two
2014 SA districts ECSA's site lacks or gets wrong (Fisher: no general-election page;
Mawson: its polling-place page repeats MacKillop's).

## New South Wales

- **Optional preferential voting.** Ballots can exhaust. Exhaustion is modelled as one more
  choice at every exclusion (`model/preferences.py`), estimated from the NSWEC distributions,
  which record exhausted ballots at each count.
- **Notional baseline.** NSW redistributed in 2021, so the 2019 result is re-cut onto the 2023
  districts by polling place: each election-day venue goes to the district where it took votes
  in 2023; declaration and pre-poll votes follow the old district's venue votes
  (`model/states.py`). The notional Labor v Coalition 2PP uses the NSWEC venue-level counts.
- **Members.** The 2023 ballot (public at nominations) gives retirements and members moving
  seats; by-elections are curated. The Shooters' 2019 seat vote counts as an independent vote
  (all three members stood as independents in 2023); a member who left a major party to stand
  as an independent keeps half their old primary vote as a prior.

## Queensland

- **Full preferential voting** since 2016, so no exhaustion. The 2020 and 2024 elections were
  held on the 2017 boundaries, so 2024 seats start directly from the 2020 result.
- **Two-party preferred.** The ECQ publishes Labor v LNP counts only where those were the final
  two (85 of 93 seats in 2020 and 2024); statewide 2PP figures come from the election results.
- **Members.** Katter's Australian Party members are simulated as independents and scored as
  such. Stephen Andrew (Mirani) was elected for One Nation in 2020 and stood for KAP in 2024;
  he keeps half his old primary vote as a prior. Ipswich West was vacant at dissolution after
  the death of its by-election winner.

## Western Australia

- **Full preferential voting.** Liberals and Nationals run against each other in most country
  seats; the model treats them as one Coalition bloc, the seat going to whichever ran stronger
  last time (or is the only one standing).
- **Notional baseline.** Boundaries are redrawn after every election (2023 for 2025). The 2021
  result is re-cut by polling place as for NSW. The WAEC publishes no Labor v Coalition count by
  polling place, so each old seat's 2PP follows its votes. Regions
  (`regions_wa-2023.csv`) are the 2021 Legislative Council regions of each seat's main origin.
- **Statewide results** (`election_results_wa.csv`): WAEC first preferences; the 2PP is the
  election article's figure.

## Tasmania

- **Hare-Clark.** Five divisions each elect 5 (to 2021) or 7 members (from 2024) by
  proportional representation, so there is no seat-by-seat 2CP and the single-member model
  does not apply. `model/hareclark.py` simulates the count with one unit per party (it can win
  several seats and keeps its surplus) and one per independent (one seat at most), using quotas,
  exclusions and bloc preference flows with some exhaustion.
- **Inputs.** Division bloc shares swing from the previous result as in the other states.
  Independents keep their own previous vote (candidate-level under Hare-Clark); a sitting
  member who leaves their party takes half their old personal vote; new independents and new
  parties start small (1% and 1.5%). Sitting members are those marked on the TEC count pages.
- **Flows** come from the full preference distributions in Tasmania's five federal divisions
  (same boundaries) at the two federal elections before the state election.
- **Nationals** (standing from 2025, against the Liberals) count with Others, in polls and results.
  Polls of single divisions (on the 2025 polling page) are left out of the statewide aggregate.
- **No 2PP**: Hare-Clark has no two-party count, so `election_results_tas.csv` has none.
- **Known limits.** A new party's breakthrough (the Lambie Network's 3 seats in 2024) and new
  independents (Peter George, Franklin 2025) are not foreseen: the model only knows votes
  already cast. The site does not yet have multi-member result or forecast pages.

## ACT and Northern Territory

- **ACT: Hare-Clark.** Five electorates of five members; the Tasmanian count model applies
  (`model/hareclark.py`), with flows from the federal ACT divisions (Bean, Canberra, Fenner).
  Elections ACT does not mark sitting members, so the previous election's winners are taken as
  sitting. Independents for Canberra and Strong Independents ran party tickets and are
  simulated as minor parties; one-candidate groups (Fiona Carrick Independent) as independents.
- **Few or no polls.** With fewer than three polls before polling day (ACT 2024: none; NT
  2024: two), the poll aggregate is replaced by a centre plus a swing drawn from the
  jurisdiction's own election-to-election changes (`swing_prior` in `model/pipeline.py`): the
  centre is each party's average in the polls of the last year where any report it, else the
  previous result. No further polling error is added.
- **NT.** 25 single-member divisions, full preferential; the CLP is the Coalition. The NTEC
  publishes no distributions of preferences in a form we can read, so flows come from the
  federal NT divisions (Lingiari, Solomon), calibrated to the NT seats' own Labor v CLP results.
  The 2024 election was on new boundaries: the notional 2020 vote per seat is each party's 2024
  share less its change in the per-division results (changes there are against the notional
  result), with the notional holder from whether the seat was held or gained.

## Candidates and local factors

- `data/curated/members_vic-2026.csv`: sitting members, first-elected year and 2026 status
  (recontesting / retiring / vacant). Retirements come from the election article's cited
  "Candidates and retiring MPs" list; edit by hand as announcements change.
- `data/curated/candidates_vic-2026.csv`: the ballot, once VEC nominations close
  (12 noon, 9 November 2026). One row per candidate: `district,name,party,ballot_position,prior_share,note`.
  Seats listed here only give votes to parties with a candidate; `prior_share` (%) sets
  the expected first-preference vote of a notable independent.
- Model effects (logit primary vote): retiring member and first-term member effects are
  estimated from past elections in backtests (about −0.10 and +0.20); the live forecast's
  defaults are −0.08 and +0.05; half of a by-election's swing beyond the statewide poll movement is
  carried forward where Labor, the Coalition and the Greens all stood.
