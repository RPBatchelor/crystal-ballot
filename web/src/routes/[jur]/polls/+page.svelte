<script lang="ts">
	import type { PageData } from './$types';
	import TimeSeriesChart from '$lib/components/charts/TimeSeriesChart.svelte';
	import { fmtDate, fmtInt } from '$lib/format';
	import { PRIMARY_SERIES, TPP_SERIES } from '$lib/series';

	let { data }: { data: PageData } = $props();
	const polls = $derived(data.polls);
	const j = $derived(data.jurisdiction);

	const pollsters = $derived([...new Set(polls.polls.map((p) => p.pollster))].sort());
	let pollster = $state('all');
	const shown = $derived(pollster === 'all' ? polls.polls : polls.polls.filter((p) => p.pollster === pollster));

	const events = $derived(
		polls.events
			.filter((e) => e.event_date)
			.map((e) => ({ date: e.event_date!, label: e.description }))
			.sort((a, b) => a.date.localeCompare(b.date))
	);
	const v = (n: number | null) => (n == null ? '–' : n.toString());
</script>

<svelte:head>
	<title>{j.name} polls · Prophecy</title>
</svelte:head>

<p class="eyebrow">{j.name} · voting intention</p>
<h1>Every poll since the 2022 election</h1>
<p class="lede">
	{polls.polls.length} published state voting-intention polls from {pollsters.length} pollsters. Dots are
	individual polls; lines are a simple smoothed average.
</p>

<h2>Primary vote</h2>
<TimeSeriesChart
	title="Victorian primary vote polling since 2022"
	series={PRIMARY_SERIES}
	points={polls.polls}
	pointDate={(p) => p.field_end}
	trend={polls.trend}
	{events}
	end={polls.election_date}
/>

<h2>Two-party preferred</h2>
<p class="muted small">Labor share of the Labor-versus-Coalition two-party-preferred vote, as reported by each pollster.</p>
<TimeSeriesChart
	title="Labor two-party-preferred vote in Victorian polls since 2022"
	series={TPP_SERIES}
	points={polls.polls}
	pointDate={(p) => p.field_end}
	trend={polls.trend}
	end={polls.election_date}
	yRef={50}
	height={280}
/>

<p class="muted small method">
	<strong>About the average.</strong>
	{polls.trend_method} It does not adjust for pollster house effects or sample design; the forecast model
	will.
</p>

<h2>All polls</h2>
<div class="controls">
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
			{#each shown as p (p.pollster + p.field_end + p.field_start)}
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
