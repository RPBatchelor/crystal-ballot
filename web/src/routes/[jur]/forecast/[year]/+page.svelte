<script lang="ts">
	import { SITE_NAME } from '$lib/site';
	import type { PageData } from './$types';
	import OutcomeBar from '$lib/components/charts/OutcomeBar.svelte';
	import SeatHistogram from '$lib/components/charts/SeatHistogram.svelte';
	import Hemicycle from '$lib/components/charts/Hemicycle.svelte';
	import SeatMap from '$lib/components/charts/SeatMap.svelte';
	import { fmtDate } from '$lib/format';
	import { chamberSeats, tierOpacity, TIERS, mapFrame } from '$lib/maps';
	import { party, partyColour } from '$lib/parties';

	let { data }: { data: PageData } = $props();
	const f = $derived(data.forecast);
	const j = $derived(data.jurisdiction);
	const retro = $derived(f.mode === 'retrospective');
	const area = $derived(j.kind === 'federal' ? 'National' : 'Statewide');

	const headline = $derived.by(() => {
		const o = f.outcome;
		const top = [
			{ p: o.coal_majority, t: 'a Coalition majority' },
			{ p: o.hung, t: 'a hung parliament' },
			{ p: o.alp_majority, t: 'a Labor majority' }
		].sort((a, b) => b.p - a.p)[0];
		return retro ? `The model's most likely outcome was ${top.t}` : `The most likely outcome is ${top.t}`;
	});

	const minor = ['GRN', 'ONP', 'IND'];
	// Independents are inside Others in the poll aggregate, so they have no statewide row.
	const voteOrder = ['ALP', 'COAL', 'GRN', 'ONP', 'OTH'];
	const voteMax = $derived(Math.ceil(Math.max(...voteOrder.map((k) => f.statewide_primary[k]?.[2] ?? 0)) / 5) * 5);

	// Seat table
	const partyOrder = ['ALP', 'GRN', 'IND', 'OTH', 'ONP', 'NAT', 'LIB', 'LNP', 'COAL'];
	let sortKey = $state<'name' | 'certainty' | 'alp' | 'coal'>('certainty');
	let query = $state('');
	const coalP = (d: (typeof f.districts)[number]) => (d.probs.LIB ?? 0) + (d.probs.NAT ?? 0) + (d.probs.LNP ?? 0) + (d.probs.COAL ?? 0);
	const rows = $derived(
		f.districts
			.filter((d) => !query || d.district.toLowerCase().includes(query.toLowerCase()))
			.toSorted((a, b) => {
				if (sortKey === 'name') return a.district.localeCompare(b.district);
				if (sortKey === 'alp') return (b.probs.ALP ?? 0) - (a.probs.ALP ?? 0);
				if (sortKey === 'coal') return coalP(b) - coalP(a);
				return a.leader_prob - b.leader_prob;
			})
	);
	const pct = (p: number) => (p < 0.005 ? '<1%' : p > 0.995 ? '>99%' : `${Math.round(p * 100)}%`);
	const seatHref = (slug: string) =>
		data.lastResults ? `/${j.code}/results/${data.lastResults}/${slug}/` : undefined;
	const bySlug = $derived(Object.fromEntries(f.districts.map((d) => [d.slug, d])));
	const chamber = $derived(
		chamberSeats(
			f.districts.map((d) => ({
				slug: d.slug,
				name: d.district,
				party: d.leader,
				strength: d.leader_prob,
				detail: `${pct(d.leader_prob)} chance`,
				href: seatHref(d.slug),
				opacity: tierOpacity(d.leader_prob)
			}))
		)
	);
	const favCounts = $derived(
		Object.entries(
			f.districts.reduce<Record<string, number>>((acc, d) => ((acc[d.leader] = (acc[d.leader] ?? 0) + 1), acc), {})
		).sort((a, b) => b[1] - a[1])
	);
	function seatTip(slug: string) {
		const d = bySlug[slug];
		if (!d) return { title: slug, lines: [] };
		const probs = Object.entries(d.probs)
			.filter(([, p]) => p >= 0.01)
			.sort((a, b) => b[1] - a[1])
			.map(([p, v]) => `${party(p).short} ${pct(v)}`);
		const prim = ['ALP', 'COAL', 'GRN', 'ONP']
			.filter((b) => (d.primary[b]?.[1] ?? 0) >= 3)
			.map((b) => `${party(b).short} ${d.primary[b][1].toFixed(0)}%`);
		return {
			title: `${d.district} (held by ${party(d.incumbent).short})`,
			lines: [`Chance: ${probs.join(' · ')}`, `Median first prefs: ${prim.join(', ')}`, ...(d.notes ?? [])]
		};
	}

	const noted = $derived(
		f.districts.filter((d) => d.notes?.length).toSorted((a, b) => a.district.localeCompare(b.district))
	);

	const changes = $derived(
		f.districts.filter((d) => d.leader !== d.incumbent && d.leader_prob > 0.5).length
	);
