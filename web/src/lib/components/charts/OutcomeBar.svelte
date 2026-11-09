<script lang="ts" module>
	const barHeight = 40; // px, matches .bar height (2.5rem)
</script>

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

	// The hung-parliament label sits under the middle of its own segment, nudged only as far
	// as it must be to clear the Labor and Coalition labels; a leader line links the two.
	const total = $derived(alpMajority + hung + coalMajority || 1);
	const centrePct = $derived((100 * (alpMajority + hung / 2)) / total);

	let figure: HTMLElement | undefined = $state();
	let hungSeg: HTMLElement | undefined = $state();
	let hungLab: HTMLElement | undefined = $state();
	let alpLab: HTMLElement | undefined = $state();
	let coalLab: HTMLElement | undefined = $state();
	// Measured placement of the hung label: x of its centre (px) or a row of its own.
	let hungX = $state<number | null>(null);
	let stacked = $state(false);
	let width = $state(0);
	let labWidth = $state(0);
	let leader = $state<{ x1: number; x2: number; y2: number } | null>(null);

	const GAP = 16; // px kept clear between labels

	$effect(() => {
		// Re-measure whenever the layout can change.
		void width;
		void labWidth;
		void centrePct;
		if (!figure || !hungSeg || !hungLab || !alpLab || !coalLab) {
			leader = null;
			return;
		}
		const f = figure.getBoundingClientRect();
		const s = hungSeg.getBoundingClientRect();
		const centre = s.left + s.width / 2 - f.left;
		const half = hungLab.offsetWidth / 2;
		const lo = alpLab.offsetWidth + GAP + half;
		const hi = f.width - coalLab.offsetWidth - GAP - half;
		stacked = lo > hi;
		hungX = stacked
			? Math.min(Math.max(centre, half), f.width - half)
			: Math.min(Math.max(centre, lo), hi);
		// Wait for the new position to apply before measuring where the label ended up.
		requestAnimationFrame(() => {
			if (!hungLab || !figure) return;
			const l = hungLab.getBoundingClientRect();
			const g = figure.getBoundingClientRect();
			leader = { x1: centre, x2: l.left + l.width / 2 - g.left, y2: l.top - g.top };
		});
	});
</script>

<figure class="outcome" bind:this={figure} bind:clientWidth={width}>
	<div
		class="bar"
		role="img"
		aria-label={segs.map((s) => `${s.label} ${inHundred(s.p)} in 100`).join(', ')}
	>
		{#each segs as s (s.key)}
			{#if s.p > 0}
				{#if s.key === 'hung'}
					<span bind:this={hungSeg} style:flex-grow={s.p} style:background={s.colour}></span>
				{:else}
					<span style:flex-grow={s.p} style:background={s.colour}></span>
				{/if}
			{/if}
		{/each}
	</div>
	{#if leader && hung > 0}
		<svg class="leader" aria-hidden="true" width={width} height={leader.y2}>
			<path
				d="M{leader.x1} {barHeight} V{barHeight + 6} H{leader.x2} V{leader.y2 - 3}"
				fill="none"
				stroke="var(--muted)"
				stroke-width="1.25"
			/>
			<circle cx={leader.x1} cy={barHeight} r="2.5" fill="var(--muted)" />
		</svg>
	{/if}
	<div class="labels" class:stacked style:--centre="{centrePct}%" style:--hung-x={hungX == null ? undefined : `${hungX}px`}>
		{#each segs as s (s.key)}
			{#if s.key === 'hung'}
				<div class="lab hung" bind:this={hungLab} bind:clientWidth={labWidth}>
					<strong class="num">{inHundred(s.p)}<small> in 100</small></strong>
					<span><i style:background={s.colour}></i>{s.label}</span>
				</div>
			{:else if s.key === 'alp'}
				<div class="lab alp" bind:this={alpLab}>
					<strong class="num">{inHundred(s.p)}<small> in 100</small></strong>
					<span><i style:background={s.colour}></i>{s.label}</span>
				</div>
			{:else}
				<div class="lab {s.key}" bind:this={coalLab}>
					<strong class="num">{inHundred(s.p)}<small> in 100</small></strong>
					<span><i style:background={s.colour}></i>{s.label}</span>
				</div>
			{/if}
		{/each}
	</div>
</figure>

<style>
	.outcome {
		margin: 0;
		position: relative;
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
	.leader {
		position: absolute;
		top: 0;
		left: 0;
		overflow: visible;
		pointer-events: none;
	}
	/* Labor and Coalition at the ends; the hung label under the centre of its segment,
	   kept clear of both (about 11rem each side). */
	.labels {
		position: relative;
		display: flex;
		justify-content: space-between;
		gap: 1rem;
		margin-top: 1.1rem;
	}
	.lab {
		display: flex;
		flex-direction: column;
		flex: none;
		line-height: 1.2;
		/* Natural widths: the hung label's placement is measured from them. */
		white-space: nowrap;
	}
	.lab.hung {
		position: absolute;
		top: 0;
		/* Measured in the browser; without JS, a conservative estimate. */
		left: var(--hung-x, clamp(14rem, var(--centre), calc(100% - 14rem)));
		transform: translateX(-50%);
		text-align: center;
		align-items: center;
		white-space: nowrap;
	}
	.lab.coal {
		text-align: right;
		align-items: flex-end;
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
		display: inline-flex;
		align-items: center;
		gap: 0.35rem;
	}
	.lab i {
		width: 0.65rem;
		height: 0.65rem;
		border-radius: 2px;
		flex: none;
	}
	/* No room for three labels in a row: the hung label drops to its own line. */
	.labels.stacked {
		flex-wrap: wrap;
		row-gap: 1rem;
	}
	.labels.stacked .lab.hung {
		position: relative;
		order: 3;
		flex-basis: 100%;
		align-items: flex-start;
		left: 0;
		transform: none;
		padding-left: max(0px, calc(var(--hung-x, 50%) - 4.5rem));
	}
	.labels.stacked .lab.coal {
		order: 2;
	}
	@media (max-width: 34rem) {
		.labels:not(.stacked) .lab.hung {
			/* Before measurement on narrow screens. */
			position: relative;
		}
	}
</style>
