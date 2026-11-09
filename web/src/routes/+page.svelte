<script lang="ts">
	import { SITE_NAME, SITE_STRAPLINE, SITE_TAGLINE } from '$lib/site';
	import Orby from '$lib/components/brand/Orby.svelte';
	import { JURISDICTIONS, isActive } from '$lib/jurisdictions';
	import { daysUntil, fmtDate } from '$lib/format';
</script>

<svelte:head>
	<title>{SITE_NAME} · {SITE_TAGLINE}</title>
</svelte:head>

<section class="hero">
	<div class="copy">
		<p class="eyebrow">Australian elections, seat by seat</p>
		<h1>{SITE_STRAPLINE}.</h1>
		<p class="lede">
			{SITE_NAME} combines every published poll with historical results and preference flows in a
			Bayesian model, simulating each seat thousands of times. It gives odds, never certainties. The
			first live forecast is the Victorian state election on <strong>28 November 2026</strong>.
		</p>
		<p class="actions">
			<a class="button" href="/vic/forecast/2026/">Victoria 2026 forecast →</a>
			<a class="text-link" href="/methodology/">How it works</a>
		</p>
	</div>
	<div class="art">
		<Orby size={240} card="odds" label="Orby, the Crystal Ballot mascot: a crystal ball riding in a ballot box, holding up a card that says odds" />
	</div>
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
		display: grid;
		grid-template-columns: minmax(0, 1fr) auto;
		align-items: center;
		gap: 2rem;
		padding: 2.25rem 2.5rem;
		margin-bottom: 1rem;
		background:
			radial-gradient(circle at 85% 40%, color-mix(in srgb, var(--brand-glass) 70%, transparent) 0 30%, transparent 60%),
			var(--surface);
		border: 1px solid var(--rule);
		border-radius: var(--radius-lg);
		box-shadow: var(--shadow);
	}
	.hero h1 {
		max-width: 22ch;
	}
	.actions {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 1rem;
		margin-top: 1.5rem;
	}
	.text-link {
		font-weight: 600;
		color: var(--fg-2);
	}
	@media (max-width: 44rem) {
		.hero {
			grid-template-columns: 1fr;
			padding: 1.5rem 1.25rem;
		}
		.art {
			justify-self: center;
			order: -1;
			width: 160px;
		}
	}
	.grid {
		list-style: none;
		padding: 0;
		margin: 0;
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(15rem, 1fr));
		gap: 0.9rem;
	}
	.grid a {
		display: flex;
		flex-direction: column;
		gap: 0.15rem;
		height: 100%;
		padding: 1.1rem 1.25rem;
		border: 1px solid var(--rule);
		border-radius: var(--radius-md);
		background: var(--surface);
		text-decoration: none;
		transition:
			transform 0.15s ease,
			box-shadow 0.15s ease,
			border-color 0.15s ease;
	}
	.grid li:not(.inactive) a:hover {
		border-color: var(--rule-strong);
		box-shadow: var(--shadow);
		transform: translateY(-2px);
	}
	.grid .inactive a {
		background: transparent;
		border-style: dashed;
	}
	.grid strong {
		font-family: var(--font-display);
		font-weight: 750;
		font-size: 1.15rem;
	}
	.next {
		margin-top: 0.5rem;
		font-weight: 600;
		color: var(--fg);
	}
	@media (prefers-reduced-motion: reduce) {
		.grid a {
			transition: none;
		}
		.grid li:not(.inactive) a:hover {
			transform: none;
		}
	}
</style>
