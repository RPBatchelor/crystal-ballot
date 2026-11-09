"""Command-line entry point: ``uv run prophecy <command>``."""

from __future__ import annotations

import polars as pl
import typer

from prophecy import DATA_DIR, jurisdictions

app = typer.Typer(no_args_is_help=True, add_completion=False)
PROCESSED_DIR = DATA_DIR / "processed"


@app.callback()
def main() -> None:
    """Prophecy election forecasting pipeline."""


@app.command("ingest-polls")
def ingest_polls(
    jurisdiction: str = typer.Option("VIC", help="Jurisdiction code"),
    refresh: bool = typer.Option(True, help="Re-download the Wikipedia pages"),
) -> None:
    """Download and parse voting-intention polls for every cycle in a jurisdiction."""
    from prophecy.ingest.polls import ingest_wikipedia_polls

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    all_polls, all_events, all_results = [], [], []
    for e in jurisdictions.in_jurisdiction(jurisdiction):
        prev = jurisdictions.previous(e)
        if not e.polls_wiki_title or prev is None:
            continue
        # The current cycle has a dedicated polling page; older ones are a section of the
        # election article.
        slug = e.election_id if "Opinion polling" in e.polls_wiki_title else f"{e.election_id}-election"
        df, events, results = ingest_wikipedia_polls(
            e.polls_wiki_title, e.jurisdiction, slug, refresh, window=(prev.date, e.date),
            cycle=e.election_id, oldid=e.polls_wiki_oldid,
        )
        if df.height == 0:
            typer.echo(f"{e.election_id}: no parseable polls, skipped")
            all_results.append(results)
            continue
        df.write_csv(PROCESSED_DIR / f"polls_{e.election_id}.csv")
        if events.height:
            events.write_csv(PROCESSED_DIR / f"events_{e.election_id}.csv")
            all_events.append(events.with_columns(pl.lit(e.election_id).alias("cycle")))
        all_polls.append(df)
        all_results.append(results)
        bad = df.filter((df["primary_sum"] - 100).abs() > 2.5)
        typer.echo(f"{e.election_id}: {df.height} polls ({df['field_end'].min()} to "
                   f"{df['field_end'].max()}), {events.height} events"
                   + (f", {bad.height} not summing to ~100" if bad.height else ""))

    code = jurisdiction.lower()
    pl.concat(all_polls, how="diagonal_relaxed").sort("field_end", descending=True).write_csv(
        PROCESSED_DIR / f"polls_{code}_all.csv")
    if all_events:
        pl.concat(all_events, how="diagonal_relaxed").write_csv(PROCESSED_DIR / f"events_{code}_all.csv")

    # Statewide election results, dated from the registry (pages only give the year).
    dates = {e.date.year: e.date for e in jurisdictions.in_jurisdiction(jurisdiction)}
    results = (
        pl.concat(all_results, how="diagonal_relaxed")
        .with_columns(pl.col("field_end").dt.year().alias("year"))
        .unique(subset="year", keep="first")
        .filter(pl.col("year").is_in(list(dates)))
        .with_columns(pl.col("year").replace_strict(dates, return_dtype=pl.Date).alias("date"))
        .select("year", "date", "ALP", "COAL", "GRN", "ONP", "OTH", "tpp_alp_vs_coal")
        .sort("year")
    )
    # Curated official results fill years with no result row on any poll page.
    curated = DATA_DIR / "curated" / f"election_results_{code}.csv"
    if curated.exists():
        extra = pl.read_csv(curated, try_parse_dates=True).select(results.columns)
        extra = extra.with_columns([pl.col(c).cast(results.schema[c]) for c in results.columns])
        results = pl.concat([results.filter(~pl.col("year").is_in(extra["year"].implode())), extra]).sort("year")
    results.write_csv(PROCESSED_DIR / f"election_results_{code}.csv")
    typer.echo(f"election results: {results['year'].to_list()}")


@app.command("ingest-results")
def ingest_results(year: int = typer.Option(2022, help="Victorian state election year")) -> None:
    """Scrape VEC Legislative Assembly results for an election year."""
    from prophecy.ingest.vec import (
        ARCHIVE_YEARS,
        ingest_vec_archive,
        ingest_vec_assembly,
        ingest_vec_by_elections,
    )

    e = jurisdictions.get(f"vic-{year}")
    if year in ARCHIVE_YEARS:
        # Archived elections: results only (by-elections and DoPs come from the 2022 site).
        _write_tables(ingest_vec_archive(year), PROCESSED_DIR / e.election_id)
        return
    _write_tables(ingest_vec_assembly(year), PROCESSED_DIR / e.election_id)
    # By-elections held after this general election (until the next one).
    _write_tables(ingest_vec_by_elections(since=e.date), PROCESSED_DIR / f"{e.election_id}-by-elections")

    from prophecy.ingest.vec_dop import attach_parties, ingest_dop

    primary = pl.read_csv(PROCESSED_DIR / e.election_id / "primary.csv")
    _write_tables({"dop_transfers": attach_parties(ingest_dop(year), primary)},
                  PROCESSED_DIR / e.election_id)


