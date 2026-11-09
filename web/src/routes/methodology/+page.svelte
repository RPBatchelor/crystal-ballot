<script lang="ts">
	import { SITE_NAME } from '$lib/site';
	import Orby from '$lib/components/brand/Orby.svelte';
	import type { PageData } from './$types';
	import { party } from '$lib/parties';
	import { allForecastYears, getJurisdiction } from '$lib/jurisdictions';

	let { data }: { data: PageData } = $props();
	const ADJECTIVES: Record<string, string> = { Victoria: 'Victorian', 'New South Wales': 'NSW', Queensland: 'Queensland', 'South Australia': 'SA', 'Western Australia': 'WA' };
	const adjective = (name: string) => ADJECTIVES[name] ?? name.toLowerCase();
	const pct = (p: number) => `${Math.round(p * 100)}%`;
	const signed = (v: number | null) => (v == null ? '–' : `${v > 0 ? '+' : ''}${v.toFixed(1)}`);
	// Earlier backtests are scored here without a forecast page of their own.
	const hasPage = (code: string, year: string) => {
		const j = getJurisdiction(code);
		return !!j && allForecastYears(j).includes(Number(year));
	};
</script>

<svelte:head>
	<title>Methodology · {SITE_NAME}</title>
</svelte:head>

<div class="intro">
	<div>
		<p class="eyebrow">How it works</p>
		<h1>Methodology</h1>
		<p class="lede">
			The model has three layers, each checked against past Victorian, NSW, Queensland and federal elections. Everything below is
			reproducible from the open pipeline. Like Orby, it holds up odds, never certainties.
		</p>
	</div>
	<Orby size={170} />
</div>

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
		month's poll average missed the result at past elections in the same jurisdiction, with heavy tails, and corrects
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
	<p>
		New South Wales uses optional preferential voting: a voter need only number one box, so many
		ballots exhaust instead of reaching the final two. The NSW model treats exhausting as one more
		choice at every exclusion, estimated from the NSW Electoral Commission's distributions; it becomes
		likelier as fewer candidates remain. NSW redraws its boundaries between elections, so the previous
		result is first re-cut onto the new districts, polling place by polling place, with pre-poll,
		postal and other declaration votes following each old district's polling-place votes.
	</p>
	<p>
		Queensland has used full preferential voting since 2016, and its 2020 and 2024 elections were held on
		the same boundaries, so its seats start directly from the previous result. Katter's Australian Party
		members are modelled like independents: their vote is largely personal.
	</p>
</div>

{#each data.models as { code, name, model } (name)}
<h2>{name}</h2>
{#if model?.poll_error.length}
	<h3 class="jur">How far have {adjective(name)} polls missed?</h3>
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
	<h3 class="jur">Backtest: forecasting the {year} {adjective(name)} election blind</h3>
	<p class="prose">
		Using only what was known before polling day (the previous result, that cycle's polls, and polling
		error from earlier elections), the model gave Labor a majority a
		<strong>{pct(b.outcome.alp_majority)}</strong> chance and a hung parliament {pct(b.outcome.hung)}. Its favourite
		won {Math.round(b.favourite_accuracy * b.n_seats)} of {b.n_seats} seats (Brier score {b.brier.toFixed(3)});
		simply assuming every seat stays with its holder would have got {Math.round(b.status_quo_accuracy * b.n_seats)}
		right.
	</p>
	{#if hasPage(code, year)}
		<p class="prose">
			<a href="/{code}/forecast/{year}/">The {year} forecast</a> ·
			<a href="/{code}/forecast/{year}/vs-result/">Forecast against the result: seats, vote, calibration and every miss →</a>
		</p>
	{/if}
{/each}
{/each}

<style>
	.intro {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 2rem;
		margin-bottom: 1rem;
	}
	@media (max-width: 40rem) {
		.intro :global(.orby) {
			display: none;
		}
	}
	h3.jur {
		font-family: var(--font-display);
		font-size: 1.3rem;
		margin-top: 2rem;
	}
	.prose {
		max-width: 44rem;
	}
	.narrow {
		max-width: 36rem;
	}
	h3 {
		margin-top: 1.25rem;
		font-family: var(--font-sans);
		font-size: 1rem;
	}
</style>
