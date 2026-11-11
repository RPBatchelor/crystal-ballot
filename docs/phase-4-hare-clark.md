# Phase 4: Tasmania and ACT on the site (Hare-Clark)

Status at 11 Nov 2026: **not started**. Phases 0–3 are done and on `main` (`59fd0f9`):
all 20 blind tests rerun leak-free, retrospectives published for every single-member
jurisdiction, NT on NTEC counts, the Victorian forecast live at model 1.0.0, and
per-jurisdiction Coalition labels (Tas and ACT already map to "Liberal").

Tasmania and the ACT elect 5–7 members per division by Hare-Clark. The site's results
and forecast pages assume single-member seats (a winner, a 2CP, a pendulum), so these two
need their own data shape and views. Work on `dev`; merge to `main` only when asked.

## What already exists

**Processed results** (`data/processed/`):

| Election | Files | Notes |
|---|---|---|
| tas-2018, tas-2021, tas-2024, tas-2025 | `districts.csv`, `members.csv`, `primary.csv` (+ `booths.csv` from 2021) | `districts` has seats, quota, formal, informal, elected (`;`-joined) and elected_party |
| act-2016, act-2020, act-2024 | `districts.csv`, `members.csv`, `primary.csv` | `districts` has **no quota or informal**: quota = floor(formal / (seats + 1)) + 1 |

- `primary.csv` is one row per candidate: group (ticket), party, bloc, votes, pct, elected. Tasmania also has `sitting`.
- `members.csv` lists each member elected, in the order elected.
- There are no `tcp.csv` or `tpp.csv` files, and none are meant to exist. That's why `publish_results` (`pipeline/src/prophecy/publish/results.py`) can't be reused as it is.

**Blind tests** (`data/processed/backtest-{tas-2024,tas-2025,act-2024}/`):
- They were rerun clean on 10 and 11 Nov.
- Scores (seat Brier): tas-2024 0.311, tas-2025 0.319, act-2024 0.133.
- `forecast_summary.json` keys are `n_sims`, `seats_total`, `majority`, `outcome`, `seats` (statewide seat quantiles by party), `statewide_primary` and `divisions[]`.
- Each division has `district`, `seats`, `notes`, `expected` (mean seats by party) and `seat_probs` (party → {seat count → probability}). So **per-division seat distributions are already saved**, and nothing needs re-simulating.
- `backtest_metrics.json` keys are `n_divisions`, `seat_brier`, `mean_p_actual_seats`, `median_abs_error`, `seats` (party → median, p90 and actual), `by_division` (division × party → median, mean, actual and p_actual), `statewide` and `outcome`.
- `publish_retrospective` (`publish/forecast.py`) assumes the single-member schema: districts, winners and tcp. It is not called for Tas or the ACT, because those jurisdictions have no next-election id in the publish loop.

**Already published**: `web/static/data/{tas,act}/model.json`. The methodology page already shows their Hare-Clark blind tests. Minor-party display names (IFC, STR, BEL, X_JLN…) sit in the `MINOR` map in `web/src/routes/methodology/+page.svelte`.

**Polls**:
- Tasmania: `polls_tas_all.csv`, plus per-cycle files for 2014, 2018, 2021, 2024 and 2025.
- ACT: `polls_act_all.csv` and `polls_act-2020.csv`. There was no public polling for 2024.

**Elections registry** (`pipeline/src/prophecy/jurisdictions.py`): `act-2028` exists. There is **no tas-2029** yet. Tasmania's next election is due by mid-2029, after the 2025 early election; the date is not fixed, so mark it approximate.

**Site config** (`web/src/lib/jurisdictions.ts`): both have `resultYears: []` and `hasPolls: false`, so their hub pages show only the "on the roadmap" text.

## Steps

1. **Registry.**
   - Add `tas-2029`, with an approximate date and the same boundary set as tas-2025.
   - Check that `prophecy publish --election tas-2029` and `--election act-2028` run: polls should publish, and "no forecast yet" is expected.
