<!--
	Labor's two-party-preferred vote across every simulation: bars right of 50% are Labor
	wins of the two-party vote, left of it Coalition wins. An optional line marks the result.
-->
<script lang="ts">
	import { cap } from '$lib/format';
	import { partyColour } from '$lib/parties';

	interface Props {
		hist: { min: number; step: number; counts: number[] };
		actual?: number | null;
		actualLabel?: string;
		/** The same as a sentence subject ("the LNP", "the Coalition"). */
		theCoal?: string;
	}
	let { hist, actual = null, actualLabel = 'Result', theCoal = 'the Coalition' }: Props = $props();

	let width = $state(640);
	const height = 190;
	const m = { top: 22, right: 12, bottom: 40, left: 12 };
	const total = $derived(hist.counts.reduce((a, b) => a + b, 0));
	const peak = $derived(Math.max(...hist.counts));
	const top = $derived(hist.min + hist.counts.length * hist.step);
	const lo = $derived(Math.floor(Math.min(hist.min, actual ?? 100, 50) / 5) * 5);
	const hi = $derived(Math.ceil(Math.max(top, actual ?? 0, 50) / 5) * 5);
	const innerW = $derived(Math.max(10, width - m.left - m.right));
	const innerH = height - m.top - m.bottom;
	const x = (v: number) => m.left + ((v - lo) / (hi - lo)) * innerW;
	const y = (c: number) => m.top + innerH - (innerH * c) / peak;
	const bw = $derived(x(hist.step) - x(0));
	const pAlp = $derived(hist.counts.reduce((a, c, i) => (hist.min + i * hist.step >= 50 ? a + c : a), 0) / total);
	const ticks = $derived(Array.from({ length: Math.round((hi - lo) / 5) + 1 }, (_, i) => lo + 5 * i));
	let hover = $state<number | null>(null);
	const in100 = (p: number) => (p < 0.01 ? 'fewer than 1' : p > 0.99 ? 'more than 99' : Math.round(p * 100).toString());
</script>

<figure class="tpp">
	<div class="plot" bind:clientWidth={width}>
		<svg
			viewBox="0 0 {width} {height}"
			role="img"
			aria-label="Labor two-party-preferred vote across the simulations. Labor wins the two-party vote in {in100(pAlp)} of 100.{actual != null ? ` ${actualLabel}: ${actual.toFixed(1)}%.` : ''}"
		>
			{#each hist.counts as c, i (i)}
				{@const v = hist.min + i * hist.step}
				{#if c > 0}
					<rect
						x={x(v) + 0.5}
						y={y(c)}
						width={Math.max(1, bw - 1)}
						height={m.top + innerH - y(c)}
						rx={Math.min(2, bw / 4)}
						fill={v >= 50 ? partyColour('ALP') : partyColour('COAL')}
						opacity={hover == null || hover === i ? 1 : 0.55}
					/>
					<rect
						class="hit"
						x={x(v)}
						y={m.top}
						width={bw}
						height={innerH}
						role="presentation"
						onpointerenter={() => (hover = i)}
						onpointerleave={() => (hover = null)}
					/>
				{/if}
			{/each}
			<line class="axis" x1={m.left} x2={m.left + innerW} y1={m.top + innerH} y2={m.top + innerH} />
			<line class="even" x1={x(50)} x2={x(50)} y1={m.top - 8} y2={m.top + innerH} />
			{#if actual != null}
				<line class="result" x1={x(actual)} x2={x(actual)} y1={m.top - 14} y2={m.top + innerH} />
				<text class="result-label" x={x(actual) + 5} y={m.top - 6}>{actualLabel} {actual.toFixed(1)}%</text>
			{/if}
			{#each ticks as t (t)}
				<text class="tick" x={x(t)} y={m.top + innerH + 16} text-anchor="middle">{t}%</text>
			{/each}
			<text class="dir" x={m.left} y={height - 4}>← {cap(theCoal)} wins the two-party vote</text>
			<text class="dir" x={m.left + innerW} y={height - 4} text-anchor="end">Labor wins →</text>
		</svg>
		{#if hover != null}
			{@const v = hist.min + hover * hist.step}
			<div class="tip" style:left="{Math.min(Math.max(x(v + hist.step / 2), 80), width - 80)}px">
				<strong>Labor {v.toFixed(1)}–{(v + hist.step).toFixed(1)}%</strong>
				{((100 * hist.counts[hover]) / total).toFixed(1)}% of simulations
			</div>
		{/if}
	</div>
	<figcaption class="small muted">
		Labor wins the two-party-preferred vote in <strong>{in100(pAlp)} of 100</strong> simulations.
	</figcaption>
</figure>

<style>
	.tpp {
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
	.even {
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
	}
	figcaption strong {
		color: var(--fg);
	}
</style>
