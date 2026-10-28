<script lang="ts">
	import { partyColour } from '$lib/parties';

	interface Props {
		alpMajority: number;
		hung: number;
		coalMajority: number;
	}
	let { alpMajority, hung, coalMajority }: Props = $props();

	const segs = $derived([
		{ key: 'alp', label: 'Labor majority', p: alpMajority, colour: partyColour('ALP') },
		{ key: 'hung', label: 'Hung parliament', p: hung, colour: 'var(--rule-strong)' },
		{ key: 'coal', label: 'Coalition majority', p: coalMajority, colour: partyColour('COAL') }
	]);
	const inHundred = (p: number) => (p < 0.01 ? '<1' : p > 0.99 ? '>99' : Math.round(p * 100).toString());
</script>

<figure class="outcome">
	<div
		class="bar"
		role="img"
		aria-label={segs.map((s) => `${s.label} ${inHundred(s.p)} in 100`).join(', ')}
	>
		{#each segs as s (s.key)}
			{#if s.p > 0}
				<span style:flex-grow={s.p} style:background={s.colour}></span>
			{/if}
		{/each}
	</div>
	<div class="labels">
		{#each segs as s (s.key)}
			<div class="lab {s.key}">
				<strong class="num">{inHundred(s.p)}<small> in 100</small></strong>
				<span>{s.label}</span>
			</div>
		{/each}
	</div>
</figure>

<style>
	.outcome {
		margin: 0;
	}
	.bar {
		display: flex;
		gap: 2px;
		height: 2.5rem;
	}
	.bar span {
		flex-basis: 0;
		min-width: 3px;
	}
	.bar span:first-child {
		border-radius: 4px 0 0 4px;
	}
	.bar span:last-child {
		border-radius: 0 4px 4px 0;
	}
	.labels {
		display: grid;
		grid-template-columns: 1fr 1fr 1fr;
		margin-top: 0.6rem;
		gap: 1rem;
	}
	.lab {
		display: flex;
		flex-direction: column;
		line-height: 1.2;
	}
	.lab.hung {
		text-align: center;
	}
	.lab.coal {
		text-align: right;
	}
	.lab strong {
		font-size: clamp(1.4rem, 4vw, 2rem);
		font-weight: 700;
	}
	.lab small {
		font-size: 0.8rem;
		font-weight: 500;
		color: var(--muted);
	}
	.lab span {
		font-size: 0.85rem;
		color: var(--fg-2);
	}
</style>