@app.command("ingest-nominations")
def ingest_nominations_cmd(
    election: str = typer.Option("vic-2026", help="Election id"),
    ballot_order: bool = typer.Option(False, help="Pages are in ballot-draw order: record positions"),
) -> None:
    """Legislative Assembly candidates from the VEC nominations pages."""
    from prophecy import CURATED_DIR
    from prophecy.ingest.vec_nominations import ingest_nominations
    from prophecy.schema.parties import bloc

    members = pl.read_csv(CURATED_DIR / f"members_{election}.csv")
    cands = ingest_nominations(election, members["district"].to_list(), ballot_order=ballot_order)
    path = CURATED_DIR / f"candidates_{election}.csv"
    cands.write_csv(path)
    blocs = cands.with_columns(pl.col("party").map_elements(bloc, return_dtype=pl.String).alias("bloc"))
    typer.echo(f"{cands.height} candidates in {cands['district'].n_unique()} districts -> {path}")
    for b in ("ALP", "COAL", "GRN", "ONP", "IND"):
        n = blocs.filter(pl.col("bloc") == b)["district"].n_unique()
        typer.echo(f"  {b}: {n} districts")


@app.command("ingest-nswec")
def ingest_nswec(years: str = typer.Option("2015,2019,2023", help="Comma-separated NSW years")) -> None:
    """NSWEC Legislative Assembly results: primaries, 2CP, 2PP, preferences, venues."""
    from prophecy import CURATED_DIR
    from prophecy.ingest.nswec import ingest_nswec_assembly

    rows = []
    for y in (int(x) for x in years.split(",")):
        tables = ingest_nswec_assembly(y)
        _write_tables(tables, PROCESSED_DIR / f"nsw-{y}")
        # Statewide result: every seat has a Labor v Coalition count, so the 2PP is exact.
        prim, tpp = tables["primary"], tables["tpp"]
        share = {b: 100 * v / prim["votes"].sum()
                 for b, v in prim.group_by("bloc").agg(pl.col("votes").sum()).iter_rows()}
        rows.append({
            "year": y, "date": jurisdictions.get(f"nsw-{y}").date,
            **{b: round(share[b], 2) if b in share else None for b in ("ALP", "COAL", "GRN", "ONP")},
            "OTH": round(share.get("OTH", 0.0) + share.get("IND", 0.0), 2),
            "tpp_alp_vs_coal": round(100 * tpp["alp_votes"].sum()
                                     / (tpp["alp_votes"].sum() + tpp["coal_votes"].sum()), 2),
            "source": f"NSWEC {y} first preferences; 2PP summed over {tpp.height} seat counts",
        })
    path = CURATED_DIR / "election_results_nsw.csv"
    new = pl.DataFrame(rows)
    if path.exists():
        old = pl.read_csv(path, try_parse_dates=True)
        new = pl.concat([old.filter(~pl.col("year").is_in(new["year"].implode())), new],
                        how="diagonal_relaxed")
    new.sort("year").write_csv(path)
    typer.echo(f"statewide results -> {path}")


@app.command("ingest-ecq")
def ingest_ecq(years: str = typer.Option("2012,2015,2017,2020,2024", help="Comma-separated Queensland years")) -> None:
    """ECQ Legislative Assembly results: primaries, booths, 2CP, preferences."""
    from prophecy.ingest.ecq import ingest_ecq_assembly

    for y in (int(x) for x in years.split(",")):
        tables = ingest_ecq_assembly(y)
        _write_tables(tables, PROCESSED_DIR / f"qld-{y}")
        seats = dict(tables["districts"]["elected_party"].value_counts().iter_rows())
        typer.echo(f"qld-{y} seats: {seats}")


@app.command("ingest-ecsa")
def ingest_ecsa(years: str = typer.Option("2014,2018,2022,2026", help="Comma-separated SA years")) -> None:
    """ECSA House of Assembly results: primaries, polling places, 2CP, preferences (2022 on)."""
    from prophecy.ingest.ecsa import ingest_ecsa_assembly

    for y in (int(x) for x in years.split(",")):
        tables = ingest_ecsa_assembly(y)
        _write_tables(tables, PROCESSED_DIR / f"sa-{y}")
        seats = dict(tables["districts"]["elected_party"].value_counts().iter_rows())
        typer.echo(f"sa-{y} seats: {seats}")


@app.command("ingest-waec")
def ingest_waec(years: str = typer.Option("2008,2013,2017,2021,2025", help="Comma-separated WA years")) -> None:
    """WAEC Legislative Assembly results: primaries, polling places, 2CP, preferences."""
    from prophecy.ingest.waec import ingest_waec_assembly

    for y in (int(x) for x in years.split(",")):
        tables = ingest_waec_assembly(y)
        _write_tables(tables, PROCESSED_DIR / f"wa-{y}")
        seats = dict(tables["districts"]["elected_party"].value_counts().iter_rows())
        typer.echo(f"wa-{y} seats: {seats}")


