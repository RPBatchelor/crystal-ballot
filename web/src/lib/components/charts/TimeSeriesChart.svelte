<script lang="ts" generics="P extends object, T extends { date: string }">
	import { scaleLinear, scaleTime } from 'd3-scale';
	import { area, curveMonotoneX, line } from 'd3-shape';
	import { bisector } from 'd3-array';
	import { timeFormat } from 'd3-time-format';
	import { fmtDate } from '$lib/format';

	interface Series {
		key: string;
		label: string;
		colour: string;
	}
	interface ChartEvent {
		date: string;
		label: string;
	}
	interface Props {
		title: string;
		series: Series[];
		/** Raw observations (polls), drawn as faint dots. */
		points: P[];
		pointDate: (p: P) => string;
		/** Smoothed trend, drawn as lines with a hover crosshair. */
		trend: T[];
		events?: ChartEvent[];
		/** Extend the x-axis to this date (e.g. election day). */
		end?: string;
		endLabel?: string;
		yDomain?: [number, number];
		/** Horizontal reference line (e.g. 50 for 2PP). */
		yRef?: number;
		height?: number;
	}

	let {
		title,
		series,
		points,
		pointDate,
		trend,
		events = [],
		end,
		endLabel = 'Election',
		yDomain,
		yRef,
		height = 380
	}: Props = $props();

	let width = $state(720);
	let hoverIndex = $state<number | null>(null);
	let hoverEvent = $state<number | null>(null);

	const narrow = $derived(width < 560);
	const m = $derived({ top: 22, right: narrow ? 64 : 104, bottom: 28, left: 34 });
	const innerW = $derived(Math.max(10, width - m.left - m.right));
	const innerH = $derived(height - m.top - m.bottom);

	const value = (d: object, key: string) =>
		(d as Record<string, unknown>)[key] as number | null | undefined;

	const xDomain = $derived.by(() => {
		const dates = [...trend.map((d) => +new Date(d.date)), ...points.map((p) => +new Date(pointDate(p)))];
		if (end) dates.push(+new Date(end));
		return [new Date(Math.min(...dates)), new Date(Math.max(...dates))] as [Date, Date];
	});
	const x = $derived(scaleTime().domain(xDomain).range([0, innerW]));

	const y = $derived.by(() => {
		if (yDomain) return scaleLinear().domain(yDomain).range([innerH, 0]);
		const vals = series.flatMap((s) => [
			...points.map((p) => value(p, s.key)),
			...trend.map((t) => value(t, s.key))
		]).filter((v): v is number => v != null);
		const lo = Math.max(0, Math.floor((Math.min(...vals) - 2) / 5) * 5);
		const hi = Math.ceil((Math.max(...vals) + 2) / 5) * 5;
		return scaleLinear().domain([lo, hi]).range([innerH, 0]).nice();
	});

	const yTicks = $derived(y.ticks(narrow ? 4 : 6));
	const xTicks = $derived(x.ticks(Math.max(2, Math.floor(innerW / 110))));
	const xFmt = timeFormat('%b %Y');

	const paths = $derived(
		series.map((s) => ({
			...s,
			d:
				line<T>()
					.defined((d) => value(d, s.key) != null)
					.x((d) => x(new Date(d.date)))
					.y((d) => y(value(d, s.key)!))
					.curve(curveMonotoneX)(trend) ?? '',
			// Uncertainty band when the trend carries `<key>_lo` / `<key>_hi`.
			band:
				area<T>()
					.defined((d) => value(d, `${s.key}_lo`) != null && value(d, `${s.key}_hi`) != null)
					.x((d) => x(new Date(d.date)))
					.y0((d) => y(value(d, `${s.key}_lo`)!))
					.y1((d) => y(value(d, `${s.key}_hi`)!))
					.curve(curveMonotoneX)(trend) ?? ''
		}))
	);

	// Direct labels at each line's last value, nudged apart to avoid collisions.
	const endLabels = $derived.by(() => {
		const labels = series
			.map((s) => {
				const last = [...trend].reverse().find((d) => value(d, s.key) != null);
				return last ? { ...s, v: value(last, s.key)!, y: y(value(last, s.key)!), x: x(new Date(last.date)) } : null;
			})
			.filter((l): l is NonNullable<typeof l> => l !== null)
			.sort((a, b) => a.y - b.y);
		const gap = 15;
		for (let i = 1; i < labels.length; i++) {
			if (labels[i].y - labels[i - 1].y < gap) labels[i].y = labels[i - 1].y + gap;
		}
		const overflow = labels.length ? labels[labels.length - 1].y - innerH : 0;
		if (overflow > 0) labels.forEach((l) => (l.y -= overflow));
		return labels;
	});

	const bisect = bisector<T, Date>((d) => new Date(d.date)).center;

	function onPointer(e: PointerEvent) {
		const rect = (e.currentTarget as SVGRectElement).getBoundingClientRect();
		const date = x.invert(e.clientX - rect.left);
		hoverIndex = bisect(trend, date);
	}

	function onKey(e: KeyboardEvent) {
		if (e.key === 'ArrowLeft' || e.key === 'ArrowRight') {
			e.preventDefault();
			const step = e.key === 'ArrowLeft' ? -1 : 1;
			hoverIndex = Math.min(trend.length - 1, Math.max(0, (hoverIndex ?? trend.length - 1) + step));
		} else if (e.key === 'Escape') {
			hoverIndex = null;
		}
	}

	const hovered = $derived(hoverIndex != null ? trend[hoverIndex] : null);
	const hoverRows = $derived(
		hovered
			? series
					.map((s) => ({
						...s,
						v: value(hovered, s.key),
						lo: value(hovered, `${s.key}_lo`),
						hi: value(hovered, `${s.key}_hi`)
					}))
					.filter((r) => r.v != null)
					.sort((a, b) => b.v! - a.v!)
			: []
	);
	const valueText = $derived.by(() => {
		const d = trend[hoverIndex ?? trend.length - 1];
		if (!d) return '';
		const vals = series
			.map((s) => ({ s, v: value(d, s.key) }))
			.filter((r) => r.v != null)
			.map((r) => `${r.s.label} ${r.v!.toFixed(1)}`);
		return `${fmtDate(d.date)}: ${vals.join(', ')}`;
	});
	const tipLeft = $derived(hovered ? m.left + x(new Date(hovered.date)) : 0);
