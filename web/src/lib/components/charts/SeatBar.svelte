<script lang="ts">
	import { partyColour, party } from '$lib/parties';

	interface Segment {
		code: string;
		seats: number;
		label?: string;
	}
	interface Props {
		segments: Segment[];
		total: number;
		majority: number;
		title: string;
	}
	let { segments, total, majority, title }: Props = $props();

	let hover = $state<string | null>(null);
	const withOffsets = $derived.by(() => {
		let acc = 0;
		return segments
			.filter((s) => s.seats > 0)
			.map((s) => {
				const start = acc;
				acc += s.seats;
				return { ...s, start, label: s.label ?? party(s.code).short };
			});
	});
</script>

<figure class="seatbar">
	<div class="bar" role="img" aria-label={title}>
		{#each withOffsets as s (s.code)}
			<div
				class="seg"
				class:dim={hover && hover !== s.code}
				style:left="{(100 * s.start) / total}%"
				style:width="calc({(100 * s.seats) / total}% - 2px)"
				style:background={partyColour(s.code)}
				role="presentation"
				onpointerenter={() => (hover = s.code)}
				onpointerleave={() => (hover = null)}
				title="{s.label}: {s.seats} seats"
			></div>
		{/each}
		<div class="majority" style:left="{(100 * majority) / total}%">
			<span>{majority} for majority</span>
		</div>
	</div>
	<ul class="key">
		{#each withOffsets as s (s.code)}
			<li class:dim={hover && hover !== s.code}>
				<span class="swatch" style:background={partyColour(s.code)}></span>
				<span class="lbl">{s.label}</span>
				<strong class="num">{s.seats}</strong>
			</li>
		{/each}
	</ul>
</figure>

<style>
	.seatbar {
		margin: 0;
		padding-top: 1.4rem;
	}
	.bar {
		position: relative;
		height: 2.25rem;
	}
	.seg {
		position: absolute;
		top: 0;
		bottom: 0;
		border-radius: 4px;
		transition: opacity 120ms;
	}
	.dim {
		opacity: 0.35;
	}
	.majority {
		position: absolute;
		top: -0.4rem;
		bottom: -0.4rem;
		border-left: 2px solid var(--fg);
	}
	.majority span {
		position: absolute;
		bottom: 100%;
		left: 0;
		transform: translateX(-50%);
		font-size: 0.75rem;
		font-weight: 600;
		white-space: nowrap;
		color: var(--fg-2);
	}
	.key {
		list-style: none;
		padding: 0;
		margin: 0.75rem 0 0;
		display: flex;
		flex-wrap: wrap;
		gap: 0.35rem 1.25rem;
		font-size: 0.9rem;
	}
	.key li {
		display: flex;
		align-items: center;
		gap: 0.4rem;
	}
	.swatch {
		width: 0.75rem;
		height: 0.75rem;
		border-radius: 3px;
	}
	.lbl {
		color: var(--fg-2);
	}
</style>