</script>

<svelte:head>
	<title>{j.name} {data.year} forecast · {SITE_NAME}</title>
</svelte:head>

{#if retro && f.actual}
	<aside class="retro">
		<strong>A forecast of a past election.</strong> This is what the model would have published on the eve of
		polling day, built blind: only the previous result, that cycle's polls and polling error from earlier
		elections went in.
		{#if f.actual}
			On the day, Labor won {f.actual.seat_counts.ALP ?? 0} seats with {f.actual.tpp_alp.toFixed(1)}% two-party
			preferred.
		{/if}
		<a href="vs-result/">Forecast against the result →</a>
	</aside>
{:else if !f.validated}
	<aside class="preview">
		<strong>Development preview.</strong> The model has been <a href="/methodology/">backtested on past elections</a>,
		but its treatment of independents is still provisional. Do not cite.
	</aside>
{/if}

<p class="eyebrow">
	{j.name} · {fmtDate(f.election_date)} · {retro ? 'forecast as at the eve of polling day' : `updated ${fmtDate(f.generated_at)}`}
</p>
<h1>{headline}</h1>
<p class="lede">
	Across {f.n_sims.toLocaleString()} simulations of all {j.seats} seats, combining the poll aggregate,
	polling-error history, seat-level swings and preference flows.
</p>

<OutcomeBar alpMajority={f.outcome.alp_majority} hung={f.outcome.hung} coalMajority={f.outcome.coal_majority} />
<p class="small muted">
	Largest party: Coalition in {Math.round(f.outcome.coal_most_seats * 100)} of 100, Labor in {Math.round(
		f.outcome.alp_most_seats * 100
	)} of 100.
</p>

<h2>Seat by seat</h2>
<p class="small muted">
	Each seat coloured by its most likely winner; shading shows how confident the model is. Close races sit
	near the centre of the chamber.
</p>
<div class="chamber">
	<Hemicycle title="Most likely winner in each seat" seats={chamber} majority={f.majority} />
	<ul class="fav small">
		{#each favCounts as [p, n] (p)}
			<li><span class="chip" style:--c={partyColour(p)}>{party(p).short}</span> favoured in <strong>{n}</strong></li>
		{/each}
		<li class="tiers">
			{#each TIERS as t (t.label)}
				<span><i style:opacity={t.opacity}></i>{t.label}</span>
			{/each}
		</li>
	</ul>
</div>

{#if data.geo}
	<SeatMap
		title="Forecast favourite by district"
		geo={data.geo}
		frame={mapFrame(data.jurisdiction.code)}
		fill={(slug) => partyColour(bySlug[slug]?.leader ?? 'OTH')}
		opacity={(slug) => tierOpacity(bySlug[slug]?.leader_prob ?? 0)}
		tooltip={seatTip}
		href={seatHref}
		legend={[
			...favCounts.map(([p]) => ({ label: party(p).short, colour: partyColour(p) })),
			...TIERS.map((t) => ({ label: t.label, colour: 'var(--fg-2)', opacity: t.opacity }))
		]}
	/>
{/if}

{#if noted.length}
	<details class="local">
		<summary><strong>Local factors in {noted.length} seats</strong> — retiring members, first-term members and by-election swings</summary>
		<ul class="small">
			{#each noted as d (d.slug)}
				<li><strong>{d.district}</strong> ({party(d.incumbent).short}): {d.notes!.join('; ')}</li>
			{/each}
		</ul>
	</details>
{/if}

<h2>Seat totals</h2>
<div class="hists">
	<SeatHistogram label="Labor" colour={partyColour('ALP')} counts={f.seat_hist.ALP} majority={f.majority} quantiles={f.seats.ALP} />
	<SeatHistogram label="Coalition" colour={partyColour('COAL')} counts={f.seat_hist.COAL} majority={f.majority} quantiles={f.seats.COAL} />
</div>
<table class="data minor">
	<thead><tr><th class="left">Party</th><th>Median seats</th><th>Likely range (50%)</th><th>90% range</th></tr></thead>
	<tbody>
		{#each minor as p (p)}
			<tr>
				<td class="left"><span class="chip" style:--c={partyColour(p)}>{party(p).short}</span></td>
				<td>{f.seats[p][2]}</td>
				<td>{f.seats[p][1]}–{f.seats[p][3]}</td>
				<td>{f.seats[p][0]}–{f.seats[p][4]}</td>
			</tr>
		{/each}
	</tbody>
</table>

<h2>{area} vote</h2>
<p class="small muted">Election-day first-preference estimates with 90% intervals, including polling error.</p>
<ul class="forest">
	{#each voteOrder as k (k)}
		{@const v = f.statewide_primary[k]}
		{#if v}
			<li>
				<span class="lbl">{party(k).short}</span>
				<span class="track">
					<span class="range" style:left="{(100 * v[0]) / voteMax}%" style:width="{(100 * (v[2] - v[0])) / voteMax}%" style:background={partyColour(k)}></span>
					<span class="dot" style:left="{(100 * v[1]) / voteMax}%" style:background={partyColour(k)}></span>
				</span>
				<span class="num v">{v[1].toFixed(1)}% <span class="muted small">({v[0].toFixed(0)}–{v[2].toFixed(0)})</span></span>
			</li>
		{/if}
	{/each}
	<li class="tpp">
		<span class="lbl">Labor 2PP</span>
		<span class="track">
			<span class="half" style:left="50%"></span>
			<span class="range" style:left="{f.tpp_alp[0]}%" style:width="{f.tpp_alp[2] - f.tpp_alp[0]}%" style:background={partyColour('ALP')}></span>
			<span class="dot" style:left="{f.tpp_alp[1]}%" style:background={partyColour('ALP')}></span>
		</span>
		<span class="num v">{f.tpp_alp[1].toFixed(1)}% <span class="muted small">({f.tpp_alp[0].toFixed(0)}–{f.tpp_alp[2].toFixed(0)})</span></span>
	</li>
</ul>

<h2>Every seat</h2>
<p class="small muted">
	Chance of each party winning, from the simulations. {changes} seats {retro ? 'favoured' : 'currently favour'} a
	different party from the one holding them.
</p>
<div class="controls">
	<input type="search" placeholder="Search seats" bind:value={query} aria-label="Search seats" />
	<label class="small">Sort
		<select bind:value={sortKey}>
			<option value="certainty">Closest first</option>
			<option value="name">Name</option>
			<option value="alp">Labor chance</option>
			<option value="coal">Coalition chance</option>
		</select>
	</label>
</div>
<ol class="seats">
	{#each rows as d (d.slug)}
		<li>
			<a href={data.lastResults ? `/${j.code}/results/${data.lastResults}/${d.slug}/` : undefined}>
				<span class="name">{d.district}<span class="muted small">&nbsp;· held by {party(d.incumbent).short}</span></span>
				<span class="probbar" role="img" aria-label={Object.entries(d.probs).map(([p, v]) => `${party(p).short} ${pct(v)}`).join(', ')}>
					{#each partyOrder as p (p)}
						{#if (d.probs[p] ?? 0) > 0.004}
							<span style:flex-grow={d.probs[p]} style:background={partyColour(p)}></span>
						{/if}
					{/each}
				</span>
				<span class="fav num"><strong>{party(d.leader).short}</strong> {pct(d.leader_prob)}</span>
			</a>
		</li>
	{/each}
</ol>

<p class="small muted diag">
	Model {f.model_version}. Poll aggregate diagnostics: R-hat ≤ {f.diagnostics.max_rhat?.toFixed(3)}, minimum
	ESS {Math.round(f.diagnostics.min_ess_bulk ?? 0)}, {f.diagnostics.divergences} divergences.
</p>

<style>
	.preview {
		border: 1px solid var(--brand-spark);
		background: color-mix(in srgb, var(--brand-spark) 16%, var(--surface));
		border-radius: var(--radius-md);
		padding: 0.7rem 1rem;
		margin-bottom: 1.25rem;
		font-size: 0.92rem;
	}
	.retro {
		border-left: 3px solid var(--fg);
		background: var(--surface);
		border-radius: var(--radius);
		padding: 0.7rem 1rem;
		margin-bottom: 1.25rem;
		font-size: 0.92rem;
		max-width: 52rem;
	}
	.local {
		margin: 1.5rem 0 0;
		border: 1px solid var(--rule);
		border-radius: var(--radius);
		padding: 0.6rem 1rem;
		background: var(--surface);
	}
	.local summary {
		cursor: pointer;
		font-size: 0.9rem;
	}
	.local ul {
		columns: 2 22rem;
		column-gap: 2rem;
		padding-left: 1.1rem;
	}
	.local li {
		break-inside: avoid;
		margin-bottom: 0.25rem;
	}
	.chamber {
		display: grid;
		grid-template-columns: minmax(0, 1.4fr) minmax(0, 1fr);
		gap: 1rem 2rem;
		align-items: center;
		margin-bottom: 1.5rem;
	}
	@media (max-width: 760px) {
		.chamber {
			grid-template-columns: 1fr;
		}
	}
	.fav {
		list-style: none;
		padding: 0;
		margin: 0;
		display: grid;
		gap: 0.4rem;
	}
	.fav .tiers {
		display: flex;
		flex-wrap: wrap;
		gap: 0.3rem 0.9rem;
		margin-top: 0.6rem;
		color: var(--fg-2);
	}
	.fav .tiers i {
		display: inline-block;
		width: 0.75rem;
		height: 0.75rem;
		border-radius: 50%;
		background: var(--fg-2);
		margin-right: 0.35rem;
		vertical-align: -0.1rem;
	}
	.hists {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(18rem, 1fr));
		gap: 1.5rem 2rem;
	}
	.minor {
		max-width: 34rem;
		margin-top: 1.25rem;
	}
	.chip {
		display: inline-flex;
		align-items: center;
		gap: 0.35rem;
	}
	.chip::before {
		content: '';
		width: 0.6rem;
		height: 0.6rem;
		border-radius: 2px;
		background: var(--c);
	}
	.forest {
		list-style: none;
		padding: 0;
		margin: 0;
		display: grid;
		gap: 0.6rem;
		max-width: 44rem;
	}
	.forest li {
		display: grid;
		grid-template-columns: 6.5rem 1fr 8rem;
		gap: 0.75rem;
		align-items: center;
		font-size: 0.9rem;
	}
	.forest .tpp {
		margin-top: 0.5rem;
		padding-top: 0.6rem;
		border-top: 1px solid var(--rule);
	}
	.lbl {
		color: var(--fg-2);
	}
	.track {
		position: relative;
		height: 1rem;
		background: linear-gradient(var(--rule), var(--rule)) center / 100% 1px no-repeat;
	}
	.range {
		position: absolute;
		top: 0.3rem;
		height: 0.4rem;
		border-radius: 3px;
		opacity: 0.45;
	}
	.dot {
		position: absolute;
		top: 0.1rem;
		width: 0.8rem;
		height: 0.8rem;
		border-radius: 50%;
		transform: translateX(-50%);
		border: 2px solid var(--surface);
	}
	.half {
		position: absolute;
		top: -0.2rem;
		bottom: -0.2rem;
		border-left: 1px dashed var(--fg-2);
	}
	.v {
		text-align: right;
		font-weight: 600;
	}
	.controls {
		display: flex;
		gap: 1rem;
		align-items: center;
		margin-bottom: 0.75rem;
	}
	input[type='search'],
	select {
		font: inherit;
		font-size: 0.9rem;
		padding: 0.35rem 0.6rem;
		border: 1px solid var(--rule-strong);
		border-radius: var(--radius);
		background: var(--surface);
		color: var(--fg);
	}
	select {
		margin-left: 0.35rem;
	}
	.seats {
		list-style: none;
		margin: 0;
		padding: 0;
		columns: 2 30rem;
		column-gap: 2.5rem;
	}
	.seats li {
		break-inside: avoid;
	}
	.seats a {
		display: grid;
		grid-template-columns: minmax(0, 1.4fr) minmax(5rem, 1fr) 7.5rem;
		gap: 0.75rem;
		align-items: center;
		padding: 0.3rem 0.25rem;
		border-bottom: 1px solid var(--rule);
		font-size: 0.88rem;
		text-decoration: none;
	}
	.seats a:hover {
		background: var(--rule);
	}
	.name {
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}
	.probbar {
		display: flex;
		gap: 1px;
		height: 0.75rem;
		border-radius: 3px;
		overflow: hidden;
	}
	.probbar span {
		flex-basis: 0;
	}
	.fav {
		text-align: right;
	}
	.diag {
		margin-top: 2rem;
	}
</style>