@app.command("ingest-tec")
def ingest_tec(years: str = typer.Option("2018,2021,2024,2025", help="Comma-separated Tasmanian years")) -> None:
    """TEC House of Assembly results (Hare-Clark): primaries, members elected, booths."""
    from prophecy.ingest.tec import ingest_tec_assembly

    for y in (int(x) for x in years.split(",")):
        tables = ingest_tec_assembly(y)
        _write_tables(tables, PROCESSED_DIR / f"tas-{y}")
        seats = dict(tables["members"]["party"].value_counts().iter_rows())
        typer.echo(f"tas-{y} seats: {seats}")


@app.command("ingest-elections-act")
def ingest_elections_act(years: str = typer.Option("2016,2020,2024", help="Comma-separated ACT years")) -> None:
    """Elections ACT Legislative Assembly results (Hare-Clark): primaries, members elected."""
    from prophecy.ingest.elections_act import ingest_act_assembly

    for y in (int(x) for x in years.split(",")):
        tables = ingest_act_assembly(y)
        _write_tables(tables, PROCESSED_DIR / f"act-{y}")
        typer.echo(f"act-{y} seats: {dict(tables['members']['party'].value_counts().iter_rows())}")


@app.command("ingest-nt")
def ingest_nt(
    years: str = typer.Option("2016,2020,2024", help="Comma-separated NT years"),
    refresh: bool = typer.Option(True, help="Re-download the Wikipedia pages"),
) -> None:
    """NT Legislative Assembly results (Wikipedia's per-division tables of the NTEC counts),
    and the notional baseline after a redistribution."""
    from prophecy.ingest.wiki_nt import ingest_nt_assembly, notional_from_changes

    for y in (int(x) for x in years.split(",")):
        tables = ingest_nt_assembly(y, refresh)
        _write_tables(tables, PROCESSED_DIR / f"nt-{y}")
        typer.echo(f"nt-{y} seats: {dict(tables['districts']['elected_party'].value_counts().iter_rows())}")
        e = jurisdictions.get(f"nt-{y}")
        prev = jurisdictions.previous(e)
        if prev and e.boundary_set != prev.boundary_set and (PROCESSED_DIR / prev.election_id / "districts.csv").exists():
            notional = notional_from_changes(e.election_id, pl.read_csv(PROCESSED_DIR / prev.election_id / "districts.csv"))
            _write_tables(notional, PROCESSED_DIR / f"{e.election_id}-notional")
            typer.echo(f"{e.election_id} notional holders: "
                       f"{dict(notional['districts']['elected_party'].value_counts().iter_rows())}")


@app.command("notional")
@app.command("nsw-notional", hidden=True)
def notional(election: str = typer.Option("nsw-2023", help="Election on new boundaries")) -> None:
    """Previous result re-cut onto this election's districts (by venue): NSW, WA, SA."""
    from prophecy.model.states import notional_baseline

    e = jurisdictions.get(election)
    tables = notional_baseline(jurisdictions.previous(e), e, log=typer.echo)
    _write_tables(tables, PROCESSED_DIR / f"{election}-notional")
    d = tables["districts"]
    typer.echo(f"notional seats: {dict(d['elected_party'].value_counts().iter_rows())}")


@app.command("ingest-aec")
def ingest_aec(years: str = typer.Option("2022,2025", help="Comma-separated federal years")) -> None:
    """AEC House results (and the notional baseline for elections on new boundaries)."""
    from prophecy.ingest.aec import download, ingest_aec_house, notional_baseline

    for y in (int(x) for x in years.split(",")):
        download(y)
        _write_tables(ingest_aec_house(y), PROCESSED_DIR / f"fed-{y}")
        if y == 2025:  # 2025 redistribution: NSW, Vic and WA boundaries changed
            _write_tables(notional_baseline(y), PROCESSED_DIR / f"fed-{y}-notional")


@app.command("aggregate")
def aggregate(
    election: str = typer.Option("vic-2026", help="Election id"),
    iter_sampling: int = typer.Option(1000, help="Post-warmup draws per chain"),
) -> None:
    """Fit the Bayesian poll aggregator and save trend, house effects and draws."""
    from prophecy.model.pipeline import RUNS, run_aggregate

    e = jurisdictions.get(election)
    prev = jurisdictions.previous(e)
    polls = pl.read_csv(PROCESSED_DIR / f"polls_{election}.csv", try_parse_dates=True)
    if election.endswith("-next"):
        # No election date yet: model the trend only a few weeks past the latest poll
        # rather than across a long, data-free stretch to a placeholder date.
        from dataclasses import replace
        from datetime import timedelta

        e = replace(e, date=polls["field_end"].max() + timedelta(weeks=8))
    run_aggregate(e, prev, polls, PROCESSED_DIR / election, RUNS / election, log=typer.echo,
                  iter_sampling=iter_sampling)
    typer.echo(f"wrote {PROCESSED_DIR / election / 'poll_trend.csv'}")
    if e.jurisdiction == "FED":
        # No seat forecast for this cycle yet: add the model-implied 2PP trend here, using
        # flows from the last election's full distributions.
        import numpy as np

        from prophecy.model.pipeline import add_tpp_trend, federal_flows, load_draws

        shares, parties = load_draws(RUNS / election)
        prim = pl.read_csv(PROCESSED_DIR / prev.election_id / "primary.csv")
        by = dict(prim.group_by("bloc").agg(pl.col("votes").sum()).iter_rows())
        ind_frac = by.get("IND", 0) / (by.get("IND", 0) + by.get("OTH", 0))
        flows = federal_flows(prev, log=typer.echo)
        add_tpp_trend(shares, parties, flows, PROCESSED_DIR / election / "poll_trend.csv",
                      float(np.clip(ind_frac, 0, 1)))
        typer.echo("added model-implied 2PP trend")


