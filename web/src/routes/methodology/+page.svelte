<script lang="ts">
	import { SITE_NAME } from '$lib/site';
	import Orby from '$lib/components/brand/Orby.svelte';
	import type { PageData } from './$types';
	import { party } from '$lib/parties';
	import { allForecastYears, coalName, getJurisdiction, theCoal } from '$lib/jurisdictions';
	import { isHareClark, type Backtest, type HareClarkBacktest } from './model';
	import { NOTES } from './notes';

	let { data }: { data: PageData } = $props();

	const pct = (p: number) => {
		const v = p * 100;
		return v > 0 && v < 1 ? '<1%' : v < 100 && v > 99 ? '>99%' : `${Math.round(v)}%`;
	};
	const signed = (v: number | null) => (v == null ? '–' : `${v > 0 ? '+' : ''}${v.toFixed(1)}`);
	const yearOf = (id: string) => Number(id.match(/(\d{4})/)?.[1]);
	const hasPage = (code: string, year: number) => {
		const j = getJurisdiction(code);
		return !!j && allForecastYears(j).includes(year);
	};

	// Minor parties that appear in the Hare-Clark tests (codes from the pipeline's ingest).
	const MINOR: Record<string, string> = {
		IFC: 'Independents for Canberra',
		STR: 'Strong Independents',
		BEL: 'Belco Party',
		FFP: 'Family First',
		AJP: 'Animal Justice',
		DLP: 'Democratic Labour'
	};
	const label = (code: string, p: string) =>
		p === 'COAL' && coalName(code) !== 'Coalition'
			? coalName(code)
			: p === 'tpp'
				? 'Labor two-party'
				: (MINOR[p] ?? (p.startsWith('X_') ? 'Other' : party(p).short));

	type AnyBacktest = Backtest | HareClarkBacktest;
	// Published backtests in date order, without the alternative-aggregator A/B runs.
	const tests = (code: string): AnyBacktest[] =>
		(data.models[code]?.backtests ?? [])
			.filter((b) => !b.election_id.endsWith('-corr'))
			.sort((a, b) => yearOf(a.election_id) - yearOf(b.election_id));
	const latest = (code: string) => tests(code).at(-1);

	// Who governed after the election, from the seats each side actually won.
	function result(b: AnyBacktest, code: string): string {
		const total = isHareClark(b)
			? Object.values(b.seats).reduce((s, r) => s + r.actual, 0)
			: b.n_seats;
		const alp = b.seats.ALP?.actual ?? 0;
		const coal = (isHareClark(b) ? b.seats.LIB?.actual : b.seats.COAL?.actual) ?? 0;
		const need = Math.floor(total / 2) + 1;
		if (alp >= need) return `Labor won a majority (${alp} of ${total} seats)`;
		if (coal >= need) return `${theCoal(code)} won a majority (${coal} of ${total} seats)`;
		return `no party won a majority (Labor ${alp}, ${label(code, 'COAL')} ${coal}, of ${total} seats)`;
	}

	function odds(b: AnyBacktest, code: string): string {
		const o = b.outcome as Record<string, number>;
		const coal = isHareClark(b) ? o.lib_majority : o.coal_majority;
		return `Labor majority ${pct(o.alp_majority)}, ${label(code, 'COAL')} majority ${pct(coal)}, hung parliament ${pct(o.hung)}`;
	}

	// Seat-by-seat calls the model got most confidently wrong.
	const worstMisses = (b: Backtest) => [...b.misses].sort((x, y) => y.p_fav - x.p_fav).slice(0, 3);
	// Parties that won seats or were expected to (the Hare-Clark tests list every party on the ballot).
	const seatRows = (b: AnyBacktest) => Object.entries(b.seats).filter(([, r]) => r.actual > 0 || r.median > 0);
	// Seats won by parties the single-member scoring does not list (One Nation, Katter's, ...).
	const otherSeats = (b: AnyBacktest) =>
		isHareClark(b) ? 0 : b.n_seats - Object.values(b.seats).reduce((s, r) => s + r.actual, 0);
	const range = (r: [number, number]) => `${r[0]}–${r[1]}`;

	// Single-member chambers' latest tests, for the headline figure.
	const headline = $derived.by(() => {
		let called = 0;
		let seats = 0;
		let held = 0;
		let n = 0;
		for (const note of NOTES) {
			const b = latest(note.code);
			if (!b || isHareClark(b)) continue;
			called += Math.round(b.favourite_accuracy * b.n_seats);
			held += Math.round(b.status_quo_accuracy * b.n_seats);
			seats += b.n_seats;
			n += 1;
		}
		return { called, seats, held, n };
	});
