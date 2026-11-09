<!--
	A few series over time with optional uncertainty bands, a legend, direct end labels and a
	crosshair tooltip. Used for how the forecast has moved from day to day.
-->
<script lang="ts" module>
	export interface TrendSeries {
		key: string;
		label: string;
		colour: string;
		dashed?: boolean;
		points: { date: string; v: number; lo?: number; hi?: number }[];
	}
</script>

<script lang="ts">
	import { timeFormat, timeParse } from 'd3-time-format';

	interface Props {
		title: string;
		series: TrendSeries[];
		yMax: number;
		yMin?: number;
		format: (v: number) => string;
		/** Horizontal reference line, e.g. the majority. */
		reference?: { value: number; label: string } | null;
	}
	let { title, series, yMax, yMin = 0, format, reference = null }: Props = $props();

	const parse = timeParse('%Y-%m-%d');
	const fmtDay = timeFormat('%-d %b');
	let width = $state(640);
	const height = 220;
	const m = { top: 14, right: 118, bottom: 26, left: 36 };
	const dates = $derived([...new Set(series.flatMap((s) => s.points.map((p) => p.date)))].sort());
	const t0 = $derived(parse(dates[0])!.getTime());
	const t1 = $derived(parse(dates.at(-1)!)!.getTime());
	const innerW = $derived(Math.max(10, width - m.left - m.right));
	const innerH = height - m.top - m.bottom;
	const x = (d: string) => m.left + (t1 === t0 ? innerW / 2 : ((parse(d)!.getTime() - t0) / (t1 - t0)) * innerW);
	const y = (v: number) => m.top + innerH - ((v - yMin) / (yMax - yMin)) * innerH;
	const path = (pts: { date: string; v: number }[]) => pts.map((p, i) => `${i ? 'L' : 'M'}${x(p.date)},${y(p.v)}`).join('');
	const band = (pts: { date: string; lo?: number; hi?: number }[]) => {
		const b = pts.filter((p) => p.lo != null && p.hi != null);
		if (b.length < 2) return '';
		return `M${b.map((p) => `${x(p.date)},${y(p.hi!)}`).join('L')}L${b
			.toReversed()
			.map((p) => `${x(p.date)},${y(p.lo!)}`)
			.join('L')}Z`;
	};
	// Round steps (1, 2, 5, 10, 20, 25, 50...) giving four to six gridlines.
	const yTicks = $derived.by(() => {
		const raw = (yMax - yMin) / 4;
		const mag = 10 ** Math.floor(Math.log10(raw));
		const step = [1, 2, 2.5, 5, 10].map((s) => s * mag).find((s) => s >= raw) ?? 10 * mag;
		const out = [];
		for (let v = Math.ceil(yMin / step) * step; v <= yMax + 1e-9; v += step) out.push(v);
		return out;
	});
	// Date labels at least 60px apart, always keeping the latest.
	const xTicks = $derived.by(() => {
		const out: string[] = [];
		for (const d of dates.toReversed()) if (!out.length || x(out.at(-1)!) - x(d) >= 60) out.push(d);
		return out.reverse();
	});
	// End labels, nudged apart so they never overlap.
	const ends = $derived.by(() => {
		const out = series
			.filter((s) => s.points.length)
			.map((s) => ({ s, y: y(s.points.at(-1)!.v) }))
			.sort((a, b) => a.y - b.y);
		for (let i = 1; i < out.length; i++) out[i].y = Math.max(out[i].y, out[i - 1].y + 14);
		return out;
	});
	let hover = $state<string | null>(null);
	function onMove(e: PointerEvent) {
		const r = (e.currentTarget as SVGElement).getBoundingClientRect();
		const px = ((e.clientX - r.left) / r.width) * width;
		hover = dates.reduce((best, d) => (Math.abs(x(d) - px) < Math.abs(x(best) - px) ? d : best), dates[0]);
	}
</script>