@app.command("forecast")
def forecast(
    election: str = typer.Option("vic-2026", help="Election id"),
    n_per_draw: int = typer.Option(5, help="Simulations per aggregator draw"),
) -> None:
    """Run the seat simulation from saved aggregator draws."""
    import json

    from prophecy.model.pipeline import (
        RUNS,
        add_tpp_trend,
        flow_weights,
        ind_fraction,
        load_draws,
        seat_inputs,
    )
    from prophecy.model.simulate import simulate, summarise

    e = jurisdictions.get(election)
    prev = jurisdictions.previous(e)
    shares, parties = load_draws(RUNS / election)
    inputs = seat_inputs(prev, boundaries="assembly2022", onp_geography="ONP" in parties,
                         log=typer.echo, election=e)
    flows = flow_weights(prev, inputs, log=typer.echo)
    add_tpp_trend(shares, parties, flows, PROCESSED_DIR / election / "poll_trend.csv",
                  ind_fraction(inputs))
    from prophecy import CURATED_DIR

    ballot_path = CURATED_DIR / f"candidates_{election}.csv"
    ballot = pl.read_csv(ballot_path, infer_schema_length=None) if ballot_path.exists() else None
    if ballot is not None and ballot.height:
        # As in the backtests: first-time independents on the ballot polled like earlier ones.
        from prophecy.model import new_candidates

        inputs.new_ind = new_candidates.count_new_on_ballot(ballot, prev, inputs.districts)
        inputs.new_ind_pool = new_candidates.pool(e.date)
        typer.echo(f"first-time independents: {int(inputs.new_ind.sum())} on the ballot; "
                   f"{len(inputs.new_ind_pool)} earlier ones to draw from")
    # Settings estimated from every election held so far (as in the backtests).
    cfg = _historical_config(e)
    cfg.n_per_draw = n_per_draw
    typer.echo(f"polling error sd: {cfg.poll_error_sd}")
    from datetime import UTC, datetime

    import numpy as np

    from prophecy.model.simulate import sim_arrays

    res = simulate(inputs, shares[:, -1, :], parties, flows, cfg)
    summary = summarise(res)
    # Stamps the summary and its simulations, so publishing can tell they belong together.
    summary["simulated_at"] = datetime.now(UTC).isoformat(timespec="seconds")
    # The simulations themselves (a few MB) stay out of git; `publish` packs them for the site.
    np.savez_compressed(RUNS / election / "forecast_sims.npz",
                        simulated_at=np.array(summary["simulated_at"]), **sim_arrays(res))

    out = PROCESSED_DIR / election
    (out / "forecast_summary.json").write_text(json.dumps(summary, indent=1))
    _echo_summary(summary)


def _echo_summary(summary: dict) -> None:
    o, s = summary["outcome"], summary["seats"]
    typer.echo(f"{summary['n_sims']} sims")
    typer.echo("outcome: " + ", ".join(f"{k} {v:.1%}" for k, v in o.items()))
    for p in ["ALP", "COAL", "LIB", "NAT", "LNP", "CLP", "GRN", "ONP", "IND"]:
        if p in s:
            typer.echo(f"  {p:5s} seats median {s[p][2]:.0f}  90% [{s[p][0]:.0f}, {s[p][4]:.0f}]")
    typer.echo(f"statewide 2PP ALP v COAL: {summary['tpp_alp']}")


@app.command("poll-error")
def poll_error(jurisdiction: str = typer.Option("VIC", help="Jurisdiction code")) -> None:
    """Historical final-poll error table, and the polling-error sizes it implies."""
    import json

    from prophecy.model.backtest import error_bias, error_sd, poll_error_table
    from prophecy.model.simulate import SimConfig

    code = jurisdiction.lower()
    polls = pl.read_csv(PROCESSED_DIR / f"polls_{code}_all.csv", try_parse_dates=True,
                        infer_schema_length=None)
    results = pl.read_csv(PROCESSED_DIR / f"election_results_{code}.csv", try_parse_dates=True)
    table = poll_error_table(polls, results)
    table.write_csv(PROCESSED_DIR / f"poll_error_{code}.csv")
    # The provisional values act as a floor: five elections is a small sample.
    sd = error_sd(table, floor=SimConfig().poll_error_sd)
    bias = error_bias(table)
    (PROCESSED_DIR / f"poll_error_{code}.json").write_text(json.dumps(
        {"sd": sd, "bias": bias, "elections": table["year"].to_list() if table.height else [],
         "window_days": 28},
        indent=1))
    if not table.height:
        typer.echo("no election had polls in its final four weeks: provisional error sizes")
    with pl.Config(tbl_cols=20, tbl_width_chars=200):
        typer.echo(table.drop("pollsters") if table.height else table)
    typer.echo(f"polling error sd (RMS, floored): {sd}")
    typer.echo(f"poll bias correction (shrunk mean error, subtracted): {bias}")


