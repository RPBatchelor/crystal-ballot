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


@app.command("publish")
def publish(election: str = typer.Option("vic-2026", help="Election id")) -> None:
    """Write website data files for an election."""
    from prophecy.publish.polls import publish_polls
    from prophecy.publish.results import publish_results

    e = jurisdictions.get(election)
    typer.echo(publish_polls(e))
    # Historical results for every past election in the same jurisdiction we have ingested.
    for past in jurisdictions.ELECTIONS.values():
        if past.jurisdiction == e.jurisdiction and (PROCESSED_DIR / past.election_id).exists():
            typer.echo(publish_results(past))


def _write_tables(tables: dict, out) -> None:
    out.mkdir(parents=True, exist_ok=True)
    for name, df in tables.items():
        df.write_csv(out / f"{name}.csv")
        typer.echo(f"{out.name}/{name}: {df.height} rows")


if __name__ == "__main__":
    app()