2. **Results publisher: `publish/results_hareclark.py`.** Write `web/static/data/{tas,act}/results/{year}.json`. For each division, give:
   - seats, quota, formal and informal votes (ACT: compute the quota; informal is null)
   - members elected, in order, with party
   - first preferences by candidate, grouped by party ticket, with each ticket's votes in quotas (votes ÷ quota)

   Statewide, give seats by party and first-preference share by party. Call it from the `publish` loop when `jurisdiction in ("TAS", "ACT")`, instead of `publish_results`.
3. **Retrospective publisher.** Add `publish_retrospective_hareclark(election)`, writing `forecast/{year}.json` with:
   - `mode: 'retrospective'`
   - statewide `outcome` and `seats` quantiles
   - for each division, `seat_probs` and `expected`, plus the actual seats from `by_division`
   - `actual` (statewide seats by party)

   Choose the function by jurisdiction in `publish`. Add a `system: 'hare-clark'` field to the JSON so the web can switch views on it.
4. **Web types and config.**
   - Add `system?: 'single' | 'hare-clark'` to `Jurisdiction`.
   - TAS: `resultYears: [2018, 2021, 2024, 2025]`, `retroYears: [2024, 2025]`, `hasPolls: true`, `commission: 'TEC'`, `system: 'hare-clark'`.
   - ACT: `resultYears: [2016, 2020, 2024]`, `retroYears: [2024]`, `hasPolls: true`, `commission: 'Elections ACT'`, `system: 'hare-clark'`.
   - Add a `dataNote` for the ACT saying there was no public polling in 2024.
   - Move the methodology page's `MINOR` names into `web/src/lib/parties.ts`.
5. **Web views.** These branch on `j.system === 'hare-clark'` (or the JSON's `system`). Keep the first version to tables and bars, with no maps (maps are Phase 5).
   - **Results page:**
     - seats by party (hemicycle works; the seat count is `seats_total`)
     - for each division, a party quota bar and the members elected
     - no pendulum and no 2CP or swing columns
   - **Division page** (replacing the seat page): candidates by ticket, votes, quotas and elected order.
   - **Forecast and forecast-vs-result:**
     - statewide seat range for each party, with the actual result marked
     - outcome bar: majority, hung or the largest party; check what `outcome` keys the Hare-Clark summary uses
     - a table of each division's seat chances by party, with the actual result marked

     Reuse the `SeatHistogram` styling.
   - **Hub page:** the latest retrospective card. Its sentence ("the favourite won X of Y seats") must change for Hare-Clark: use "median seats against actual" instead.
6. **Polls.** Publish them as they are. Check that `PRIMARY_SERIES` covers Tasmania's parties (Jacqui Lambie Network and independents fall into Others).
7. **Tests.**
   - The shape of the Hare-Clark publisher's output.
   - Quota maths (ACT computed quota against Elections ACT's published quotas for one division).
   - Every `retroYears` entry has a `forecast/{year}.json`.
8. **Verify.** Run `npm run check` and `npm run build`. Then check by eye at 1280px and phone width: tas and act hub, results/2025 or 2024, a division page, forecast/2025 and vs-result.

## Open questions

- **"Majority" in Tasmania:** the Hare-Clark `outcome` keys are `lib_majority`, `alp_majority`, `hung`, `lib_most_seats` and `alp_most_seats`, not the single-member `coal_majority` and `coal_most_seats`. tas-2025 had 98.6% hung and Liberal largest party 82%. The outcome bar needs mapping from `lib_*` to `coal`, and because hung parliaments dominate, the "largest party" figures should lead the headline.
- **2018 Tasmania** has 25 seats (5 × 5). Results pages must not hard-code 35 seats; take it from the data.
- **Live forecasts** for tas-2029 and act-2028 come later (after Phase 6). This phase covers results, polls and blind tests only.