@app.command("backtest")
def backtest(
    election: str = typer.Option("vic-2018", help="Past election to forecast blind"),
    boundaries: str = typer.Option("assembly2013", help="Vicmap boundary layer in force"),
    refit: bool = typer.Option(True, help="Refit the poll aggregator"),
    hand_set: bool = typer.Option(False, "--hand-set", help="Previous hand-set seat noise and per-state "
                                  "floored polling error, for comparison (writes to backtest-<id>-handset)"),
    aggregator: str = typer.Option("poll_aggregator", help="Stan poll model: poll_aggregator, or "
                                   "poll_aggregator_corr (correlated trends, drifting house effects; "
                                   "writes to backtest-<id>-corr)"),
) -> None:
    """Forecast a past election using only information available beforehand, and score it."""
    import json

    from prophecy.model.backtest import score
    from prophecy.model.pipeline import (
        RUNS,
        default_config,
        flow_weights,
        load_draws,
        run_aggregate,
        seat_inputs,
    )
    from prophecy.model.simulate import simulate, summarise

    e = jurisdictions.get(election)
    prev = jurisdictions.previous(e)
    suffix = "-corr" if aggregator == "poll_aggregator_corr" else ""
    out = PROCESSED_DIR / (f"backtest-{election}{suffix}-handset" if hand_set else f"backtest-{election}{suffix}")
    run_dir = RUNS / f"backtest-{election}{suffix}"
    polls_path = PROCESSED_DIR / f"polls_{election}.csv"
    polls = (pl.read_csv(polls_path, try_parse_dates=True, infer_schema_length=None)
             .filter(pl.col("field_end") < e.date)  # only polls published before polling day
             if polls_path.exists() else None)
    no_polls = polls is None or polls.height < MIN_POLLS
    if refit or not (run_dir / "aggregate_draws.npz").exists():
        if no_polls:
            from prophecy.model.pipeline import swing_prior

            swing_prior(e, prev, out, run_dir, polls, log=typer.echo)
        else:
            run_aggregate(e, prev, polls, out, run_dir, log=typer.echo, model_name=aggregator)
    shares, parties = load_draws(run_dir)
    if e.jurisdiction in ("TAS", "ACT"):
        _backtest_tas(e, prev, shares, parties, out, no_polls, hand_set)
        return

    federal = e.jurisdiction == "FED"
    exhaust = None  # optional preferential voting (NSW) only; Queensland and WA are full preferential
    if federal:
        from prophecy.model.pipeline import federal_flows, federal_inputs

        inputs = federal_inputs(e, prev, log=typer.echo)
        flows = federal_flows(prev, log=typer.echo)
    elif e.jurisdiction in ("NSW", "QLD", "WA", "SA", "NT"):
        from prophecy.model.states import state_flows, state_inputs

        inputs = state_inputs(e, prev, log=typer.echo, federal_onp=not hand_set)
        if e.jurisdiction == "NT" or not (PROCESSED_DIR / prev.election_id / "dop_transfers.csv").exists():
            # No distributions published: the jurisdiction's federal divisions'
            from prophecy.model.hareclark import tas_flows

            flows, exhaust = state_flows(prev, log=typer.echo, weights=tas_flows(e, log=typer.echo))
        else:
            flows, exhaust = state_flows(prev, log=typer.echo)
    else:
        inputs = seat_inputs(prev, boundaries=boundaries, onp_geography=False, log=typer.echo)
        flows = flow_weights(prev, inputs, log=typer.echo)
    if not hand_set:
        from prophecy.model import new_candidates

        inputs.new_ind = new_candidates.count_new(e, prev, inputs.districts)
        inputs.new_ind_pool = new_candidates.pool(e.date)
        typer.echo(f"first-time independents: {int(inputs.new_ind.sum())} on the ballot; "
                   f"{len(inputs.new_ind_pool)} earlier ones to draw from")
    code = e.jurisdiction.lower()
    # Polling error/bias from elections *before* this one only (no hindsight).
    cfg = _handset_config(e, no_polls) if hand_set else _historical_config(e, no_polls)
    res = simulate(inputs, shares[:, -1, :], parties, flows, cfg, exhaust=exhaust)
    summary = summarise(res)

    actual_df = pl.read_csv(PROCESSED_DIR / election / "districts.csv")
    actual = dict(actual_df.select("district", "elected_party").iter_rows())
    if federal:
        # The notional baseline has no Liberal/National split: score the Coalition as one
        # bloc, and minor-party members (KAP, Centre Alliance) with independents.
        from prophecy.schema.parties import bloc as _bloc

        inputs.coal_party = ["COAL"] * len(inputs.districts)
        actual = {d: ("COAL" if _bloc(p) == "COAL" else _bloc(p)) for d, p in actual.items()}
    incumbents = {d: ("COAL" if federal and h in ("LIB", "NAT", "LNP", "CLP") else h)
                  for d, h in zip(inputs.districts, inputs.incumbent)}
    if federal:
        from prophecy.schema.parties import bloc as _bloc

        incumbents = {d: _bloc(h) for d, h in incumbents.items()}
    else:
        # Minor-party members simulated as independents (KAP in Queensland) are scored as
        # independents; Coalition parties keep their own labels.
        from prophecy.schema.parties import bloc as _bloc

        as_sim = lambda p: p if _bloc(p) == "COAL" else _bloc(p)
        actual = {d: as_sim(p) for d, p in actual.items()}
        incumbents = {d: as_sim(h) for d, h in incumbents.items()}
    metrics = score(res, actual, incumbents)
    results = pl.read_csv(PROCESSED_DIR / f"election_results_{code}.csv", try_parse_dates=True)
    actual_state = results.filter(pl.col("year") == e.date.year).row(0, named=True)
    from prophecy.model.backtest import pendulum_accuracy, seat_vote_scores

    prim = pl.read_csv(PROCESSED_DIR / election / "primary.csv", infer_schema_length=None)
    prim = prim.with_columns(pl.col("bloc").replace({"LNP": "COAL"}))
    seat_pct = (prim.group_by("district", "bloc").agg(pl.col("votes").sum())
                .with_columns((100 * pl.col("votes") / pl.col("votes").sum().over("district")).alias("pct")))
    metrics["seat_vote"] = seat_vote_scores(res, seat_pct)
    base_tpp = _baseline_tpp(e, prev)
    prev_state = results.filter(pl.col("year") == prev.date.year)
    if base_tpp and prev_state.height and prev_state["tpp_alp_vs_coal"][0] is not None:
        swing = summary["tpp_alp"][1] - prev_state["tpp_alp_vs_coal"][0]
        metrics["pendulum_accuracy"] = pendulum_accuracy(base_tpp, swing, actual, incumbents)
    metrics["statewide"] = {
        p: {"forecast": summary["statewide_primary"][p], "actual": actual_state[p]}
        for p in ["ALP", "COAL", "GRN"]
    }
    metrics["statewide"]["tpp"] = {"forecast": summary["tpp_alp"],
                                   "actual": actual_state["tpp_alp_vs_coal"]}
    metrics["outcome"] = summary["outcome"]
    out.mkdir(parents=True, exist_ok=True)
    (out / "forecast_summary.json").write_text(json.dumps(summary, indent=1))
    (out / "backtest_metrics.json").write_text(json.dumps(metrics, indent=1))
    _write_manifest(out, e, cfg, {"hand_set": hand_set, "no_polls": no_polls})

    _echo_summary(summary)
    typer.echo(json.dumps({k: v for k, v in metrics.items() if k not in ("misses", "calibration")}, indent=1))
    typer.echo(f"misses ({len(metrics['misses'])}):")
    for m in metrics["misses"]:
        typer.echo(f"  {m['district']}: favourite {m['favourite']} ({m['p_fav']:.0%}), "
                   f"won {m['won']} (p={m['p_won']:.0%})")


