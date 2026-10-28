<script lang="ts">
	import type { CandidateResult } from '$lib/types';
	import { partyColour, partyLabel } from '$lib/parties';
	import { displayName, fmtInt } from '$lib/format';

	interface Props {
		candidates: CandidateResult[];
		/** Scale bars to this max % (keeps related charts comparable). */
		max?: number;
		winner?: string;
	}
	let { candidates, max, winner }: Props = $props();
	const top = $derived(max ?? Math.max(...candidates.map((c) => c.pct)));
</script>

<ul class="bars">
	{#each candidates as c (c.candidate)}
		<li>
			<div class="who">
				<span class="name">
					{displayName(c.candidate)}
					{#if c.candidate === winner}<span class="won">✓ elected</span>{/if}
				</span>
				<span class="party muted">{partyLabel(c.party, c.party_name)}</span>
			</div>
			<div class="track" aria-hidden="true">
				<span class="fill" style:width="{(100 * c.pct) / top}%" style:background={partyColour(c.party)}
				></span>
			</div>
			<div class="val num">
				<strong>{c.pct.toFixed(1)}%</strong>
				<span class="muted small">{fmtInt(c.votes)}</span>
			</div>
		</li>
	{/each}
</ul>

<style>
	.bars {
		list-style: none;
		padding: 0;
		margin: 0;
		display: grid;
		gap: 0.55rem;
	}
	li {
		display: grid;
		grid-template-columns: minmax(9rem, 15rem) 1fr 5.5rem;
		gap: 0.75rem;
		align-items: center;
	}
	@media (max-width: 560px) {
		li {
			grid-template-columns: 1fr 4.5rem;
		}
		.track {
			grid-column: 1 / -1;
			grid-row: 2;
		}
	}
	.who {
		display: flex;
		flex-direction: column;
		line-height: 1.25;
		min-width: 0;
	}
	.name {
		font-weight: 550;
		font-size: 0.92rem;
	}
	.won {
		font-weight: 600;
		font-size: 0.78rem;
		color: var(--fg-2);
	}
	.party {
		font-size: 0.78rem;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}
	.track {
		height: 0.85rem;
	}
	.fill {
		display: block;
		height: 100%;
		min-width: 2px;
		border-radius: 0 4px 4px 0;
	}
	.val {
		text-align: right;
		display: flex;
		flex-direction: column;
		line-height: 1.2;
	}
</style>
