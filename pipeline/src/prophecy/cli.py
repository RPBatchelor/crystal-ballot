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
    election: str = typer.Option("vic-2026", help="Election id, e.g. vic-2026"),
    refresh: bool = typer.Option(True, help="Re-download the Wikipedia page"),
) -> None:
    """Download and parse voting-intention polls for an election."""
    from prophecy.ingest.polls import ingest_wikipedia_polls

    e = jurisdictions.get(election)
    if not e.polls_wiki_title:
        raise typer.BadParameter(f"No poll source configured for {election}")
    df, events = ingest_wikipedia_polls(e.polls_wiki_title, e.jurisdiction, election, refresh)

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    df.write_csv(PROCESSED_DIR / f"polls_{election}.csv")
    if events.height:
        events.write_csv(PROCESSED_DIR / f"events_{election}.csv")

    bad = df.filter((df["primary_sum"] - 100).abs() > 2.5)
    typer.echo(f"{df.height} polls, {events.height} events -> {PROCESSED_DIR}")
    typer.echo(f"latest: {df['field_end'].max()}  earliest: {df['field_end'].min()}")
    if bad.height:
        typer.echo(f"WARNING: {bad.height} polls with primaries not summing to ~100:")
        typer.echo(str(bad.select("field_end", "pollster", "primary_sum")))


@app.command("ingest-results")
def ingest_results(year: int = typer.Option(2022, help="Victorian state election year")) -> None:
    """Scrape VEC Legislative Assembly results for an election year."""
    from prophecy.ingest.vec import ingest_vec_assembly, ingest_vec_by_elections

    e = jurisdictions.get(f"vic-{year}")
    _write_tables(ingest_vec_assembly(year), PROCESSED_DIR / e.election_id)
    # By-elections held after this general election (until the next one).
    _write_tables(ingest_vec_by_elections(since=e.date), PROCESSED_DIR / f"{e.election_id}-by-elections")

    from prophecy.ingest.vec_dop import attach_parties, ingest_dop

    primary = pl.read_csv(PROCESSED_DIR / e.election_id / "primary.csv")
    _write_tables({"dop_transfers": attach_parties(ingest_dop(year), primary)},
                  PROCESSED_DIR / e.election_id)


@app.command("aggregate")
def aggregate(
    election: str = typer.Option("vic-2026", help="Election id"),
    previous: str = typer.Option("vic-2022", help="Previous election (random-walk anchor)"),
) -> None:
    """Fit the Bayesian poll aggregator and save trend, house effects and draws."""
    import json

    import numpy as np

    from prophecy.model.aggregate import PARTIES, fit, summarise

    e, prev = jurisdictions.get(election), jurisdictions.get(previous)
    polls = pl.read_csv(PROCESSED_DIR / f"polls_{election}.csv", try_parse_dates=True)
    # Start from the previous result; ONP barely contested the 2022 Assembly, so its
    # start uses its federal-2022 Victorian level (~3%) under a vague prior.
    share = pl.read_csv(PROCESSED_DIR / previous / "primary.csv").group_by("bloc").agg(
        pl.col("votes").sum()
    )
    total = share["votes"].sum()
    start = {b: 100 * v / total for b, v in share.iter_rows()}
    start = {"ALP": start["ALP"], "COAL": start["COAL"], "GRN": start["GRN"], "ONP": 3.0,
             "OTH": 100 - start["ALP"] - start["COAL"] - start["GRN"] - 3.0}

    f = fit(polls, prev, e, start)
    diag = {k: v for k, v in f.diagnostics.items() if k != "report"}
    typer.echo(f"diagnostics: {diag}")
    if diag["max_rhat"] > 1.01 or diag["divergences"] > 0:
        typer.echo("WARNING: sampler diagnostics failed thresholds", err=True)

    # Persist draws first so post-processing failures never require a refit.
    run_dir = DATA_DIR.parent / "runs" / election
    run_dir.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(run_dir / "aggregate_draws.npz", shares=f.shares.astype(np.float32),
                        parties=np.array(PARTIES))
    out = PROCESSED_DIR / election
    out.mkdir(parents=True, exist_ok=True)
    f.house.write_csv(out / "house_effects.csv")
    (out / "aggregate_meta.json").write_text(json.dumps(
        {"diagnostics": diag, "start_share": start, "pollsters": f.pollsters,
         "weeks": [w.isoformat() for w in f.weeks]}, indent=1))
    summarise(f, polls).write_csv(out / "poll_trend.csv")
    typer.echo(f"wrote {out / 'poll_trend.csv'}")