def _write_manifest(out, e, cfg, extra: dict | None = None) -> None:
    """Record what produced a backtest: code version (and whether the tree had
    uncommitted changes), a hash of every input file it could have read, and the full
    simulation settings."""
    import dataclasses
    import hashlib
    import json
    import subprocess
    from datetime import datetime, timezone

    def git(*args: str) -> str:
        try:
            return subprocess.run(["git", *args], capture_output=True, text=True, check=True,
                                  cwd=PROCESSED_DIR).stdout.strip()
        except (OSError, subprocess.CalledProcessError):
            return ""

    prev = jurisdictions.previous(e)
    code = e.jurisdiction.lower()
    candidates = [PROCESSED_DIR / e.election_id, PROCESSED_DIR / prev.election_id,
                  PROCESSED_DIR / f"{e.election_id}-notional", PROCESSED_DIR / f"polls_{e.election_id}.csv",
                  PROCESSED_DIR / f"election_results_{code}.csv"]
    inputs = {}
    for path in candidates:
        for f in sorted([path] if path.is_file() else path.glob("*.csv") if path.is_dir() else []):
            inputs[str(f.relative_to(PROCESSED_DIR))] = hashlib.sha256(f.read_bytes()).hexdigest()[:16]
    manifest = {
        "election": e.election_id, "run_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        # Uncommitted changes to the model code or hand-curated inputs (outputs excluded).
        "git_commit": git("rev-parse", "HEAD"),
        "uncommitted_changes": bool(git("status", "--porcelain", "--", "../../pipeline/src", "../curated")),
        "config": dataclasses.asdict(cfg), "inputs": inputs, **(extra or {}),
    }
    out.mkdir(parents=True, exist_ok=True)
    (out / "manifest.json").write_text(json.dumps(manifest, indent=1, default=str))


