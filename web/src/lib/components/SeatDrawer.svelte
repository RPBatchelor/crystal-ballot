<script lang="ts">
	import type { ForecastDistrict, Sims } from '$lib/types';
	import { conditionSims } from '$lib/sims';
	import { party, partyColour } from '$lib/parties';

	interface Props {
		district: ForecastDistrict | null;
		coalLabel: string;
		majority: number;
		resultsHref?: string;
		resultsYear?: number;
		sims?: Sims | null;
		onClose: () => void;
		onLockSeat?: (districtName: string, partyCode: string) => void;
	}
	let {
		district,
		coalLabel,
		majority,
		resultsHref,
		resultsYear,
		sims = null,
		onClose,
		onLockSeat
	}: Props = $props();

	const pct = (p: number) => (p < 0.005 ? '<1%' : p > 0.995 ? '>99%' : `${Math.round(p * 100)}%`);
	const blocOrder = ['ALP', 'COAL', 'GRN', 'ONP', 'IND', 'OTH'];

	const sortedProbs = $derived(
		district
			? Object.entries(district.probs)
					.filter(([, p]) => p >= 0.005)
					.sort((a, b) => b[1] - a[1])
			: []
	);

	const primRows = $derived(
		district
			? blocOrder
					.filter((b) => (district.primary[b]?.[2] ?? 0) >= 1)
					.map((b) => ({
						code: b,
						label: b === 'COAL' ? coalLabel : party(b).short,
						lo: district.primary[b][0],
						med: district.primary[b][1],
						hi: district.primary[b][2]
					}))
			: []
	);
	const primMax = $derived(
		Math.max(40, Math.ceil(Math.max(0, ...primRows.map((r) => r.hi)) / 10) * 10)
	);

	// Conditional impact of top two contenders winning this seat (when sims.bin is loaded).
	const impact = $derived.by(() => {
		if (!district || !sims) return null;
		const dIdx = sims.header.districts.indexOf(district.district);
		if (dIdx < 0) return null;
		const top = sortedProbs.slice(0, 2);
		return top.map(([code, prob]) => {
			const res = conditionSims(sims, { locks: { [dIdx]: code } }, majority);
			return { code, prob, res };
		});
	});

	function onKey(e: KeyboardEvent) {
		if (e.key === 'Escape' && district) onClose();
	}
</script>

<svelte:window onkeydown={onKey} />

