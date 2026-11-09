<script lang="ts">
	import { ABOUT_URL, SITE_NAME, SITE_STRAPLINE, SITE_TAGLINE } from '$lib/site';
	import BrandMark from '$lib/components/brand/BrandMark.svelte';
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
	<title>{SITE_NAME} · {SITE_TAGLINE}</title>
	<meta
		name="description"
		content="Bayesian seat-by-seat forecasts, polling and results for Australian elections."
	/>
</svelte:head>

<a class="skip" href="#main">Skip to content</a>

<header class="site">
	<div class="bar">
		<a href="/" class="brand" aria-label="{SITE_NAME} home">
			<BrandMark size={34} variant="small" />{SITE_NAME}
		</a>
		<nav class="meta" aria-label="About this site">
			<a href="/methodology/" aria-current={path.startsWith('/methodology/') ? 'page' : undefined}>Methodology</a>
			<a href={ABOUT_URL} target="_blank" rel="noopener noreferrer">About<span class="ext" aria-hidden="true">↗</span><span class="visually-hidden"> (GitHub, opens in a new tab)</span></a>
		</nav>
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
	<div class="foot-brand">
		<BrandMark size={44} variant="icon" />
		<div>
			<strong>{SITE_NAME}</strong>
			<span>{SITE_STRAPLINE}</span>
		</div>
	</div>
	<p>
		{SITE_NAME} is an independent, non-partisan forecasting project. Results data from the Victorian
		Electoral Commission, the NSW Electoral Commission, the Electoral Commission of Queensland, the
		Electoral Commission of South Australia and the Australian Electoral Commission; polls from published
		pollster releases. <a href="/methodology/">Methodology</a> · <a href={ABOUT_URL} target="_blank" rel="noopener noreferrer">About</a>
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
		border-radius: var(--radius);
		z-index: 10;
	}
	header.site {
		background: color-mix(in srgb, var(--bg) 88%, transparent);
		backdrop-filter: blur(10px);
		-webkit-backdrop-filter: blur(10px);
		border-bottom: 1px solid var(--rule);
		position: sticky;
		top: 0;
		z-index: 5;
	}
	.bar,
	nav.jurisdictions,
	nav.sections {
		max-width: 72rem;
		margin: 0 auto;
		padding: 0 var(--gutter);
	}
	.bar {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 1rem;
		height: 3.75rem;
	}
	.brand {
		font-family: var(--font-display);
		font-weight: 800;
		font-size: 1.4rem;
		letter-spacing: -0.02em;
		text-decoration: none;
		display: flex;
		align-items: center;
		gap: 0.55rem;
		color: var(--fg);
		white-space: nowrap;
	}
	.meta {
		display: flex;
		gap: 0.25rem;
	}
	.meta a {
		font-size: 0.9rem;
		font-weight: 600;
		color: var(--fg-2);
		text-decoration: none;
		padding: 0.4rem 0.8rem;
		border-radius: 999px;
	}
	.meta a:hover {
		background: var(--rule);
		color: var(--fg);
	}
	.meta a[aria-current='page'] {
		background: var(--accent);
		color: var(--on-accent);
	}
	.ext {
		font-size: 0.75em;
		margin-left: 0.2em;
		opacity: 0.7;
	}
	nav.jurisdictions,
	nav.sections {
		display: flex;
		gap: 0.3rem;
		overflow-x: auto;
		scrollbar-width: none;
	}
	nav.jurisdictions {
		padding-bottom: 0.6rem;
	}
	nav.jurisdictions a {
		flex: none;
		font-size: 0.85rem;
		font-weight: 650;
		text-decoration: none;
		padding: 0.3rem 0.85rem;
		border-radius: 999px;
		border: 1px solid var(--rule);
		background: var(--surface);
		color: var(--fg-2);
	}
	nav.jurisdictions a:hover {
		border-color: var(--rule-strong);
		color: var(--fg);
	}
	nav.jurisdictions a.inactive {
		color: var(--muted);
		font-weight: 500;
		background: transparent;
	}
	nav.jurisdictions a[aria-current='page'] {
		background: var(--accent);
		border-color: var(--accent);
		color: var(--on-accent);
	}
	nav.sections {
		border-top: 1px solid var(--rule);
	}
	nav.sections a {
		flex: none;
		font-size: 0.88rem;
		font-weight: 600;
		text-decoration: none;
		padding: 0.6rem 0.75rem 0.5rem;
		border-bottom: 3px solid transparent;
		color: var(--fg-2);
	}
	nav.sections a:hover {
		color: var(--fg);
	}
	nav.sections a[aria-current='page'] {
		color: var(--fg);
		border-bottom-color: var(--brand-spark);
	}
	main {
		flex: 1 0 auto;
		width: 100%;
		max-width: 72rem;
		margin: 0 auto;
		padding: 2rem var(--gutter) 3.5rem;
	}
	footer {
		background: var(--brand-night);
		color: #c9c5f2;
		font-size: 0.85rem;
		margin-top: 2rem;
	}
	footer > * {
		max-width: 72rem;
		margin: 0 auto;
		padding-left: var(--gutter);
		padding-right: var(--gutter);
	}
	.foot-brand {
		display: flex;
		align-items: center;
		gap: 0.75rem;
		padding-top: 2rem;
		--brand-box: #3d3890;
		--brand-lid: #5149b5;
	}
	.foot-brand strong {
		display: block;
		font-family: var(--font-display);
		font-weight: 800;
		font-size: 1.2rem;
		color: #ffffff;
	}
	footer p {
		padding-top: 1rem;
		padding-bottom: 2.25rem;
		max-width: 72rem;
	}
	footer a {
		color: #ffffff;
		text-decoration-color: rgb(255 255 255 / 0.4);
	}
	@media (max-width: 40rem) {
		.bar {
			gap: 0.5rem;
		}
		.brand {
			font-size: 1.15rem;
			gap: 0.4rem;
		}
		.meta a {
			font-size: 0.82rem;
			padding: 0.35rem 0.5rem;
		}
	}
</style>
