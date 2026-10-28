<script lang="ts">
	import type { PageData } from './$types';
	import TimeSeriesChart from '$lib/components/charts/TimeSeriesChart.svelte';
	import Hemicycle from '$lib/components/charts/Hemicycle.svelte';
	import { chamberSeats } from '$lib/maps';
	import { daysUntil, fmtDate } from '$lib/format';
	import { partyColour } from '$lib/parties';
	import { PRIMARY_SERIES } from '$lib/series';

	let { data }: { data: PageData } = $props();
	const j = $derived(data.jurisdiction);
	const latest = $derived(data.polls?.trend.at(-1));
	const days = $derived(j.nextElection ? daysUntil(j.nextElection) : null);

	const tiles = $derived(
		latest && data.results
			? [
					...PRIMARY_SERIES.map((s) => ({
						label: s.label,
						colour: s.colour,
						value: latest[s.key as keyof typeof latest] as number | null,
						prev: data.results!.primary_share[s.key] ?? null
					})),
					{
						label: 'Labor 2PP',
						colour: partyColour('ALP'),
						value: latest.tpp_alp_vs_coal,
						prev: data.results.tpp_alp
					}
				]
			: []
	);
</script>

<svelte:head>
	<title>{j.name} · Prophecy</title>
</svelte:head>

<p class="eyebrow">{j.name} · {j.chamber}</p>

{#if !data.polls && !data.results}
	<h1>{j.name}</h1>
	<p class="lede">
		Polling, historical results and forecasts for {j.name} are on the roadmap. Victoria is the
		first jurisdiction; the platform is built so each state and federal election slots in the same
		way.
	</p>
{:else}
	<h1>{j.name} state election{#if j.nextElection}, {fmtDate(j.nextElection)}{/if}</h1>
	{#if days != null && days > 0}
		<p class="lede">
			<strong>{days} days</strong> until polling day. All {j.seats} Legislative Assembly seats are up;
			{Math.floor(j.seats / 2) + 1} are needed to govern in majority.
		</p>
	{/if}

	<aside class="card notice">
		<strong>The forecast launches in mid-November.</strong>
		A <a href="/{j.code}/forecast/2026/">development preview</a> is available; it becomes the official
		forecast once the model passes its historical backtests.
	</aside>

	{#if data.polls && latest}
		<h2>Where the polls are</h2>
		<p class="muted small">
			Simple poll average to {fmtDate(latest.date)} (primary vote %). Change is from the 2022 election
			result.
		</p>
		<div class="tiles">
			{#each tiles as t (t.label)}
				{#if t.value != null}
					<div class="tile">
						<span class="tile-label"><span class="swatch" style:background={t.colour}></span>{t.label}</span>
						<span class="tile-value num">{t.value.toFixed(1)}</span>
						{#if t.prev != null}
							{@const d = t.value - t.prev}
							<span class="tile-delta num muted">{d >= 0 ? '+' : '−'}{Math.abs(d).toFixed(1)} since 2022</span>
						{/if}
					</div>
				{/if}
			{/each}
		</div>

		<TimeSeriesChart
			title="Victorian primary vote polling since the 2022 election"
			series={PRIMARY_SERIES}
			points={data.polls.polls}
			pointDate={(p) => p.field_end}
			trend={data.polls.trend}
			end={data.polls.election_date}
			height={340}
			cycleStart={data.results?.date}
			initialRange="cycle"
		/>
		<p><a href="/{j.code}/polls/">All polls, 2PP and pollster detail →</a></p>
	{/if}

	{#if data.results}
		<h2>The 2022 baseline</h2>
		<p class="muted">
			Labor won {data.results.seat_counts.ALP} of {data.results.seats_total} seats with {data.results.tpp_alp.toFixed(
				1
			)}% of the two-party-preferred vote.
		</p>
		<div class="baseline">
			<Hemicycle
				title="Seats won at the 2022 Victorian election"
				seats={chamberSeats(
					data.results.seats.map((s) => ({
						slug: s.slug,
						name: s.name,
						party: s.party,
						strength: s.margin,
						detail: `margin ${s.margin.toFixed(1)}`,
						href: `/${j.code}/results/2022/${s.slug}/`
					}))
				)}
				majority={data.results.majority}
			/>
		</div>
		<p><a href="/{j.code}/results/2022/">Seat-by-seat results and pendulum →</a></p>
	{/if}
{/if}

<style>
	.baseline {
		max-width: 30rem;
	}
	.notice {
		margin: 1.25rem 0 0.5rem;
		max-width: 46rem;
		border-left: 3px solid var(--fg);
	}
	.tiles {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(8.5rem, 1fr));
		gap: 0.75rem;
		margin: 1rem 0 1.5rem;
	}
	.tile {
		display: flex;
		flex-direction: column;
		padding: 0.75rem 0.9rem;
		border: 1px solid var(--rule);
		border-radius: var(--radius);
		background: var(--surface);
	}
	.tile-label {
		display: flex;
		align-items: center;
		gap: 0.4rem;
		font-size: 0.85rem;
		color: var(--fg-2);
	}
	.swatch {
		width: 0.65rem;
		height: 0.65rem;
		border-radius: 2px;
	}
	.tile-value {
		font-size: 1.9rem;
		font-weight: 650;
		line-height: 1.2;
	}
	.tile-delta {
		font-size: 0.8rem;
	}
</style>