</script>

<figure class="chart">
	<div class="legend" aria-hidden="true">
		{#each series as s (s.key)}
			<span class="item"><span class="swatch" style:background={s.colour}></span>{s.label}</span>
		{/each}
	</div>

	<div
		class="plot"
		bind:clientWidth={width}
		role="slider"
		aria-label="{title}. Use left and right arrow keys to read values week by week."
		aria-valuemin={0}
		aria-valuemax={trend.length - 1}
		aria-valuenow={hoverIndex ?? trend.length - 1}
		aria-valuetext={valueText}
		tabindex="0"
		onkeydown={onKey}
		onblur={() => (hoverIndex = null)}
	>
		<!-- viewBox lets the prerendered (pre-measurement) SVG scale to fit before hydration. -->
		<svg viewBox="0 0 {width} {height}" aria-hidden="true">
			<g transform="translate({m.left},{m.top})">
				{#each yTicks as t (t)}
					<line class="grid" x1="0" x2={innerW} y1={y(t)} y2={y(t)} />
					<text class="tick" x="-8" y={y(t)} dy="0.32em" text-anchor="end">{t}</text>
				{/each}
				{#each xTicks as t (+t)}
					<text class="tick" x={x(t)} y={innerH + 18} text-anchor="middle">{xFmt(t)}</text>
				{/each}
				<line class="axis" x1="0" x2={innerW} y1={innerH} y2={innerH} />

				{#if yRef != null}
					<line class="ref" x1="0" x2={innerW} y1={y(yRef)} y2={y(yRef)} />
				{/if}

				{#each events as ev, i (ev.date + ev.label)}
					{@const ex = x(new Date(ev.date))}
					<g
						class="event"
						role="presentation"
						onpointerenter={() => (hoverEvent = i)}
						onpointerleave={() => (hoverEvent = null)}
					>
						<line x1={ex} x2={ex} y1="-6" y2={innerH} />
						<rect x={ex - 7} y="-16" width="14" height={innerH + 16} fill="transparent" />
						<circle cx={ex} cy="-10" r="7" />
						<text x={ex} y="-10" dy="0.35em" text-anchor="middle">{i + 1}</text>
					</g>
				{/each}

				{#if end}
					{@const ex = x(new Date(end))}
					<line class="end" x1={ex} x2={ex} y1="0" y2={innerH} />
					<text class="end-label" x={ex - 4} y="10" text-anchor="end">{endLabel}</text>
				{/if}

				{#each series as s (s.key)}
					{#each points as p, i (i)}
						{@const v = value(p, s.key)}
						{#if v != null}
							<circle class="dot" cx={x(new Date(pointDate(p)))} cy={y(v)} r="3" fill={s.colour} />
						{/if}
					{/each}
				{/each}

				{#each paths as p (p.key)}
					{#if p.band}<path class="band" d={p.band} fill={p.colour} />{/if}
				{/each}
				{#each paths as p (p.key)}
					<path class="trend" d={p.d} stroke={p.colour} />
				{/each}

				{#each endLabels as l (l.key)}
					<line class="leader" x1={l.x + 4} x2={l.x + 10} y1={y(l.v)} y2={l.y} />
					<text class="end-value" x={l.x + 12} y={l.y} dy="0.32em">
						<tspan class="v">{l.v.toFixed(1)}</tspan>
						{#if !narrow}<tspan class="lbl" dx="4">{l.label}</tspan>{/if}
					</text>
				{/each}

				{#if hovered}
					{@const hx = x(new Date(hovered.date))}
					<line class="crosshair" x1={hx} x2={hx} y1="0" y2={innerH} />
					{#each hoverRows as r (r.key)}
						<circle class="hover-dot" cx={hx} cy={y(r.v!)} r="4.5" fill={r.colour} />
					{/each}
				{/if}

				<rect
					class="overlay"
					width={innerW}
					height={innerH}
					role="presentation"
					onpointermove={onPointer}
					onpointerleave={() => (hoverIndex = null)}
				/>
			</g>
		</svg>

		{#if hovered}
			<div class="tooltip" style:left="{tipLeft}px" class:flip={tipLeft > width * 0.6}>
				<div class="tip-date">Week of {fmtDate(hovered.date)}</div>
				{#each hoverRows as r (r.key)}
					<div class="tip-row">
						<span class="swatch" style:background={r.colour}></span>
						<span class="tip-label">{r.label}</span>
						<span class="tip-v">{r.v!.toFixed(1)}</span>
						{#if r.lo != null && r.hi != null}
							<span class="tip-range">{r.lo.toFixed(1)}–{r.hi.toFixed(1)}</span>
						{/if}
					</div>
				{/each}
			</div>
		{/if}
		{#if hoverEvent != null}
			<div class="tooltip event-tip" style:left="{m.left + x(new Date(events[hoverEvent].date))}px">
				<div class="tip-date">{fmtDate(events[hoverEvent].date)}</div>
				<div>{events[hoverEvent].label}</div>
			</div>
		{/if}
	</div>

	{#if events.length}
		<ol class="events-key small muted">
			{#each events as ev (ev.date + ev.label)}
				<li><span class="num">{fmtDate(ev.date)}</span> — {ev.label}</li>
			{/each}
		</ol>
	{/if}
</figure>

<style>
	.chart {
		margin: 0;
	}
	.legend {
		display: flex;
		flex-wrap: wrap;
		gap: 0.35rem 1rem;
		font-size: 0.85rem;
		color: var(--fg-2);
		margin-bottom: 0.5rem;
	}
	.item {
		display: inline-flex;
		align-items: center;
		gap: 0.4rem;
	}
	.swatch {
		width: 0.75rem;
		height: 0.75rem;
		border-radius: 3px;
		display: inline-block;
		flex: none;
	}
	.plot {
		position: relative;
		width: 100%;
		/* Width comes from the page, never from the SVG we size from it. */
		contain: inline-size;
	}
	svg {
		display: block;
		overflow: visible;
		width: 100%;
		height: auto;
	}
	.plot:focus-visible {
		outline: 2px solid var(--focus);
		outline-offset: 4px;
		border-radius: 4px;
	}
	.grid {
		stroke: var(--rule);
		stroke-width: 1;
	}
	.axis {
		stroke: var(--rule-strong);
	}
	.ref {
		stroke: var(--muted);
		stroke-dasharray: 4 3;
	}
	.tick {
		font-size: 11px;
		fill: var(--muted);
		font-variant-numeric: tabular-nums;
	}
	.dot {
		opacity: 0.35;
	}
	.band {
		opacity: 0.14;
		stroke: none;
	}
	.trend {
		fill: none;
		stroke-width: 2;
		stroke-linecap: round;
	}
	.leader {
		stroke: var(--rule-strong);
	}
	.end-value {
		font-size: 12px;
		fill: var(--fg);
		font-variant-numeric: tabular-nums;
	}
	.end-value .v {
		font-weight: 650;
	}
	.end-value .lbl {
		fill: var(--fg-2);
	}
	.end {
		stroke: var(--fg-2);
		stroke-width: 1;
	}
	.end-label {
		font-size: 11px;
		fill: var(--fg-2);
		font-weight: 600;
	}
	.event line {
		stroke: var(--rule-strong);
		stroke-dasharray: 2 3;
	}
	.event circle {
		fill: var(--surface);
		stroke: var(--rule-strong);
	}
	.event text {
		font-size: 9px;
		fill: var(--fg-2);
		font-weight: 600;
		pointer-events: none;
	}
	.crosshair {
		stroke: var(--fg-2);
		stroke-width: 1;
	}
	.hover-dot {
		stroke: var(--surface);
		stroke-width: 2;
	}
	.overlay {
		fill: transparent;
		cursor: crosshair;
	}
	.tooltip {
		position: absolute;
		top: 0;
		transform: translateX(12px);
		background: var(--surface);
		border: 1px solid var(--rule-strong);
		border-radius: var(--radius);
		padding: 0.5rem 0.65rem;
		font-size: 0.8rem;
		pointer-events: none;
		min-width: 9.5rem;
		box-shadow: 0 4px 16px rgb(0 0 0 / 0.08);
	}
	.tooltip.flip {
		transform: translateX(calc(-100% - 12px));
	}
	.event-tip {
		max-width: 16rem;
		white-space: normal;
	}
	.tip-date {
		font-weight: 600;
		margin-bottom: 0.25rem;
	}
	.tip-row {
		display: flex;
		align-items: center;
		gap: 0.45rem;
	}
	.tip-label {
		flex: 1;
		color: var(--fg-2);
	}
	.tip-range {
		font-size: 0.72rem;
		color: var(--muted);
		font-variant-numeric: tabular-nums;
		min-width: 4.5rem;
		text-align: right;
	}
	.tip-v {
		font-variant-numeric: tabular-nums;
		font-weight: 600;
	}
	.events-key {
		margin: 0.75rem 0 0;
		padding-left: 1.4rem;
		columns: 2 18rem;
	}
</style>
