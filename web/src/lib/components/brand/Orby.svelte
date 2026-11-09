<!--
	Orby, the Crystal Ballot mascot: rides in the ballot box and holds up odds, never
	certainties. For empty states, loading screens and the methodology page.
-->
<script lang="ts">
	let {
		size = 180,
		card = '4 in 10',
		label = 'Orby, a smiling crystal ball riding in a ballot box and holding up a forecast card'
	}: { size?: number; card?: string; label?: string } = $props();
</script>

<svg width={size} height={(size * 240) / 220} viewBox="0 0 220 240" role="img" aria-label={label} class="orby">
	<ellipse cx="110" cy="228" rx="70" ry="8" fill="var(--rule)" />
	<rect x="82" y="200" width="14" height="26" rx="6" fill="var(--brand-box)" />
	<rect x="124" y="200" width="14" height="26" rx="6" fill="var(--brand-box)" />
	<g class="ball">
		<circle cx="110" cy="92" r="62" fill="var(--brand-glass)" stroke="var(--brand-box)" stroke-width="4" />
		<path d="M70 70 C 85 50, 100 52, 110 62" fill="none" stroke="var(--swirl-violet)" stroke-width="6" stroke-linecap="round" stroke-opacity="0.7" />
		<path d="M150 78 C 140 58, 126 56, 118 64" fill="none" stroke="var(--swirl-amber)" stroke-width="6" stroke-linecap="round" stroke-opacity="0.7" />
		<path d="M78 122 C 96 136, 124 136, 142 122" fill="none" stroke="var(--swirl-teal)" stroke-width="6" stroke-linecap="round" stroke-opacity="0.7" />
		<ellipse cx="80" cy="60" rx="14" ry="7" fill="#ffffff" transform="rotate(-35 80 60)" />
		<ellipse cx="92" cy="94" rx="8" ry="11" fill="#15123f" />
		<ellipse cx="128" cy="94" rx="8" ry="11" fill="#15123f" />
		<circle cx="95" cy="90" r="3" fill="#ffffff" />
		<circle cx="131" cy="90" r="3" fill="#ffffff" />
		<path d="M98 112 Q 110 122 122 112" fill="none" stroke="#15123f" stroke-width="4" stroke-linecap="round" />
		<circle cx="80" cy="110" r="6" fill="var(--swirl-amber)" fill-opacity="0.35" />
		<circle cx="140" cy="110" r="6" fill="var(--swirl-amber)" fill-opacity="0.35" />
	</g>
	<rect x="54" y="152" width="112" height="56" rx="10" fill="var(--brand-box)" />
	<rect x="46" y="144" width="128" height="16" rx="6" fill="var(--brand-lid)" />
	<path d="M92 182 L104 194 L128 170" fill="none" stroke="var(--brand-spark)" stroke-width="7" stroke-linecap="round" stroke-linejoin="round" />
	<path d="M174 158 C 186 150, 190 136, 186 124" fill="none" stroke="var(--brand-box)" stroke-width="8" stroke-linecap="round" />
	{#if card}
		<g transform="rotate(10 188 108)">
			<rect x="168" y="86" width="40" height="44" rx="5" fill="#ffffff" stroke="var(--brand-box)" stroke-width="3" />
			<text x="188" y="114" text-anchor="middle" style="font-family: var(--font-display)" font-weight="800" font-size="15" fill="#15123f">{card}</text>
		</g>
	{/if}
	<path class="spark" d="M30 40 L33 48 L41 51 L33 54 L30 62 L27 54 L19 51 L27 48 Z" fill="var(--brand-spark)" />
	<path class="spark" d="M190 30 L192 36 L198 38 L192 40 L190 46 L188 40 L182 38 L188 36 Z" fill="var(--brand-spark)" />
</svg>

<style>
	.orby {
		display: block;
		max-width: 100%;
		height: auto;
		overflow: visible;
	}
	.ball {
		transform-origin: 110px 150px;
		animation: bob 4s ease-in-out infinite;
	}
	.spark {
		transform-box: fill-box;
		transform-origin: center;
		animation: twinkle 2.6s ease-in-out infinite;
	}
	.spark:last-of-type {
		animation-delay: 1.3s;
	}
	@keyframes bob {
		0%,
		100% {
			transform: rotate(-2deg);
		}
		50% {
			transform: rotate(2deg);
		}
	}
	@keyframes twinkle {
		0%,
		100% {
			transform: scale(1);
			opacity: 1;
		}
		50% {
			transform: scale(0.7);
			opacity: 0.6;
		}
	}
	@media (prefers-reduced-motion: reduce) {
		.ball,
		.spark {
			animation: none;
		}
	}
</style>
