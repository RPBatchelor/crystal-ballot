<!--
	Wikipedia-inspired Election Scorecard / Leader Overview band.
	Works in both 'results' mode (actual seats, primary votes, 2PP, turnout, head of government)
	and 'forecast' mode (probabilistic medians, 90% intervals, swings vs previous election,
	and clickable leader seats wired to SeatDrawer).
-->
<script lang="ts">
	import type { ElectionLeaders, ForecastFile, LeaderEntry, ResultsFile } from '$lib/types';
	import type { Jurisdiction } from '$lib/jurisdictions';
	import type { SampledElection } from '$lib/sims';
	import { coalName, coalShort } from '$lib/jurisdictions';
	import { party, partyColour } from '$lib/parties';

	interface Props {
		mode: 'results' | 'forecast';
		jurisdiction: Jurisdiction;
		year: number;
		/** Results mode: this election's results. Forecast mode: previous/baseline election results. */
		results?: ResultsFile | null;
		/** Results mode only: the previous election's results for swings & seat deltas. */
		previous?: ResultsFile | null;
		prevYear?: number | null;
		/** Forecast mode only: the forecast payload. */
		forecast?: ForecastFile | null;
		/** Optional curated leader names, seats, portraits, and head of government. */
		leaders?: ElectionLeaders | null;
		/** Results mode: base URL for seat links (e.g. /vic/results/2022). */
		base?: string;
		/** Forecast mode: callback when a user clicks a leader's seat (opens SeatDrawer). */
		onSelectSeat?: (slug: string) => void;
		/** Forecast mode: optional sampled election night (HOP mode). */
		sampled?: SampledElection | null;
	}

	let {
		mode,
		jurisdiction,
		year,
		results = null,
		previous = null,
		prevYear = null,
		forecast = null,
		leaders = null,
		base,
		onSelectSeat,
		sampled = null
	}: Props = $props();

	const COAL_CODES = new Set(['LIB', 'NAT', 'LNP', 'CLP', 'COAL']);
	const coalLabel = $derived(coalName(jurisdiction.code));
	const coalShortLbl = $derived(coalShort(jurisdiction.code));
	const retro = $derived(forecast?.mode === 'retrospective');

	function blocSeats(r: ResultsFile | null | undefined, bloc: string): number {
		if (!r) return 0;
		if (bloc === 'COAL') {
			return Object.entries(r.seat_counts).reduce((a, [k, v]) => a + (COAL_CODES.has(k) ? v : 0), 0);
		}
		return r.seat_counts[bloc] ?? 0;
	}

	function blocRawVotes(r: ResultsFile | null | undefined, bloc: string): number | null {
		if (!r?.seats?.length) return null;
		let sum = 0;
		for (const s of r.seats) {
			for (const c of s.primary) {
				if (bloc === 'COAL' ? COAL_CODES.has(c.party) : c.party === bloc) sum += c.votes;
			}
		}
		return sum > 0 ? sum : null;
	}

	function blocPrimary(r: ResultsFile | null | undefined, bloc: string): number | null {
		if (!r) return null;
		return r.primary_share[bloc] ?? null;
	}

	function blocTpp(r: ResultsFile | null | undefined, bloc: string): number | null {
		if (!r || r.tpp_alp == null) return null;
		if (bloc === 'ALP') return r.tpp_alp;
		if (bloc === 'COAL') return 100 - r.tpp_alp;
		return null;
	}

	function initials(name: string): string {
		const parts = name.trim().split(/\s+/);
		if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
		return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
	}

	function defaultHeadTitle(j: Jurisdiction): string {
		if (j.kind === 'federal') return 'Prime Minister';
		if (j.kind === 'territory') return 'Chief Minister';
		return 'Premier';
	}

	// Turnout & enrolment (results mode)
	const participation = $derived.by(() => {
		if (mode !== 'results' || !results?.seats?.length) return null;
		const enrolled = results.seats.reduce((a, s) => a + (s.enrolment || 0), 0);
		const totalVotes = results.seats.reduce((a, s) => a + (s.formal || 0) + (s.informal || 0), 0);
		const informal = results.seats.reduce((a, s) => a + (s.informal || 0), 0);
		if (enrolled <= 0 || totalVotes <= 0) return null;
		const turnoutPct = (100 * totalVotes) / enrolled;
		const informalPct = (100 * informal) / totalVotes;
		let deltaPp: number | null = null;
		if (previous?.seats?.length) {
			const pEnr = previous.seats.reduce((a, s) => a + (s.enrolment || 0), 0);
			const pTot = previous.seats.reduce((a, s) => a + (s.formal || 0) + (s.informal || 0), 0);
			if (pEnr > 0 && pTot > 0) deltaPp = turnoutPct - (100 * pTot) / pEnr;
		}
		return { enrolled, totalVotes, turnoutPct, informalPct, deltaPp };
	});

	// Determine which 3 (or 4, if a 4th party has >=10% primary share) blocs to display.
	const activeBlocs = $derived.by(() => {
		const base3 = ['ALP', 'COAL', 'GRN'];
		const extraCandidates = ['ONP', 'KAP'];
		let fourth: string | null = null;
		if (mode === 'forecast' && forecast) {
			for (const b of extraCandidates) {
				const primMed = forecast.statewide_primary[b]?.[1] ?? 0;
				if (primMed >= 10) {
					fourth = b;
					break;
				}
			}
		} else if (mode === 'results' && results) {
			for (const b of extraCandidates) {
				const prim = results.primary_share[b] ?? 0;
				if (prim >= 10) {
					fourth = b;
					break;
				}
			}
		}

		// Order: ALP/COAL first (largest/winner first), then GRN and optional 4th (sorted by primary share).
		const majors = ['ALP', 'COAL'];
		if (mode === 'results' && results) {
			const alpS = blocSeats(results, 'ALP');
			const coalS = blocSeats(results, 'COAL');
			if (coalS > alpS) majors.reverse();
		} else if (mode === 'forecast' && forecast) {
			if (forecast.outcome.coal_most_seats > forecast.outcome.alp_most_seats) majors.reverse();
		}

		const minors = fourth ? ['GRN', fourth] : ['GRN'];
		if (fourth) {
			const score = (b: string) =>
				mode === 'forecast'
					? (forecast?.statewide_primary[b]?.[1] ?? 0)
					: (results?.primary_share[b] ?? 0);
			minors.sort((a, b) => score(b) - score(a));
		}

		// Only keep GRN if it actually contested or is in leaders metadata
		const hasGrn =
			(mode === 'forecast' ? (forecast?.statewide_primary.GRN?.[1] ?? 0) > 0 : (results?.primary_share.GRN ?? 0) > 0) ||
			Boolean(leaders?.leaders.some((l) => l.bloc === 'GRN'));
		const list = [...majors, ...(hasGrn ? minors : minors.filter((b) => b !== 'GRN'))];
		// Ensure base3 order fallback if empty
		return list.length ? list : base3;
	});

	interface CardModel {
		bloc: string;
		partyLabel: string;
		leaderName: string | null;
		seat: string | null;
		seatSlug: string | null;
		portrait: string | null;
		credit: string | null;
		colour: string;
		// Results mode
		seatsWon?: number;
		seatsBefore?: number | null;
		seatDelta?: number | null;
		primaryPct?: number | null;
		primaryVotes?: number | null;
		primarySwing?: number | null;
		tppPct?: number | null;
		tppSwing?: number | null;
		// Forecast mode
		seatsMed?: number;
		seatsLo?: number;
		seatsHi?: number;
		sampledSeats?: number | null;
		actualSeats?: number | null;
		primMed?: number | null;
		primLo?: number | null;
		primHi?: number | null;
		tppMed?: number | null;
		tppLo?: number | null;
		tppHi?: number | null;
		oddsLabel?: string | null;
	}

	const cards = $derived.by<CardModel[]>(() => {
		const byBloc = new Map<string, LeaderEntry>((leaders?.leaders ?? []).map((l) => [l.bloc, l]));
		const baseline = mode === 'results' ? previous : results;

		return activeBlocs.map((bloc) => {
			const meta = byBloc.get(bloc);
			const partyLabel = meta?.party_label ?? (bloc === 'COAL' ? coalLabel : party(bloc).short);
			const colour = partyColour(bloc);
			const prevSeats = baseline ? blocSeats(baseline, bloc) : null;
			const prevPrim = blocPrimary(baseline, bloc);
			const prevTpp = blocTpp(baseline, bloc);

			if (mode === 'results' && results) {
				const seatsWon = blocSeats(results, bloc);
				const primaryPct = blocPrimary(results, bloc);
				const tppPct = blocTpp(results, bloc);
				return {
					bloc,
					partyLabel,
					leaderName: meta?.name ?? null,
					seat: meta?.seat ?? null,
					seatSlug: meta?.seat_slug ?? null,
					portrait: meta?.portrait ?? null,
					credit: meta?.credit ?? null,
					colour,
					seatsWon,
					seatsBefore: prevSeats,
					seatDelta: prevSeats != null ? seatsWon - prevSeats : null,
					primaryPct,
					primaryVotes: blocRawVotes(results, bloc),
					primarySwing: primaryPct != null && prevPrim != null ? primaryPct - prevPrim : null,
					tppPct,
					tppSwing: tppPct != null && prevTpp != null ? tppPct - prevTpp : null
				};
			}

			// Forecast mode
			const f = forecast!;
			const q = f.seats[bloc];
			const seatsMed = q ? Math.round(q[2]) : 0;
			const seatsLo = q ? Math.round(q[0]) : 0;
			const seatsHi = q ? Math.round(q[4]) : 0;
			const sp = f.statewide_primary[bloc];
			const primMed = sp ? sp[1] : null;
			const primLo = sp ? sp[0] : null;
			const primHi = sp ? sp[2] : null;
			const tppMed = bloc === 'ALP' ? f.tpp_alp[1] : bloc === 'COAL' ? 100 - f.tpp_alp[1] : null;
			const tppLo = bloc === 'ALP' ? f.tpp_alp[0] : bloc === 'COAL' ? 100 - f.tpp_alp[2] : null;
			const tppHi = bloc === 'ALP' ? f.tpp_alp[2] : bloc === 'COAL' ? 100 - f.tpp_alp[0] : null;

			let oddsLabel: string | null = null;
			if (bloc === 'ALP') {
				const pMaj = Math.round(f.outcome.alp_majority * 100);
				const pMost = Math.round(f.outcome.alp_most_seats * 100);
				oddsLabel = `${pMaj}% majority · ${pMost}% most seats`;
			} else if (bloc === 'COAL') {
				const pMaj = Math.round(f.outcome.coal_majority * 100);
				const pMost = Math.round(f.outcome.coal_most_seats * 100);
				oddsLabel = `${pMaj}% majority · ${pMost}% most seats`;
			} else if (f.seat_hist[bloc]) {
				const h = f.seat_hist[bloc];
				const tot = h.reduce((a, b) => a + b, 0) || 1;
				const pAny = Math.round((100 * (tot - (h[0] ?? 0))) / tot);
				oddsLabel = `${pAny}% chance of ≥1 seat`;
			}

			let actualSeats: number | null = null;
			if (retro && f.actual) {
				if (bloc === 'COAL') {
					actualSeats = Object.entries(f.actual.seat_counts).reduce(
						(a, [k, v]) => a + (COAL_CODES.has(k) ? v : 0),
						0
					);
				} else {
					actualSeats = f.actual.seat_counts[bloc] ?? 0;
				}
			}

			const sampledSeats = sampled ? (sampled.counts[bloc] ?? 0) : null;

			return {
				bloc,
				partyLabel,
				leaderName: meta?.name ?? null,
				seat: meta?.seat ?? null,
				seatSlug: meta?.seat_slug ?? null,
				portrait: meta?.portrait ?? null,
				credit: meta?.credit ?? null,
				colour,
				seatsBefore: prevSeats,
				seatsMed,
				seatsLo,
				seatsHi,
				sampledSeats,
				actualSeats,
				seatDelta: prevSeats != null ? (sampledSeats ?? seatsMed) - prevSeats : null,
				primMed,
				primLo,
				primHi,
				primarySwing: primMed != null && prevPrim != null ? primMed - prevPrim : null,
				tppMed,
				tppLo,
				tppHi,
				tppSwing: tppMed != null && prevTpp != null ? tppMed - prevTpp : null,
				oddsLabel
			};
		});
	});

	const hasPortraits = $derived(cards.some((c) => Boolean(c.portrait)));
	const headTitle = $derived(leaders?.head_title ?? defaultHeadTitle(jurisdiction));
	const majority = $derived(mode === 'results' ? (results?.majority ?? Math.floor(jurisdiction.seats / 2) + 1) : (forecast?.majority ?? Math.floor(jurisdiction.seats / 2) + 1));
	const seatsTotal = $derived(mode === 'results' ? (results?.seats_total ?? jurisdiction.seats) : jurisdiction.seats);

	function fmtDelta(v: number, decimals = 0, suffix = ''): { cls: string; text: string } {
		const eps = decimals === 0 ? 0.5 : 0.05;
		if (Math.abs(v) < eps) return { cls: 'flat', text: '—' };
		const arrow = v > 0 ? '▲' : '▼';
		const abs = Math.abs(v).toFixed(decimals);
		return { cls: v > 0 ? 'up' : 'down', text: `${arrow} ${abs}${suffix}` };
	}

	// Track broken portrait URLs gracefully if any image fails to load
	let broken = $state<Record<string, boolean>>({});
