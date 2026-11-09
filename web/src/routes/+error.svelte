<script lang="ts">
	import { page } from '$app/state';
	import { SITE_NAME } from '$lib/site';
	import Orby from '$lib/components/brand/Orby.svelte';
</script>

<svelte:head>
	<title>{page.status === 404 ? 'Not found' : 'Error'} · {SITE_NAME}</title>
</svelte:head>

<section class="empty">
	<Orby size={180} card="?" label="Orby, the Crystal Ballot mascot, holding up a card with a question mark" />
	<p class="eyebrow">{page.status}</p>
	<h1>{page.status === 404 ? "Orby can't see this page" : 'Something went wrong'}</h1>
	<p class="lede">
		{page.status === 404
			? 'It may have moved, or the forecast it belongs to has not been published yet.'
			: (page.error?.message ?? 'Please try again.')}
	</p>
	<p><a class="button" href="/">Back to the forecasts</a></p>
</section>

<style>
	.empty {
		display: flex;
		flex-direction: column;
		align-items: center;
		text-align: center;
		padding: 2rem 0 1rem;
	}
	.empty .eyebrow {
		margin-top: 1rem;
	}
	.empty .lede {
		margin-left: auto;
		margin-right: auto;
	}
</style>
