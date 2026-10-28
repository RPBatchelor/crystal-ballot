<svelte:head>
	<title>Methodology · Prophecy</title>
</svelte:head>

<p class="eyebrow">How it works</p>
<h1>Methodology</h1>
<p class="lede">
	The full methodology will be published with the first forecast. In outline, the model has three
	layers, each calibrated against past Australian elections.
</p>

<div class="prose">
	<h2>1. Poll aggregation</h2>
	<p>
		A Bayesian state-space model tracks each party's primary vote day by day since the last election,
		estimating every pollster's systematic lean ("house effect") and the noise in each poll. Two-party
		preferred figures reported by pollsters are used as a separate, linked observation.
	</p>

	<h2>2. Election-day uncertainty</h2>
	<p>
		Polls in Australia have missed by several points before; Victoria 2018 is the textbook case. The
		forecast adds a polling-error term sized from how far final poll averages have missed actual
		results at past state and federal elections, with heavy tails for the occasional large miss.
	</p>

	<h2>3. Seats</h2>
	<p>
		Each seat starts from its last result. Statewide swings are applied with seat-specific
		sensitivity, correlated regional swings, local factors (retiring members, by-elections,
		independents) and seat-level noise. Every candidate's primary vote is simulated, then preferences
		are distributed exactly as in a real count, using flows estimated from the electoral commission's
		full preference distributions. That lets Greens-versus-Labor, Liberal-versus-Nationals and
		independent contests work properly.
	</p>
	<p>
		Simulating the whole election tens of thousands of times gives each seat's chance of each outcome,
		and the chance of each party governing.
	</p>
</div>

<style>
	.prose {
		max-width: 44rem;
	}
</style>
