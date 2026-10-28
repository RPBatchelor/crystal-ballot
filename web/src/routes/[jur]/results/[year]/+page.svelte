<script lang="ts">
	import type { PageData } from './$types';
	import Hemicycle from '$lib/components/charts/Hemicycle.svelte';
	import SeatMap from '$lib/components/charts/SeatMap.svelte';
	import Pendulum from '$lib/components/Pendulum.svelte';
	import SeatTable from '$lib/components/SeatTable.svelte';
	import { displayName, fmtDate } from '$lib/format';
	import { chamberSeats, swingColour, tppColour, TPP_GRADIENT } from '$lib/maps';
	import { party, partyColour } from '$lib/parties';

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
	const coalSeats = $derived((r.seat_counts.LIB ?? 0) + (r.seat_counts.NAT ?? 0) + (r.seat_counts.LNP ?? 0));
	const alpSeats = $derived(r.seat_counts.ALP ?? 0);
	const government = $derived(alpSeats >= coalSeats ? 'ALP' : 'COAL');
	const govSeats = $derived(government === 'ALP' ? alpSeats : coalSeats);
	const nonClassic = $derived(r.seats.filter((s) => !s.classic).length);
	const years = $derived(j.resultYears);

	const chamber = $derived(
		chamberSeats(
			r.seats.map((s) => ({
				slug: s.slug,
				name: s.name,
				party: s.party,
				strength: s.margin,
				detail: `margin ${s.margin.toFixed(1)}`,
				href: `${base}/${s.slug}/`
			}))
		)
	);
	const tallyOrder = ['ALP', 'LIB', 'NAT', 'GRN', 'IND', 'ONP', 'OTH'];
	const tally = $derived(
		Object.entries(r.seat_counts)
			.map(([code, seats]) => ({
				code,
				seats,
				pct: r.party_share?.[code] ?? r.primary_share[code] ?? null
			}))
			.sort((a, b) => tallyOrder.indexOf(a.code) - tallyOrder.indexOf(b.code))
	);

	const bySlug = $derived(Object.fromEntries(r.seats.map((s) => [s.slug, s])));
	const swing = $derived.by(() => {
		const prev = data.previous;
		if (!prev) return {} as Record<string, number | null>;
		const before = Object.fromEntries(prev.seats.map((s) => [s.slug, s.tpp_alp]));
		return Object.fromEntries(
			r.seats.map((s) => [s.slug, s.tpp_alp != null && before[s.slug] != null ? s.tpp_alp - before[s.slug]! : null])
		) as Record<string, number | null>;
	});
	const modes = $derived([
		{ key: 'winner', label: 'Winner' },
		{ key: 'tpp', label: 'Two-party preferred' },
		...(data.previous ? [{ key: 'swing', label: `Swing since ${data.prevYear}` }] : [])
	]);
	let mode = $state('winner');
	const winnerLegend = $derived(
		tallyOrder.filter((c) => r.seat_counts[c]).map((c) => ({ label: party(c).short, colour: partyColour(c) }))
	);
	function seatTip(slug: string) {
		const s = bySlug[slug];
		if (!s) return { title: slug, lines: [] };
		const lines = [
			`${party(s.party).short} · ${displayName(s.elected)}`,
			`Margin ${s.margin.toFixed(1)}% v ${party(s.runner_up_party).short}`
		];
		if (s.tpp_alp != null) lines.push(`Labor 2PP ${s.tpp_alp.toFixed(1)}%`);
		const sw = swing[slug];
		if (sw != null) lines.push(`Swing ${sw >= 0 ? '+' : '−'}${Math.abs(sw).toFixed(1)} to ${sw >= 0 ? 'Labor' : 'Coalition'}`);
		return { title: s.name, lines };
	}
</script>

<svelte:head>
	<title>{j.name} {data.year} results · Prophecy</title>
</svelte:head>

