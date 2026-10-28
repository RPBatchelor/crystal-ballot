<script lang="ts">
	import { JURISDICTIONS, isActive } from '$lib/jurisdictions';
	import { daysUntil, fmtDate } from '$lib/format';
</script>

<svelte:head>
	<title>Prophecy · Australian election forecasts</title>
</svelte:head>

<section class="hero">
	<p class="eyebrow">Australian elections, seat by seat</p>
	<h1>Forecasts built from polls, results and uncertainty.</h1>
	<p class="lede">
		Prophecy combines every published poll with historical results and preference flows in a
		Bayesian model, simulating each seat thousands of times. The first live forecast is the
		Victorian state election on <strong>28 November 2026</strong>.
	</p>
	<p><a class="cta" href="/vic/">Victoria 2026 →</a></p>
</section>

<h2>Jurisdictions</h2>
<ul class="grid">
	{#each JURISDICTIONS as j (j.code)}
		<li class:inactive={!isActive(j)}>
			<a href="/{j.code}/">
				<span class="eyebrow">{j.kind}</span>
				<strong>{j.name}</strong>
				<span class="muted small">{j.chamber} · {j.seats} seats</span>
				{#if j.nextElection}
					<span class="next small">
						Next election {fmtDate(j.nextElection)}
						{#if daysUntil(j.nextElection) > 0}· {daysUntil(j.nextElection)} days{/if}
					</span>
				{/if}
				{#if !isActive(j)}<span class="muted small">Coming later</span>{/if}
			</a>
		</li>
	{/each}
</ul>

<style>
	.hero {
		padding: 1.5rem 0 1rem;
		max-width: 50rem;
	}
	.cta {
		display: inline-block;
		font-weight: 600;
		background: var(--fg);
		color: var(--bg);
		padding: 0.55rem 1rem;
		border-radius: var(--radius);
		text-decoration: none;
	}
	.grid {
		list-style: none;
		padding: 0;
		margin: 0;
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(15rem, 1fr));
		gap: 0.75rem;
	}
	.grid a {
		display: flex;
		flex-direction: column;
		gap: 0.15rem;
		height: 100%;
		padding: 1rem 1.1rem;
		border: 1px solid var(--rule);
		border-radius: var(--radius);
		background: var(--surface);
		text-decoration: none;
	}
	.grid a:hover {
		border-color: var(--rule-strong);
	}
	.grid .inactive a {
		background: transparent;
	}
	.grid strong {
		font-size: 1.05rem;
	}
	.next {
		margin-top: 0.4rem;
		font-weight: 550;
	}
</style>
