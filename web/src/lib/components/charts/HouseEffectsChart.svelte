<script lang="ts">
	import { party, partyColour } from '$lib/parties';

	interface HouseRow {
		pollster: string;
		party: string;
		median: number;
		lo: number;
		hi: number;
	}
	interface Props {
		effects: HouseRow[];
		coalLabel?: string;
	}
	let { effects, coalLabel = 'Coalition' }: Props = $props();

	const parties = $derived(
		['ALP', 'COAL', 'GRN', 'ONP'].filter((p) => effects.some((e) => e.party === p))
	);
	const pollsters = $derived([...new Set(effects.map((e) => e.pollster))].sort());
	const maxAbs = $derived(
		Math.max(3, Math.ceil(Math.max(...effects.map((e) => Math.max(Math.abs(e.lo), Math.abs(e.hi)))) + 0.5))
	);
	const pctX = (v: number) => 50 + (v / maxAbs) * 46;
	const partyName = (p: string) => (p === 'COAL' ? coalLabel : party(p).short);
</script>

<div class="grid">
	{#each parties as p (p)}
		{@const rows = pollsters
			.map((name) => effects.find((e) => e.pollster === name && e.party === p))
			.filter((r): r is HouseRow => r != null)
			.sort((a, b) => b.median - a.median)}
		<figure class="panel">
			<figcaption>
				<span class="swatch" style:background={partyColour(p)}></span>
				<strong>{partyName(p)}</strong>
			</figcaption>
			<ul class="rows">
				{#each rows as r (r.pollster)}
					{@const sig = r.lo > 0 || r.hi < 0}
					<li class:sig>
						<span class="name" title={r.pollster}>{r.pollster}</span>
						<span class="track">
							<span class="zero"></span>
							<span
								class="bar"
								style:left="{pctX(r.lo)}%"
								style:width="{Math.max(1, pctX(r.hi) - pctX(r.lo))}%"
								style:background={partyColour(p)}
							></span>
							<span class="dot" style:left="{pctX(r.median)}%" style:background={partyColour(p)}></span>
						</span>
						<span class="val num">{r.median > 0 ? '+' : ''}{r.median.toFixed(1)}</span>
					</li>
				{/each}
			</ul>
			<div class="axis small muted num">
				<span>−{maxAbs}</span>
				<span>0</span>
				<span>+{maxAbs} pts</span>
			</div>
		</figure>
	{/each}
</div>

<style>
	.grid {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(16.5rem, 1fr));
		gap: 1rem 1.5rem;
		margin: 0.75rem 0 1rem;
	}
	.panel {
		margin: 0;
		padding: 0.9rem 1rem;
		border: 1px solid var(--rule);
		border-radius: var(--radius-md);
		background: var(--surface);
	}
	figcaption {
		display: flex;
		align-items: center;
		gap: 0.45rem;
		margin-bottom: 0.65rem;
		font-size: 0.92rem;
	}
	.swatch {
		width: 0.65rem;
		height: 0.65rem;
		border-radius: 2px;
	}
	.rows {
		list-style: none;
		margin: 0;
		padding: 0;
		display: grid;
		gap: 0.4rem;
	}
	.rows li {
		display: grid;
		grid-template-columns: 7.5rem 1fr 2.6rem;
		gap: 0.5rem;
		align-items: center;
		font-size: 0.82rem;
		color: var(--fg-2);
	}
	.rows li.sig {
		color: var(--fg);
		font-weight: 600;
	}
	.name {
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}
	.track {
		position: relative;
		height: 0.9rem;
		background: linear-gradient(var(--rule), var(--rule)) center / 100% 1px no-repeat;
	}
	.zero {
		position: absolute;
		left: 50%;
		top: 0;
		bottom: 0;
		border-left: 1px dashed var(--fg-2);
		opacity: 0.6;
	}
	.bar {
		position: absolute;
		top: 0.3rem;
		height: 0.3rem;
		border-radius: 2px;
		opacity: 0.35;
	}
	.sig .bar {
		opacity: 0.65;
	}
	.dot {
		position: absolute;
		top: 0.12rem;
		width: 0.65rem;
		height: 0.65rem;
		border-radius: 50%;
		transform: translateX(-50%);
		border: 1.5px solid var(--surface);
	}
	.val {
		text-align: right;
	}
	.axis {
		display: grid;
		grid-template-columns: 7.5rem 1fr 2.6rem;
		margin-top: 0.45rem;
		font-size: 0.72rem;
	}
	.axis span:nth-child(1) {
		grid-column: 2;
		justify-self: start;
	}
	.axis span:nth-child(2) {
		grid-column: 2;
		grid-row: 1;
		justify-self: center;
	}
	.axis span:nth-child(3) {
		grid-column: 2;
		grid-row: 1;
		justify-self: end;
	}
</style>
