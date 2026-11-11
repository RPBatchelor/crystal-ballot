<script lang="ts">
	import { coalName, theCoal } from '$lib/jurisdictions';
	import { SITE_NAME } from '$lib/site';
	import type { PageData } from './$types';
	import TimeSeriesChart from '$lib/components/charts/TimeSeriesChart.svelte';
	import { fmtDate, fmtInt } from '$lib/format';
	import { primarySeries, TPP_SERIES } from '$lib/series';

	let { data }: { data: PageData } = $props();
	const polls = $derived(data.polls);
	const j = $derived(data.jurisdiction);
	const coalLabel = $derived(coalName(j.code));
	const theC = $derived(theCoal(j.code));

	const pollsters = $derived([...new Set(polls.polls.map((p) => p.pollster))].sort());
	const cycles = $derived([...(polls.cycles ?? [])].reverse());
	// The current cycle starts at the previous election.
	const cycleStart = $derived(
		(polls.results ?? []).map((r) => r.date).filter((d) => d < polls.election_date).at(-1)
	);
	const firstYear = $derived(new Date(polls.polls.at(-1)?.field_end ?? polls.election_date).getFullYear());
	let pollster = $state('all');
	let cycle = $state('all');
	const shown = $derived(
		polls.polls
			.filter((p) => pollster === 'all' || p.pollster === pollster)
			.filter((p) => cycle === 'all' || p.cycle === cycle)
	);
	const markers = $derived(
		(polls.results ?? []).map((r) => ({ ...r, label: `${r.year} election` }))
	);
	const cycleLabel = (id: string) => {
		const i = (polls.cycles ?? []).findIndex((c) => c.election_id === id);
		const prev = (polls.results ?? []).filter((r) => r.date < (polls.cycles ?? [])[i]?.date).at(-1);
		return `${prev ? prev.year : '…'}–${id.slice(-4)}`;
	};

	const events = $derived(
		polls.events
			.filter((e) => e.event_date)
			.map((e) => ({ date: e.event_date!, label: e.description }))
			.sort((a, b) => a.date.localeCompare(b.date))
	);
	const v = (n: number | null) => (n == null ? '–' : n.toString());
	const houseParties = ['ALP', 'COAL', 'GRN', 'ONP'];
	const housePollsters = $derived([...new Set((polls.house_effects ?? []).map((h) => h.pollster))].sort());
</script>

<svelte:head>
	<title>{j.name} polls · {SITE_NAME}</title>
</svelte:head>

<p class="eyebrow">{j.name} · voting intention</p>
<h1>Every {j.kind === 'federal' ? 'federal' : 'state'} poll since {firstYear}</h1>
<p class="lede">
	{polls.polls.length} published {j.kind === 'federal' ? 'federal' : 'state'} voting-intention polls from {pollsters.length} pollsters across
	{cycles.length} election cycles. Dots are individual polls, lines the poll average, and diamonds the actual
	election results. Use the range buttons or drag across the strip under each chart to zoom.
</p>

<h2>Primary vote</h2>
<TimeSeriesChart
	title="{j.name} primary vote polling since {firstYear}"
	series={primarySeries(coalLabel)}
	points={polls.polls}
	pointDate={(p) => p.field_end}
	trend={polls.trend}
	{events}
	{markers}
	end={polls.election_date_known === false ? undefined : polls.election_date}
	zoomable
	{cycleStart}
	initialRange="cycle"
/>

<h2>Two-party preferred</h2>
<p class="muted small">
	Labor share of the Labor-versus-{coalLabel} two-party-preferred vote. Dots are each pollster's own figure;
	the line is implied from the primary-vote average using estimated preference flows.
</p>
<TimeSeriesChart
	title="Labor two-party-preferred vote in {j.name} polls since {firstYear}"
	series={TPP_SERIES}
	points={polls.polls}
	pointDate={(p) => p.field_end}
	trend={polls.trend}
	{markers}
	end={polls.election_date_known === false ? undefined : polls.election_date}
	yRef={50}
	height={280}
	zoomable
	{cycleStart}
	initialRange="cycle"
