<script lang="ts">
	import { SITE_NAME } from '$lib/site';
	import type { PageData } from './$types';
	import OutcomeBar from '$lib/components/charts/OutcomeBar.svelte';
	import Hemicycle from '$lib/components/charts/Hemicycle.svelte';
	import SeatMap from '$lib/components/charts/SeatMap.svelte';
	import { fmtDate } from '$lib/format';
	import { chamberSeats, tierOpacity, mapFrame } from '$lib/maps';
	import { party, partyColour } from '$lib/parties';

	let { data }: { data: PageData } = $props();
	const f = $derived(data.forecast);
	const j = $derived(data.jurisdiction);
	const actual = $derived(f.actual!);
	const scores = $derived(f.scores!);
	const area = $derived(j.kind === 'federal' ? 'National' : 'Statewide');
	const electionName = $derived(j.kind === 'federal' ? `${data.year} federal election` : `${data.year} ${j.name === 'Victoria' ? 'Victorian' : j.name} ${j.kind === 'territory' ? 'territory' : 'state'} election`);

	const pct = (p: number) => (p < 0.005 ? '<1%' : p > 0.995 ? '>99%' : `${Math.round(p * 100)}%`);
	const inHundred = (p: number) => (p < 0.01 ? 'less than 1' : p > 0.99 ? 'more than 99' : `${Math.round(p * 100)}`);
	const COAL = ['COAL', 'LIB', 'NAT', 'LNP', 'CLP'];
	const sumSeats = (codes: string[]) => codes.reduce((a, c) => a + (actual.seat_counts[c] ?? 0), 0);

	// What happened, in the forecast's outcome categories.
	const outcome = $derived.by(() => {
		const alp = sumSeats(['ALP']);
		const coal = sumSeats(COAL);
		if (alp >= f.majority) return { label: 'Labor majority', p: f.outcome.alp_majority };
		if (coal >= f.majority) return { label: 'Coalition majority', p: f.outcome.coal_majority };
		return { label: 'hung parliament', p: f.outcome.hung };
	});

	const n = $derived(f.districts.length);
	const hits = $derived(f.districts.filter((d) => d.leader === d.actual_winner).length);
	const statusQuo = $derived(Math.round(scores.status_quo_accuracy * n));

	// Seat totals: forecast 90% range and median against the actual count.
	const seatRows = $derived(Object.entries(scores.seats));
	const seatMax = $derived(
		Math.ceil(Math.max(f.majority, ...seatRows.map(([, s]) => Math.max(s.p90[1], s.actual))) / 10) * 10
	);

	// Vote: forecast interval against the actual share.
	const voteRows = $derived(
		['ALP', 'COAL', 'GRN', 'ONP']
			// Skip parties neither forecast nor recorded (One Nation did not contest Victoria in 2018).
			.filter((k) => f.statewide_primary[k] && (f.statewide_primary[k][1] >= 0.5 || actual.primary[k] != null))
			.map((k) => ({ k, v: f.statewide_primary[k], a: actual.primary[k] ?? null }))
	);
	const voteMax = $derived(
		Math.ceil(Math.max(...voteRows.map((r) => Math.max(r.v[2], r.a ?? 0))) / 5) * 5
	);
	const inRange = (a: number | null, v: number[]) => a != null && a >= v[0] && a <= v[v.length - 1];

	// Chambers
	const seatHref = (slug: string) => `/${j.code}/results/${data.year}/${slug}/`;
	const forecastChamber = $derived(
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
	const actualChamber = $derived(
		chamberSeats(
			f.districts.map((d) => ({
				slug: d.slug,
				name: d.district,
				party: d.actual_winner ?? 'OTH',
				strength: d.p_actual ?? 0,
				detail: d.leader === d.actual_winner ? 'favourite won' : `favourite lost (model gave ${pct(d.p_actual ?? 0)})`,
				href: seatHref(d.slug),
				// Seats the favourite lost stand out; the rest are faded.
				opacity: d.leader === d.actual_winner ? 0.35 : 1
			}))
		)
	);

	// Map
	const bySlug = $derived(Object.fromEntries(f.districts.map((d) => [d.slug, d])));
	function seatTip(slug: string) {
		const d = bySlug[slug];
		if (!d) return { title: slug, lines: [] };
		const prims = ['ALP', 'COAL', 'GRN', 'ONP']
			.filter((b) => (d.primary[b]?.[1] ?? 0) >= 3 || (d.actual_primary?.[b] ?? 0) >= 3)
			.map((b) => `${party(b).short} ${d.primary[b]?.[1].toFixed(0) ?? '–'} → ${d.actual_primary?.[b]?.toFixed(0) ?? '–'}`);
		return {
			title: `${d.district} (held by ${party(d.incumbent).short})`,
			lines: [
				`Favourite: ${party(d.leader).short} ${pct(d.leader_prob)}`,
				`Won by ${party(d.actual_winner ?? 'OTH').short} (model gave ${pct(d.p_actual ?? 0)})`,
				`First prefs, forecast → actual: ${prims.join(', ')}`
			]
		};
	}

	// Calibration chart
	const CAL = { w: 320, h: 260, l: 40, r: 12, t: 12, b: 38, lo: 0.4 };
	const cx = (p: number) => CAL.l + ((p - CAL.lo) / (1 - CAL.lo)) * (CAL.w - CAL.l - CAL.r);
	const cy = (p: number) => CAL.h - CAL.b - ((p - CAL.lo) / (1 - CAL.lo)) * (CAL.h - CAL.t - CAL.b);
	const ticks = [0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1];

	// Seat table
	let view = $state<'all' | 'misses' | 'changed'>('all');
	let sortKey = $state<'surprise' | 'name' | 'confidence'>('surprise');
	let query = $state('');
	const rows = $derived(
		f.districts
			.filter((d) => !query || d.district.toLowerCase().includes(query.toLowerCase()))
			.filter((d) =>
				view === 'misses' ? d.leader !== d.actual_winner : view === 'changed' ? d.actual_winner !== d.incumbent : true
			)
			.toSorted((a, b) => {
				if (sortKey === 'name') return a.district.localeCompare(b.district);
				if (sortKey === 'confidence') return a.leader_prob - b.leader_prob;
				return (a.p_actual ?? 0) - (b.p_actual ?? 0) || a.district.localeCompare(b.district);
			})
	);
	const surprises = $derived(
		f.districts.filter((d) => (d.p_actual ?? 0) < 0.1).toSorted((a, b) => (a.p_actual ?? 0) - (b.p_actual ?? 0))
	);
</script>

<svelte:head>
	<title>{electionName}: forecast vs result · {SITE_NAME}</title>
</svelte:head>

<p class="eyebrow">
	{j.name} · {fmtDate(f.election_date)} · <a href="../">the forecast</a>
</p>
<h1>The {electionName}: forecast against the result</h1>
<p class="lede">
	The election produced a {outcome.label}; the model's blind forecast had given that a
	<strong>{inHundred(outcome.p)} in 100</strong> chance. Labor won {sumSeats(['ALP'])} of {n} seats with
	{actual.tpp_alp.toFixed(1)}% of the two-party vote, against a forecast of {f.tpp_alp[1].toFixed(1)}%.
</p>
{#if j.dataNote}<p class="small muted">{j.dataNote}</p>{/if}

<div class="tiles">
	<div class="tile">
		<span class="tile-label">Favourite won</span>
		<span class="tile-value num">{hits}<span class="of">/{n}</span></span>
		<span class="tile-note muted">seats</span>
	</div>
	<div class="tile">
		<span class="tile-label">"No change" guess</span>
		<span class="tile-value num">{statusQuo}<span class="of">/{n}</span></span>
		<span class="tile-note muted">every seat kept by its holder</span>
	</div>
	<div class="tile">
		<span class="tile-label">Brier score</span>
		<span class="tile-value num">{scores.brier.toFixed(3)}</span>
		<span class="tile-note muted">"no change": {(2 * (1 - scores.status_quo_accuracy)).toFixed(3)}; lower is better</span>
	</div>
	<div class="tile">
		<span class="tile-label">Labor 2PP</span>
		<span class="tile-value num">{actual.tpp_alp.toFixed(1)}</span>
		<span class="tile-note muted">forecast {f.tpp_alp[1].toFixed(1)} ({f.tpp_alp[0].toFixed(0)}–{f.tpp_alp[2].toFixed(0)})</span>
	</div>
</div>

<h2>Who forms government</h2>
<OutcomeBar alpMajority={f.outcome.alp_majority} hung={f.outcome.hung} coalMajority={f.outcome.coal_majority} />
<p class="small">
	<span class="actual-key"></span> Actual outcome: <strong>{outcome.label}</strong> ({sumSeats(['ALP'])} Labor,
	{sumSeats(COAL)} Coalition, {n - sumSeats(['ALP']) - sumSeats(COAL)} crossbench; {f.majority} needed for a majority).
</p>

<h2>Seat totals</h2>
<p class="small muted">
	Bars show the forecast 90% range, the hollow dot the median, and the black mark the number actually won.
</p>
<ul class="ranges">
	{#each seatRows as [p, s] (p)}
		<li>
			<span class="lbl"><span class="chip" style:--c={partyColour(p)}>{party(p).short}</span></span>
			<span class="track">
				{#if p === 'ALP' || p === 'COAL'}
					<span class="maj" style:left="{(100 * f.majority) / seatMax}%" title="Majority: {f.majority}"></span>
				{/if}
				<span class="range" style:left="{(100 * s.p90[0]) / seatMax}%" style:width="{(100 * (s.p90[1] - s.p90[0])) / seatMax}%" style:background={partyColour(p)}></span>
				<span class="median" style:left="{(100 * s.median) / seatMax}%" style:border-color={partyColour(p)}></span>
				<span class="actual" style:left="{(100 * s.actual) / seatMax}%"></span>
			</span>
			<span class="num v">
				<strong>{s.actual}</strong>
				<span class="muted small">vs {s.median} ({s.p90[0]}–{s.p90[1]}){s.covered_90 ? '' : ' · outside'}</span>
			</span>
		</li>
	{/each}
	<li class="axis small muted">
		<span></span>
		<span class="track-axis"><span>0</span><span>{f.majority} for majority</span><span>{seatMax}</span></span>
		<span></span>
	</li>
</ul>

<h2>{area} vote</h2>
<p class="small muted">First preferences: forecast 90% interval and median, with the actual result marked.</p>
<ul class="ranges">
	{#each voteRows as { k, v, a } (k)}
		<li>
			<span class="lbl">{party(k).short}</span>
			<span class="track">
				<span class="range" style:left="{(100 * v[0]) / voteMax}%" style:width="{(100 * (v[2] - v[0])) / voteMax}%" style:background={partyColour(k)}></span>
				<span class="median" style:left="{(100 * v[1]) / voteMax}%" style:border-color={partyColour(k)}></span>
				{#if a != null}<span class="actual" style:left="{(100 * a) / voteMax}%"></span>{/if}
			</span>
			<span class="num v">
				{#if a != null}<strong>{a.toFixed(1)}%</strong>{:else}<span class="muted">–</span>{/if}
				<span class="muted small">vs {v[1].toFixed(1)}{a != null && !inRange(a, v) ? ' · outside' : ''}</span>
			</span>
		</li>
	{/each}
	<li class="tpp">
		<span class="lbl">Labor 2PP</span>
		<span class="track">
			<span class="half" style:left="50%"></span>
			<span class="range" style:left="{f.tpp_alp[0]}%" style:width="{f.tpp_alp[2] - f.tpp_alp[0]}%" style:background={partyColour('ALP')}></span>
			<span class="median" style:left="{f.tpp_alp[1]}%" style:border-color={partyColour('ALP')}></span>
			<span class="actual" style:left="{actual.tpp_alp}%"></span>
		</span>
		<span class="num v"><strong>{actual.tpp_alp.toFixed(1)}%</strong> <span class="muted small">vs {f.tpp_alp[1].toFixed(1)}</span></span>
	</li>
</ul>

<h2>Seat by seat</h2>
<p class="small muted">
	Left: the forecast favourite in each seat, shaded by confidence. Right: who won, with the {n - hits} seats the
	favourite lost in full colour.
</p>
<div class="chambers">
	<Hemicycle title="Forecast favourite" seats={forecastChamber} majority={f.majority} />
	<Hemicycle title="Actual winner" seats={actualChamber} majority={f.majority} />
</div>

{#if data.geo}
	<SeatMap
		title="Where the forecast favourite lost"
		geo={data.geo}
		frame={mapFrame(data.jurisdiction.code)}
		fill={(slug) => partyColour(bySlug[slug]?.actual_winner ?? 'OTH')}
		opacity={(slug) => (bySlug[slug] && bySlug[slug].leader !== bySlug[slug].actual_winner ? 1 : 0.18)}
		tooltip={seatTip}
		href={seatHref}
		legend={[
			{ label: 'Favourite lost (coloured by winner)', colour: 'var(--fg-2)' },
			{ label: 'Favourite won', colour: 'var(--fg-2)', opacity: 0.18 }
		]}
	/>
{/if}

<div class="grid2">
	<div>
		<h2>Were the probabilities honest?</h2>
		<p class="small muted">
			Seats grouped by how confident the model was in its favourite. A well-calibrated forecast sits on the
			diagonal: favourites given about 80% should win about 80% of the time. Circle size shows the number of
			seats.
		</p>
		<svg class="cal" viewBox="0 0 {CAL.w} {CAL.h}" role="img" aria-label="Calibration: {scores.calibration.map((c) => `${c.bin} ${c.n} seats, forecast ${pct(c.mean_prob)}, won ${pct(c.hit_rate)}`).join('; ')}">
			{#each ticks as t (t)}
				<line class="grid" x1={cx(t)} x2={cx(t)} y1={cy(CAL.lo)} y2={cy(1)} />
				<line class="grid" x1={cx(CAL.lo)} x2={cx(1)} y1={cy(t)} y2={cy(t)} />
				<text class="tick" x={cx(t)} y={CAL.h - CAL.b + 14} text-anchor="middle">{Math.round(t * 100)}</text>
				<text class="tick" x={CAL.l - 6} y={cy(t) + 4} text-anchor="end">{Math.round(t * 100)}</text>
			{/each}
			<line class="diag" x1={cx(CAL.lo)} y1={cy(CAL.lo)} x2={cx(1)} y2={cy(1)} />
			{#each scores.calibration as c (c.bin)}
				<circle cx={cx(c.mean_prob)} cy={cy(Math.max(c.hit_rate, CAL.lo))} r={3 + Math.sqrt(c.n) * 1.4}>
					<title>{c.bin.replace('-', '–')}: {c.n} seats, average forecast {pct(c.mean_prob)}, favourite won {pct(c.hit_rate)}</title>
				</circle>
			{/each}
			<text class="axis-label" x={(CAL.l + CAL.w - CAL.r) / 2} y={CAL.h - 4} text-anchor="middle">Favourite's forecast chance (%)</text>
			<text class="axis-label" transform="translate(11 {(CAL.t + CAL.h - CAL.b) / 2}) rotate(-90)" text-anchor="middle">Favourite won (%)</text>
		</svg>
	</div>
	<div>
		<h2>Biggest surprises</h2>
		<p class="small muted">Seats won by a party the model gave less than a 10% chance.</p>
		{#if surprises.length}
			<ul class="surprises small">
				{#each surprises as d (d.slug)}
					<li>
						<a href={seatHref(d.slug)}><strong>{d.district}</strong></a>: {party(d.actual_winner ?? 'OTH').short} won
						({pct(d.p_actual ?? 0)}); {party(d.leader).short} was favoured at {pct(d.leader_prob)}.
					</li>
				{/each}
			</ul>
		{:else}
			<p class="small">None.</p>
		{/if}
	</div>
</div>

<h2>Every seat</h2>
<div class="controls">
	<input type="search" placeholder="Search seats" bind:value={query} aria-label="Search seats" />
	<label class="small">Show
		<select bind:value={view}>
			<option value="all">All seats</option>
			<option value="misses">Favourite lost</option>
			<option value="changed">Changed hands</option>
		</select>
	</label>
	<label class="small">Sort
		<select bind:value={sortKey}>
			<option value="surprise">Biggest surprise first</option>
			<option value="confidence">Closest forecast first</option>
			<option value="name">Name</option>
		</select>
	</label>
	<span class="small muted">{rows.length} seats</span>
</div>
<div class="table-wrap">
	<table class="data seats">
		<thead>
			<tr>
				<th class="left">Seat</th>
				<th class="left">Held by</th>
				<th class="left">Forecast favourite</th>
				<th class="left">Won by</th>
				<th>Model's chance for winner</th>
			</tr>
		</thead>
		<tbody>
			{#each rows as d (d.slug)}
				{@const hit = d.leader === d.actual_winner}
				<tr class:miss={!hit}>
					<td class="left"><a href={seatHref(d.slug)}>{d.district}</a></td>
					<td class="left"><span class="chip" style:--c={partyColour(d.incumbent)}>{party(d.incumbent).short}</span></td>
					<td class="left">
						<span class="chip" style:--c={partyColour(d.leader)}>{party(d.leader).short}</span>
						<span class="muted">{pct(d.leader_prob)}</span>
					</td>
					<td class="left">
						<span class="chip" style:--c={partyColour(d.actual_winner ?? 'OTH')}>{party(d.actual_winner ?? 'OTH').short}</span>
					</td>
					<td>
						<span class="pbar"><span style:width="{100 * (d.p_actual ?? 0)}%" style:background={partyColour(d.actual_winner ?? 'OTH')}></span></span>
						<span class="num">{pct(d.p_actual ?? 0)}</span>
						<span class="mark" aria-label={hit ? 'favourite won' : 'favourite lost'}>{hit ? '✓' : '✗'}</span>
					</td>
				</tr>
			{/each}
		</tbody>
	</table>
</div>

<p class="small muted diag">
	Forecast built with model {f.model_version}{j.kind === 'federal'
		? '. Federal seats are scored with the Liberals, Nationals and LNP counted together as the Coalition'
		: ''}. See the <a href="/methodology/">methodology</a> for how the backtest is run.
</p>

<style>
	.tiles {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(10rem, 1fr));
		gap: 0.75rem;
		margin: 1.25rem 0 0.5rem;
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
		font-size: 0.85rem;
		color: var(--fg-2);
	}
	.tile-value {
		font-size: 1.9rem;
		font-weight: 650;
		line-height: 1.2;
	}
	.of {
		font-size: 1rem;
		font-weight: 500;
		color: var(--fg-2);
	}
	.tile-note {
		font-size: 0.8rem;
	}
	.actual-key {
		display: inline-block;
		width: 3px;
		height: 0.9rem;
		background: var(--fg);
		vertical-align: -0.15rem;
		margin-right: 0.2rem;
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
	.ranges {
		list-style: none;
		padding: 0;
		margin: 0;
		display: grid;
		gap: 0.65rem;
		max-width: 46rem;
	}
	.ranges li {
		display: grid;
		grid-template-columns: 6.5rem 1fr 10rem;
		gap: 0.75rem;
		align-items: center;
		font-size: 0.9rem;
	}
	.ranges .tpp {
		margin-top: 0.5rem;
		padding-top: 0.6rem;
		border-top: 1px solid var(--rule);
	}
	.lbl {
		color: var(--fg-2);
	}
	.track {
		position: relative;
		height: 1.1rem;
		background: linear-gradient(var(--rule), var(--rule)) center / 100% 1px no-repeat;
	}
	.range {
		position: absolute;
		top: 0.3rem;
		height: 0.5rem;
		border-radius: 3px;
		opacity: 0.4;
	}
	.median {
		position: absolute;
		top: 0.15rem;
		width: 0.8rem;
		height: 0.8rem;
		border-radius: 50%;
		transform: translateX(-50%);
		border: 2px solid;
		background: var(--surface);
	}
	.actual {
		position: absolute;
		top: -0.15rem;
		bottom: -0.15rem;
		width: 3px;
		transform: translateX(-50%);
		background: var(--fg);
		border-radius: 1px;
	}
	.maj,
	.half {
		position: absolute;
		top: -0.25rem;
		bottom: -0.25rem;
		border-left: 1px dashed var(--fg-2);
	}
	.track-axis {
		display: flex;
		justify-content: space-between;
	}
	.v {
		text-align: right;
	}
	.chambers {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(17rem, 1fr));
		gap: 1rem 2rem;
		margin-bottom: 1.5rem;
	}
	.grid2 {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(18rem, 1fr));
		gap: 1rem 2.5rem;
		align-items: start;
	}
	.cal {
		width: 100%;
		max-width: 26rem;
		height: auto;
		display: block;
	}
	.cal .grid {
		stroke: var(--rule);
	}
	.cal .diag {
		stroke: var(--fg-2);
		stroke-dasharray: 4 3;
	}
	.cal circle {
		fill: var(--fg);
		fill-opacity: 0.75;
		stroke: var(--surface);
		stroke-width: 1.5;
	}
	.cal .tick {
		font-size: 10px;
		fill: var(--fg-2);
	}
	.cal .axis-label {
		font-size: 11px;
		fill: var(--fg-2);
	}
	.surprises {
		padding-left: 1.1rem;
		margin: 0;
	}
	.surprises li {
		margin-bottom: 0.3rem;
	}
	.controls {
		display: flex;
		flex-wrap: wrap;
		gap: 0.6rem 1rem;
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
	.table-wrap {
		overflow-x: auto;
	}
	.seats {
		width: 100%;
		font-size: 0.88rem;
	}
	.seats td {
		white-space: nowrap;
	}
	.seats tr.miss td:first-child {
		box-shadow: inset 3px 0 0 var(--fg);
	}
	.pbar {
		display: inline-block;
		width: 5rem;
		height: 0.55rem;
		background: var(--rule);
		border-radius: 3px;
		overflow: hidden;
		vertical-align: middle;
		margin-right: 0.4rem;
	}
	.pbar span {
		display: block;
		height: 100%;
	}
	.mark {
		display: inline-block;
		width: 1.2rem;
		text-align: center;
	}
	.miss .mark {
		font-weight: 700;
	}
	.diag {
		margin-top: 2rem;
	}
	@media (max-width: 560px) {
		.ranges li {
			grid-template-columns: 4.5rem 1fr 7.5rem;
			gap: 0.5rem;
		}
	}
</style>
