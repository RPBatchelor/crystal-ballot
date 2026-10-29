<script lang="ts">
	import '../app.css';
	import { page } from '$app/state';
	import { JURISDICTIONS, getJurisdiction, isActive } from '$lib/jurisdictions';

	let { children } = $props();

	const current = $derived(getJurisdiction(page.params.jur ?? ''));
	const path = $derived(page.url.pathname);

	const sections = $derived(
		current
			? [
					{ href: `/${current.code}/`, label: 'Overview' },
					// Live forecasts; with none, the latest retrospective forecast.
					...(current.forecastYears?.length ? current.forecastYears : (current.retroYears ?? []).slice(-1)).map(
						(y) => ({ href: `/${current.code}/forecast/${y}/`, label: `${y} forecast` })
					),
					...(current.hasPolls ? [{ href: `/${current.code}/polls/`, label: 'Polls' }] : []),
					...(current.resultYears.length
						? [{ href: `/${current.code}/results/${current.resultYears.at(-1)}/`, label: 'Results', prefix: `/${current.code}/results/` }]
						: [])
				]
			: []
	);
</script>

<svelte:head>
	<title>Prophecy · Australian election forecasts</title>
	<meta
		name="description"
		content="Bayesian seat-by-seat forecasts, polling and results for Australian elections."
	/>
</svelte:head>

<a class="skip" href="#main">Skip to content</a>

<header class="site">
	<div class="bar">
		<a href="/" class="brand" aria-label="Prophecy home">
			<span class="mark" aria-hidden="true"></span>Prophecy
		</a>
		<a href="/methodology/" class="meta-link">Methodology</a>
	</div>
	<nav class="jurisdictions" aria-label="Jurisdiction">
		{#each JURISDICTIONS as j (j.code)}
			<a
				href="/{j.code}/"
				class:active={current?.code === j.code}
				class:inactive={!isActive(j)}
				aria-current={current?.code === j.code ? 'page' : undefined}>{j.short}</a
			>
		{/each}
	</nav>
	{#if sections.length > 1}
		<nav class="sections" aria-label="{current?.name} sections">
			{#each sections as s (s.href)}
				<a href={s.href} aria-current={path === s.href || ('prefix' in s && path.startsWith(s.prefix as string)) ? 'page' : undefined}>{s.label}</a>
			{/each}
		</nav>
	{/if}
</header>

<main id="main">
	{@render children()}
</main>

<footer>
	<p>
		Prophecy is an independent, non-partisan forecasting project. Results data from the Victorian
		Electoral Commission and the Australian Electoral Commission; polls from published pollster
		releases.
	</p>
</footer>

<style>
	.skip {
		position: absolute;
		left: -999px;
	}
	.skip:focus {
		left: 1rem;
		top: 1rem;
		background: var(--surface);
		padding: 0.5rem 1rem;
		z-index: 10;
	}
	header.site {
		border-bottom: 1px solid var(--rule);
		background: var(--bg);
		position: sticky;
		top: 0;
		z-index: 5;
	}
	.bar,
	nav {
		max-width: 72rem;
		margin: 0 auto;
		padding: 0 var(--gutter);
	}
	.bar {
		display: flex;
		align-items: center;
		justify-content: space-between;
		height: 3.25rem;
	}
	.brand {
		font-family: var(--font-serif);
		font-weight: 700;
		font-size: 1.35rem;
		text-decoration: none;
		display: flex;
		align-items: center;
		gap: 0.5rem;
	}
	.mark {
		width: 0.9rem;
		height: 0.9rem;
		border-radius: 50%;
		background: conic-gradient(var(--party-ALP) 0 50%, var(--party-COAL) 50% 100%);
	}
	.meta-link {
		font-size: 0.9rem;
		color: var(--fg-2);
		text-decoration: none;
	}
	nav {
		display: flex;
		gap: 0.25rem;
		overflow-x: auto;
		scrollbar-width: none;
	}
	nav a {
		flex: none;
		font-size: 0.85rem;
		font-weight: 550;
		text-decoration: none;
		padding: 0.45rem 0.7rem;
		border-bottom: 2px solid transparent;
		color: var(--fg-2);
	}
	nav a.inactive {
		color: var(--muted);
		font-weight: 450;
	}
	nav a[aria-current='page'] {
		color: var(--fg);
		border-bottom-color: var(--fg);
	}
	.sections {
		border-top: 1px solid var(--rule);
	}
	main {
		max-width: 72rem;
		margin: 0 auto;
		padding: 1.75rem var(--gutter) 3rem;
	}
	footer {
		border-top: 1px solid var(--rule);
		color: var(--muted);
		font-size: 0.85rem;
	}
	footer p {
		max-width: 72rem;
		margin: 0 auto;
		padding: 1.25rem var(--gutter) 2rem;
	}
</style>
