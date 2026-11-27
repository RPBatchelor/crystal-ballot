<script lang="ts">
	import { browser } from '$app/environment';
	import { coalName, coalShort, theCoal } from '$lib/jurisdictions';
	import { SITE_NAME } from '$lib/site';
	import type { PageData } from './$types';
	import type { ForecastDistrict, Sims } from '$lib/types';
	import { loadSims } from '$lib/data';
	import { sampleElection, type SampledElection } from '$lib/sims';
	import OutcomeBar from '$lib/components/charts/OutcomeBar.svelte';
	import SeatHistogram from '$lib/components/charts/SeatHistogram.svelte';
	import MarginHistogram from '$lib/components/charts/MarginHistogram.svelte';
	import SeatHeatmap from '$lib/components/charts/SeatHeatmap.svelte';
	import TppDistribution from '$lib/components/charts/TppDistribution.svelte';
	import TrendLines from '$lib/components/charts/TrendLines.svelte';
	import Hemicycle from '$lib/components/charts/Hemicycle.svelte';
	import SeatMap from '$lib/components/charts/SeatMap.svelte';
	import SeatDrawer from '$lib/components/SeatDrawer.svelte';
	import ScenarioExplorer from '$lib/components/ScenarioExplorer.svelte';
	import { article, fmtDate } from '$lib/format';
	import { chamberSeats, tierOpacity, TIERS, mapFrame } from '$lib/maps';
	import { party, partyColour } from '$lib/parties';

	let { data }: { data: PageData } = $props();
	const f = $derived(data.forecast);
	const j = $derived(data.jurisdiction);
	const coalLabel = $derived(coalName(j.code));
	const coalShortLbl = $derived(coalShort(j.code));
	const theC = $derived(theCoal(j.code));
	const retro = $derived(f.mode === 'retrospective');
	const area = $derived(j.kind === 'federal' ? 'National' : 'Statewide');

	// Client-side load of 20,000 raw simulations for Scenario Explorer + HOPs (live forecasts).
	let sims = $state<Sims | null>(null);
	let scenarioLocks = $state<Record<number, string>>({});
	let sampled = $state<SampledElection | null>(null);

	$effect(() => {
		if (!browser || retro) {
			sims = null;
			return;
		}
		let alive = true;
		const code = j.code;
		const yr = data.year;
		loadSims(fetch, code, yr).then((res) => {
			if (alive) sims = res;
		});
		return () => {
			alive = false;
		};
	});

	function drawOneNight() {
		if (!sims) return;
		sampled = sampleElection(sims, f.majority);
	}

	// Seat forecast drawer state
	let selectedSlug = $state<string | null>(null);
	const bySlug = $derived(Object.fromEntries(f.districts.map((d) => [d.slug, d])));
	const byName = $derived(Object.fromEntries(f.districts.map((d) => [d.district, d])));
	const selectedDistrict = $derived<ForecastDistrict | null>(
		selectedSlug ? (bySlug[selectedSlug] ?? null) : null
	);

	function lockFromDrawer(districtName: string, partyCode: string) {
		if (!sims) return;
		const idx = sims.header.districts.indexOf(districtName);
		if (idx < 0) return;
		scenarioLocks = { ...scenarioLocks, [idx]: partyCode };
		document.getElementById('scenarios')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
	}

	const headline = $derived.by(() => {
		const o = f.outcome;
		const top = [
			{ p: o.coal_majority, t: `${article(coalLabel)} ${coalLabel} majority` },
			{ p: o.hung, t: 'a hung parliament' },
			{ p: o.alp_majority, t: 'a Labor majority' }
		].sort((a, b) => b.p - a.p)[0];
		return retro ? `The model's most likely outcome was ${top.t}` : `The most likely outcome is ${top.t}`;
	});

	const minor = $derived(
		(['GRN', 'ONP', 'IND'] as const).filter((p) => (f.seats[p]?.[4] ?? 0) > 0 && f.seat_hist[p])
	);
	const hasOnp = $derived((f.statewide_primary.ONP?.[1] ?? 0) >= 1.5);
	const voteOrder = ['ALP', 'COAL', 'GRN', 'ONP', 'OTH'];
	const voteMax = $derived(
		Math.ceil(Math.max(...voteOrder.map((k) => f.statewide_primary[k]?.[2] ?? 0)) / 5) * 5
	);

	// Multi-mode forecast map
	type MapMode = 'favourite' | 'flips' | 'uncertainty' | 'onp' | 'grn';
	let mapMode = $state<MapMode>('favourite');
	const mapModes = $derived<{ key: MapMode; label: string }[]>([
		{ key: 'favourite', label: 'Favourite & confidence' },
		{ key: 'flips', label: 'Likely flips' },
		{ key: 'uncertainty', label: 'Closest races' },
		...(hasOnp ? [{ key: 'onp' as const, label: 'One Nation primary' }] : []),
		{ key: 'grn', label: 'Greens primary' }
	]);

	// Sampled election winners keyed by district slug (for HOP mode).
	const sampledBySlug = $derived.by(() => {
		if (!sampled || !sims) return null;
		const out: Record<string, string> = {};
		sims.header.districts.forEach((name, idx) => {
			const d = byName[name];
			if (d) out[d.slug] = sampled!.winners[idx];
		});
		return out;
	});

	// Seat table filters & sorting
	const partyOrder = ['ALP', 'GRN', 'IND', 'OTH', 'ONP', 'NAT', 'LIB', 'LNP', 'COAL'];
	let sortKey = $state<'name' | 'certainty' | 'alp' | 'coal' | 'onp' | 'grn'>('certainty');
	let seatFilter = $state<'all' | 'flips' | 'tossups' | 'local'>('all');
	let regionFilter = $state('all');
	let query = $state('');
	const regions = $derived([...new Set(f.districts.map((d) => d.region))].sort());
	const coalP = (d: ForecastDistrict) =>
		(d.probs.LIB ?? 0) + (d.probs.NAT ?? 0) + (d.probs.LNP ?? 0) + (d.probs.COAL ?? 0);
	const rows = $derived(
		f.districts
			.filter((d) => !query || d.district.toLowerCase().includes(query.toLowerCase()))
			.filter((d) => regionFilter === 'all' || d.region === regionFilter)
			.filter((d) => {
				if (seatFilter === 'flips') return d.leader !== d.incumbent;
				if (seatFilter === 'tossups') return d.leader_prob < 0.7;
				if (seatFilter === 'local') return Boolean(d.notes?.length);
				return true;
			})
			.toSorted((a, b) => {
				if (sortKey === 'name') return a.district.localeCompare(b.district);
				if (sortKey === 'alp') return (b.probs.ALP ?? 0) - (a.probs.ALP ?? 0);
				if (sortKey === 'coal') return coalP(b) - coalP(a);
				if (sortKey === 'onp') return (b.probs.ONP ?? 0) - (a.probs.ONP ?? 0);
				if (sortKey === 'grn') return (b.probs.GRN ?? 0) - (a.probs.GRN ?? 0);
				return a.leader_prob - b.leader_prob;
			})
	);

	const pct = (p: number) => (p < 0.005 ? '<1%' : p > 0.995 ? '>99%' : `${Math.round(p * 100)}%`);
	const seatHref = (slug: string) =>
		data.lastResults ? `/${j.code}/results/${data.lastResults}/${slug}/` : undefined;

	const chamber = $derived(
		chamberSeats(
			f.districts.map((d) => {
				const win = sampledBySlug?.[d.slug];
				if (win) {
					return {
						slug: d.slug,
						name: d.district,
						party: win,
						strength: 1,
						detail: `Simulation #${sampled!.simIndex + 1}`,
						opacity: 1
					};
				}
				return {
					slug: d.slug,
					name: d.district,
					party: d.leader,
					strength: d.leader_prob,
					detail: `${pct(d.leader_prob)} chance`,
					opacity: tierOpacity(d.leader_prob)
				};
			})
		)
	);
	const favCounts = $derived(
		Object.entries(
			f.districts.reduce<Record<string, number>>((acc, d) => {
				const k = sampledBySlug?.[d.slug] ?? d.leader;
				acc[k] = (acc[k] ?? 0) + 1;
				return acc;
			}, {})
		).sort((a, b) => b[1] - a[1])
	);

	function seatFill(slug: string): string {
		const d = bySlug[slug];
		if (!d) return 'var(--rule)';
		if (sampledBySlug) return partyColour(sampledBySlug[slug] ?? 'OTH');
		if (mapMode === 'uncertainty') return 'var(--swirl-violet)';
		if (mapMode === 'onp') return partyColour('ONP');
		if (mapMode === 'grn') return partyColour('GRN');
		return partyColour(d.leader);
	}
	function seatOpacity(slug: string): number {
		const d = bySlug[slug];
		if (!d) return 0.2;
		if (sampledBySlug) return 1;
		if (mapMode === 'flips') return d.leader !== d.incumbent ? 1 : 0.14;
		if (mapMode === 'uncertainty') return Math.min(1, Math.max(0.08, (1 - d.leader_prob) / 0.5));
		if (mapMode === 'onp') return Math.min(1, Math.max(0.08, (d.primary.ONP?.[1] ?? 0) / 38));
		if (mapMode === 'grn') return Math.min(1, Math.max(0.08, (d.primary.GRN?.[1] ?? 0) / 32));
		return tierOpacity(d.leader_prob);
	}
	const mapLegend = $derived.by(() => {
		if (sampledBySlug) return favCounts.map(([p]) => ({ label: party(p).short, colour: partyColour(p) }));
		if (mapMode === 'flips') {
			return [
				{ label: 'Favoured to change hands (coloured by leader)', colour: 'var(--fg-2)', opacity: 1 },
				{ label: 'Favoured to hold', colour: 'var(--fg-2)', opacity: 0.16 }
			];
		}
		if (mapMode === 'uncertainty') {
			return [
				{ label: 'High uncertainty (toss-up)', colour: 'var(--swirl-violet)', opacity: 0.95 },
				{ label: 'Moderate', colour: 'var(--swirl-violet)', opacity: 0.45 },
				{ label: 'Safe', colour: 'var(--swirl-violet)', opacity: 0.1 }
			];
		}
		if (mapMode === 'onp') {
			return [
				{ label: '35%+ median ONP', colour: partyColour('ONP'), opacity: 0.95 },
				{ label: '~20% ONP', colour: partyColour('ONP'), opacity: 0.5 },
				{ label: '<5% ONP', colour: partyColour('ONP'), opacity: 0.12 }
			];
		}
		if (mapMode === 'grn') {
			return [
				{ label: '30%+ median Greens', colour: partyColour('GRN'), opacity: 0.95 },
				{ label: '~15% Greens', colour: partyColour('GRN'), opacity: 0.5 },
				{ label: '<5% Greens', colour: partyColour('GRN'), opacity: 0.12 }
			];
		}
		return [
			...favCounts.map(([p]) => ({ label: party(p).short, colour: partyColour(p) })),
			...TIERS.map((t) => ({ label: t.label, colour: 'var(--fg-2)', opacity: t.opacity }))
		];
	});

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
		const extra = sampledBySlug ? [`This simulation: ${party(sampledBySlug[slug] ?? 'OTH').short} wins`] : [];
		return {
			title: `${d.district} (held by ${party(d.incumbent).short})`,
			lines: [...extra, `Chance: ${probs.join(' · ')}`, `Median first prefs: ${prim.join(', ')}`, ...(d.notes ?? []), 'Click for full seat forecast']
		};
	}

	const noted = $derived(
		f.districts.filter((d) => d.notes?.length).toSorted((a, b) => a.district.localeCompare(b.district))
	);

	// Past elections: where the result landed on each distribution.
	const COAL_CODES = ['LIB', 'NAT', 'LNP', 'CLP', 'COAL'];
	const actualSeats = $derived(
		retro && f.actual
			? {
					alp: f.actual.seat_counts.ALP ?? 0,
					coal: COAL_CODES.reduce((a, k) => a + (f.actual!.seat_counts[k] ?? 0), 0)
				}
			: null
	);
	const resultLabel = $derived(`${data.year} result`);

	const history = $derived(data.history && data.history.length >= 2 ? data.history : null);
	const chanceSeries = $derived(
		history
			? [
					{ key: 'coal', label: `${coalLabel} majority`, colour: partyColour('COAL'), points: history.map((h) => ({ date: h.date, v: 100 * h.outcome.coal_majority })) },
					{ key: 'hung', label: 'Hung', colour: 'var(--fg-2)', dashed: true, points: history.map((h) => ({ date: h.date, v: 100 * h.outcome.hung })) },
					{ key: 'alp', label: 'Labor majority', colour: partyColour('ALP'), points: history.map((h) => ({ date: h.date, v: 100 * h.outcome.alp_majority })) }
				]
			: []
	);
	const seatSeries = $derived(
		history
			? (['COAL', 'ALP'] as const).map((k) => ({
					key: k,
					label: k === 'ALP' ? 'Labor' : coalLabel,
					colour: partyColour(k),
					points: history
						.filter((h) => h.seats[k])
						.map((h) => ({ date: h.date, v: h.seats[k][1], lo: h.seats[k][0], hi: h.seats[k][2] }))
				}))
			: []
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
		but this forecast is not yet final. Do not cite.
	</aside>
{:else if data.blindTests.length}
	<aside class="retro">
		<strong>How this model did in blind tests.</strong> Run on the eve of past elections in {j.name} with only
		what was known at the time, the favourite won
		{#each data.blindTests as t, i (t.year)}{i > 0 ? (i === data.blindTests.length - 1 ? ' and ' : ', ') : ''}<a
				href="/{j.code}/forecast/{t.year}/vs-result/">{Math.round(t.favourite * t.seats)} of {t.seats} seats in {t.year}</a
			>{/each}. Assuming no seat changes hands would have got
		{#each data.blindTests as t, i (t.year)}{i > 0 ? (i === data.blindTests.length - 1 ? ' and ' : ', ') : ''}{Math.round(
				t.statusQuo * t.seats
			)}{/each}: few seats change hands, so the forecast's value is in how likely each upset is, not in naming more
		winners. <a href="/methodology/">How the model works →</a>
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
{#if j.dataNote}<p class="small muted">{j.dataNote}</p>{/if}

<OutcomeBar alpMajority={f.outcome.alp_majority} hung={f.outcome.hung} coalMajority={f.outcome.coal_majority} coal={coalShortLbl} />
<p class="small muted">
	Largest party: {coalLabel} in {Math.round(f.outcome.coal_most_seats * 100)} of 100, Labor in {Math.round(
		f.outcome.alp_most_seats * 100
	)} of 100.
</p>

<nav class="jump card" aria-label="Jump to section">
	<a href="#seat-by-seat">Chamber &amp; Map</a>
	<a href="#seat-totals">Seat totals</a>
	{#if !retro}<a href="#scenarios">What-If scenarios</a>{/if}
	<a href="#statewide-vote">{area} vote</a>
	<a href="#every-seat">Every seat ({f.districts.length})</a>
</nav>

{#if history}
	<h2>How the forecast has moved</h2>
	<p class="small muted">One point for each day the model ran; seat lines show the median with a 90% band.</p>
	<div class="trends">
		<TrendLines title="Chance of each outcome" series={chanceSeries} yMax={100} format={(v) => `${Math.round(v)}%`} />
		<TrendLines
			title="Seats won"
			series={seatSeries}
			yMax={Math.ceil(Math.max(f.majority + 10, ...seatSeries.flatMap((s) => s.points.map((p) => p.hi ?? p.v))) / 10) * 10}
			format={(v) => `${Math.round(v)}`}
			reference={{ value: f.majority, label: `${f.majority} for majority` }}
		/>
	</div>
{/if}

<div class="sec-head" id="seat-by-seat">
	<div>
		<h2>Seat by seat</h2>
		<p class="small muted">
			{#if sampled}
				Showing <strong>Simulation #{sampled.simIndex + 1}</strong> — one plausible election night from the model. Click any seat to inspect its full odds.
			{:else}
				Each seat coloured by its most likely winner; shading shows confidence. Click any seat for its full forecast.
			{/if}
		</p>
	</div>
	{#if sims}
		<div class="hop-controls">
			<button type="button" class="hop-btn" onclick={drawOneNight}>
				🎲 {sampled ? 'Draw another night' : 'Simulate 1 election night'}
			</button>
			{#if sampled}
				<button type="button" class="hop-reset" onclick={() => (sampled = null)}>Back to odds</button>
			{/if}
		</div>
	{/if}
</div>

{#if sampled}
	<aside class="hop-banner small">
		<strong>
			{sampled.outcome === 'coal_majority'
				? `${coalLabel} majority`
				: sampled.outcome === 'alp_majority'
					? 'Labor majority'
					: 'Hung parliament'}
		</strong>
		· {coalLabel} <strong class="num">{sampled.counts.COAL}</strong>, Labor <strong class="num">{sampled.counts.ALP}</strong>,
		Greens <strong class="num">{sampled.counts.GRN}</strong>, One Nation <strong class="num">{sampled.counts.ONP}</strong>,
		Ind. <strong class="num">{sampled.counts.IND}</strong>
		· Labor 2PP <strong class="num">{sampled.tppAlp.toFixed(1)}%</strong>
	</aside>
{/if}

<div class="chamber">
	<Hemicycle
		title={sampled ? `Simulated election #${sampled.simIndex + 1}` : 'Most likely winner in each seat'}
		seats={chamber}
		majority={f.majority}
		onSelect={(slug) => (selectedSlug = slug)}
	/>
	<ul class="fav small">
		{#each favCounts as [p, n] (p)}
			<li><span class="chip" style:--c={partyColour(p)}>{party(p).short}</span> {sampled ? 'wins' : 'favoured in'} <strong>{n}</strong></li>
		{/each}
		{#if !sampled}
			<li class="tiers">
				{#each TIERS as t (t.label)}
					<span><i style:opacity={t.opacity}></i>{t.label}</span>
				{/each}
			</li>
		{/if}
	</ul>
</div>

{#if data.geo}
	{#if !sampled}
		<div class="modes" role="group" aria-label="Forecast map view">
			{#each mapModes as m (m.key)}
				<button type="button" aria-pressed={mapMode === m.key} onclick={() => (mapMode = m.key)}>{m.label}</button>
			{/each}
		</div>
	{/if}
	<SeatMap
		title={sampled ? `Simulated election #${sampled.simIndex + 1} by district` : `Forecast map: ${mapMode}`}
		geo={data.geo}
		frame={mapFrame(data.jurisdiction.code)}
		fill={seatFill}
		opacity={seatOpacity}
		tooltip={seatTip}
		onSelect={(slug) => (selectedSlug = slug)}
		legend={mapLegend}
	/>
{/if}

{#if noted.length}
	<details class="local">
		<summary><strong>Local factors in {noted.length} seats</strong> — retiring members, first-term members and by-election swings</summary>
		<ul class="small">
			{#each noted as d (d.slug)}
				<li>
					<button type="button" class="link-btn" onclick={() => (selectedSlug = d.slug)}><strong>{d.district}</strong></button>
					({party(d.incumbent).short}): {d.notes!.join('; ')}
				</li>
			{/each}
		</ul>
	</details>
{/if}

<h2 id="seat-totals">Seat totals</h2>
<div class="hists">
	<SeatHistogram label="Labor" colour={partyColour('ALP')} counts={f.seat_hist.ALP} majority={f.majority} quantiles={f.seats.ALP} />
	<SeatHistogram label={coalLabel} colour={partyColour('COAL')} counts={f.seat_hist.COAL} majority={f.majority} quantiles={f.seats.COAL} />
</div>
{#if minor.length}
	<div class="hists minor-hists">
		{#each minor as p (p)}
			<SeatHistogram
				label={party(p).short}
				colour={partyColour(p)}
				counts={f.seat_hist[p]}
				majority={f.majority}
				quantiles={f.seats[p]}
				showMajority={false}
			/>
		{/each}
	</div>
{/if}

{#if f.seat_margin && f.seat_joint}
	<h2>How big a win?</h2>
	<p class="small muted">
		Every simulation, by how many more seats one major party wins than the other, and by the seats each wins.
		{#if retro}The dashed line and ring mark what happened.{/if}
	</p>
	<div class="win">
		<MarginHistogram
			margin={f.seat_margin}
			actual={actualSeats ? actualSeats.coal - actualSeats.alp : null}
			actualLabel={resultLabel}
			coal={coalShortLbl}
			theCoal={theC}
		/>
		<SeatHeatmap joint={f.seat_joint} majority={f.majority} outcome={f.outcome} actual={actualSeats} actualLabel={resultLabel} coal={coalLabel} />
	</div>
{/if}

{#if !retro}
	<div id="scenarios">
		{#if sims}
			<ScenarioExplorer
				{sims}
				majority={f.majority}
				{coalLabel}
				coalShortLabel={coalShortLbl}
				locks={scenarioLocks}
				onLocksChange={(next) => (scenarioLocks = next)}
				onSelectDistrict={(name) => {
					const d = byName[name];
					if (d) selectedSlug = d.slug;
				}}
			/>
		{:else}
			<section class="card small muted" style="margin-top: 1.5rem;">
				Loading {f.n_sims.toLocaleString()} simulations for the interactive What-If scenario explorer…
			</section>
		{/if}
	</div>
{/if}

<h2 id="statewide-vote">{area} vote</h2>
<p class="small muted">Election-day first-preference estimates with 90% intervals, including polling error.</p>
<ul class="forest">
	{#each voteOrder as k (k)}
		{@const v = f.statewide_primary[k]}
		{#if v && v[2] >= 0.5}
			<li>
				<span class="lbl">{k === 'COAL' ? coalLabel : party(k).short}</span>
				<span class="track">
					<span class="range" style:left="{(100 * v[0]) / voteMax}%" style:width="{(100 * (v[2] - v[0])) / voteMax}%" style:background={partyColour(k)}></span>
					<span class="dot" style:left="{(100 * v[1]) / voteMax}%" style:background={partyColour(k)}></span>
				</span>
				<span class="num v">{v[1].toFixed(1)}% <span class="muted small">({v[0].toFixed(0)}–{v[2].toFixed(0)})</span></span>
			</li>
		{/if}
	{/each}
</ul>
{#if f.tpp_hist}
	<div class="tpp-dist">
		<p class="small muted tpp-head">
			<strong>Labor two-party preferred:</strong> median <strong class="num">{f.tpp_alp[1].toFixed(1)}%</strong>
			(90% range {f.tpp_alp[0].toFixed(1)}–{f.tpp_alp[2].toFixed(1)}%)
		</p>
		<TppDistribution hist={f.tpp_hist} actual={retro ? (f.actual?.tpp_alp ?? null) : null} actualLabel={resultLabel} theCoal={theC} />
	</div>
{/if}

<h2 id="every-seat">Every seat</h2>
<p class="small muted">
	Chance of each party winning, from the simulations. {changes} seats {retro ? 'favoured' : 'currently favour'} a
	different party from the one holding them. Click any seat to inspect its full forecast.
</p>
<div class="controls">
	<input type="search" placeholder="Search seats" bind:value={query} aria-label="Search seats" />
	<div class="modes" role="group" aria-label="Filter seats">
		<button type="button" aria-pressed={seatFilter === 'all'} onclick={() => (seatFilter = 'all')}>All</button>
		<button type="button" aria-pressed={seatFilter === 'flips'} onclick={() => (seatFilter = 'flips')}>Likely flips</button>
		<button type="button" aria-pressed={seatFilter === 'tossups'} onclick={() => (seatFilter = 'tossups')}>Toss-ups (&lt;70%)</button>
		{#if noted.length}
			<button type="button" aria-pressed={seatFilter === 'local'} onclick={() => (seatFilter = 'local')}>Local factors</button>
		{/if}
	</div>
	<label class="small">Region
		<select bind:value={regionFilter}>
			<option value="all">All regions</option>
			{#each regions as reg (reg)}<option value={reg}>{reg}</option>{/each}
		</select>
	</label>
	<label class="small">Sort
		<select bind:value={sortKey}>
			<option value="certainty">Closest first</option>
			<option value="name">Name</option>
			<option value="alp">Labor chance</option>
			<option value="coal">{coalLabel} chance</option>
			{#if hasOnp}<option value="onp">One Nation chance</option>{/if}
			<option value="grn">Greens chance</option>
		</select>
	</label>
	<span class="small muted">{rows.length} seats</span>
</div>
<ol class="seats">
	{#each rows as d (d.slug)}
		{@const flip = d.leader !== d.incumbent}
		<li>
			<button type="button" class="seat-row" onclick={() => (selectedSlug = d.slug)}>
				<span class="name">
					{d.district}
					<span class="muted small">· {party(d.incumbent).short}</span>
					{#if flip}<span class="badge flip">GAIN</span>{/if}
					{#if d.notes?.length}<span class="badge local-dot" title={d.notes.join('; ')}>●</span>{/if}
				</span>
				<span class="probbar" role="img" aria-label={Object.entries(d.probs).map(([p, v]) => `${party(p).short} ${pct(v)}`).join(', ')}>
					{#each partyOrder as p (p)}
						{#if (d.probs[p] ?? 0) > 0.004}
							<span style:flex-grow={d.probs[p]} style:background={partyColour(p)}></span>
						{/if}
					{/each}
				</span>
				<span class="fav num"><strong>{party(d.leader).short}</strong> {pct(d.leader_prob)}</span>
			</button>
		</li>
	{/each}
</ol>

<p class="small muted diag">
	Model {f.model_version}. Poll aggregate diagnostics: R-hat ≤ {f.diagnostics.max_rhat?.toFixed(3)}, minimum
	ESS {Math.round(f.diagnostics.min_ess_bulk ?? 0)}, {f.diagnostics.divergences} divergences.
</p>

<SeatDrawer
	district={selectedDistrict}
	{coalLabel}
	majority={f.majority}
	resultsHref={selectedDistrict ? seatHref(selectedDistrict.slug) : undefined}
	resultsYear={data.lastResults}
	{sims}
	onClose={() => (selectedSlug = null)}
	onLockSeat={!retro ? lockFromDrawer : undefined}
/>

<style>
	.jump {
		display: flex;
		flex-wrap: wrap;
		gap: 0.45rem 1.25rem;
		padding: 0.65rem 1.1rem;
		margin: 1rem 0 0.5rem;
		font-size: 0.88rem;
		font-weight: 600;
	}
	.jump a {
		text-decoration: none;
		color: var(--fg-2);
	}
	.jump a:hover {
		color: var(--fg);
	}
	.sec-head {
		display: flex;
		justify-content: space-between;
		align-items: flex-end;
		gap: 1rem;
		flex-wrap: wrap;
		margin-top: 2.25rem;
	}
	.sec-head h2 {
		margin-top: 0;
	}
	.sec-head p {
		margin: 0 0 0.75rem;
	}
	.hop-controls {
		display: flex;
		gap: 0.5rem;
		align-items: center;
		margin-bottom: 0.75rem;
	}
	.hop-btn {
		font: inherit;
		font-size: 0.85rem;
		font-weight: 650;
		padding: 0.4rem 0.9rem;
		border: 1px solid var(--accent);
		border-radius: 999px;
		background: var(--accent);
		color: var(--on-accent);
		cursor: pointer;
	}
	.hop-btn:hover {
		filter: brightness(1.12);
	}
	.hop-reset {
		font: inherit;
		font-size: 0.82rem;
		padding: 0.35rem 0.75rem;
		border: 1px solid var(--rule-strong);
		border-radius: 999px;
		background: var(--surface);
		color: var(--fg);
		cursor: pointer;
	}
	.hop-banner {
		padding: 0.55rem 0.9rem;
		margin-bottom: 1rem;
		border-radius: var(--radius);
		background: color-mix(in srgb, var(--brand-spark) 22%, var(--surface));
		border: 1px solid var(--brand-spark);
	}
	.modes {
		display: inline-flex;
		flex-wrap: wrap;
		border: 1px solid var(--rule-strong);
		border-radius: var(--radius);
		overflow: hidden;
		margin-bottom: 0.85rem;
	}
	.modes button {
		font: inherit;
		font-size: 0.82rem;
		padding: 0.32rem 0.65rem;
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
	.trends {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(min(100%, 26rem), 1fr));
		gap: 1.5rem 2rem;
	}
	.win {
		display: grid;
		grid-template-columns: minmax(0, 1.4fr) minmax(0, 1fr);
		align-items: start;
		gap: 1.5rem 2rem;
	}
	@media (max-width: 52rem) {
		.win {
			grid-template-columns: minmax(0, 1fr);
		}
	}
	.tpp-dist {
		margin-top: 1.4rem;
		max-width: 46rem;
	}
	.tpp-head {
		margin: 0 0 0.4rem;
	}
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
	.link-btn {
		font: inherit;
		background: none;
		border: 0;
		padding: 0;
		color: inherit;
		text-decoration: underline;
		text-decoration-color: var(--rule-strong);
		cursor: pointer;
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
	.minor-hists {
		margin-top: 1.4rem;
		grid-template-columns: repeat(auto-fit, minmax(15rem, 1fr));
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
	.v {
		text-align: right;
		font-weight: 600;
	}
	.controls {
		display: flex;
		flex-wrap: wrap;
		gap: 0.6rem 1rem;
		align-items: center;
		margin-bottom: 0.75rem;
	}
	.controls .modes {
		margin-bottom: 0;
	}
	input[type='search'],
	select {
		font: inherit;
		font-size: 0.88rem;
		padding: 0.33rem 0.6rem;
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
	.seat-row {
		width: 100%;
		font: inherit;
		color: inherit;
		background: transparent;
		border: 0;
		border-bottom: 1px solid var(--rule);
		text-align: left;
		cursor: pointer;
		display: grid;
		grid-template-columns: minmax(0, 1.5fr) minmax(5rem, 1fr) 7rem;
		gap: 0.75rem;
		align-items: center;
		padding: 0.32rem 0.3rem;
		font-size: 0.88rem;
	}
	.seat-row:hover {
		background: var(--rule);
	}
	.name {
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}
	.badge {
		display: inline-block;
		margin-left: 0.35rem;
		vertical-align: middle;
	}
	.badge.flip {
		font-size: 0.66rem;
		font-weight: 700;
		letter-spacing: 0.04em;
		padding: 0.05rem 0.32rem;
		border-radius: 3px;
		background: color-mix(in srgb, var(--brand-spark) 35%, transparent);
		color: var(--fg);
	}
	.badge.local-dot {
		font-size: 0.55rem;
		color: var(--swirl-violet);
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
