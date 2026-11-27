<script lang="ts">
	import { browser } from '$app/environment';
	import type { PageData } from './$types';
	import type { LiveResultsFile, Sims } from '$lib/types';
	import { loadLiveResults, loadSims } from '$lib/data';
	import {
		AUTO_PROJECT_MARGIN,
		AUTO_PROJECT_PCT,
		conditionLiveForecast,
		mergeLiveSeats,
		scoreLiveSeats,
		type ManualCall
	} from '$lib/live';
	import { coalName, coalShort } from '$lib/jurisdictions';
	import { SITE_NAME } from '$lib/site';
	import { fmtDate } from '$lib/format';
	import { chamberSeats, mapFrame, tierOpacity } from '$lib/maps';
	import { party, partyColour } from '$lib/parties';
	import OutcomeBar from '$lib/components/charts/OutcomeBar.svelte';
	import Hemicycle from '$lib/components/charts/Hemicycle.svelte';
	import SeatMap from '$lib/components/charts/SeatMap.svelte';
	import SeatDrawer from '$lib/components/SeatDrawer.svelte';

	let { data }: { data: PageData } = $props();
	const f = $derived(data.forecast);
	const j = $derived(data.jurisdiction);
	const coalLabel = $derived(coalName(j.code));
	const coalShortLbl = $derived(coalShort(j.code));

	// Client-side simulations for live Bayesian conditioning
	let sims = $state<Sims | null>(null);
	$effect(() => {
		if (!browser) return;
		let alive = true;
		loadSims(fetch, j.code, data.year).then((s) => {
			if (alive) sims = s;
		});
		return () => {
			alive = false;
		};
	});

	// Live feed state + 60s auto-refresh
	let feed = $state<LiveResultsFile | null>(null);
	$effect(() => {
		feed = data.initialLive;
	});
	let autoRefresh = $state(true);
	let refreshing = $state(false);
	let lastFetchMs = $state<number>(Date.now());
	let nowMs = $state<number>(Date.now());

	async function refreshFeed() {
		if (!browser || refreshing) return;
		refreshing = true;
		try {
			const next = await loadLiveResults(fetch, j.code, data.year);
			if (next) feed = next;
			lastFetchMs = Date.now();
		} finally {
			refreshing = false;
		}
	}

	$effect(() => {
		if (!browser) return;
		const tick = setInterval(() => {
			nowMs = Date.now();
		}, 5000);
		return () => clearInterval(tick);
	});

	$effect(() => {
		if (!browser || !autoRefresh) return;
		const timer = setInterval(() => {
			refreshFeed();
		}, 60_000);
		return () => clearInterval(timer);
	});

	const agoLabel = $derived.by(() => {
		const sec = Math.max(0, Math.round((nowMs - lastFetchMs) / 1000));
		if (sec < 10) return 'just now';
		if (sec < 60) return `${sec}s ago`;
		return `${Math.round(sec / 60)}m ago`;
	});

	// Interactive Call Desk (persisted per election in localStorage)
	let callDeskOpen = $state(true);
	let includeProjected = $state(true);
	let manualCalls = $state<Record<string, ManualCall>>({});
	const storageKey = $derived(`cb-live-calls-${j.code}-${data.year}`);

	$effect(() => {
		if (!browser) return;
		try {
			const raw = localStorage.getItem(storageKey);
			manualCalls = raw ? (JSON.parse(raw) as Record<string, ManualCall>) : {};
		} catch {
			manualCalls = {};
		}
	});

	function setManualCall(slug: string, partyCode: string | null) {
		const next = { ...manualCalls };
		if (!partyCode || next[slug]?.party === partyCode) {
			delete next[slug];
		} else {
			next[slug] = { party: partyCode, calledAt: new Date().toISOString() };
		}
		manualCalls = next;
		if (browser) {
			try {
				localStorage.setItem(storageKey, JSON.stringify(next));
			} catch {}
		}
	}

	function clearManualCalls() {
		manualCalls = {};
		if (browser) {
			try {
				localStorage.removeItem(storageKey);
			} catch {}
		}
	}

	// Core live merge, model scoring, and Bayesian conditioning
	const seats = $derived(mergeLiveSeats(f, feed, manualCalls, includeProjected));
	const score = $derived(scoreLiveSeats(seats));
	const conditioned = $derived(conditionLiveForecast(sims, seats, f.majority));
	const bySlug = $derived(Object.fromEntries(seats.map((s) => [s.district.slug, s])));

	// Active outcome probabilities: conditioned on called seats when available, else final forecast
	const activeOutcome = $derived(
		conditioned && conditioned.matched > 0 ? conditioned.outcome : f.outcome
	);
	const activeSeats = $derived.by(() => {
		const blocs = ['COAL', 'ALP', 'GRN', 'ONP', 'IND'] as const;
		return blocs.map((b) => {
			const called = score.seatCounts.called[b] ?? 0;
			const leading = score.seatCounts.leading[b] ?? 0;
			const proj =
				conditioned && conditioned.matched > 0
					? conditioned.seats[b]
					: f.seats[b]
						? ([f.seats[b][0], f.seats[b][2], f.seats[b][4]] as [number, number, number])
						: ([0, 0, 0] as [number, number, number]);
			return {
				bloc: b,
				label: b === 'COAL' ? coalLabel : party(b).short,
				colour: partyColour(b),
				called,
				leading,
				proj
			};
		});
	});

	// Live chamber & map views
	type ViewMode = 'live' | 'accuracy' | 'remaining';
	let viewMode = $state<ViewMode>('live');

	const HIT_COLOUR = '#15803d';
	const UPSET_COLOUR = '#dc2626';

	const chamber = $derived(
		chamberSeats(
			seats.map((s) => {
				if (viewMode === 'accuracy') {
					if (s.hit === true) {
						return {
							slug: s.district.slug,
							name: s.district.district,
							party: s.effectiveWinner!,
							strength: 1,
							detail: `Hit · ${party(s.effectiveWinner!).short} (${Math.round((s.pActual ?? 0) * 100)}%)`,
							opacity: 0.9
						};
					}
					if (s.hit === false) {
						return {
							slug: s.district.slug,
							name: s.district.district,
							party: s.effectiveWinner!,
							strength: 0.2,
							detail: `Upset · ${party(s.effectiveWinner!).short} (model gave ${Math.round((s.pActual ?? 0) * 100)}%)`,
							opacity: 1
						};
					}
					return {
						slug: s.district.slug,
						name: s.district.district,
						party: 'OTH',
						strength: 0,
						detail: 'Not yet called',
						opacity: 0.14
					};
				}
				const winner = s.effectiveWinner ?? s.leadingParty ?? s.district.leader;
				const opacity = s.effectiveWinner ? 1 : s.leadingParty ? 0.55 : 0.16;
				const detail = s.effectiveWinner
					? `Called: ${party(s.effectiveWinner).short}`
					: s.leadingParty
						? `Leading: ${party(s.leadingParty).short} (${s.pctCounted.toFixed(0)}%)`
						: `Uncalled · forecast fav ${party(s.district.leader).short} ${Math.round(s.district.leader_prob * 100)}%`;
				return {
					slug: s.district.slug,
					name: s.district.district,
					party: winner,
					strength: s.effectiveWinner ? 1 : s.district.leader_prob,
					detail,
					opacity
				};
			})
		)
	);

	function mapFill(slug: string): string {
		const s = bySlug[slug];
		if (!s) return 'var(--rule)';
		if (viewMode === 'accuracy') {
			if (s.hit === true) return HIT_COLOUR;
			if (s.hit === false) return UPSET_COLOUR;
			return 'var(--rule)';
		}
		if (viewMode === 'remaining') {
			return s.effectiveWinner ? 'var(--rule)' : 'var(--swirl-violet)';
		}
		return partyColour(s.effectiveWinner ?? s.leadingParty ?? s.district.leader);
	}

	function mapOpacity(slug: string): number {
		const s = bySlug[slug];
		if (!s) return 0.15;
		if (viewMode === 'accuracy') return s.hit != null ? 0.92 : 0.2;
		if (viewMode === 'remaining') {
			return s.effectiveWinner ? 0.14 : Math.min(1, Math.max(0.15, (1 - s.district.leader_prob) / 0.45));
		}
		if (s.effectiveWinner) return 1;
		if (s.leadingParty) return 0.55;
		return tierOpacity(s.district.leader_prob) * 0.3;
	}

	const mapLegend = $derived.by(() => {
		if (viewMode === 'accuracy') {
			return [
				{ label: 'Model favourite won', colour: HIT_COLOUR, opacity: 0.92 },
				{ label: 'Upset (favourite lost)', colour: UPSET_COLOUR, opacity: 0.92 },
				{ label: 'Uncalled', colour: 'var(--rule)', opacity: 0.4 }
			];
		}
		if (viewMode === 'remaining') {
			return [
				{ label: 'Uncalled toss-up', colour: 'var(--swirl-violet)', opacity: 0.95 },
				{ label: 'Uncalled leaning', colour: 'var(--swirl-violet)', opacity: 0.4 },
				{ label: 'Already called', colour: 'var(--rule)', opacity: 0.3 }
			];
		}
		return [
			{ label: 'Labor', colour: partyColour('ALP'), opacity: 1 },
			{ label: coalLabel, colour: partyColour('COAL'), opacity: 1 },
			{ label: 'Greens', colour: partyColour('GRN'), opacity: 1 },
			{ label: 'One Nation', colour: partyColour('ONP'), opacity: 1 },
			{ label: 'Ind.', colour: partyColour('IND'), opacity: 1 },
			{ label: 'Solid = called · Faded = forecast', colour: 'var(--fg-2)', opacity: 0.35 }
		];
	});

	function seatTip(slug: string) {
		const s = bySlug[slug];
		if (!s) return { title: slug, lines: [] };
		const d = s.district;
		const lines: string[] = [];
		if (s.effectiveWinner) {
			const tag = s.source === 'projected' ? 'Projected' : s.source === 'manual' ? 'Called (Call Desk)' : 'Called';
			lines.push(`${tag}: ${party(s.effectiveWinner).short} (model gave ${pct(s.pActual ?? 0)})`);
			lines.push(s.hit ? 'Model favourite won ✓' : `Upset — model favoured ${party(d.leader).short} ${pct(d.leader_prob)}`);
		} else if (s.leadingParty) {
			lines.push(`Leading: ${party(s.leadingParty).short} (${s.pctCounted.toFixed(0)}% counted)`);
			lines.push(`Forecast favourite: ${party(d.leader).short} ${pct(d.leader_prob)}`);
		} else {
			lines.push(`Not yet called · Forecast fav: ${party(d.leader).short} ${pct(d.leader_prob)}`);
		}
		lines.push('Click for full seat forecast');
		return { title: `${d.district} (${d.region})`, lines };
	}

	// Seat table filtering
	let seatFilter = $state<'all' | 'called' | 'uncalled' | 'upsets' | 'tossups'>('all');
	let query = $state('');
	const filteredSeats = $derived(
		seats
			.filter((s) => !query || s.district.district.toLowerCase().includes(query.toLowerCase()))
			.filter((s) => {
				if (seatFilter === 'called') return Boolean(s.effectiveWinner);
				if (seatFilter === 'uncalled') return !s.effectiveWinner;
				if (seatFilter === 'upsets') return s.hit === false;
				if (seatFilter === 'tossups') return !s.effectiveWinner && s.district.leader_prob < 0.7;
				return true;
			})
			.toSorted((a, b) => {
				// Closest uncalled first when viewing uncalled/tossups; else surprises/called first
				if (seatFilter === 'uncalled' || seatFilter === 'tossups') {
					return a.district.leader_prob - b.district.leader_prob;
				}
				if (a.effectiveWinner && !b.effectiveWinner) return -1;
				if (!a.effectiveWinner && b.effectiveWinner) return 1;
				return a.district.leader_prob - b.district.leader_prob;
			})
	);

	// SeatDrawer integration
	let selectedSlug = $state<string | null>(null);
	const selectedDistrict = $derived(selectedSlug ? (bySlug[selectedSlug]?.district ?? null) : null);

	const pct = (p: number) => (p < 0.005 ? '<1%' : p > 0.995 ? '>99%' : `${Math.round(p * 100)}%`);

	const statusBadge = $derived.by(() => {
		if (score.effectiveCalled >= j.seats) return { cls: 'final', label: 'FINAL' };
		if (feed?.status === 'counting' || score.effectiveCalled > 0) return { cls: 'live', label: 'LIVE' };
		return { cls: 'pre', label: 'PRE-POLLS' };
	});

	// Statewide live vote vs forecast 90% interval
	const voteCompare = $derived(
		(['ALP', 'COAL', 'GRN', 'ONP'] as const)
			.filter((k) => f.statewide_primary[k] && f.statewide_primary[k][2] >= 1)
			.map((k) => ({
				code: k,
				label: k === 'COAL' ? coalLabel : party(k).short,
				colour: partyColour(k),
				lo: f.statewide_primary[k][0],
				med: f.statewide_primary[k][1],
				hi: f.statewide_primary[k][2],
				live: feed?.statewide_primary?.[k] ?? null
			}))
	);
	const voteMax = $derived(
		Math.ceil(Math.max(40, ...voteCompare.map((v) => Math.max(v.hi, v.live ?? 0))) / 5) * 5
	);

	// Top candidate parties for quick Call Desk buttons per seat
	function quickParties(s: (typeof seats)[number]): string[] {
		const top = Object.entries(s.district.probs)
			.filter(([, p]) => p >= 0.01)
			.sort((a, b) => b[1] - a[1])
			.map(([k]) => k)
			.slice(0, 4);
		return top.length ? top : ['ALP', 'LIB', 'GRN'];
	}
