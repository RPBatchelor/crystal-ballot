<script lang="ts">
	import { geoMercator, geoPath, type GeoPermissibleObjects } from 'd3-geo';
	import type { FeatureCollection, Geometry } from 'geojson';
	import type { MapFrame } from '$lib/maps';

	export interface SeatProps {
		name: string;
		slug: string;
		region: string;
	}
	export interface LegendItem {
		label: string;
		colour: string;
		opacity?: number;
	}
	interface Props {
		title: string;
		geo: FeatureCollection<Geometry, SeatProps>;
		frame: MapFrame;
		fill: (slug: string) => string;
		opacity?: (slug: string) => number;
		tooltip: (slug: string) => { title: string; lines: string[] };
		href?: (slug: string) => string | undefined;
		legend?: LegendItem[];
		/** Continuous legend: CSS gradient + end labels. */
		gradient?: { css: string; left: string; mid?: string; right: string };
	}
	let { title, geo, frame, fill, opacity = () => 1, tooltip, href, legend = [], gradient }: Props = $props();

	// Inset frame on the capital city.
	const metro = $derived.by((): [number, number][] => {
		const { west, south, east, north } = frame.inset;
		return [
			[west, south],
			[east, south],
			[east, north],
			[west, north]
		];
	});
	const metroFit = $derived({ type: 'MultiPoint', coordinates: metro } as GeoPermissibleObjects);

	let width = $state(900);
	let hover = $state<string | null>(null);
	let tip = $state<{ x: number; y: number } | null>(null);

	const wide = $derived(width >= 760);
	const mainW = $derived(wide ? Math.round(width * 0.6) : width);
	const mainH = $derived(Math.round(mainW * frame.aspect));
	const insetW = $derived(wide ? width - mainW - 16 : width);
	const insetH = $derived(Math.round(insetW * (wide ? (frame.inset.aspect ?? 0.95) : 0.75)));

	const mainProj = $derived(geoMercator().fitSize([mainW, mainH], geo as GeoPermissibleObjects));
	const insetProj = $derived(geoMercator().fitSize([insetW, insetH], metroFit));
	const mainPath = $derived(geoPath(mainProj));
	const insetPath = $derived(geoPath(insetProj));
	const box = $derived.by(() => {
		const pts = metro.map((c) => mainProj(c)!);
		const xs = pts.map((p) => p[0]);
		const ys = pts.map((p) => p[1]);
		return { x: Math.min(...xs), y: Math.min(...ys), w: Math.max(...xs) - Math.min(...xs), h: Math.max(...ys) - Math.min(...ys) };
	});
	const clipId = `metro-${Math.random().toString(36).slice(2, 8)}`;

	function move(e: PointerEvent, slug: string) {
		hover = slug;
		const box = (e.currentTarget as Element).closest('.seatmap')!.getBoundingClientRect();
		tip = { x: e.clientX - box.left, y: e.clientY - box.top };
	}
	function leave() {
		hover = null;
		tip = null;
	}
	const hovered = $derived(hover ? tooltip(hover) : null);
	const hoverFeature = $derived(hover ? geo.features.find((f) => f.properties.slug === hover) : undefined);
</script>