</script>

<section class="scorecard card" aria-label="{year} {jurisdiction.name} election overview">
	<header class="sc-meta">
		<div class="meta-pills">
			<span><strong>{seatsTotal}</strong> seats · <strong>{majority}</strong> for majority</span>
			{#if mode === 'results' && participation}
				<span>Registered <strong class="num">{participation.enrolled.toLocaleString()}</strong></span>
				<span>
					Turnout <strong class="num">{participation.turnoutPct.toFixed(1)}%</strong>
					{#if participation.deltaPp != null}
						{@const d = fmtDelta(participation.deltaPp, 1, ' pp')}
						<span class="delta {d.cls} num">{d.text}</span>
					{/if}
				</span>
			{:else if mode === 'forecast' && forecast}
				<span>
					{#if sampled}
						Showing <strong>Simulation #{sampled.simIndex + 1}</strong>
					{:else}
						Median &amp; 90% range{#if prevYear} · swings vs {prevYear}{/if}
					{/if}
				</span>
			{/if}
		</div>
	</header>

	<div class="leader-grid" style:--cols={cards.length}>
		{#each cards as c (c.bloc)}
			<article class="lcard">
				<div class="portrait-wrap">
					{#if c.portrait && !broken[c.bloc]}
						<img
							src={c.portrait}
							alt="{c.leaderName ?? c.partyLabel}"
							loading="eager"
							decoding="async"
							onerror={() => (broken = { ...broken, [c.bloc]: true })}
						/>
					{:else}
						<div class="avatar" style:--c={c.colour} aria-hidden="true">
							<span>{c.leaderName ? initials(c.leaderName) : c.bloc}</span>
						</div>
					{/if}
					<div class="bar" style:background={c.colour}></div>
				</div>

				<div class="identity">
					{#if c.leaderName}
						<div class="lname">{c.leaderName}</div>
						<div class="lparty small muted">{c.partyLabel}</div>
					{:else}
						<div class="lname">{c.partyLabel}</div>
					{/if}
					{#if c.seat}
						<div class="lseat small">
							{#if mode === 'results' && base && c.seatSlug}
								<a href="{base}/{c.seatSlug}/">{c.seat}</a>
							{:else if mode === 'forecast' && onSelectSeat && c.seatSlug}
								<button type="button" class="seat-btn" onclick={() => onSelectSeat(c.seatSlug!)}>{c.seat}</button>
							{:else}
								<span class="muted">{c.seat}</span>
							{/if}
						</div>
					{/if}
				</div>

				{#if mode === 'forecast' && c.oddsLabel}
					<div class="odds-pill small num">{c.oddsLabel}</div>
				{/if}

				<dl class="metrics num">
					{#if mode === 'results'}
						<div class="mrow">
							<dt>Seats</dt>
							<dd>
								<strong>{c.seatsWon}</strong>
								{#if c.seatDelta != null}
									{@const d = fmtDelta(c.seatDelta, 0)}
									<span class="delta {d.cls}">{d.text}</span>
								{/if}
							</dd>
						</div>
						{#if c.primaryPct != null}
							<div class="mrow">
								<dt>Primary</dt>
								<dd>
									<strong>{c.primaryPct.toFixed(1)}%</strong>
									{#if c.primarySwing != null}
										{@const d = fmtDelta(c.primarySwing, 1)}
										<span class="delta {d.cls}">{d.text}</span>
									{/if}
									{#if c.primaryVotes != null}
										<span class="sub-val muted">{c.primaryVotes.toLocaleString()} votes</span>
									{/if}
								</dd>
							</div>
						{/if}
						{#if c.tppPct != null}
							<div class="mrow">
								<dt>2PP</dt>
								<dd>
									<strong>{c.tppPct.toFixed(1)}%</strong>
									{#if c.tppSwing != null}
										{@const d = fmtDelta(c.tppSwing, 1)}
										<span class="delta {d.cls}">{d.text}</span>
									{/if}
								</dd>
							</div>
						{/if}
					{:else}
						<!-- Forecast mode -->
						<div class="mrow">
							<dt>{sampled ? 'Sim seats' : 'Seats'}</dt>
							<dd>
								<strong>{sampled ? c.sampledSeats : c.seatsMed}</strong>
								{#if !sampled}
									<span class="range muted">({c.seatsLo}–{c.seatsHi})</span>
								{/if}
								{#if c.seatDelta != null}
									{@const d = fmtDelta(c.seatDelta, 0)}
									<span class="delta {d.cls}">{d.text}</span>
								{/if}
								{#if retro && c.actualSeats != null}
									<span class="sub-val muted">Actual: {c.actualSeats}</span>
								{/if}
							</dd>
						</div>
						{#if c.primMed != null}
							<div class="mrow">
								<dt>Primary</dt>
								<dd>
									<strong>{c.primMed.toFixed(1)}%</strong>
									{#if c.primLo != null && c.primHi != null}
										<span class="range muted">({c.primLo.toFixed(0)}–{c.primHi.toFixed(0)})</span>
									{/if}
									{#if c.primarySwing != null}
										{@const d = fmtDelta(c.primarySwing, 1)}
										<span class="delta {d.cls}">{d.text}</span>
									{/if}
								</dd>
							</div>
						{/if}
						{#if c.tppMed != null}
							<div class="mrow">
								<dt>2PP</dt>
								<dd>
									<strong>{c.tppMed.toFixed(1)}%</strong>
									{#if c.tppLo != null && c.tppHi != null}
										<span class="range muted">({c.tppLo.toFixed(0)}–{c.tppHi.toFixed(0)})</span>
									{/if}
									{#if c.tppSwing != null}
										{@const d = fmtDelta(c.tppSwing, 1)}
										<span class="delta {d.cls}">{d.text}</span>
									{/if}
								</dd>
							</div>
						{/if}
					{/if}
				</dl>
			</article>
		{/each}
	</div>

	{#if leaders?.head_before || leaders?.head_after || hasPortraits}
		<footer class="sc-foot small">
			{#if mode === 'results' && (leaders?.head_before || leaders?.head_after)}
				<div class="hog">
					{#if leaders.head_before}
						<span>
							<span class="muted">{headTitle} before:</span>
							<strong class="chip" style:--c={partyColour(leaders.head_before.party)}>{leaders.head_before.name}</strong>
						</span>
					{/if}
					{#if leaders.head_before && leaders.head_after}
						<span class="muted" aria-hidden="true">→</span>
					{/if}
					{#if leaders.head_after}
						<span>
							<span class="muted">{headTitle} after:</span>
							<strong class="chip" style:--c={partyColour(leaders.head_after.party)}>{leaders.head_after.name}</strong>
						</span>
					{/if}
				</div>
			{:else if mode === 'forecast' && leaders?.head_before}
				<div class="hog">
					<span>
						<span class="muted">Incumbent {headTitle}:</span>
						<strong class="chip" style:--c={partyColour(leaders.head_before.party)}>{leaders.head_before.name}</strong>
					</span>
					{#if forecast && !retro}
						<span class="muted">
							· {coalShortLbl} majority {Math.round(forecast.outcome.coal_majority * 100)}% · Hung {Math.round(forecast.outcome.hung * 100)}% · Labor majority {Math.round(forecast.outcome.alp_majority * 100)}%
						</span>
					{/if}
				</div>
			{/if}
			{#if hasPortraits}
				<span class="credits muted">Portraits: Wikimedia Commons (CC)</span>
			{/if}
		</footer>
	{/if}
</section>

<style>
	.scorecard {
		margin: 1.25rem 0 1.75rem;
		padding: 1rem 1.2rem;
		display: grid;
		gap: 0.9rem;
	}
	.sc-meta {
		border-bottom: 1px solid var(--rule);
		padding-bottom: 0.6rem;
		font-size: 0.84rem;
		color: var(--fg-2);
	}
	.meta-pills {
		display: flex;
		flex-wrap: wrap;
		gap: 0.35rem 1.25rem;
		align-items: baseline;
	}
	.leader-grid {
		display: grid;
		grid-template-columns: repeat(var(--cols, 3), minmax(0, 1fr));
		gap: 0.9rem;
	}
	@media (max-width: 780px) {
		.leader-grid {
			grid-template-columns: repeat(2, minmax(0, 1fr));
		}
	}
	@media (max-width: 460px) {
		.leader-grid {
			grid-template-columns: 1fr;
		}
	}
	.lcard {
		display: flex;
		flex-direction: column;
		gap: 0.5rem;
		padding: 0.75rem;
		background: var(--bg);
		border: 1px solid var(--rule);
		border-radius: var(--radius);
	}
	.portrait-wrap {
		width: 6.2rem;
		margin: 0 auto;
		overflow: hidden;
		border-radius: 6px 6px 2px 2px;
		background: var(--surface);
		box-shadow: 0 1px 3px rgb(0 0 0 / 0.08);
	}
	.portrait-wrap img {
		display: block;
		width: 100%;
		aspect-ratio: 4 / 5;
		object-fit: cover;
		object-position: top center;
	}
	.avatar {
		width: 100%;
		aspect-ratio: 4 / 5;
		display: grid;
		place-items: center;
		background: color-mix(in srgb, var(--c) 15%, var(--surface));
		color: var(--c);
		font-family: var(--font-display);
		font-size: 1.55rem;
		font-weight: 700;
		letter-spacing: 0.02em;
	}
	.bar {
		height: 4px;
		width: 100%;
	}
	.identity {
		text-align: center;
		display: grid;
		gap: 0.1rem;
	}
	.lname {
		font-weight: 650;
		font-size: 0.98rem;
		line-height: 1.2;
	}
	.lparty {
		line-height: 1.2;
	}
	.lseat {
		margin-top: 0.1rem;
	}
	.lseat a,
	.seat-btn {
		font: inherit;
		color: var(--fg-2);
		text-decoration: underline;
		text-decoration-color: var(--rule-strong);
		text-underline-offset: 2px;
		background: none;
		border: 0;
		padding: 0;
		cursor: pointer;
	}
	.lseat a:hover,
	.seat-btn:hover {
		color: var(--fg);
	}
	.odds-pill {
		text-align: center;
		font-size: 0.74rem;
		padding: 0.2rem 0.45rem;
		border-radius: 999px;
		background: var(--surface);
		border: 1px solid var(--rule);
		color: var(--fg-2);
	}
	.metrics {
		margin: 0.15rem 0 0;
		padding-top: 0.5rem;
		border-top: 1px solid var(--rule);
		display: grid;
		gap: 0.35rem;
		font-size: 0.84rem;
	}
	.mrow {
		display: flex;
		justify-content: space-between;
		align-items: baseline;
		gap: 0.4rem;
	}
	.mrow dt {
		color: var(--fg-2);
		font-size: 0.78rem;
		flex-shrink: 0;
	}
	.mrow dd {
		margin: 0;
		text-align: right;
		display: flex;
		flex-wrap: wrap;
		justify-content: flex-end;
		align-items: baseline;
		gap: 0.15rem 0.35rem;
	}
	.range {
		font-size: 0.76rem;
	}
	.sub-val {
		flex-basis: 100%;
		font-size: 0.72rem;
	}
	.delta {
		font-size: 0.75rem;
		font-weight: 600;
		white-space: nowrap;
	}
	.delta.up {
		color: #15803d;
	}
	.delta.down {
		color: #b91c1c;
	}
	:global([data-theme='dark']) .delta.up {
		color: #4ade80;
	}
	:global([data-theme='dark']) .delta.down {
		color: #f87171;
	}
	.delta.flat {
		color: var(--muted);
	}
	.sc-foot {
		border-top: 1px solid var(--rule);
		padding-top: 0.6rem;
		display: flex;
		flex-wrap: wrap;
		justify-content: space-between;
		align-items: baseline;
		gap: 0.4rem 1rem;
	}
	.hog {
		display: flex;
		flex-wrap: wrap;
		align-items: baseline;
		gap: 0.35rem 0.65rem;
	}
	.chip {
		display: inline-flex;
		align-items: center;
		gap: 0.35rem;
	}
	.chip::before {
		content: '';
		width: 0.55rem;
		height: 0.55rem;
		border-radius: 2px;
		background: var(--c);
	}
	.credits {
		font-size: 0.74rem;
	}
</style>
