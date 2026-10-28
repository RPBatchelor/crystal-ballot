<script lang="ts">
	export interface HemiSeat {
		key: string;
		colour: string;
		opacity?: number;
		label: string;
		href?: string;
	}
	interface Props {
		title: string;
		/** Seats in left-to-right order (parties should be contiguous). */
		seats: HemiSeat[];
		majority: number;
		rows?: number;
	}
	let { title, seats, majority, rows }: Props = $props();

	const R0 = 0.36; // inner radius as a fraction of the outer

	// Parliament-diagram layout: seats per row proportional to radius; then every
	// position is sorted by angle (left to right) and filled in order, so each party
	// forms a wedge.
	// Rows chosen so the gap between rows matches the gap between seats along each arc.
	function bestRows(n: number) {
		let best = 3;
		let bestErr = Infinity;
		for (let k = 3; k <= 20; k++) {
			const d = (1 - R0) / (k - 1);
			const arc = Array.from({ length: k }, (_, i) => Math.PI * (R0 + d * i)).reduce((a, b) => a + b, 0);
			const err = Math.abs(arc / d - n);
			if (err < bestErr) [best, bestErr] = [k, err];
		}
		return best;
	}

	const layout = $derived.by(() => {
		const n = seats.length;
		const nRows = rows ?? bestRows(n);
		const radii = Array.from({ length: nRows }, (_, i) => R0 + ((1 - R0) * i) / (nRows - 1));
		const total = radii.reduce((a, b) => a + b, 0);
		const perRow = radii.map((r) => Math.round((n * r) / total));
		let diff = n - perRow.reduce((a, b) => a + b, 0);
		for (let i = nRows - 1; diff !== 0; i = (i - 1 + nRows) % nRows) {
			perRow[i] += Math.sign(diff);
			diff -= Math.sign(diff);
		}
		const pts: { r: number; a: number }[] = [];
		radii.forEach((r, i) => {
			const k = perRow[i];
			for (let j = 0; j < k; j++) pts.push({ r, a: Math.PI - (k === 1 ? Math.PI / 2 : (Math.PI * j) / (k - 1)) });
		});
		pts.sort((p, q) => q.a - p.a || p.r - q.r);
		const spacing = (1 - R0) / (nRows - 1);
		return { pts, dot: spacing * 0.46 };
	});

	let hover = $state<number | null>(null);
	const W = 2.2;
	const H = 1.18;
</script>

<figure class="hemi">
	<svg viewBox="{-W / 2} {-1.08} {W} {H}" role="img" aria-label={title}>
		{#each layout.pts as p, i (i)}
			{@const s = seats[i]}
			{#if s}
				<a href={s.href} aria-label={s.label}>
					<circle
						cx={Math.cos(p.a) * p.r}
						cy={-Math.sin(p.a) * p.r}
						r={hover === i ? layout.dot * 1.25 : layout.dot}
						fill={s.colour}
						fill-opacity={s.opacity ?? 1}
						class:dim={hover !== null && hover !== i}
						role="presentation"
						onpointerenter={() => (hover = i)}
						onpointerleave={() => (hover = null)}
					/>
				</a>
			{/if}
		{/each}
		<text class="total" x="0" y="-0.06" text-anchor="middle">{seats.length}</text>
		<text class="maj" x="0" y="0.07" text-anchor="middle">{majority} for majority</text>
	</svg>
	<p class="hover-label small" aria-live="polite">
		{#if hover !== null && seats[hover]}{seats[hover].label}{:else}&nbsp;{/if}
	</p>
</figure>

<style>
	.hemi {
		margin: 0 auto;
		width: 100%;
		max-width: 38rem;
	}
	svg {
		display: block;
		width: 100%;
		height: auto;
	}
	circle {
		stroke: var(--surface);
		stroke-width: 0.006;
		cursor: pointer;
		transition: r 100ms;
	}
	.dim {
		opacity: 0.55;
	}
	.total {
		font-family: var(--font-serif);
		font-size: 0.22px;
		font-weight: 700;
		fill: var(--fg);
	}
	.maj {
		font-size: 0.065px;
		fill: var(--muted);
	}
	.hover-label {
		text-align: center;
		margin: 0.25rem 0 0;
		color: var(--fg-2);
		min-height: 1.3em;
	}
</style>