<figure class="trend">
	<figcaption>
		<strong>{title}</strong>
		<span class="legend">
			{#each series as s (s.key)}
				<span><i class:dashed={s.dashed} style:--c={s.colour}></i>{s.label}</span>
			{/each}
		</span>
	</figcaption>
	<div class="plot" bind:clientWidth={width}>
		<svg
			viewBox="0 0 {width} {height}"
			role="img"
			aria-label="{title}, {fmtDay(parse(dates[0])!)} to {fmtDay(parse(dates.at(-1)!)!)}. Latest: {series
				.map((s) => `${s.label} ${format(s.points.at(-1)?.v ?? 0)}`)
				.join(', ')}."
			onpointermove={onMove}
			onpointerleave={() => (hover = null)}
		>
			{#each yTicks as t (t)}
				<line class="grid" x1={m.left} x2={m.left + innerW} y1={y(t)} y2={y(t)} />
				<text class="tick" x={m.left - 6} y={y(t) + 4} text-anchor="end">{format(t)}</text>
			{/each}
			{#if reference}
				<line class="ref" x1={m.left} x2={m.left + innerW} y1={y(reference.value)} y2={y(reference.value)} />
				<text class="ref-label" x={m.left + 4} y={y(reference.value) - 4}>{reference.label}</text>
			{/if}
			{#each series as s (s.key)}
				{@const b = band(s.points)}
				{#if b}<path d={b} fill={s.colour} opacity="0.15" />{/if}
			{/each}
			{#each series as s (s.key)}
				<path d={path(s.points)} fill="none" stroke={s.colour} stroke-width="2" stroke-dasharray={s.dashed ? '5 3' : undefined} stroke-linejoin="round" />
				{#if dates.length <= 20}
					{#each s.points as p (p.date)}
						<circle cx={x(p.date)} cy={y(p.v)} r="3.5" fill={s.colour} stroke="var(--bg)" stroke-width="2" />
					{/each}
				{/if}
			{/each}
			{#each ends as e (e.s.key)}
				<text class="end" x={m.left + innerW + 8} y={e.y + 4}>{format(e.s.points.at(-1)!.v)} {e.s.label}</text>
			{/each}
			{#each xTicks as d (d)}
				<text class="tick" x={x(d)} y={height - 6} text-anchor="middle">{fmtDay(parse(d)!)}</text>
			{/each}
			{#if hover}
				<line class="cross" x1={x(hover)} x2={x(hover)} y1={m.top} y2={m.top + innerH} />
			{/if}
		</svg>
		{#if hover}
			<div class="tip" style:left="{Math.min(Math.max(x(hover), 90), width - 90)}px">
				<strong>{fmtDay(parse(hover)!)}</strong>
				{#each series as s (s.key)}
					{@const p = s.points.find((q) => q.date === hover)}
					{#if p}
						<span><i style:background={s.colour}></i>{s.label}: {format(p.v)}{#if p.lo != null && p.hi != null}
								<span class="muted"> ({format(p.lo)}–{format(p.hi)})</span>{/if}</span>
					{/if}
				{/each}
			</div>
		{/if}
	</div>
</figure>

<style>
	.trend {
		margin: 0;
	}
	figcaption {
		display: flex;
		flex-wrap: wrap;
		align-items: baseline;
		justify-content: space-between;
		gap: 0.25rem 1rem;
		font-size: 0.9rem;
		margin-bottom: 0.25rem;
	}
	.legend {
		display: flex;
		flex-wrap: wrap;
		gap: 0.25rem 0.85rem;
		font-size: 0.8rem;
		color: var(--fg-2);
	}
	.legend span {
		display: inline-flex;
		align-items: center;
		gap: 0.35rem;
	}
	.legend i {
		width: 1rem;
		height: 0;
		border-top: 2px solid var(--c);
	}
	.legend i.dashed {
		border-top-style: dashed;
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
		touch-action: pan-y;
	}
	.grid {
		stroke: var(--rule);
	}
	.tick {
		font-size: 11px;
		fill: var(--muted);
	}
	.ref {
		stroke: var(--fg-2);
		stroke-dasharray: 4 3;
	}
	.ref-label {
		font-size: 11px;
		font-weight: 600;
		fill: var(--fg-2);
	}
	.end {
		font-size: 12px;
		font-weight: 600;
		fill: var(--fg);
	}
	.cross {
		stroke: var(--fg-2);
		stroke-width: 1;
	}
	.tip {
		position: absolute;
		top: 0;
		transform: translateX(-50%);
		display: flex;
		flex-direction: column;
		gap: 0.1rem;
		background: var(--surface);
		border: 1px solid var(--rule-strong);
		border-radius: var(--radius);
		box-shadow: var(--shadow);
		padding: 0.35rem 0.6rem;
		font-size: 0.78rem;
		pointer-events: none;
		white-space: nowrap;
	}
	.tip i {
		display: inline-block;
		width: 0.6rem;
		height: 0.6rem;
		border-radius: 2px;
		margin-right: 0.3rem;
	}
</style>
