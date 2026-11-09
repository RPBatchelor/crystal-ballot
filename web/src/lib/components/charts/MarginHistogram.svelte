<!--
	How big a win: Coalition seats minus Labor seats across every simulation. Left of zero
	Labor wins more seats, right of zero the Coalition does; an optional line marks the result.
-->
<script lang="ts">
	import { partyColour } from '$lib/parties';

	interface Props {
		margin: { min: number; counts: number[] };
		/** Actual Coalition-minus-Labor margin, for past elections. */
		actual?: number | null;
		actualLabel?: string;
	}
	let { margin, actual = null, actualLabel = 'Result' }: Props = $props();

	let width = $state(640);
	const height = 230;
	const m = { top: 22, right: 12, bottom: 44, left: 12 };
	const total = $derived(margin.counts.reduce((a, b) => a + b, 0));
	const peak = $derived(Math.max(...margin.counts));
	const maxV = $derived(margin.min + margin.counts.length - 1);
	// Symmetric about a tie, so left and right read as Labor and Coalition.
	const ext = $derived(Math.max(10, Math.ceil(Math.max(Math.abs(margin.min), Math.abs(maxV), Math.abs(actual ?? 0)) / 10) * 10));
	const innerW = $derived(Math.max(10, width - m.left - m.right));
	const innerH = height - m.top - m.bottom;
	const bw = $derived(innerW / (2 * ext + 1));
	const x = (v: number) => m.left + (v + ext) * bw;
	const y = (c: number) => m.top + innerH - (innerH * c) / peak;
	const share = (pred: (v: number) => boolean) =>
		margin.counts.reduce((a, c, i) => (pred(margin.min + i) ? a + c : a), 0) / total;
	const pCoal = $derived(share((v) => v > 0));
	const pAlp = $derived(share((v) => v < 0));
	const tickStep = $derived(ext > 40 ? 20 : 10);
	// Labels need about 90px each; thin them out on narrow screens.
	const ticks = $derived.by(() => {
		const every = Math.max(1, Math.ceil(90 / (tickStep * bw)));
		const n = Math.floor(ext / tickStep);
		return Array.from({ length: 2 * n + 1 }, (_, i) => (i - n) * tickStep).filter((t) => (t / tickStep) % every === 0);
	});
	const tickLabel = (v: number) => (v === 0 ? 'Tie' : v < 0 ? `+${-v} Labor` : `+${v} Coalition`);
	const colour = (v: number) => (v < 0 ? partyColour('ALP') : v > 0 ? partyColour('COAL') : 'var(--muted)');
	let hover = $state<number | null>(null);
	const in100 = (p: number) => (p < 0.01 ? 'fewer than 1' : Math.round(p * 100).toString());
</script>

<figure class="margin">
	<div class="plot" bind:clientWidth={width}>
		<svg
			viewBox="0 0 {width} {height}"
			role="img"
			aria-label="Seat margin between the major parties. Coalition wins more seats in {in100(pCoal)} of 100 simulations, Labor in {in100(pAlp)}.{actual != null ? ` ${actualLabel}: ${tickLabel(actual)}.` : ''}"
		>
			{#each margin.counts as c, i (i)}
				{@const v = margin.min + i}
				{#if c > 0 && Math.abs(v) <= ext}
					<rect
						x={x(v) + 1}
						y={y(c)}
						width={Math.max(1, bw - 2)}
						height={m.top + innerH - y(c)}
						rx={Math.min(2, bw / 4)}
						fill={colour(v)}
						opacity={hover == null || hover === v ? 1 : 0.55}
					/>
				{/if}
			{/each}
			<!-- Wide invisible hit targets, one per seat margin. -->
			{#each margin.counts as c, i (i)}
				{@const v = margin.min + i}
				{#if c > 0 && Math.abs(v) <= ext}
					<rect
						class="hit"
						x={x(v)}
						y={m.top}
						width={bw}
						height={innerH}
						role="presentation"
						onpointerenter={() => (hover = v)}
						onpointerleave={() => (hover = null)}
					/>
				{/if}
			{/each}
			<line class="axis" x1={m.left} x2={m.left + innerW} y1={m.top + innerH} y2={m.top + innerH} />
			<line class="tie" x1={x(0) + bw / 2} x2={x(0) + bw / 2} y1={m.top - 8} y2={m.top + innerH} />
			{#if actual != null}
				<line class="result" x1={x(actual) + bw / 2} x2={x(actual) + bw / 2} y1={m.top - 14} y2={m.top + innerH} />
				<text class="result-label" x={x(actual) + bw / 2 + 5} y={m.top - 6} text-anchor={actual > ext * 0.5 ? 'end' : 'start'} dx={actual > ext * 0.5 ? -10 : 0}>{actualLabel}</text>
			{/if}
			{#each ticks as t (t)}
				<text class="tick" x={x(t) + bw / 2} y={m.top + innerH + 16} text-anchor="middle">{tickLabel(t)}</text>
			{/each}
			<text class="dir" x={m.left} y={height - 4}>← Labor wins more seats</text>
			<text class="dir" x={m.left + innerW} y={height - 4} text-anchor="end">Coalition wins more seats →</text>
		</svg>
		{#if hover != null}
			{@const c = margin.counts[hover - margin.min] ?? 0}
			<div class="tip" style:left="{Math.min(Math.max(x(hover) + bw / 2, 80), width - 80)}px">
				<strong>{hover === 0 ? 'A tie on seats' : hover < 0 ? `Labor by ${-hover}` : `Coalition by ${hover}`}</strong>
				{((100 * c) / total).toFixed(1)}% of simulations
			</div>
		{/if}
	</div>
	<figcaption class="small muted">
		The Coalition wins more seats than Labor in <strong>{in100(pCoal)} of 100</strong> simulations; Labor in
		<strong>{in100(pAlp)} of 100</strong>. Winning more seats is not the same as a majority: the crossbench decides
		the rest.
	</figcaption>
</figure>

<style>
	.margin {
		margin: 0;
	}
	.plot {
		position: relative;
		contain: inline-size;
	}
	svg {
		display: block;
		width: 100%;
		height: auto;
		overflow: visible;
	}
	.hit {
		fill: transparent;
	}
	.axis {
		stroke: var(--rule-strong);
	}
	.tie {
		stroke: var(--fg-2);
		stroke-width: 1.5;
	}
	.result {
		stroke: var(--fg);
		stroke-width: 2;
		stroke-dasharray: 5 3;
	}
	.result-label {
		font-size: 12px;
		font-weight: 700;
		fill: var(--fg);
	}
	.tick {
		font-size: 11px;
		fill: var(--muted);
	}
	.dir {
		font-size: 12px;
		font-weight: 600;
		fill: var(--fg-2);
	}
	.tip {
		position: absolute;
		top: 0;
		transform: translateX(-50%);
		background: var(--surface);
		border: 1px solid var(--rule-strong);
		border-radius: var(--radius);
		box-shadow: var(--shadow);
		padding: 0.3rem 0.55rem;
		font-size: 0.78rem;
		pointer-events: none;
		white-space: nowrap;
	}
	.tip strong {
		display: block;
	}
	figcaption {
		margin-top: 0.4rem;
		max-width: 46rem;
	}
	figcaption strong {
		color: var(--fg);
	}
</style>
