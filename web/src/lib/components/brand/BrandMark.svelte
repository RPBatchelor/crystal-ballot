<!--
	Crystal Ballot mark: a crystal ball in the slot of a ballot box. The three swirls stand
	for the three-way race and use neutral brand colours, never party colours.
	Detail drops away as it shrinks (brand concept v1): `full` has sparkles and highlights,
	`icon` keeps the tick, `small` drops the tick for header and tab sizes.
-->
<script lang="ts">
	let {
		size = 40,
		variant = 'icon',
		label
	}: { size?: number; variant?: 'full' | 'icon' | 'small'; label?: string } = $props();
</script>

<svg
	width={size}
	height={size}
	viewBox="0 0 120 120"
	role={label ? 'img' : undefined}
	aria-label={label}
	aria-hidden={label ? undefined : 'true'}
	class="mark"
>
	{#if variant === 'full'}
		<circle cx="60" cy="40" r="28" fill="var(--brand-glass)" stroke="var(--brand-box)" stroke-width="3" />
		<circle cx="51" cy="44" r="10" fill="var(--swirl-teal)" fill-opacity="0.85" />
		<circle cx="69" cy="44" r="10" fill="var(--swirl-amber)" fill-opacity="0.85" />
		<circle cx="60" cy="29" r="10" fill="var(--swirl-violet)" fill-opacity="0.85" />
		<ellipse cx="48" cy="25" rx="7" ry="4" fill="#ffffff" transform="rotate(-30 48 25)" />
		<rect x="20" y="66" width="80" height="42" rx="6" fill="var(--brand-box)" />
		<rect x="14" y="60" width="92" height="11" rx="4" fill="var(--brand-lid)" />
		<path d="M46 86 L55 95 L74 76" fill="none" stroke="var(--brand-spark)" stroke-width="6" stroke-linecap="round" stroke-linejoin="round" />
		<path d="M100 6 L103 14 L111 17 L103 20 L100 28 L97 20 L89 17 L97 14 Z" fill="var(--brand-spark)" />
		<path d="M16 22 L18 27 L23 29 L18 31 L16 36 L14 31 L9 29 L14 27 Z" fill="var(--brand-spark)" />
	{:else if variant === 'icon'}
		<circle cx="60" cy="42" r="30" fill="var(--brand-glass)" stroke="var(--brand-box)" stroke-width="5" />
		<circle cx="50" cy="46" r="11" fill="var(--swirl-teal)" />
		<circle cx="70" cy="46" r="11" fill="var(--swirl-amber)" />
		<circle cx="60" cy="30" r="11" fill="var(--swirl-violet)" />
		<rect x="16" y="68" width="88" height="42" rx="8" fill="var(--brand-box)" />
		<rect x="10" y="62" width="100" height="13" rx="5" fill="var(--brand-lid)" />
		<path d="M44 88 L55 99 L76 78" fill="none" stroke="var(--brand-spark)" stroke-width="8" stroke-linecap="round" stroke-linejoin="round" />
	{:else}
		<circle cx="60" cy="42" r="30" fill="var(--brand-glass)" stroke="var(--brand-box)" stroke-width="7" />
		<circle cx="50" cy="46" r="12" fill="var(--swirl-teal)" />
		<circle cx="70" cy="46" r="12" fill="var(--swirl-amber)" />
		<circle cx="60" cy="30" r="12" fill="var(--swirl-violet)" />
		<rect x="10" y="64" width="100" height="46" rx="10" fill="var(--brand-box)" />
	{/if}
</svg>

<style>
	.mark {
		flex: none;
		display: block;
	}
</style>