{#if years.length > 1}
	<nav class="years" aria-label="Election year">
		{#each years as y (y)}
			<a href="/{j.code}/results/{y}/" aria-current={y === data.year ? 'page' : undefined}>{y}</a>
		{/each}
	</nav>
{/if}

<p class="eyebrow">{j.name} · {j.chamber} · {fmtDate(r.date)}</p>
<h1>{data.year} {j.name} election results</h1>
<p class="lede">
	{party(government).short} formed government with {govSeats} of {r.seats_total} seats{govSeats >=
	r.majority
		? ''
		: ' (short of a majority)'}. Labor won {r.tpp_alp.toFixed(1)}% of the statewide two-party-preferred vote.
</p>

<div class="hero">
	<Hemicycle title="Seats won at the {data.year} election" seats={chamber} majority={r.majority} />
	<div>
		<table class="data tally">
			<thead><tr><th class="left">Party</th><th>Seats</th><th>First pref.</th></tr></thead>
			<tbody>
				{#each tally as t (t.code)}
					<tr>
						<td class="left"><span class="chip" style:--c={partyColour(t.code)}>{party(t.code).short}</span></td>
						<td><strong>{t.seats}</strong></td>
						<td>{t.pct != null ? `${t.pct.toFixed(1)}%` : '–'}</td>
					</tr>
				{/each}
			</tbody>
		</table>
		<h3 class="sub">Statewide first preferences</h3>
		<ul class="shares">
			{#each shares as s (s.code)}
				<li>
					<span class="lbl">{s.label}</span>
					<span class="track"><span class="fill" style:width="{(100 * s.pct) / maxShare}%" style:background={partyColour(s.code)}></span></span>
					<span class="num v">{s.pct.toFixed(1)}%</span>
				</li>
			{/each}
		</ul>
	</div>
</div>

{#if data.geo}
	<h2>Map</h2>
	<div class="modes" role="group" aria-label="Map view">
		{#each modes as m (m.key)}
			<button type="button" aria-pressed={mode === m.key} onclick={() => (mode = m.key)}>{m.label}</button>
		{/each}
	</div>
	{#if mode === 'winner'}
		<SeatMap
			title="Winning party by district, {data.year}"
			geo={data.geo}
			fill={(slug) => partyColour(bySlug[slug]?.party ?? 'OTH')}
			tooltip={seatTip}
			href={(slug) => `${base}/${slug}/`}
			legend={winnerLegend}
		/>
	{:else if mode === 'tpp'}
		<SeatMap
			title="Labor two-party-preferred vote by district, {data.year}"
			geo={data.geo}
			fill={(slug) => (bySlug[slug]?.tpp_alp != null ? tppColour(bySlug[slug].tpp_alp!) : 'var(--rule)')}
			tooltip={seatTip}
			href={(slug) => `${base}/${slug}/`}
			gradient={{ css: TPP_GRADIENT, left: 'Coalition 75%', right: 'Labor 75%', mid: 'Grey: no Labor-v-Coalition count' }}
		/>
	{:else}
		<SeatMap
			title="Two-party-preferred swing by district, {data.prevYear} to {data.year}"
			geo={data.geo}
			fill={(slug) => (swing[slug] != null ? swingColour(swing[slug]!) : 'var(--rule)')}
			tooltip={seatTip}
			href={(slug) => `${base}/${slug}/`}
			gradient={{ css: TPP_GRADIENT, left: '12 pts to Coalition', right: '12 pts to Labor' }}
		/>
	{/if}
{/if}

<h2>Pendulum</h2>
<p class="muted small">
	Seats ranked by two-candidate-preferred margin: the swing needed for each seat to change hands. {nonClassic}
	seats were not Labor-versus-Coalition contests and are tagged with the runner-up.
</p>
<Pendulum seats={r.seats} {government} {base} />

<h2>Every seat</h2>
<SeatTable seats={r.seats} {base} />

<style>
	.hero {
		display: grid;
		grid-template-columns: minmax(0, 1.2fr) minmax(0, 1fr);
		gap: 1.5rem 2.5rem;
		align-items: start;
		margin-top: 1rem;
	}
	@media (max-width: 760px) {
		.hero {
			grid-template-columns: 1fr;
		}
	}
	.tally {
		max-width: 22rem;
	}
	.chip {
		display: inline-flex;
		align-items: center;
		gap: 0.4rem;
		font-weight: 550;
	}
	.chip::before {
		content: '';
		width: 0.65rem;
		height: 0.65rem;
		border-radius: 2px;
		background: var(--c);
	}
	h3.sub {
		font-family: var(--font-sans);
		font-size: 0.95rem;
		margin: 1.5rem 0 0.6rem;
	}
	.modes {
		display: inline-flex;
		border: 1px solid var(--rule-strong);
		border-radius: var(--radius);
		overflow: hidden;
		margin-bottom: 1rem;
	}
	.modes button {
		font: inherit;
		font-size: 0.85rem;
		padding: 0.35rem 0.75rem;
		border: 0;
		background: var(--surface);
		color: var(--fg-2);
		cursor: pointer;
	}
	.modes button + button {
		border-left: 1px solid var(--rule-strong);
	}
	.modes button[aria-pressed='true'] {
		background: var(--fg);
		color: var(--bg);
	}
	.years {
		display: flex;
		gap: 0.35rem;
		margin-bottom: 1rem;
	}
	.years a {
		font-size: 0.85rem;
		font-weight: 550;
		padding: 0.25rem 0.7rem;
		border: 1px solid var(--rule-strong);
		border-radius: 999px;
		text-decoration: none;
		color: var(--fg-2);
	}
	.years a[aria-current='page'] {
		background: var(--fg);
		color: var(--bg);
		border-color: var(--fg);
	}
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