</script>

<svelte:head>
	<title>Methodology · {SITE_NAME}</title>
	<meta
		name="description"
		content="How the {SITE_NAME} election model works, what is different in each state and territory, and how its blind forecasts of past elections compared with the results."
	/>
</svelte:head>

<div class="intro">
	<div>
		<p class="eyebrow">How it works</p>
		<h1>Methodology</h1>
		<p class="lede">
			{SITE_NAME} doesn’t pick a winner. It plays out the election 20,000 times, each a little differently, and
			counts how often each result comes up. A party that wins in 7,000 of those runs has a 35% chance, not
			no chance. Like Orby, the model holds up odds, never certainties.
		</p>
	</div>
	<Orby size={170} />
</div>

<nav class="toc card" aria-label="On this page">
	<a href="#overview">The model in four steps</a>
	<a href="#detail">Each step in more detail</a>
	<a href="#testing">How we test it</a>
	<a href="#states">State by state</a>
</nav>

<section id="overview">
	<h2>The model in four steps</h2>
	<ol class="steps">
		<li class="card">
			<span class="step-n" aria-hidden="true">1</span>
			<h3>Read the polls</h3>
			<p>
				Every published poll since the last election is combined into one trend for each party, allowing
				for each pollster’s habits and for the ordinary noise in any single poll.
			</p>
		</li>
		<li class="card">
			<span class="step-n" aria-hidden="true">2</span>
			<h3>Allow for the polls being wrong</h3>
			<p>
				Polls as a whole sometimes miss. Each simulation adds a statewide polling error the size of past
				misses in that state, so the forecast covers a 2019-style surprise.
			</p>
		</li>
		<li class="card">
			<span class="step-n" aria-hidden="true">3</span>
			<h3>Play out every seat</h3>
			<p>
				Each seat starts from its last result and moves with the state, its region and its own local
				factors: who is standing, who is retiring, and seat-by-seat surprises.
			</p>
		</li>
		<li class="card">
			<span class="step-n" aria-hidden="true">4</span>
			<h3>Count the preferences</h3>
			<p>
				The model then runs a real preference count in each seat, excluding candidates one by one, using
				how each party’s voters have actually directed preferences.
			</p>
		</li>
	</ol>
	<p class="prose">
		Repeat that 20,000 times and you have the forecast: each seat’s chance is the share of runs it was won,
		each party’s seat range is the spread across runs, and the chance of a majority is how often a party
		reached it.
	</p>
</section>

