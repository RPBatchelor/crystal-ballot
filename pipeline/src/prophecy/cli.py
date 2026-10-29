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
            cycle=e.election_id,
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
        default_config,
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
    cfg = default_config(n_per_draw)
    typer.echo(f"polling error sd: {cfg.poll_error_sd}")
    summary = summarise(simulate(inputs, shares[:, -1, :], parties, flows, cfg))

    out = PROCESSED_DIR / election
    (out / "forecast_summary.json").write_text(json.dumps(summary, indent=1))
    _echo_summary(summary)


def _echo_summary(summary: dict) -> None:
    o, s = summary["outcome"], summary["seats"]
    typer.echo(f"{summary['n_sims']} sims")
    typer.echo("outcome: " + ", ".join(f"{k} {v:.1%}" for k, v in o.items()))
    for p in ["ALP", "COAL", "LIB", "NAT", "GRN", "ONP", "IND"]:
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
        {"sd": sd, "bias": bias, "elections": table["year"].to_list(), "window_days": 28},
        indent=1))
    with pl.Config(tbl_cols=20, tbl_width_chars=200):
        typer.echo(table.drop("pollsters"))
    typer.echo(f"polling error sd (RMS, floored): {sd}")
    typer.echo(f"poll bias correction (shrunk mean error, subtracted): {bias}")


@app.command("backtest")
def backtest(
    election: str = typer.Option("vic-2018", help="Past election to forecast blind"),
    boundaries: str = typer.Option("assembly2013", help="Vicmap boundary layer in force"),
    refit: bool = typer.Option(True, help="Refit the poll aggregator"),
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
    out = PROCESSED_DIR / f"backtest-{election}"
    run_dir = RUNS / f"backtest-{election}"
    if refit or not (run_dir / "aggregate_draws.npz").exists():
        polls = pl.read_csv(PROCESSED_DIR / f"polls_{election}.csv", try_parse_dates=True,
                            infer_schema_length=None)
        # Only polls published before polling day.
        polls = polls.filter(pl.col("field_end") < e.date)
        run_aggregate(e, prev, polls, out, run_dir, log=typer.echo)
    shares, parties = load_draws(run_dir)

    federal = e.jurisdiction == "FED"
    if federal:
        from prophecy.model.pipeline import federal_flows, federal_inputs

        inputs = federal_inputs(e, prev, log=typer.echo)
        flows = federal_flows(prev, log=typer.echo)
    else:
        inputs = seat_inputs(prev, boundaries=boundaries, onp_geography=False, log=typer.echo)
        flows = flow_weights(prev, inputs, log=typer.echo)
    code = e.jurisdiction.lower()

    # Polling error/bias from elections *before* this one only (no hindsight).
    from prophecy.model.backtest import error_bias, error_sd, poll_error_table
    from prophecy.model.simulate import SimConfig

    hist = poll_error_table(
        pl.read_csv(PROCESSED_DIR / f"polls_{code}_all.csv", try_parse_dates=True, infer_schema_length=None),
        pl.read_csv(PROCESSED_DIR / f"election_results_{code}.csv", try_parse_dates=True)
        .filter(pl.col("year") < e.date.year),
    )
    cfg = default_config()
    cfg.poll_error_sd.update(error_sd(hist, floor=SimConfig().poll_error_sd))
    cfg.poll_bias = error_bias(hist)
    typer.echo(f"pre-{e.date.year} polling error sd {cfg.poll_error_sd}, bias {cfg.poll_bias}")
    res = simulate(inputs, shares[:, -1, :], parties, flows, cfg)
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
    metrics = score(res, actual, incumbents)
    results = pl.read_csv(PROCESSED_DIR / f"election_results_{code}.csv", try_parse_dates=True)
    actual_state = results.filter(pl.col("year") == e.date.year).row(0, named=True)
    metrics["statewide"] = {
        p: {"forecast": summary["statewide_primary"][p], "actual": actual_state[p]}
        for p in ["ALP", "COAL", "GRN"]
    }
    metrics["statewide"]["tpp"] = {"forecast": summary["tpp_alp"],
                                   "actual": actual_state["tpp_alp_vs_coal"]}
    metrics["outcome"] = summary["outcome"]
    (out / "forecast_summary.json").write_text(json.dumps(summary, indent=1))
    (out / "backtest_metrics.json").write_text(json.dumps(metrics, indent=1))

    _echo_summary(summary)
    typer.echo(json.dumps({k: v for k, v in metrics.items() if k != "misses"}, indent=1))
    typer.echo(f"misses ({len(metrics['misses'])}):")
    for m in metrics["misses"]:
        typer.echo(f"  {m['district']}: favourite {m['favourite']} ({m['p_fav']:.0%}), "
                   f"won {m['won']} (p={m['p_won']:.0%})")


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


def _write_tables(tables: dict, out) -> None:
    out.mkdir(parents=True, exist_ok=True)
    for name, df in tables.items():
        df.write_csv(out / f"{name}.csv")
        typer.echo(f"{out.name}/{name}: {df.height} rows")




@app.command("publish-geo")
def publish_geo(
    boundaries: str = typer.Option("assembly2022,assembly2013", help="Comma-separated layers"),
) -> None:
    """Simplify Vicmap boundaries to GeoJSON for the site (needs raw Vicmap downloads)."""
    from prophecy.publish.geo import publish_boundaries

    for b in boundaries.split(","):
        typer.echo(publish_boundaries(b))


if __name__ == "__main__":
    app()