</script>

<svelte:head>
	<title>{j.name} {data.year} Election Night Live Tracker · {SITE_NAME}</title>
</svelte:head>

<div class="topbar">
	<div class="status-group">
		<span class="pill {statusBadge.cls}"><i></i>{statusBadge.label}</span>
		<span class="small muted">
			{j.name} {data.year} · {fmtDate(f.election_date)} ·
			<strong>{score.effectiveCalled}</strong> of {j.seats} seats called
			{#if feed?.pct_counted} · {feed.pct_counted.toFixed(1)}% counted{/if}
		</span>
	</div>
	<div class="controls-group">
		<span class="small muted">Updated {agoLabel}</span>
		<button type="button" class="btn-sm" onclick={refreshFeed} disabled={refreshing}>
			{refreshing ? 'Refreshing…' : 'Refresh'}
		</button>
		<label class="toggle small">
			<input type="checkbox" bind:checked={autoRefresh} /> Auto (60s)
		</label>
		<a class="btn-sm link" href="/{j.code}/forecast/{data.year}/">Final forecast →</a>
	</div>
</div>

<h1>{data.year} {j.name} Election Night Tracker</h1>
<p class="lede">
	Tracking incoming results live against Crystal Ballot's frozen eve-of-election forecast
	(model v{f.model_version}, {f.n_sims.toLocaleString()} simulations).
</p>

{#if feed?.note && score.effectiveCalled === 0}
	<aside class="notice small">
		{feed.note}
	</aside>
{/if}

<div class="desk-bar card small">
	<label class="toggle">
		<input type="checkbox" bind:checked={includeProjected} />
		Include projected calls (≥{AUTO_PROJECT_PCT}% counted &amp; ≥{AUTO_PROJECT_MARGIN}% margin)
	</label>
	<label class="toggle">
		<input type="checkbox" bind:checked={callDeskOpen} />
		Interactive Call Desk (click seats below to record calls live)
	</label>
	{#if Object.keys(manualCalls).length > 0}
		<button type="button" class="btn-sm danger" onclick={clearManualCalls}>
			Clear my {Object.keys(manualCalls).length} call{Object.keys(manualCalls).length === 1 ? '' : 's'}
		</button>
	{/if}
</div>

<div class="hero-grid">
	<section class="card panel">
		<p class="eyebrow">
			{score.effectiveCalled > 0
				? `Live Bayesian projection · conditioned on ${score.effectiveCalled} called seats`
				: 'Final pre-election forecast · awaiting first calls'}
		</p>
		<h2>Live race to {f.majority} seats</h2>
		<OutcomeBar
			alpMajority={activeOutcome.alp_majority}
			hung={activeOutcome.hung}
			coalMajority={activeOutcome.coal_majority}
			coal={coalShortLbl}
		/>
		{#if conditioned && score.effectiveCalled > 0}
			<p class="small muted match-note">
				{#if conditioned.matched > 0}
					Matching <strong class="num">{conditioned.matched.toLocaleString()}</strong> of
					{conditioned.total.toLocaleString()} simulations · Live projected Labor 2PP
					<strong class="num">{conditioned.tpp[1].toFixed(1)}%</strong> ({conditioned.tpp[0].toFixed(1)}–{conditioned.tpp[2].toFixed(1)}%)
				{:else}
					<strong>0 matching simulations</strong> — this exact combination of calls sits outside the 20,000 pre-election runs.
				{/if}
			</p>
		{/if}
		<table class="data tally">
			<thead>
				<tr>
					<th class="left">Party</th>
					<th>Called</th>
					<th>Leading</th>
					<th>Projected (90%)</th>
				</tr>
			</thead>
			<tbody class="num">
				{#each activeSeats as row (row.bloc)}
					<tr>
						<td class="left"><span class="chip" style:--c={row.colour}>{row.label}</span></td>
						<td><strong>{row.called}</strong></td>
						<td class="muted">{row.leading}</td>
						<td>
							<strong>{Math.round(row.proj[1])}</strong>
							<span class="muted small">({Math.round(row.proj[0])}–{Math.round(row.proj[2])})</span>
						</td>
					</tr>
				{/each}
			</tbody>
		</table>
	</section>

	<section class="card panel">
		<p class="eyebrow">Live model scorecard · vs frozen final forecast</p>
		<h2>How Crystal Ballot is performing</h2>
		{#if score.effectiveCalled === 0}
			<p class="small muted">
				No seats called yet. Once VEC begins reporting—or as you record calls in the Interactive Call Desk below—this
				panel scores the model's calls against expected hits, Brier score, log loss, and calibration in real time.
			</p>
		{/if}
		<div class="kpi-grid num">
			<div class="kpi">
				<span class="small muted">Calls right</span>
				<strong>
					{score.effectiveCalled ? `${score.hits} / ${score.effectiveCalled}` : '—'}
				</strong>
				<span class="small muted">
					{#if score.effectiveCalled}
						{Math.round((100 * score.hits) / score.effectiveCalled)}% · model expected {score.expectedHits.toFixed(1)} ({Math.round((100 * score.expectedHits) / score.effectiveCalled)}%)
					{:else}
						Expected vs actual hits
					{/if}
				</span>
			</div>
			<div class="kpi">
				<span class="small muted">Live Brier score</span>
				<strong>{score.brier != null ? score.brier.toFixed(3) : '—'}</strong>
				<span class="small muted">
					{#if score.statusQuoBrier != null}
						Status quo: {score.statusQuoBrier.toFixed(3)} · lower is better
					{:else}
						VIC backtest avg: 0.175
					{/if}
				</span>
			</div>
			<div class="kpi">
				<span class="small muted">Log loss</span>
				<strong>{score.logLoss != null ? score.logLoss.toFixed(3) : '—'}</strong>
				<span class="small muted">
					{score.effectiveCalled ? `Status quo hits: ${score.statusQuoHits}/${score.effectiveCalled}` : 'Penalises overconfidence'}
				</span>
			</div>
			<div class="kpi">
				<span class="small muted">Upsets so far</span>
				<strong>{score.upsets.length}</strong>
				<span class="small muted">
					{score.upsets.length ? `Biggest: ${score.upsets[0].district.district} (${pct(score.upsets[0].pActual ?? 0)})` : 'Favourite lost seat'}
				</span>
			</div>
		</div>

		{#if score.effectiveCalled > 0}
			<div class="cal-mini">
				<h3 class="sub">Live calibration by confidence tier</h3>
				<table class="data small num">
					<thead>
						<tr>
							<th class="left">Model confidence</th>
							<th>Called</th>
							<th>Expected</th>
							<th>Actual hit rate</th>
						</tr>
					</thead>
					<tbody>
						{#each score.calibration as bin (bin.label)}
							{#if bin.n > 0}
								<tr>
									<td class="left">{bin.label}</td>
									<td>{bin.n}</td>
									<td>{Math.round(bin.meanProb * 100)}%</td>
									<td><strong>{Math.round(bin.hitRate * 100)}%</strong></td>
								</tr>
							{/if}
						{/each}
					</tbody>
				</table>
			</div>
		{/if}
	</section>
</div>

<div class="sec-head">
	<div>
		<h2>Live chamber &amp; map</h2>
		<p class="small muted">Switch between live winners, model hits &amp; upsets, and remaining uncalled toss-ups.</p>
	</div>
	<div class="modes" role="group" aria-label="Live map view">
		<button type="button" aria-pressed={viewMode === 'live'} onclick={() => (viewMode = 'live')}>Live calls</button>
		<button type="button" aria-pressed={viewMode === 'accuracy'} onclick={() => (viewMode = 'accuracy')}>Model hits &amp; misses</button>
		<button type="button" aria-pressed={viewMode === 'remaining'} onclick={() => (viewMode = 'remaining')}>Uncalled toss-ups</button>
	</div>
</div>

<div class="visual-grid">
	<Hemicycle
		title={viewMode === 'accuracy' ? 'Model hits and upsets' : 'Live chamber seat status'}
		seats={chamber}
		majority={f.majority}
		onSelect={(slug) => (selectedSlug = slug)}
	/>
	{#if data.geo}
		<SeatMap
			title="Live election night map"
			geo={data.geo}
			frame={mapFrame(j.code)}
			fill={mapFill}
			opacity={mapOpacity}
			tooltip={seatTip}
			onSelect={(slug) => (selectedSlug = slug)}
			legend={mapLegend}
		/>
	{/if}
</div>

{#if score.recentCalls.length > 0}
	<section class="card feed-card">
		<div class="sec-head tight">
			<h2>Latest calls &amp; surprises ({score.recentCalls.length})</h2>
			<span class="small muted">{score.upsets.length} upset{score.upsets.length === 1 ? '' : 's'}</span>
		</div>
		<ul class="call-feed">
			{#each score.recentCalls.slice(0, 12) as s (s.district.slug)}
				<li>
					<button type="button" class="link-btn" onclick={() => (selectedSlug = s.district.slug)}>
						<strong>{s.district.district}</strong>
					</button>
					<span class="chip" style:--c={partyColour(s.effectiveWinner!)}>
						{party(s.effectiveWinner!).short}
					</span>
					<span class="small muted num">Model gave {pct(s.pActual ?? 0)}</span>
					<span class="tag {s.hit ? 'hit' : 'upset'}">{s.hit ? 'Hit' : 'Upset'}</span>
					{#if s.source === 'projected'}
						<span class="tag proj">Projected</span>
					{:else if s.source === 'manual'}
						<span class="tag manual">Call Desk</span>
					{/if}
				</li>
			{/each}
		</ul>
	</section>
{/if}

<section class="card vote-card">
	<h2>Statewide vote vs. final forecast</h2>
	<p class="small muted">
		Bars show the frozen forecast's 90% interval (dot = median). Diamonds appear as live statewide votes report.
	</p>
	<ul class="forest">
		{#each voteCompare as v (v.code)}
			<li>
				<span class="lbl">{v.label}</span>
				<span class="track">
					<span class="range" style:left="{(100 * v.lo) / voteMax}%" style:width="{(100 * (v.hi - v.lo)) / voteMax}%" style:background={v.colour}></span>
					<span class="dot" style:left="{(100 * v.med) / voteMax}%" style:background={v.colour}></span>
					{#if v.live != null}
						<span class="actual-mark" style:left="{(100 * v.live) / voteMax}%" title="Live: {v.live.toFixed(1)}%"></span>
					{/if}
				</span>
				<span class="num v">
					{#if v.live != null}
						<strong>{v.live.toFixed(1)}%</strong>
						<span class="muted small">vs {v.med.toFixed(1)}%</span>
					{:else}
						{v.med.toFixed(1)}% <span class="muted small">({v.lo.toFixed(0)}–{v.hi.toFixed(0)})</span>
					{/if}
				</span>
			</li>
		{/each}
	</ul>
</section>

<h2 id="live-seats">Every seat ({filteredSeats.length})</h2>
<div class="table-controls">
	<input type="search" placeholder="Search seats" bind:value={query} aria-label="Search seats" />
	<div class="modes" role="group" aria-label="Filter seats">
		<button type="button" aria-pressed={seatFilter === 'all'} onclick={() => (seatFilter = 'all')}>All ({seats.length})</button>
		<button type="button" aria-pressed={seatFilter === 'called'} onclick={() => (seatFilter = 'called')}>Called ({score.effectiveCalled})</button>
		<button type="button" aria-pressed={seatFilter === 'uncalled'} onclick={() => (seatFilter = 'uncalled')}>Uncalled ({seats.length - score.effectiveCalled})</button>
		<button type="button" aria-pressed={seatFilter === 'upsets'} onclick={() => (seatFilter = 'upsets')}>Upsets ({score.upsets.length})</button>
		<button type="button" aria-pressed={seatFilter === 'tossups'} onclick={() => (seatFilter = 'tossups')}>Closest uncalled</button>
	</div>
</div>

<div class="scroll-x">
	<table class="data seat-table">
		<thead>
			<tr>
				<th class="left">Seat</th>
				<th class="left">Forecast fav.</th>
				<th class="left">Live status</th>
				<th>Model on winner</th>
				{#if callDeskOpen}
					<th class="left">Call Desk</th>
				{/if}
			</tr>
		</thead>
		<tbody>
			{#each filteredSeats as s (s.district.slug)}
				<tr>
					<td class="left">
						<button type="button" class="link-btn" onclick={() => (selectedSlug = s.district.slug)}>
							<strong>{s.district.district}</strong>
						</button>
						<span class="small muted"> · {party(s.district.incumbent).short}</span>
					</td>
					<td class="left num">
						<span class="chip" style:--c={partyColour(s.district.leader)}>
							{party(s.district.leader).short}
						</span>
						<span class="small muted">{pct(s.district.leader_prob)}</span>
					</td>
					<td class="left">
						{#if s.effectiveWinner}
							<span class="chip" style:--c={partyColour(s.effectiveWinner)}>
								<strong>{party(s.effectiveWinner).short}</strong>
							</span>
							<span class="tag {s.hit ? 'hit' : 'upset'}">{s.hit ? 'Hit' : 'Upset'}</span>
							{#if s.source === 'projected'}
								<span class="tag proj">Proj</span>
							{/if}
						{:else if s.leadingParty}
							<span class="chip" style:--c={partyColour(s.leadingParty)}>
								{party(s.leadingParty).short}
							</span>
							<span class="small muted num">{s.pctCounted.toFixed(0)}%</span>
						{:else}
							<span class="small muted">Uncalled</span>
						{/if}
					</td>
					<td class="num">
						{#if s.pActual != null}
							<strong>{pct(s.pActual)}</strong>
						{:else}
							<span class="muted">—</span>
						{/if}
					</td>
					{#if callDeskOpen}
						<td class="left">
							<div class="quick-calls">
								{#each quickParties(s) as p (p)}
									<button
										type="button"
										class="qbtn"
										class:active={manualCalls[s.district.slug]?.party === p}
										style:--c={partyColour(p)}
										onclick={() => setManualCall(s.district.slug, p)}
									>{party(p).short}</button>
								{/each}
								{#if manualCalls[s.district.slug]}
									<button
										type="button"
										class="qbtn clear"
										aria-label="Clear call for {s.district.district}"
										onclick={() => setManualCall(s.district.slug, null)}
									>✕</button>
								{/if}
							</div>
						</td>
					{/if}
				</tr>
			{/each}
		</tbody>
	</table>
</div>

<SeatDrawer
	district={selectedDistrict}
	{coalLabel}
	majority={f.majority}
	resultsHref={selectedDistrict && data.baselineYear ? `/${j.code}/results/${data.baselineYear}/${selectedDistrict.slug}/` : undefined}
	resultsYear={data.baselineYear}
	{sims}
	onClose={() => (selectedSlug = null)}
/>

<style>
	.topbar {
		display: flex;
		flex-wrap: wrap;
		justify-content: space-between;
		align-items: center;
		gap: 0.6rem 1rem;
		padding: 0.55rem 0.9rem;
		margin-bottom: 1rem;
		border: 1px solid var(--rule-strong);
		border-radius: var(--radius);
		background: var(--surface);
	}
	.status-group,
	.controls-group {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 0.5rem 0.75rem;
	}
	.pill {
		display: inline-flex;
		align-items: center;
		gap: 0.4rem;
		font-size: 0.72rem;
		font-weight: 700;
		letter-spacing: 0.06em;
		padding: 0.2rem 0.55rem;
		border-radius: 999px;
	}
	.pill i {
		width: 0.48rem;
		height: 0.48rem;
		border-radius: 50%;
		background: currentColor;
	}
	.pill.live {
		background: color-mix(in srgb, #dc2626 15%, var(--bg));
		color: #dc2626;
	}
	.pill.pre {
		background: color-mix(in srgb, var(--swirl-violet) 16%, var(--bg));
		color: var(--swirl-violet);
	}
	.pill.final {
		background: color-mix(in srgb, #15803d 16%, var(--bg));
		color: #15803d;
	}
	.btn-sm {
		font: inherit;
		font-size: 0.8rem;
		font-weight: 550;
		padding: 0.25rem 0.65rem;
		border: 1px solid var(--rule-strong);
		border-radius: 999px;
		background: var(--bg);
		color: var(--fg);
		cursor: pointer;
		text-decoration: none;
	}
	.btn-sm:hover:not(:disabled) {
		background: var(--rule);
	}
	.btn-sm.danger {
		color: #b91c1c;
		border-color: color-mix(in srgb, #b91c1c 45%, var(--rule));
	}
	.toggle {
		display: inline-flex;
		align-items: center;
		gap: 0.35rem;
		cursor: pointer;
		color: var(--fg-2);
	}
	.notice {
		padding: 0.65rem 0.9rem;
		border-left: 3px solid var(--swirl-violet);
		background: var(--surface);
		border-radius: 0 var(--radius) var(--radius) 0;
		margin: 0.75rem 0 1rem;
		color: var(--fg-2);
	}
	.desk-bar {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		justify-content: space-between;
		gap: 0.6rem 1.25rem;
		padding: 0.65rem 1rem;
		margin: 1rem 0 1.25rem;
	}
	.hero-grid {
		display: grid;
		grid-template-columns: repeat(2, minmax(0, 1fr));
		gap: 1.25rem;
		margin-bottom: 1.75rem;
	}
	@media (max-width: 820px) {
		.hero-grid {
			grid-template-columns: 1fr;
		}
	}
	.panel {
		display: flex;
		flex-direction: column;
		gap: 0.65rem;
	}
	.panel h2 {
		margin: 0;
		font-size: 1.25rem;
	}
	.match-note {
		margin: 0;
	}
	.tally {
		margin-top: 0.25rem;
	}
	.kpi-grid {
		display: grid;
		grid-template-columns: repeat(2, minmax(0, 1fr));
		gap: 0.75rem;
	}
	.kpi {
		padding: 0.65rem 0.75rem;
		background: var(--bg);
		border: 1px solid var(--rule);
		border-radius: var(--radius);
		display: flex;
		flex-direction: column;
		gap: 0.15rem;
	}
	.kpi strong {
		font-size: 1.35rem;
		line-height: 1.15;
	}
	.cal-mini {
		border-top: 1px solid var(--rule);
		padding-top: 0.65rem;
	}
	.cal-mini h3.sub {
		margin: 0 0 0.4rem;
		font-size: 0.88rem;
		font-family: var(--font-sans);
	}
	.sec-head {
		display: flex;
		flex-wrap: wrap;
		justify-content: space-between;
		align-items: flex-end;
		gap: 0.6rem 1rem;
		margin: 1.75rem 0 0.9rem;
	}
	.sec-head.tight {
		margin: 0 0 0.75rem;
		align-items: baseline;
	}
	.sec-head h2,
	.sec-head p {
		margin: 0;
	}
	.modes {
		display: inline-flex;
		flex-wrap: wrap;
		border: 1px solid var(--rule-strong);
		border-radius: var(--radius);
		overflow: hidden;
	}
	.modes button {
		font: inherit;
		font-size: 0.82rem;
		padding: 0.32rem 0.7rem;
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
	.visual-grid {
		display: grid;
		gap: 1.5rem;
		margin-bottom: 1.75rem;
	}
	.feed-card,
	.vote-card {
		margin: 1.5rem 0;
	}
	.vote-card h2 {
		margin: 0 0 0.25rem;
		font-size: 1.2rem;
	}
	.call-feed {
		list-style: none;
		padding: 0;
		margin: 0;
		display: grid;
		gap: 0.45rem;
	}
	.call-feed li {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 0.5rem 0.75rem;
		padding: 0.35rem 0;
		border-bottom: 1px solid var(--rule);
		font-size: 0.9rem;
	}
	.call-feed li:last-child {
		border-bottom: 0;
	}
	.tag {
		font-size: 0.7rem;
		font-weight: 650;
		padding: 0.1rem 0.42rem;
		border-radius: 4px;
		text-transform: uppercase;
		letter-spacing: 0.03em;
	}
	.tag.hit {
		background: color-mix(in srgb, #15803d 15%, var(--bg));
		color: #15803d;
	}
	.tag.upset {
		background: color-mix(in srgb, #dc2626 16%, var(--bg));
		color: #dc2626;
	}
	.tag.proj {
		background: color-mix(in srgb, var(--brand-spark) 22%, var(--bg));
		color: var(--fg-2);
	}
	.tag.manual {
		background: color-mix(in srgb, var(--swirl-violet) 16%, var(--bg));
		color: var(--swirl-violet);
	}
	:global([data-theme='dark']) .tag.hit {
		color: #4ade80;
	}
	:global([data-theme='dark']) .tag.upset {
		color: #f87171;
	}
	.forest {
		list-style: none;
		padding: 0;
		margin: 0.75rem 0 0;
		display: grid;
		gap: 0.55rem;
	}
	.forest li {
		display: grid;
		grid-template-columns: 7rem 1fr 8.5rem;
		gap: 0.75rem;
		align-items: center;
		font-size: 0.88rem;
	}
	.lbl {
		color: var(--fg-2);
	}
	.track {
		position: relative;
		height: 0.9rem;
		background: linear-gradient(var(--rule), var(--rule)) center / 100% 1px no-repeat;
	}
	.range {
		position: absolute;
		top: 0.25rem;
		height: 0.4rem;
		border-radius: 3px;
		opacity: 0.4;
	}
	.dot {
		position: absolute;
		top: 0.1rem;
		width: 0.7rem;
		height: 0.7rem;
		border-radius: 50%;
		transform: translateX(-50%);
		border: 2px solid var(--surface);
	}
	.actual-mark {
		position: absolute;
		top: 0.05rem;
		width: 0.75rem;
		height: 0.75rem;
		background: var(--fg);
		transform: translateX(-50%) rotate(45deg);
		border: 1.5px solid var(--surface);
	}
	.v {
		text-align: right;
	}
	.table-controls {
		display: flex;
		flex-wrap: wrap;
		gap: 0.65rem 1rem;
		align-items: center;
		margin-bottom: 0.85rem;
	}
	.table-controls input {
		font: inherit;
		font-size: 0.88rem;
		padding: 0.35rem 0.65rem;
		border: 1px solid var(--rule-strong);
		border-radius: var(--radius);
		background: var(--surface);
		color: var(--fg);
		width: 14rem;
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
	.link-btn {
		font: inherit;
		background: none;
		border: 0;
		padding: 0;
		color: inherit;
		text-decoration: underline;
		text-decoration-color: var(--rule-strong);
		text-underline-offset: 2px;
		cursor: pointer;
	}
	.quick-calls {
		display: flex;
		flex-wrap: wrap;
		gap: 0.25rem;
	}
	.qbtn {
		font: inherit;
		font-size: 0.72rem;
		font-weight: 600;
		padding: 0.14rem 0.42rem;
		border: 1px solid var(--c, var(--rule-strong));
		border-radius: 4px;
		background: transparent;
		color: var(--fg);
		cursor: pointer;
	}
	.qbtn:hover,
	.qbtn.active {
		background: var(--c, var(--fg));
		color: #fff;
	}
	.qbtn.clear {
		border-color: var(--rule-strong);
		color: var(--fg-2);
	}
</style>