<section id="detail" class="prose">
	<h2>Each step in more detail</h2>

	<h3>The poll average</h3>
	<p>
		The poll average is a Bayesian model that tracks each party’s first-preference vote week by week from
		the last election to today. It learns three things at once: where each party’s support really is,
		how much each pollster consistently leans towards or away from each party (its “house effect”), and
		how much extra noise polls carry beyond their sample size.
	</p>
	<p>
		Support is allowed to drift with some momentum, so a genuine shift shows up as a trend while a
		single odd poll is mostly treated as noise. After the last poll the momentum fades, so the forecast
		does not project a recent trend all the way to election day. House effects are set to cancel out
		across pollsters, which means the average tracks the polling industry as a whole and cannot by
		itself tell if every pollster is wrong in the same direction. That is the next step’s job.
	</p>
	<p>
		Where there are fewer than three public polls (the ACT and Northern Territory in 2024), there is
		nothing to fit, so the forecast starts from the previous result and adds a swing as large as that
		place’s past election-to-election swings.
	</p>

	<h3>How wrong could the polls be?</h3>
	<p>
		For every past election we compare the average of the final month’s polls with the actual result.
		Those misses set the size of the polling error added to each simulation. It is drawn from a
		heavy-tailed distribution, so big misses are rarer than small ones but not ruled out. Errors are
		linked across parties: if the polls overstate Labor, they usually understate someone else.
	</p>
	<p>
		Each state’s history is short, so its error size is blended with the pattern across all nine
		jurisdictions, leaning more on the state’s own record the more elections it has. Where polls have
		leaned the same way time after time (Victorian polls have tended to overstate the Greens), half of
		that lean is corrected.
	</p>

	<h3>From the statewide vote to each seat</h3>
	<p>
		Every seat starts from its vote at the last election (re-cut onto new boundaries where they have
		changed). Each simulation’s statewide swing is applied proportionally rather than as a flat number of
		points, so a party on 10% in a seat can’t lose 15 points. Swings then vary in three ways:
	</p>
	<ul>
		<li><strong>By region.</strong> Seats in the same region move together, so a bad night in one part of the state shows up across all its seats at once.</li>
		<li><strong>By seat.</strong> Every seat gets its own random surprise. These are occasionally large, as real seats sometimes defy the trend.</li>
		<li><strong>Toward the middle.</strong> A party’s safest seats tend to swing against it a little, and its weakest seats towards it.</li>
	</ul>
	<p>
		After all that, the seats are adjusted so that together they add back up to the simulated statewide
		vote. How big the seat and regional variation should be, and how strong the pull to the middle is,
		are estimated from pairs of past elections in every jurisdiction, not set by hand.
	</p>

	<h3>Candidates and local factors</h3>
	<ul>
		<li><strong>Retiring members</strong> take some personal vote with them, and <strong>first-term members</strong> standing again tend to gain some. Both effects are estimated from past elections.</li>
		<li><strong>Independents</strong> who stood last time keep most of their vote. Sitting independents keep all of it, and one who retires takes most of it away.</li>
		<li><strong>First-time independents</strong> have no previous vote, so each one’s vote is drawn from what first-time independents have polled at earlier elections. Most get a few per cent, but about one in twenty gets 20% or more, which is how “teal”-style surprises enter the forecast.</li>
		<li><strong>The ballot.</strong> Once nominations close, a party with no candidate in a seat gets no vote there.</li>
		<li><strong>By-elections</strong> since the last general election shift that seat by half of any swing beyond the statewide movement at the time.</li>
		<li><strong>One Nation</strong> is placed using its most recent vote where it stood widely, otherwise its latest federal vote re-cut onto the state seats.</li>
	</ul>

	<h3>Counting the preferences</h3>
	<p>
		With every candidate’s first-preference vote simulated, the model runs the count the way an
		electoral commission does: exclude the lowest candidate, pass their ballots on, and repeat until two
		remain (or, under Hare-Clark, until every seat is filled). Where those ballots go is estimated from
		the electoral commissions’ full distributions of preferences, which record every transfer at every
		stage. The flows are then fine-tuned so that replaying the last election reproduces each seat’s
		actual final result, and they vary a little between simulations.
	</p>

	<h3>What the model cannot see</h3>
	<p>
		The model only knows votes already cast and polls already published. A new party’s breakthrough, a
		scandal in one seat, a strong local campaign or late movement after the last poll are only covered by
		the general uncertainty, never foreseen. That is why the ranges are wide, and why a 25% chance comes
		in about one time in four.
	</p>
</section>

