<script lang="ts">
	import type { PageData } from './$types';
	import SeatBar from '$lib/components/charts/SeatBar.svelte';
	import Pendulum from '$lib/components/Pendulum.svelte';
	import SeatTable from '$lib/components/SeatTable.svelte';
	import { fmtDate } from '$lib/format';
	import { party, partyColour } from '$lib/parties';
	import { seatSegments } from '$lib/series';

	let { data }: { data: PageData } = $props();
	const r = $derived(data.results);
	const j = $derived(data.jurisdiction);
	const base = $derived(`/${j.code}/results/${data.year}`);

	const shareOrder = ['ALP', 'COAL', 'GRN', 'IND', 'ONP', 'OTH'];
	const shares = $derived(
		shareOrder
			.filter((k) => r.primary_share[k] != null)
			.map((k) => ({ code: k, label: party(k).short, pct: r.primary_share[k] }))
	);
	const maxShare = $derived(Math.max(...shares.map((s) => s.pct)));
	const government = $derived(
		Object.entries(r.seat_counts).sort((a, b) => b[1] - a[1])[0][0] === 'ALP' ? 'ALP' : 'COAL'
	);
	const nonClassic = $derived(r.seats.filter((s) => !s.classic).length);
</script>

<svelte:head>
	<title>{j.name} {data.year} results · Prophecy</title>
</svelte:head>

<p class="eyebrow">{j.name} · {j.chamber} · {fmtDate(r.date)}</p>
<h1>{data.year} {j.name} election results</h1>
<p class="lede">
	Labor retained government with {r.seat_counts.ALP} of {r.seats_total} seats and {r.tpp_alp.toFixed(1)}%
	of the statewide two-party-preferred vote.
</p>

<SeatBar
	title="Seats won at the {data.year} election"
	segments={seatSegments(r.seat_counts)}
	total={r.seats_total}
	majority={r.majority}
/>

<h2>Statewide first preferences</h2>
<ul class="shares">
	{#each shares as s (s.code)}
		<li>
			<span class="lbl">{s.label}</span>
			<span class="track"><span class="fill" style:width="{(100 * s.pct) / maxShare}%" style:background={partyColour(s.code)}></span></span>
			<span class="num v">{s.pct.toFixed(1)}%</span>
		</li>
	{/each}
</ul>

<h2>Pendulum</h2>
<p class="muted small">
	Seats ranked by two-candidate-preferred margin: the swing needed for each seat to change hands. {nonClassic}
	seats were not Labor-versus-Coalition contests and are tagged with the runner-up.
</p>
<Pendulum seats={r.seats} {government} {base} />

<h2>Every seat</h2>
<SeatTable seats={r.seats} {base} />

<style>
	.shares {
		list-style: none;
		padding: 0;
		margin: 0;
		display: grid;
		gap: 0.45rem;
		max-width: 40rem;
	}
	.shares li {
		display: grid;
		grid-template-columns: 6.5rem 1fr 3.5rem;
		gap: 0.75rem;
		align-items: center;
		font-size: 0.9rem;
	}
	.lbl {
		color: var(--fg-2);
	}
	.track {
		height: 0.8rem;
	}
	.fill {
		display: block;
		height: 100%;
		border-radius: 0 4px 4px 0;
	}
	.v {
		text-align: right;
		font-weight: 600;
	}
</style>
