<script lang="ts">
	import type { PageData } from './$types';
	import { party } from '$lib/parties';

	let { data }: { data: PageData } = $props();
	const model = $derived(data.model);
	const pct = (p: number) => `${Math.round(p * 100)}%`;
	const signed = (v: number | null) => (v == null ? '–' : `${v > 0 ? '+' : ''}${v.toFixed(1)}`);
</script>

<svelte:head>
	<title>Methodology · Prophecy</title>
</svelte:head>

<p class="eyebrow">How it works</p>
<h1>Methodology</h1>
<p class="lede">
	The model has three layers, each checked against past Victorian elections. Everything below is
	reproducible from the open pipeline.
</p>

<div class="prose">
	<h2>1. Poll aggregation</h2>
	<p>
		A Bayesian state-space model tracks each party's primary vote week by week since the last election,
		estimating every pollster's systematic lean ("house effect") and the noise in each poll. Each
		party's support follows a smooth, damped trend: it has a momentum that changes gradually, so
		poll-to-poll noise is not mistaken for movement, and momentum fades after the last poll rather than
		being projected to election day. Pollsters' house effects sum to zero, so the average tracks the
		polling industry as a whole.
	</p>

	<h2>2. Election-day uncertainty</h2>
	<p>
		The industry as a whole can miss. The forecast adds a polling-error term sized from how far the final
		month's poll average missed the result at past Victorian elections, with heavy tails, and corrects
		half of any persistent lean (polls have tended to overstate the Greens).
	</p>

	<h2>3. Seats</h2>
	<p>
		Each seat starts from its last result. Statewide swings are applied on the logit scale with
		correlated regional swings and seat-level noise; One Nation's vote is placed using its federal 2025
		result in each area. Every candidate's primary vote is simulated, then preferences are distributed
		as in a real count, with flows estimated from the electoral commission's full preference
		distributions and calibrated so that replaying the last election reproduces each seat's result.
	</p>
</div>

{#if model?.poll_error.length}
	<h2>How far have the polls missed?</h2>
	<p class="muted small">
		Final-{model.poll_error_settings?.window_days ?? 28}-day simple poll average minus the actual result, in
		points. Positive means the polls overstated the party.
	</p>
	<div class="scroll-x">
		<table class="data narrow">
			<thead>
				<tr>
					<th class="left">Election</th><th>Polls</th><th>Labor</th><th>Coalition</th><th>Greens</th>
					<th>Labor 2PP</th>
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
			Error spread used in the forecast (points, RMS with a floor):
			{Object.entries(model.poll_error_settings.sd).map(([p, v]) => `${party(p).short} ${v}`).join(', ')}.
			Lean correction (half the average error):
			{Object.entries(model.poll_error_settings.bias).map(([p, v]) => `${party(p).short} ${signed(v)}`).join(', ')}.
		</p>
	{/if}
{/if}

{#each model?.backtests ?? [] as b (b.election_id)}
	{@const year = b.election_id.slice(-4)}
	<h2>Backtest: forecasting {year} blind</h2>
	<p class="prose">
		Using only what was known before polling day (the previous result, that cycle's polls, and polling
		error from earlier elections), the model gave Labor a majority a
		<strong>{pct(b.outcome.alp_majority)}</strong> chance and a hung parliament {pct(b.outcome.hung)}. Its favourite
		won {Math.round(b.favourite_accuracy * b.n_seats)} of {b.n_seats} seats (Brier score {b.brier.toFixed(3)}).
	</p>

	<div class="grid2">
		<div>
			<h3>Seats</h3>
			<table class="data">
				<thead><tr><th class="left">Party</th><th>Forecast</th><th>90% range</th><th>Actual</th></tr></thead>
				<tbody>
					{#each Object.entries(b.seats) as [p, s] (p)}
						<tr>
							<td class="left">{party(p).short}</td>
							<td>{s.median}</td>
							<td>{s.p90[0]}–{s.p90[1]}</td>
							<td><strong>{s.actual}</strong>{s.covered_90 ? '' : ' ✗'}</td>
						</tr>
					{/each}
				</tbody>
			</table>
		</div>
		<div>
			<h3>Calibration</h3>
			<table class="data">
				<thead><tr><th class="left">Favourite's chance</th><th>Seats</th><th>Average</th><th>Won</th></tr></thead>
				<tbody>
					{#each b.calibration as c (c.bin)}
						<tr>
							<td class="left">{c.bin.replace('-', '–')}</td>
							<td>{c.n}</td>
							<td>{pct(c.mean_prob)}</td>
							<td>{pct(c.hit_rate)}</td>
						</tr>
					{/each}
				</tbody>
			</table>
		</div>
	</div>

	<h3>Seats the favourite lost</h3>
	<ul class="misses small">
		{#each b.misses as m (m.district)}
			<li>
				<strong>{m.district}</strong>: {party(m.favourite).short} favoured ({pct(m.p_fav)}); {party(m.won).short}
				won ({pct(m.p_won)}).
			</li>
		{/each}
	</ul>
{/each}

<style>
	.prose {
		max-width: 44rem;
	}
	.narrow {
		max-width: 36rem;
	}
	.grid2 {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(18rem, 1fr));
		gap: 1rem 2rem;
	}
	h3 {
		margin-top: 1.25rem;
		font-family: var(--font-sans);
		font-size: 1rem;
	}
	.misses {
		columns: 2 18rem;
		padding-left: 1.2rem;
	}
</style>