def _baseline_tpp(e, prev) -> dict[str, float]:
    """Each seat's Labor v Coalition 2PP before ``e``: the notional one after a
    redistribution, else the previous result's."""
    nd = PROCESSED_DIR / f"{e.election_id}-notional" / "districts.csv"
    if e.boundary_set != prev.boundary_set:
        if nd.exists():
            d = pl.read_csv(nd)
            if "alp_tpp" in d.columns:
                return {k: v for k, v in d.select("district", "alp_tpp").iter_rows() if v is not None}
        return {}
    path = PROCESSED_DIR / prev.election_id / "tpp.csv"
    if not path.exists():
        return {}
    return dict(pl.read_csv(path).select("district", "alp_tpp").iter_rows())


MIN_POLLS = 3  # fewer public polls than this: forecast from the previous result alone


def _handset_config(e, no_polls: bool = False) -> "SimConfig":
    """The settings before the 2026 review: hand-set seat noise, and this jurisdiction's
    own polling error, floored, with independent errors by party."""
    from prophecy.model.backtest import error_bias, error_sd, poll_error_table
    from prophecy.model.pipeline import default_config
    from prophecy.model.simulate import SimConfig

    code = e.jurisdiction.lower()
    hist = poll_error_table(
        pl.read_csv(PROCESSED_DIR / f"polls_{code}_all.csv", try_parse_dates=True, infer_schema_length=None),
        pl.read_csv(PROCESSED_DIR / f"election_results_{code}.csv", try_parse_dates=True)
        .filter(pl.col("year") < e.date.year),
    )
    cfg = default_config()
    if no_polls:
        cfg.poll_error_sd, cfg.poll_bias = {}, {}
        return cfg
    cfg.poll_error_sd.update(error_sd(hist, floor=SimConfig().poll_error_sd))
    cfg.poll_bias = error_bias(hist)
    return cfg


def _historical_config(e, no_polls: bool = False) -> "SimConfig":
    """Simulation settings estimated from elections before ``e`` only: polling error and
    bias pooled over every jurisdiction (shrunk toward ``e``'s own record), and the
    seat-swing terms.

    Without polls the swing prior already carries the statewide uncertainty, so no
    polling error or bias is added."""
    from prophecy.model.backtest import pooled_poll_error
    from prophecy.model.pipeline import default_config

    cfg = default_config()
    # Seat-swing terms (single-member seats; Hare-Clark divisions are five-to-seven-
    # member electorates, not comparable).
    if e.jurisdiction not in ("TAS", "ACT"):
        from prophecy.model import swing_fit

        swing_fit.apply(cfg, swing_fit.fit(e.date, e.jurisdiction, log=typer.echo))
    if no_polls:
        cfg.poll_error_sd, cfg.poll_bias = {}, {}
        return cfg
    err = pooled_poll_error(e.date, e.jurisdiction, PROCESSED_DIR)
    cfg.poll_error_sd.update(err["sd"])
    cfg.poll_bias = err["bias"]
    cfg.poll_error_corr, cfg.poll_error_corr_parties = err["corr"], err["parties"]
    typer.echo(f"pre-{e.date.year} polling error ({err['n_elections']} elections, {err['n_own']} own): "
               f"sd {err['sd']}, bias {err['bias']}, corr {err['corr']}")
    return cfg


def _backtest_tas(e, prev, shares, parties, out, no_polls: bool = False, hand_set: bool = False) -> None:
    """Blind Hare-Clark forecast of a Tasmanian election, scored on the members elected."""
    import json

    from prophecy.model.hareclark import score_tas, simulate_tas, summarise_tas, tas_flows, tas_inputs

    divisions = tas_inputs(e, prev, log=typer.echo)
    flows = tas_flows(e, log=typer.echo)
    if hand_set:
        cfg = _handset_config(e, no_polls)
        res = simulate_tas(divisions, shares[:, -1, :], parties, flows, cfg)
    else:
        from prophecy.model.hareclark_pools import new_ind_pool, new_party_pool

        cfg = _historical_config(e, no_polls)
        res = simulate_tas(divisions, shares[:, -1, :], parties, flows, cfg,
                           new_party_pool=new_party_pool(e.date), new_ind_pool=new_ind_pool(e.date))
    summary = summarise_tas(res)
    metrics = score_tas(res, pl.read_csv(PROCESSED_DIR / e.election_id / "members.csv"))
    actual = pl.read_csv(PROCESSED_DIR / f"election_results_{e.jurisdiction.lower()}.csv", try_parse_dates=True).filter(
        pl.col("year") == e.date.year).row(0, named=True)
    metrics["statewide"] = {p: {"forecast": summary["statewide_primary"][p], "actual": actual[p]}
                            for p in ["ALP", "COAL", "GRN"]}
    metrics["outcome"] = summary["outcome"]
    out.mkdir(parents=True, exist_ok=True)
    (out / "forecast_summary.json").write_text(json.dumps(summary, indent=1))
    (out / "backtest_metrics.json").write_text(json.dumps(metrics, indent=1))
    _write_manifest(out, e, cfg, {"hand_set": hand_set, "no_polls": no_polls})

    typer.echo(f"{summary['n_sims']} sims; outcome: "
               + ", ".join(f"{k} {v:.1%}" for k, v in summary["outcome"].items()))
    for p, t in sorted(metrics["seats"].items(), key=lambda kv: -kv[1]["median"]):
        typer.echo(f"  {p:6s} seats median {t['median']:.0f}  90% [{t['p90'][0]:.0f}, {t['p90'][1]:.0f}]"
                   f"  actual {t['actual']}")
    typer.echo("statewide: " + ", ".join(f"{p} {v['forecast'][1]} (actual {v['actual']})"
                                         for p, v in metrics["statewide"].items()))
    typer.echo(f"seat Brier {metrics['seat_brier']}, mean P(actual count) {metrics['mean_p_actual_seats']}, "
               f"mean |median - actual| {metrics['median_abs_error']}")
    for r in metrics["by_division"]:
        if r["median"] != r["actual"]:
            typer.echo(f"  {r['division']:9s} {r['party']:22s} forecast {r['median']:.0f} "
                       f"(mean {r['mean']}), won {r['actual']} (p={r['p_actual']:.0%})")