{#snippet seats(path: ReturnType<typeof geoPath>, inset: boolean)}
	{#each geo.features as f (f.properties.slug)}
		{@const link = href?.(f.properties.slug)}
		<a href={link} aria-label={f.properties.name} tabindex={inset ? -1 : undefined}>
			<path
				d={path(f) ?? ''}
				fill={fill(f.properties.slug)}
				fill-opacity={opacity(f.properties.slug)}
				class="seat"
				role="presentation"
				onpointermove={(e) => move(e, f.properties.slug)}
				onpointerleave={leave}
				onfocus={() => (hover = f.properties.slug)}
				onblur={leave}
			/>
		</a>
	{/each}
	{#if hoverFeature}
		<path class="hl" d={path(hoverFeature) ?? ''} />
	{/if}
{/snippet}

<figure class="seatmap" bind:clientWidth={width} aria-label={title}>
	<div class="maps">
		<svg viewBox="0 0 {mainW} {mainH}" class="main" role="img" aria-label="{title}: {frame.state}">
			{@render seats(mainPath, false)}
			<rect class="frame" x={box.x} y={box.y} width={box.w} height={box.h} />
		</svg>
		<div class="inset">
			<span class="inset-label">{frame.inset.label}</span>
			<svg viewBox="0 0 {insetW} {insetH}" role="img" aria-label="{title}: {frame.inset.label}">
				<defs><clipPath id={clipId}><rect width={insetW} height={insetH} /></clipPath></defs>
				<g clip-path="url(#{clipId})">{@render seats(insetPath, true)}</g>
				<rect class="inset-border" width={insetW} height={insetH} />
			</svg>
		</div>
	</div>

	{#if legend.length || gradient}
		<div class="legend">
			{#each legend as l (l.label)}
				<span class="item">
					<span class="swatch" style:background={l.colour} style:opacity={l.opacity ?? 1}></span>{l.label}
				</span>
			{/each}
			{#if gradient}
				<span class="grad">
					<span class="end">{gradient.left}</span>
					<span class="bar" style:background={gradient.css}></span>
					<span class="end">{gradient.right}</span>
				</span>
				{#if gradient.mid}<span class="muted small">{gradient.mid}</span>{/if}
			{/if}
		</div>
	{/if}

	{#if hovered && tip}
		<div class="tooltip" style:left="{tip.x}px" style:top="{tip.y}px" class:flip={tip.x > width * 0.6}>
			<strong>{hovered.title}</strong>
			{#each hovered.lines as line (line)}<div>{line}</div>{/each}
		</div>
	{/if}
</figure>

<style>
	.seatmap {
		position: relative;
		margin: 0;
		/* Layout follows the figure's own width in CSS, so the prerendered page is right
		   before JavaScript measures it. */
		container-type: inline-size;
	}
	.maps {
		display: flex;
		flex-direction: column;
		gap: 16px;
	}
	@container (min-width: 760px) {
		.maps {
			flex-direction: row;
			align-items: flex-start;
		}
		.main {
			flex: 0 0 60%;
		}
	}
	svg {
		display: block;
		width: 100%;
		height: auto;
	}
	.inset {
		flex: 1;
		position: relative;
	}
	.inset-label {
		display: block;
		font-size: 0.78rem;
		font-weight: 600;
		color: var(--fg-2);
		margin-bottom: 0.25rem;
	}
	.seat {
		stroke: var(--surface);
		stroke-width: 0.6;
		cursor: pointer;
		transition: fill-opacity 120ms;
	}
	.hl {
		fill: none;
		stroke: var(--fg);
		stroke-width: 2;
		pointer-events: none;
	}
	.frame {
		fill: none;
		stroke: var(--fg-2);
		stroke-width: 1;
		stroke-dasharray: 3 2;
		pointer-events: none;
	}
	.inset-border {
		fill: none;
		stroke: var(--rule-strong);
		pointer-events: none;
	}
	a:focus-visible .seat {
		stroke: var(--focus);
		stroke-width: 2;
	}
	.legend {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 0.4rem 1.1rem;
		margin-top: 0.75rem;
		font-size: 0.85rem;
		color: var(--fg-2);
	}
	.item {
		display: inline-flex;
		align-items: center;
		gap: 0.4rem;
	}
	.swatch {
		width: 0.8rem;
		height: 0.8rem;
		border-radius: 2px;
	}
	.grad {
		display: inline-flex;
		align-items: center;
		gap: 0.5rem;
	}
	.grad .bar {
		width: 12rem;
		height: 0.7rem;
		border-radius: 3px;
	}
	.grad .end {
		font-size: 0.8rem;
	}
	.tooltip {
		position: absolute;
		transform: translate(14px, 14px);
		background: var(--surface);
		border: 1px solid var(--rule-strong);
		border-radius: var(--radius);
		padding: 0.45rem 0.65rem;
		font-size: 0.82rem;
		pointer-events: none;
		min-width: 10rem;
		box-shadow: 0 4px 16px rgb(0 0 0 / 0.1);
		z-index: 2;
	}
	.tooltip.flip {
		transform: translate(calc(-100% - 14px), 14px);
	}
</style>