/>

<p class="muted small method">
	<strong>About the average.</strong>
	{polls.trend_method}
</p>

{#if polls.house_effects?.length}
	<h2>Pollster house effects</h2>
	<p class="muted small">
		How far each pollster's figures typically sit from the average, in points (median, with 90% interval).
		These sum to zero across pollsters, so they measure differences between pollsters, not industry-wide
		error.
	</p>
	<div class="scroll-x">
		<table class="data house">
			<thead>
				<tr>
					<th class="left">Pollster</th>
					{#each houseParties as hp (hp)}<th>{hp}</th>{/each}
				</tr>
			</thead>
			<tbody>
				{#each housePollsters as name (name)}
					<tr>
						<td class="left">{name}</td>
						{#each houseParties as hp (hp)}
							{@const h = polls.house_effects.find((r) => r.pollster === name && r.party === hp)}
							<td>
								{#if h}
									<span class:strong={h.lo > 0 || h.hi < 0}>{h.median > 0 ? '+' : ''}{h.median.toFixed(1)}</span>
									<span class="muted small">({h.lo.toFixed(1)}, {h.hi.toFixed(1)})</span>
								{:else}–{/if}
							</td>
						{/each}
					</tr>
				{/each}
			</tbody>
		</table>
	</div>
	<p class="muted small">Bold: the 90% interval excludes zero.</p>
{/if}

<h2>All polls</h2>
<div class="controls">
	<label>
		Cycle
		<select bind:value={cycle}>
			<option value="all">All cycles</option>
			{#each cycles as c (c.election_id)}<option value={c.election_id}>{cycleLabel(c.election_id)}</option>{/each}
		</select>
	</label>
	<label>
		Pollster
		<select bind:value={pollster}>
			<option value="all">All pollsters</option>
			{#each pollsters as p (p)}<option value={p}>{p}</option>{/each}
		</select>
	</label>
	<span class="muted small">{shown.length} polls</span>
</div>
<div class="scroll-x">
	<table class="data">
		<thead>
			<tr>
				<th class="left">Fieldwork</th>
				<th class="left">Pollster</th>
				<th>Sample</th>
				<th>ALP</th>
				<th>L/NP</th>
				<th>GRN</th>
				<th>ONP</th>
				<th>IND</th>
				<th>OTH</th>
				<th>2PP ALP v L/NP</th>
				<th>2PP ALP v ONP</th>
			</tr>
		</thead>
		<tbody>
			{#each shown as p, i (i)}
				<tr>
					<td class="left">{fmtDate(p.field_start)} – {fmtDate(p.field_end)}</td>
					<td class="left">{p.pollster}{#if p.client}<span class="muted small"> · {p.client}</span>{/if}</td>
					<td>{fmtInt(p.sample_size)}</td>
					<td>{v(p.ALP)}</td>
					<td>{v(p.COAL)}</td>
					<td>{v(p.GRN)}</td>
					<td>{v(p.ONP)}</td>
					<td>{v(p.IND)}</td>
					<td>{v(p.OTH)}</td>
					<td>{v(p.tpp_alp_vs_coal)}</td>
					<td>{v(p.tpp_alp_vs_onp)}</td>
				</tr>
			{/each}
		</tbody>
	</table>
</div>
<p class="muted small">
	Primary votes in %. A blank ONP or IND means the pollster did not report it separately (it is included
	in Others). Source: pollster releases, compiled via Wikipedia. Data updated {fmtDate(polls.generated_at)}.
</p>

<style>
	.house td {
		white-space: nowrap;
	}
	.house .strong {
		font-weight: 650;
	}
	.method {
		max-width: 46rem;
		margin-top: 1.5rem;
	}
	.controls {
		display: flex;
		align-items: center;
		gap: 1rem;
		margin-bottom: 0.75rem;
		font-size: 0.9rem;
	}
	select {
		font: inherit;
		margin-left: 0.4rem;
		padding: 0.3rem 0.5rem;
		border: 1px solid var(--rule-strong);
		border-radius: var(--radius);
		background: var(--surface);
		color: var(--fg);
	}
</style>