@app.command("publish")
def publish(election: str = typer.Option("vic-2026", help="Election id")) -> None:
    """Write website data files for an election."""
    from prophecy.publish.forecast import publish_forecast
    from prophecy.publish.polls import publish_polls
    from prophecy.publish.results import publish_results

    e = jurisdictions.get(election)
    typer.echo(publish_polls(e))
    typer.echo(publish_forecast(e) or "no forecast yet")
    from prophecy.publish.model_eval import publish_model_eval

    typer.echo(publish_model_eval(e.jurisdiction) or "no model evaluation yet")
    # Blind backtests, published as retrospective forecasts alongside the result.
    from prophecy.publish.forecast import publish_retrospective

    for past in jurisdictions.in_jurisdiction(e.jurisdiction):
        if (PROCESSED_DIR / f"backtest-{past.election_id}").exists():
            typer.echo(publish_retrospective(past))
    # Historical results for every past election in the same jurisdiction we have ingested.
    for past in jurisdictions.ELECTIONS.values():
        if past.jurisdiction == e.jurisdiction and (PROCESSED_DIR / past.election_id / "districts.csv").exists():
            typer.echo(publish_results(past))


@app.command("backfill-history")
def backfill_history(election: str = typer.Option("vic-2026", help="Election id")) -> None:
    """Forecast history from every committed forecast summary (last commit each day)."""
    import json
    import subprocess

    from prophecy import WEB_DATA_DIR
    from prophecy.jurisdictions import site_code
    from prophecy.publish.sims import history_entry, local_date, upsert_history

    e = jurisdictions.get(election)
    rel = f"data/processed/{election}/forecast_summary.json"
    root = PROCESSED_DIR.parent.parent
    log = subprocess.run(["git", "log", "--reverse", "--format=%H %cI", "--", rel],
                         cwd=root, capture_output=True, text=True, check=True).stdout.split("\n")
    path = WEB_DATA_DIR / site_code(e.jurisdiction) / "forecast" / f"{e.date.year}-history.json"
    n = 0
    for line in filter(None, log):
        sha, when = line.split()
        shown = subprocess.run(["git", "show", f"{sha}:{rel}"], cwd=root, capture_output=True, text=True)
        if shown.returncode:
            continue
        summary = json.loads(shown.stdout)
        stamp = summary.get("simulated_at") or when
        upsert_history(path, history_entry(summary, local_date(stamp, e.jurisdiction)))
        n += 1
    history = json.loads(path.read_text(encoding="utf-8"))
    typer.echo(f"{n} committed forecasts -> {len(history)} days in {path}")


def _write_tables(tables: dict, out) -> None:
    out.mkdir(parents=True, exist_ok=True)
    for name, df in tables.items():
        df.write_csv(out / f"{name}.csv")
        typer.echo(f"{out.name}/{name}: {df.height} rows")




@app.command("ingest-boundaries")
def ingest_boundaries(
    boundaries: str = typer.Option("nsw-2021,nsw-2013,qld-2017,qld-2008", help="Comma-separated boundary sets"),
) -> None:
    """Download NSW and Queensland electoral district boundaries (state spatial services)."""
    from prophecy.ingest.boundaries import fetch_boundaries

    for b in boundaries.split(","):
        typer.echo(fetch_boundaries(b))


@app.command("publish-geo")
def publish_geo(
    boundaries: str = typer.Option("assembly2022,assembly2013", help="Comma-separated layers"),
    jurisdiction: str = typer.Option("VIC", help="VIC (Vicmap layers), NSW or QLD (boundary sets)"),
) -> None:
    """Simplify boundaries to GeoJSON for the site (needs the raw boundary downloads)."""
    from prophecy.publish.geo import publish_boundaries

    for b in boundaries.split(","):
        typer.echo(publish_boundaries(b, jurisdiction))


if __name__ == "__main__":
    app()