<section id="testing">
	<h2>How we test it</h2>
	<div class="prose">
		<p>
			The real test of a forecast is how it would have done before the result was known. For past
			elections we run the model <strong>blind</strong>: it sees only what was public before polling day
			(the previous result, that campaign’s polls, the ballot, and polling errors and seat swings from
			<em>earlier</em> elections), then we compare it with what happened. Nothing is tuned on the election
			being tested.
		</p>
		{#if headline.n}
			<p>
				In the latest blind test for each of the {headline.n} single-member chambers, the model’s favourite
				won <strong>{headline.called} of {headline.seats}</strong> seats. Simply assuming every seat stays with
				its current holder would have got {headline.held} right.
			</p>
		{/if}
	</div>

	<dl class="glossary">
		<div>
			<dt>Favourite won</dt>
			<dd>Seats where the party the model gave the best chance actually won.</dd>
		</div>
		<div>
			<dt>No-change guess</dt>
			<dd>The simplest rival: every seat stays with whoever held it. Easy to beat in a change election, hard in a quiet one.</dd>
		</div>
		<div>
			<dt>90% range</dt>
			<dd>The middle 90% of simulations. A well-calibrated model lands outside it about one time in ten.</dd>
		</div>
		<div>
			<dt>Brier score</dt>
			<dd>How close the seat probabilities were to what happened. 0 is perfect; calling every seat 50–50 between two parties scores 0.5.</dd>
		</div>
	</dl>

	<div class="scroll-x">
		<table class="data summary">
			<caption class="visually-hidden">Latest blind test in each jurisdiction</caption>
			<thead>
				<tr>
					<th class="left" scope="col">Jurisdiction</th>
					<th scope="col">Election</th>
					<th scope="col">Favourite won</th>
					<th scope="col">No-change guess</th>
					<th scope="col">Labor 2PP forecast</th>
					<th scope="col">Actual</th>
				</tr>
			</thead>
			<tbody>
				{#each NOTES as note (note.code)}
					{@const b = latest(note.code)}
					{#if b}
						<tr>
							<th class="left" scope="row"><a href="#{note.code}">{note.name}</a></th>
							<td>{yearOf(b.election_id)}</td>
							{#if isHareClark(b)}
								<td colspan="2" class="muted">Hare-Clark: scored on seats per party</td>
								<td>–</td>
								<td>–</td>
							{:else}
								{@const t = b.statewide.tpp}
								<td>{Math.round(b.favourite_accuracy * b.n_seats)} of {b.n_seats}</td>
								<td>{Math.round(b.status_quo_accuracy * b.n_seats)} of {b.n_seats}</td>
								<td>{t ? `${t.forecast[1].toFixed(1)} (${t.forecast[0].toFixed(0)}–${t.forecast[2].toFixed(0)})` : '–'}</td>
								<td>{t?.actual != null ? t.actual.toFixed(1) : '–'}</td>
							{/if}
						</tr>
					{/if}
				{/each}
			</tbody>
		</table>
	</div>
	<p class="small muted">
		Labor two-party-preferred vote (%) against the Coalition: the model’s median with its 90% range, and
		the result.
	</p>
</section>

<section id="states">
	<h2>State by state</h2>
	<p class="prose">
		The core model is the same everywhere. What changes is the voting system, the boundaries, the data each
		electoral commission publishes, and how much polling there is. Here is what is different in each place,
		and how the model did at its latest blind test.
	</p>
	<nav class="chips" aria-label="Jurisdictions">
		{#each NOTES as note (note.code)}
			<a href="#{note.code}">{note.name}</a>
		{/each}
	</nav>

	{#each NOTES as note (note.code)}
		{@const model = data.models[note.code]}
		{@const b = latest(note.code)}
		{@const earlier = tests(note.code).slice(0, -1)}
		<article id={note.code} class="jur card">
			<header>
				<h3>{note.name}</h3>
				<p class="muted small">{note.system}</p>
				<ul class="tags" aria-label="Features">
					{#each note.tags as t (t)}<li>{t}</li>{/each}
				</ul>
			</header>

			<h4>What’s different here</h4>
			<ul class="points">
				{#each note.points as p, i (i)}<li>{p}</li>{/each}
			</ul>
			{#if note.code === 'vic' && hasPage('vic', 2026)}
				<p><a href="/vic/forecast/2026/">See the live 2026 forecast →</a></p>
			{/if}

			{#if b}
				{@const year = yearOf(b.election_id)}
				<h4>Blind test: the {year} election</h4>
				{#if note.backtestNote}<p class="muted small">{note.backtestNote}</p>{/if}
				<p>
					Before polling day the model gave {odds(b, note.code)}. In the end, {result(b, note.code)}.
					{#if !isHareClark(b)}
						Its favourite won <strong>{Math.round(b.favourite_accuracy * b.n_seats)} of {b.n_seats}</strong>
						seats, against {Math.round(b.status_quo_accuracy * b.n_seats)} for the no-change guess (Brier score
						{b.brier.toFixed(3)}).
					{:else}
						Its seat-probability Brier score, across every party in every division, was {b.seat_brier.toFixed(3)}.
					{/if}
				</p>

				<div class="tables">
					<div class="scroll-x">
						<table class="data">
							<caption>Seats</caption>
							<thead>
								<tr><th class="left" scope="col">Party</th><th scope="col">Forecast</th><th scope="col">90% range</th><th scope="col">Won</th></tr>
							</thead>
							<tbody>
								{#each seatRows(b) as [p, r] (p)}
									<tr class:outside={!r.covered_90}>
										<th class="left" scope="row">{label(note.code, p)}</th>
										<td>{r.median}</td>
										<td>{range(r.p90)}</td>
										<td>{r.actual}{#if !r.covered_90}<span class="flag" title="Outside the 90% range"> ●</span>{/if}</td>
									</tr>
								{/each}
								{#if otherSeats(b) > 0}
									<tr>
										<th class="left" scope="row">Other parties</th>
										<td class="muted">–</td>
										<td class="muted">–</td>
										<td>{otherSeats(b)}</td>
									</tr>
								{/if}
							</tbody>
						</table>
					</div>
					<div class="scroll-x">
						<table class="data">
							<caption>Vote (%)</caption>
							<thead>
								<tr><th class="left" scope="col">Vote</th><th scope="col">Forecast</th><th scope="col">90% range</th><th scope="col">Actual</th></tr>
							</thead>
							<tbody>
								{#each Object.entries(b.statewide) as [p, s] (p)}
									{#if s.actual != null}
										{@const out = s.actual < s.forecast[0] || s.actual > s.forecast[2]}
										<tr class:outside={out}>
											<th class="left" scope="row">{label(note.code, p)}</th>
											<td>{s.forecast[1].toFixed(1)}</td>
											<td>{s.forecast[0].toFixed(1)}–{s.forecast[2].toFixed(1)}</td>
											<td>{s.actual.toFixed(1)}{#if out}<span class="flag" title="Outside the 90% range"> ●</span>{/if}</td>
										</tr>
									{/if}
								{/each}
							</tbody>
						</table>
					</div>
				</div>
				<p class="small muted"><span class="flag">●</span> outside the model’s 90% range.</p>

				{#if !isHareClark(b) && b.misses.length}
					<p class="small">
						<strong>Most confident misses:</strong>
						{#each worstMisses(b) as m, i (m.district)}{i ? '; ' : ''}{m.district} ({label(note.code, m.favourite)} {pct(m.p_fav)}, won by {label(note.code, m.won)}){/each}.
					</p>
				{/if}

				{#if hasPage(note.code, year)}
					<p class="small">
						<a href="/{note.code}/forecast/{year}/vs-result/">Every seat, the calibration and every miss, forecast against the result →</a>
					</p>
				{/if}

				{#if earlier.length}
					<p class="small muted">
						Earlier blind tests:
						{#each earlier as e, i (e.election_id)}{i ? '; ' : ''}{yearOf(e.election_id)}{' '}{#if !isHareClark(e)}(favourite won {Math.round(e.favourite_accuracy * e.n_seats)} of {e.n_seats}, no-change {Math.round(e.status_quo_accuracy * e.n_seats)}){:else}(Brier {e.seat_brier.toFixed(3)}){/if}{/each}.
					</p>
				{/if}
			{:else}
				<p class="muted">No blind test has been run here yet.</p>
			{/if}

			{#if model?.poll_error.length}
				<details>
					<summary>How far have the polls missed here?</summary>
					<p class="small muted">
						Average of the final {model.poll_error_settings?.window_days ?? 28} days’ polls minus the result, in
						points. Positive means the polls overstated the party.
					</p>
					<div class="scroll-x">
						<table class="data narrow">
							<thead>
								<tr>
									<th class="left" scope="col">Election</th><th scope="col">Polls</th><th scope="col">Labor</th>
									<th scope="col">{label(note.code, 'COAL')}</th><th scope="col">Greens</th><th scope="col">Labor 2PP</th>
								</tr>
							</thead>
							<tbody>
								{#each model.poll_error as r (r.year)}
									<tr>
										<td class="left">{r.year}</td>
										<td>{r.n_polls}</td>
										<td>{signed(r.ALP_error)}</td>
										<td>{signed(r.COAL_error)}</td>
										<td>{signed(r.GRN_error)}</td>
										<td>{signed(r.tpp_error)}</td>
									</tr>
								{/each}
							</tbody>
						</table>
					</div>
					{#if model.poll_error_settings}
						<p class="small muted">
							Polling error allowed for in this forecast (points):
							{Object.entries(model.poll_error_settings.sd).map(([p, v]) => `${label(note.code, p)} ${v}`).join(', ')}.
							Lean corrected:
							{Object.entries(model.poll_error_settings.bias).map(([p, v]) => `${label(note.code, p)} ${signed(v)}`).join(', ')}.
						</p>
					{/if}
				</details>
			{/if}
		</article>
	{/each}
</section>

<p class="small muted source">
	Everything here is reproducible from the open pipeline, including every blind test.
</p>

<style>
	.intro {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 2rem;
		margin-bottom: 1.5rem;
	}
	@media (max-width: 40rem) {
		.intro :global(.orby) {
			display: none;
		}
	}
	section {
		margin-top: 2.75rem;
		scroll-margin-top: 1rem;
	}
	h2 {
		font-family: var(--font-display);
	}
	.prose {
		max-width: 44rem;
	}
	.prose h3 {
		margin-top: 1.75rem;
		font-size: 1.1rem;
	}
	.prose li + li {
		margin-top: 0.35rem;
	}

	.toc {
		display: flex;
		flex-wrap: wrap;
		gap: 0.5rem 1.5rem;
		padding: 0.85rem 1.25rem;
		font-weight: 600;
		font-size: 0.95rem;
	}

	.steps {
		list-style: none;
		padding: 0;
		margin: 1rem 0 1.25rem;
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(14rem, 1fr));
		gap: 1rem;
	}
	.steps li {
		position: relative;
	}
	.steps h3 {
		margin: 0.5rem 0 0.4rem;
		font-size: 1.05rem;
	}
	.steps p {
		margin: 0;
		color: var(--fg-2);
		font-size: 0.95rem;
	}
	.step-n {
		display: inline-grid;
		place-items: center;
		width: 2rem;
		height: 2rem;
		border-radius: 50%;
		background: var(--accent);
		color: var(--on-accent);
		font-weight: 700;
		font-family: var(--font-display);
	}

	.glossary {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(15rem, 1fr));
		gap: 0.75rem 1.5rem;
		margin: 1.25rem 0 1.5rem;
		max-width: 60rem;
	}
	.glossary dt {
		font-weight: 650;
	}
	.glossary dd {
		margin: 0.15rem 0 0;
		color: var(--fg-2);
		font-size: 0.9rem;
	}
	.summary {
		max-width: 56rem;
	}

	.chips {
		display: flex;
		flex-wrap: wrap;
		gap: 0.5rem;
		margin: 1rem 0 1.5rem;
	}
	.chips a {
		border: 1px solid var(--rule-strong);
		border-radius: 999px;
		padding: 0.3rem 0.85rem;
		font-size: 0.9rem;
		text-decoration: none;
	}
	.chips a:hover {
		background: var(--rule);
	}

	.jur {
		margin-top: 1.25rem;
		scroll-margin-top: 1rem;
		max-width: 60rem;
	}
	.jur header h3 {
		font-family: var(--font-display);
		font-size: 1.45rem;
		margin: 0;
	}
	.jur header p {
		margin: 0.25rem 0 0.5rem;
	}
	.jur h4 {
		margin: 1.4rem 0 0.5rem;
		font-size: 1rem;
	}
	.jur > p,
	.points {
		max-width: 46rem;
	}
	.points li + li {
		margin-top: 0.45rem;
	}
	.tags {
		list-style: none;
		padding: 0;
		margin: 0;
		display: flex;
		flex-wrap: wrap;
		gap: 0.4rem;
	}
	.tags li {
		font-size: 0.75rem;
		font-weight: 650;
		letter-spacing: 0.02em;
		padding: 0.15rem 0.6rem;
		border-radius: 999px;
		background: var(--rule);
		color: var(--fg-2);
	}

	.tables {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(17rem, 1fr));
		gap: 0.5rem 1.5rem;
	}
	/* Grid items default to their content's width; let wide tables scroll instead. */
	.tables > * {
		min-width: 0;
	}
	@media (max-width: 40rem) {
		.jur {
			padding: 1rem;
		}
		.tables {
			grid-template-columns: minmax(0, 1fr);
		}
	}
	.tables caption {
		text-align: left;
		font-weight: 650;
		font-size: 0.85rem;
		color: var(--muted);
		padding-bottom: 0.25rem;
	}
	/* Row labels read as ordinary cells, not column headers. */
	table tbody th {
		font-weight: 500;
		font-size: 0.9rem;
		color: var(--fg);
		border-bottom-color: var(--rule);
	}
	.flag {
		color: var(--swirl-amber);
	}
	tr.outside td:last-child {
		font-weight: 650;
	}

	details {
		margin-top: 1.25rem;
		border-top: 1px solid var(--rule);
		padding-top: 0.75rem;
	}
	summary {
		cursor: pointer;
		font-weight: 600;
		font-size: 0.95rem;
	}
	.narrow {
		max-width: 36rem;
	}
	.source {
		margin-top: 2.5rem;
	}
</style>