@app.command("forecast")
def forecast(
    election: str = typer.Option("vic-2026", help="Election id"),
    previous: str = typer.Option("vic-2022", help="Election supplying seat baselines"),
    n_per_draw: int = typer.Option(5, help="Simulations per aggregator draw"),
) -> None:
    """Run the seat simulation from saved aggregator draws."""
    import json

    import numpy as np

    from prophecy.ingest.federal_xwalk import district_regions, federal_by_state_district
    from prophecy.ingest.vec import canonical_district
    from prophecy.model.preferences import (
        IDX,
        apply_onp_targets,
        calibrate_to_results,
        estimate_weights,
    )
    from prophecy.model.simulate import SimConfig, build_inputs, simulate, summarise
    from prophecy.schema.parties import bloc

    run_dir = DATA_DIR.parent / "runs" / election
    agg = np.load(run_dir / "aggregate_draws.npz")
    parties = [str(p) for p in agg["parties"]]
    election_day = agg["shares"][:, -1, :]

    base_dir = PROCESSED_DIR / previous
    primary = pl.read_csv(base_dir / "primary.csv")
    districts = pl.read_csv(base_dir / "districts.csv")

    federal = federal_by_state_district().with_columns(
        pl.col("district").map_elements(canonical_district, return_dtype=pl.String)
    )
    federal.write_csv(base_dir / "federal2025_by_district.csv")
    regions = district_regions().with_columns(
        pl.col("district").map_elements(canonical_district, return_dtype=pl.String)
    )
    missing = set(districts["district"]) - set(federal["district"])
    if missing:
        typer.echo(f"WARNING: no federal booths matched for {sorted(missing)}")

    # Seats that changed hands at by-elections are held by the by-election winner.
    by_dir = PROCESSED_DIR / f"{previous}-by-elections"
    holders = {}
    if by_dir.exists():
        holders = dict(pl.read_csv(by_dir / "districts.csv").select("district", "elected_party").iter_rows())

    transfers = pl.read_csv(base_dir / "dop_transfers.csv").filter(pl.col("count") > 0).with_columns(
        pl.col("from_party").map_elements(bloc, return_dtype=pl.String).alias("from_bloc"),
        pl.col("to_party").map_elements(bloc, return_dtype=pl.String).alias("to_bloc"),
    )
    inputs = build_inputs(primary, districts, federal, regions, holders)

    # Flows: Luce weights from the DoPs, tilted so replaying the previous election's
    # count reproduces each seat's actual ALP-v-Coalition 2CP, then ONP flows from polls.
    tcp = pl.read_csv(base_dir / "tcp.csv")
    alp_tcp = np.full(len(inputs.districts), np.nan)
    for i, name in enumerate(inputs.districts):
        t = tcp.filter(pl.col("district") == name)
        if set(t["bloc"]) == {"ALP", "COAL"}:
            alp_tcp[i] = t.filter(pl.col("bloc") == "ALP")["pct"][0]
    flows, calib = calibrate_to_results(estimate_weights(transfers), inputs.base, alp_tcp)
    typer.echo(f"flow calibration: {calib}")
    flows = apply_onp_targets(flows)
    w = inputs.weight / inputs.weight.sum()
    ind, oth = inputs.base[:, IDX["IND"]] @ w, inputs.base[:, IDX["OTH"]] @ w
    _add_tpp_trend(agg["shares"], parties, flows, PROCESSED_DIR / election / "poll_trend.csv",
                   ind_fraction=float(ind / (ind + oth)))
    res = simulate(inputs, election_day, parties, flows, SimConfig(n_per_draw=n_per_draw))
    summary = summarise(res)

    out = PROCESSED_DIR / election
    out.mkdir(parents=True, exist_ok=True)
    (out / "forecast_summary.json").write_text(json.dumps(summary, indent=1))
    o, s = summary["outcome"], summary["seats"]
    typer.echo(f"{summary['n_sims']} sims")
    typer.echo("outcome: " + ", ".join(f"{k} {v:.1%}" for k, v in o.items()))
    for p in ["ALP", "COAL", "LIB", "NAT", "GRN", "ONP", "IND"]:
        typer.echo(f"  {p:5s} seats median {s[p][2]:.0f}  90% [{s[p][0]:.0f}, {s[p][4]:.0f}]")
    typer.echo(f"statewide 2PP ALP v COAL: {summary['tpp_alp']}")


def _add_tpp_trend(shares, parties: list[str], flows, trend_path, ind_fraction: float) -> None:
    """Add model-implied ALP-v-Coalition 2PP (median, 90%) to the weekly trend file.

    ``ind_fraction`` is independents' share of the aggregate's "Others" (from the
    previous election), split back out because their preferences differ.
    """
    import numpy as np

    from prophecy.model.preferences import BLOCS, IDX, two_party

    trend = pl.read_csv(trend_path, try_parse_dates=True, infer_schema_length=None)
    trend = trend.drop([c for c in trend.columns if c.startswith("tpp_alp_vs_coal")])
    n_draws = shares.shape[0]
    med, lo, hi = [], [], []
    for w in range(trend.height):
        prim = np.zeros((n_draws, len(BLOCS)))
        for k, p in enumerate(parties):
            prim[:, IDX[p]] = shares[:, w, k] / 100
        prim[:, IDX["IND"]] = prim[:, IDX["OTH"]] * ind_fraction
        prim[:, IDX["OTH"]] *= 1 - ind_fraction
        tpp = two_party(prim, np.repeat(flows[None], n_draws, axis=0), "ALP", "COAL")
        q = np.quantile(tpp, [0.5, 0.05, 0.95])
        med.append(round(float(q[0]), 2))
        lo.append(round(float(q[1]), 2))
        hi.append(round(float(q[2]), 2))
    trend.with_columns(
        pl.Series("tpp_alp_vs_coal", med), pl.Series("tpp_alp_vs_coal_lo", lo),
        pl.Series("tpp_alp_vs_coal_hi", hi),
    ).write_csv(trend_path)


@app.command("publish")
def publish(election: str = typer.Option("vic-2026", help="Election id")) -> None:
    """Write website data files for an election."""
    from prophecy.publish.forecast import publish_forecast
    from prophecy.publish.polls import publish_polls
    from prophecy.publish.results import publish_results

    e = jurisdictions.get(election)
    typer.echo(publish_polls(e))
    typer.echo(publish_forecast(e) or "no forecast yet")
    # Historical results for every past election in the same jurisdiction we have ingested.
    for past in jurisdictions.ELECTIONS.values():
        if past.jurisdiction == e.jurisdiction and (PROCESSED_DIR / past.election_id / "districts.csv").exists():
            typer.echo(publish_results(past))


def _write_tables(tables: dict, out) -> None:
    out.mkdir(parents=True, exist_ok=True)
    for name, df in tables.items():
        df.write_csv(out / f"{name}.csv")
        typer.echo(f"{out.name}/{name}: {df.height} rows")


if __name__ == "__main__":
    app()
