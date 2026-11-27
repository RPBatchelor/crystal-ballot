<script lang="ts">
	interface Props {
		label: string;
		colour: string;
		counts: number[]; // index = seats won
		majority: number;
		quantiles: [number, number, number, number, number];
		/** Show majority threshold line and caption (disable for minor parties). */
		showMajority?: boolean;
	}
	let { label, colour, counts, majority, quantiles, showMajority = true }: Props = $props();

	let width = $state(480);
	const height = $derived(showMajority ? 150 : 120);
	const m = { top: 14, right: 8, bottom: 22, left: 8 };
	const total = $derived(counts.reduce((a, b) => a + b, 0));
	// For minor parties, zoom x-axis to the non-zero support (+2) so bars are readable.
	const lastNonZero = $derived.by(() => {
		for (let i = counts.length - 1; i >= 0; i--) if (counts[i] > 0) return i;
		return 10;
	});
	const maxSeat = $derived(showMajority ? counts.length - 1 : Math.min(counts.length - 1, Math.max(10, lastNonZero + 2)));
	const shownCounts = $derived(counts.slice(0, maxSeat + 1));
	const peak = $derived(Math.max(1, ...shownCounts));
	const innerW = $derived(Math.max(10, width - m.left - m.right));
	const innerH = $derived(height - m.top - m.bottom);
	const bw = $derived(innerW / (maxSeat + 1));
	const x = (s: number) => m.left + s * bw;
	const y = (c: number) => m.top + innerH - (innerH * c) / peak;
	const pMaj = $derived(counts.slice(majority).reduce((a, b) => a + b, 0) / total);
	let hover = $state<number | null>(null);
	const ticks = $derived(
		showMajority
			? [0, 22, 44, 66, maxSeat].filter((t) => t <= maxSeat)
			: [0, Math.round(maxSeat / 4), Math.round(maxSeat / 2), Math.round((3 * maxSeat) / 4), maxSeat].filter(
					(v, i, a) => a.indexOf(v) === i
				)
	);
</script>

<figure class="hist">
	<figcaption>
		<span class="swatch" style:background={colour}></span>
		<strong>{label}</strong>
		<span class="muted">median {quantiles[2]} · 50% {quantiles[1]}–{quantiles[3]} · 90% {quantiles[0]}–{quantiles[4]}</span>
	</figcaption>
	<div class="plot" bind:clientWidth={width}>
		<svg viewBox="0 0 {width} {height}" role="img" aria-label="{label} seat distribution: median {quantiles[2]}, 90% range {quantiles[0]} to {quantiles[4]}.{showMajority ? ` ${Math.round(pMaj * 100)}% chance of a majority.` : ''}">
			{#each shownCounts as c, s (s)}
				{#if c > 0}
					<rect
						x={x(s) + 0.5}
						y={y(c)}
						width={Math.max(1, bw - 1)}
						height={m.top + innerH - y(c)}
						fill={colour}
						opacity={!showMajority || s >= majority ? 1 : 0.55}
						role="presentation"
						onpointerenter={() => (hover = s)}
						onpointerleave={() => (hover = null)}
					/>
				{/if}
			{/each}
			{#if showMajority}
				<line class="maj" x1={x(majority)} x2={x(majority)} y1={m.top - 6} y2={m.top + innerH} />
				<text class="maj-label" x={x(majority) + 4} y={m.top}>{majority} for majority</text>
			{/if}
			<line class="axis" x1={m.left} x2={m.left + innerW} y1={m.top + innerH} y2={m.top + innerH} />
			{#each ticks as t (t)}
				<text class="tick" x={x(t) + bw / 2} y={height - 6} text-anchor="middle">{t}</text>
			{/each}
		</svg>
		{#if hover != null}
			<div class="tip" style:left="{Math.min(Math.max(x(hover) + bw / 2, 70), width - 70)}px">
				<strong>{hover} seats</strong>
				{((100 * counts[hover]) / total).toFixed(1)}% of simulations
			</div>
		{/if}
	</div>
	{#if showMajority}
		<p class="small muted">Majority in {Math.round(pMaj * 100)} of 100 simulations.</p>
	{/if}
</figure>

<style>
	.hist {
		margin: 0;
	}
	figcaption {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 0.25rem 0.5rem;
		font-size: 0.9rem;
	}
	.swatch {
		width: 0.7rem;
		height: 0.7rem;
		border-radius: 2px;
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
	.maj {
		stroke: var(--fg);
		stroke-width: 2;
	}
	.maj-label {
		font-size: 11px;
		font-weight: 600;
		fill: var(--fg-2);
	}
	.axis {
		stroke: var(--rule-strong);
	}
	.tick {
		font-size: 11px;
		fill: var(--muted);
	}
	.tip {
		position: absolute;
		top: 0;
		transform: translateX(-50%);
		background: var(--surface);
		border: 1px solid var(--rule-strong);
		border-radius: var(--radius);
		padding: 0.3rem 0.5rem;
		font-size: 0.78rem;
		pointer-events: none;
		white-space: nowrap;
	}
	p {
		margin: 0.25rem 0 0;
	}
</style>
