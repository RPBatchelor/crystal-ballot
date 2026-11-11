<!--
	Labor seats against Coalition seats across every simulation: darker cells are more likely.
	The majority lines split the plot into Labor majority, Coalition majority and a hung
	parliament; an optional marker shows the result.
-->
<script lang="ts">
	interface Props {
		joint: [number, number, number][];
		majority: number;
		outcome: { alp_majority: number; coal_majority: number; hung: number };
		actual?: { alp: number; coal: number } | null;
		actualLabel?: string;
		/** What the Coalition side is called here ("LNP", "Liberal"…). */
		coal?: string;
	}
	let { joint, majority, outcome, actual = null, actualLabel = 'Result', coal = 'Coalition' }: Props = $props();

	let width = $state(420);
	const m = { top: 12, right: 12, bottom: 40, left: 46 };
	const total = $derived(joint.reduce((a, r) => a + r[2], 0));
	const peak = $derived(Math.max(...joint.map((r) => r[2])));
	// Cover the data, the majority lines and the result, in steps of 10 seats.
	const lim = (vals: number[]) => Math.ceil((Math.max(...vals) + 3) / 10) * 10;
	const lo = (vals: number[]) => Math.max(0, Math.floor((Math.min(...vals) - 3) / 10) * 10);
	const xMin = $derived(lo([...joint.map((r) => r[0]), actual?.alp ?? Infinity, majority]));
	const xMax = $derived(lim([...joint.map((r) => r[0]), actual?.alp ?? 0, majority]));
	const yMin = $derived(lo([...joint.map((r) => r[1]), actual?.coal ?? Infinity, majority]));
	const yMax = $derived(lim([...joint.map((r) => r[1]), actual?.coal ?? 0, majority]));
	const innerW = $derived(Math.max(10, Math.min(width, 520) - m.left - m.right));
	const cell = $derived(innerW / (xMax - xMin + 1));
	const innerH = $derived(cell * (yMax - yMin + 1));
	const height = $derived(m.top + innerH + m.bottom);
	const x = (s: number) => m.left + (s - xMin) * cell;
	const y = (s: number) => m.top + (yMax - s) * cell;
	// Square-root scale so the less likely combinations stay visible.
	const shade = (n: number) => 0.12 + 0.88 * Math.sqrt(n / peak);
	const ticks = (a: number, b: number) => Array.from({ length: Math.floor((b - a) / 10) + 1 }, (_, i) => a + 10 * i);
	let hover = $state<[number, number, number] | null>(null);
	const in100 = (p: number) => (p < 0.01 ? '<1' : p > 0.99 ? '>99' : Math.round(p * 100).toString());
</script>

<figure class="heat">
	<div class="plot" bind:clientWidth={width}>
		<svg
			width={Math.min(width, 520)}
			{height}
			viewBox="0 0 {Math.min(width, 520)} {height}"
			role="img"
			aria-label="Labor seats against {coal} seats across the simulations. Labor majority {in100(outcome.alp_majority)} in 100, {coal} majority {in100(outcome.coal_majority)} in 100, hung parliament {in100(outcome.hung)} in 100.{actual ? ` ${actualLabel}: Labor ${actual.alp}, ${coal} ${actual.coal}.` : ''}"
		>
			<!-- Majority regions -->
			<rect class="region" x={x(majority)} y={y(yMax)} width={x(xMax + 1) - x(majority)} height={y(yMin) + cell - y(yMax)} />
			<rect class="region" x={x(xMin)} y={y(yMax)} width={x(xMax + 1) - x(xMin)} height={y(majority) + cell - y(yMax)} />
			{#each joint as r (r[0] * 1000 + r[1])}
				<rect
					x={x(r[0]) + 0.5}
					y={y(r[1]) + 0.5}
					width={Math.max(0.5, cell - 1)}
					height={Math.max(0.5, cell - 1)}
					rx={Math.min(1.5, cell / 4)}
					class="cell"
					fill-opacity={shade(r[2])}
					stroke={hover === r ? 'var(--brand-spark)' : 'none'}
					stroke-width="1.5"
					role="presentation"
					onpointerenter={() => (hover = r)}
					onpointerleave={() => (hover = null)}
				/>
			{/each}
			<line class="maj" x1={x(majority)} x2={x(majority)} y1={y(yMax)} y2={y(yMin) + cell} />
			<line class="maj" x1={x(xMin)} x2={x(xMax + 1)} y1={y(majority) + cell} y2={y(majority) + cell} />
			<text class="region-label" x={x(xMax + 1) - 6} y={y(yMin) + cell - 8} text-anchor="end">Labor majority · {in100(outcome.alp_majority)} in 100</text>
			<text class="region-label" x={x(xMin) + 6} y={y(yMax) + 14}>{coal} majority · {in100(outcome.coal_majority)} in 100</text>
			<text class="region-label" x={x(xMin) + 6} y={y(yMin) + cell - 8}>Hung · {in100(outcome.hung)} in 100</text>
			{#if actual}
				<g class="result" transform="translate({x(actual.alp) + cell / 2} {y(actual.coal) + cell / 2})">
					<circle r={Math.max(6, cell * 1.4)} />
					<text x={Math.max(6, cell * 1.4) + 4} y="4">{actualLabel}</text>
				</g>
			{/if}
			{#each ticks(xMin, xMax) as t (t)}
				<text class="tick" x={x(t) + cell / 2} y={y(yMin) + cell + 14} text-anchor="middle">{t}</text>
			{/each}
			{#each ticks(yMin, yMax) as t (t)}
				<text class="tick" x={m.left - 6} y={y(t) + cell / 2 + 4} text-anchor="end">{t}</text>
			{/each}
			<text class="axis-title" x={m.left + innerW / 2} y={height - 6} text-anchor="middle">Labor seats →</text>
			<text class="axis-title" transform="translate(12 {m.top + innerH / 2}) rotate(-90)" text-anchor="middle">{coal} seats →</text>
		</svg>
		{#if hover}
			<div class="tip" style:left="{x(hover[0]) + cell / 2}px" style:top="{y(hover[1]) - 8}px">
				<strong>Labor {hover[0]}, {coal} {hover[1]}</strong>
				{((100 * hover[2]) / total).toFixed(2)}% of simulations
			</div>
		{/if}
	</div>
	<figcaption class="small muted">Each square is one combination of seats; darker squares came up more often.</figcaption>
</figure>

<style>
	.heat {
		margin: 0;
	}
	.plot {
		position: relative;
		contain: inline-size;
	}
	svg {
		display: block;
		max-width: 100%;
		height: auto;
		overflow: visible;
	}
	.region {
		fill: var(--rule);
		opacity: 0.45;
	}
	.cell {
		fill: var(--fg);
	}
	.maj {
		stroke: var(--fg-2);
		stroke-width: 1.25;
		stroke-dasharray: 4 3;
	}
	.region-label {
		font-size: 11px;
		font-weight: 650;
		fill: var(--fg-2);
	}
	.result circle {
		fill: none;
		stroke: var(--fg);
		stroke-width: 2.5;
	}
	.result text {
		font-size: 12px;
		font-weight: 700;
		fill: var(--fg);
		paint-order: stroke;
		stroke: var(--bg);
		stroke-width: 3px;
	}
	.tick {
		font-size: 11px;
		fill: var(--muted);
	}
	.axis-title {
		font-size: 12px;
		font-weight: 600;
		fill: var(--fg-2);
	}
	.tip {
		position: absolute;
		transform: translate(-50%, -100%);
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
</style>