{#if district}
	<div class="backdrop" role="presentation" onclick={onClose}></div>
	<div class="drawer" role="dialog" aria-modal="true" aria-label="{district.district} forecast">
		<header class="head">
			<div>
				<p class="eyebrow">{district.region} · held by {party(district.incumbent).short}</p>
				<h2>{district.district}</h2>
			</div>
			<button type="button" class="close" onclick={onClose} aria-label="Close seat details">✕</button>
		</header>

		<section class="block">
			<h3>Win probability</h3>
			<div class="probbar" role="img" aria-label={sortedProbs.map(([p, v]) => `${party(p).short} ${pct(v)}`).join(', ')}>
				{#each sortedProbs as [p, v] (p)}
					<span style:flex-grow={v} style:background={partyColour(p)}></span>
				{/each}
			</div>
			<ul class="problist">
				{#each sortedProbs as [p, v] (p)}
					<li>
						<span class="chip" style:--c={partyColour(p)}>{party(p).short}</span>
						<strong class="num">{pct(v)}</strong>
						{#if onLockSeat && sims}
							<button
								type="button"
								class="lock-btn"
								onclick={() => {
									onLockSeat(district.district, p);
									onClose();
								}}
							>
								What if {party(p).short} wins?
							</button>
						{/if}
					</li>
				{/each}
			</ul>
			{#if district.leader !== district.incumbent}
				<p class="flip-note small">
					<strong>Likely gain:</strong> {party(district.leader).short} favoured to gain from {party(district.incumbent).short} ({pct(district.leader_prob)}).
				</p>
			{/if}
		</section>

		{#if primRows.length}
			<section class="block">
				<h3>Forecast primary vote</h3>
				<p class="small muted">Median and 10th–90th percentile across simulations.</p>
				<ul class="forest">
					{#each primRows as r (r.code)}
						<li>
							<span class="lbl">{r.label}</span>
							<span class="track">
								<span
									class="range"
									style:left="{(100 * r.lo) / primMax}%"
									style:width="{(100 * (r.hi - r.lo)) / primMax}%"
									style:background={partyColour(r.code)}
								></span>
								<span
									class="dot"
									style:left="{(100 * r.med) / primMax}%"
									style:background={partyColour(r.code)}
								></span>
							</span>
							<span class="num v">{r.med.toFixed(1)}% <span class="muted small">({r.lo.toFixed(0)}–{r.hi.toFixed(0)})</span></span>
						</li>
					{/each}
				</ul>
			</section>
		{/if}

		{#if district.notes?.length}
			<section class="block">
				<h3>Local factors</h3>
				<ul class="notes small">
					{#each district.notes as note (note)}
						<li>{note}</li>
					{/each}
				</ul>
			</section>
		{/if}

		{#if impact && impact.length >= 2}
			<section class="block">
				<h3>What this seat means for government</h3>
				<p class="small muted">Conditioned on simulations where each party wins {district.district}:</p>
				<div class="impact-grid">
					{#each impact as item (item.code)}
						<div class="impact-card">
							<div class="small">If <span class="chip" style:--c={partyColour(item.code)}><strong>{party(item.code).short}</strong></span> wins</div>
							<div class="small muted num">
								{coalLabel} maj: <strong>{Math.round(item.res.outcome.coal_majority * 100)}%</strong> ·
								Hung: <strong>{Math.round(item.res.outcome.hung * 100)}%</strong> ·
								ALP maj: <strong>{Math.round(item.res.outcome.alp_majority * 100)}%</strong>
							</div>
						</div>
					{/each}
				</div>
			</section>
		{/if}

		{#if resultsHref}
			<footer class="foot">
				<a class="hist-link" href={resultsHref}>
					View {resultsYear ?? 'previous'} election results &amp; preference flows →
				</a>
			</footer>
		{/if}
	</div>
{/if}

<style>
	.backdrop {
		position: fixed;
		inset: 0;
		background: rgb(15 12 40 / 0.45);
		backdrop-filter: blur(2px);
		z-index: 40;
	}
	.drawer {
		position: fixed;
		top: 0;
		right: 0;
		bottom: 0;
		width: min(29rem, 94vw);
		background: var(--surface);
		border-left: 1px solid var(--rule-strong);
		box-shadow: -8px 0 32px rgb(15 12 40 / 0.22);
		z-index: 50;
		overflow-y: auto;
		padding: 1.5rem;
		display: flex;
		flex-direction: column;
		gap: 1.25rem;
	}
	.head {
		display: flex;
		justify-content: space-between;
		align-items: flex-start;
		gap: 1rem;
		border-bottom: 1px solid var(--rule);
		padding-bottom: 0.9rem;
	}
	.head h2 {
		margin: 0;
		font-size: 1.5rem;
	}
	.close {
		background: transparent;
		border: 1px solid var(--rule-strong);
		border-radius: var(--radius);
		color: var(--fg);
		font-size: 1rem;
		padding: 0.25rem 0.55rem;
		cursor: pointer;
	}
	.close:hover {
		background: var(--rule);
	}
	.block h3 {
		font-size: 0.95rem;
		margin: 0 0 0.45rem;
	}
	.probbar {
		display: flex;
		gap: 2px;
		height: 1rem;
		border-radius: 4px;
		overflow: hidden;
		margin-bottom: 0.6rem;
	}
	.probbar span {
		flex-basis: 0;
	}
	.problist {
		list-style: none;
		margin: 0;
		padding: 0;
		display: grid;
		gap: 0.4rem;
	}
	.problist li {
		display: flex;
		align-items: center;
		gap: 0.65rem;
		font-size: 0.92rem;
	}
	.lock-btn {
		margin-left: auto;
		font: inherit;
		font-size: 0.78rem;
		padding: 0.2rem 0.55rem;
		border: 1px solid var(--rule-strong);
		border-radius: 999px;
		background: var(--bg);
		color: var(--fg-2);
		cursor: pointer;
	}
	.lock-btn:hover {
		border-color: var(--fg);
		color: var(--fg);
	}
	.flip-note {
		margin: 0.6rem 0 0;
		padding: 0.45rem 0.7rem;
		background: color-mix(in srgb, var(--brand-spark) 18%, var(--bg));
		border-radius: var(--radius);
	}
	.chip {
		display: inline-flex;
		align-items: center;
		gap: 0.35rem;
	}
	.chip::before {
		content: '';
		width: 0.6rem;
		height: 0.6rem;
		border-radius: 2px;
		background: var(--c);
	}
	.forest {
		list-style: none;
		padding: 0;
		margin: 0.5rem 0 0;
		display: grid;
		gap: 0.5rem;
	}
	.forest li {
		display: grid;
		grid-template-columns: 5.2rem 1fr 7.2rem;
		gap: 0.5rem;
		align-items: center;
		font-size: 0.85rem;
	}
	.lbl {
		color: var(--fg-2);
	}
	.track {
		position: relative;
		height: 0.9rem;
		background: linear-gradient(var(--rule), var(--rule)) center / 100% 1px no-repeat;
	}
	.range {
		position: absolute;
		top: 0.25rem;
		height: 0.4rem;
		border-radius: 3px;
		opacity: 0.45;
	}
	.dot {
		position: absolute;
		top: 0.08rem;
		width: 0.72rem;
		height: 0.72rem;
		border-radius: 50%;
		transform: translateX(-50%);
		border: 2px solid var(--surface);
	}
	.v {
		text-align: right;
	}
	.notes {
		margin: 0;
		padding-left: 1.1rem;
		color: var(--fg-2);
	}
	.impact-grid {
		display: grid;
		gap: 0.5rem;
		margin-top: 0.5rem;
	}
	.impact-card {
		padding: 0.55rem 0.75rem;
		border: 1px solid var(--rule);
		border-radius: var(--radius);
		background: var(--bg);
		display: grid;
		gap: 0.2rem;
	}
	.foot {
		margin-top: auto;
		padding-top: 0.9rem;
		border-top: 1px solid var(--rule);
	}
	.hist-link {
		font-weight: 600;
		font-size: 0.9rem;
	}
</style>
