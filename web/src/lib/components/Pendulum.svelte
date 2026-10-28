<script lang="ts">
	import type { SeatResult } from '$lib/types';
	import { bloc, party, partyColour } from '$lib/parties';

	interface Props {
		seats: SeatResult[];
		/** Party bloc forming government (left column). */
		government: string;
		base: string; // link base, e.g. /vic/results/2022
	}
	let { seats, government, base }: Props = $props();

	// AEC classification of two-candidate margins.
	const BANDS = [
		{ key: 'marginal', label: 'Marginal', sub: 'under 6%', max: 6 },
		{ key: 'fairly', label: 'Fairly safe', sub: '6–10%', max: 10 },
		{ key: 'safe', label: 'Safe', sub: 'over 10%', max: Infinity }
	];
	const maxMargin = 25;

	const columns = $derived.by(() => {
		const gov = seats.filter((s) => bloc(s.party) === government);
		const opp = seats.filter((s) => bloc(s.party) !== government && bloc(s.party) === 'COAL');
		const cross = seats.filter((s) => bloc(s.party) !== government && bloc(s.party) !== 'COAL');
		const banded = (list: SeatResult[]) =>
			BANDS.map((b, i) => ({
				...b,
				seats: list
					.filter((s) => s.margin < b.max && s.margin >= (i ? BANDS[i - 1].max : 0))
					.sort((a, z) => a.margin - z.margin)
			}));
		return [
			{ title: `${party(government).short} government`, count: gov.length, bands: banded(gov) },
			{ title: 'Coalition opposition', count: opp.length, bands: banded(opp) },
			{ title: 'Crossbench', count: cross.length, bands: banded(cross) }
		].filter((c) => c.count > 0);
	});
</script>

<div class="pendulum">
	{#each columns as col (col.title)}
		<section>
			<h3>{col.title} <span class="muted num">{col.count}</span></h3>
			{#each col.bands as band (band.key)}
				{#if band.seats.length}
					<h4>{band.label} <span class="muted">{band.sub}</span></h4>
					<ol>
						{#each band.seats as s (s.slug)}
							<li>
								<a href="{base}/{s.slug}/">
									<span class="name">{s.name}</span>
									<span class="vs muted">
										{#if !s.classic}v {party(s.runner_up_party).short}{/if}
									</span>
									<span class="bar-wrap" aria-hidden="true">
										<span
											class="bar"
											style:width="{Math.min(100, (100 * s.margin) / maxMargin)}%"
											style:background={partyColour(s.party)}
										></span>
									</span>
									<span class="m num">{s.margin.toFixed(1)}</span>
								</a>
							</li>
						{/each}
					</ol>
				{/if}
			{/each}
		</section>
	{/each}
</div>

<style>
	.pendulum {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(17rem, 1fr));
		gap: 1.5rem 2rem;
	}
	h3 {
		font-size: 1rem;
		font-family: var(--font-sans);
		font-weight: 650;
		border-bottom: 2px solid var(--fg);
		padding-bottom: 0.35rem;
	}
	h4 {
		font-size: 0.75rem;
		font-weight: 600;
		text-transform: uppercase;
		letter-spacing: 0.05em;
		margin: 1rem 0 0.25rem;
	}
	ol {
		list-style: none;
		margin: 0;
		padding: 0;
	}
	a {
		display: grid;
		grid-template-columns: minmax(0, 1fr) auto 4.5rem 2.6rem;
		align-items: center;
		gap: 0.5rem;
		padding: 0.22rem 0.25rem;
		font-size: 0.875rem;
		text-decoration: none;
		border-radius: 4px;
	}
	a:hover {
		background: var(--rule);
	}
	.name {
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}
	.vs {
		font-size: 0.75rem;
	}
	.bar-wrap {
		height: 0.5rem;
	}
	.bar {
		display: block;
		height: 100%;
		border-radius: 0 3px 3px 0;
	}
	.m {
		text-align: right;
		color: var(--fg-2);
	}
</style>
