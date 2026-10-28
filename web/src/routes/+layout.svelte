<script lang="ts">
	let { children } = $props();
</script>

<svelte:head>
	<title>Prophecy</title>
</svelte:head>

<header>
	<a href="/" class="brand">Prophecy</a>
	<nav>
		<a href="/vic/2026/polls/">Victoria 2026 · Polls</a>
	</nav>
</header>

<main>
	{@render children()}
</main>

<style>
	:global(:root) {
		--bg: #fbfaf7;
		--fg: #1d1d1f;
		--muted: #6b6b70;
		--rule: #e3e1dc;
		--alp: #d7262c;
		--coal: #1c4fa1;
		--grn: #2e8b3e;
		--onp: #e8731c;
		--oth: #8a8a8a;
		color-scheme: light dark;
	}
	@media (prefers-color-scheme: dark) {
		:global(:root) {
			--bg: #141416;
			--fg: #ececee;
			--muted: #9a9aa2;
			--rule: #2c2c31;
			--alp: #ff5a5f;
			--coal: #5b8cff;
			--grn: #4cc35e;
			--onp: #ff9440;
		}
	}
	:global(body) {
		margin: 0;
		background: var(--bg);
		color: var(--fg);
		font-family: system-ui, -apple-system, 'Segoe UI', sans-serif;
		line-height: 1.5;
	}
	header {
		display: flex;
		gap: 1.5rem;
		align-items: baseline;
		padding: 1rem;
		border-bottom: 1px solid var(--rule);
	}
	.brand {
		font-weight: 700;
		font-size: 1.25rem;
		color: inherit;
		text-decoration: none;
	}
	nav a {
		color: var(--muted);
	}
	main {
		max-width: 72rem;
		margin: 0 auto;
		padding: 1rem;
	}
</style>
