<script lang="ts">
	import type { Sims } from '$lib/types';
	import { bellwetherSeats, conditionSims } from '$lib/sims';
	import OutcomeBar from '$lib/components/charts/OutcomeBar.svelte';
	import { party, partyColour } from '$lib/parties';

	interface Props {
		sims: Sims;
		majority: number;
		coalLabel: string;
		coalShortLabel: string;
		/** External locks passed in (e.g. from SeatDrawer). */
		locks?: Record<number, string>;
		onLocksChange?: (locks: Record<number, string>) => void;
		onSelectDistrict?: (districtName: string) => void;
	}
	let {
		sims,
		majority,
		coalLabel,
		coalShortLabel,
		locks = {},
		onLocksChange,
		onSelectDistrict
	}: Props = $props();

	let tppPreset = $state<'any' | 'coal_big' | 'close' | 'alp_surge'>('any');
	let onpPreset = $state<'any' | 'low' | 'mid' | 'high'>('any');
	let seatQuery = $state('');

	const hasOnp = $derived(sims.header.blocs.includes('ONP'));
	const bellwethers = $derived(bellwetherSeats(sims, majority, 8));

	const tppRange = $derived<[number, number] | null>(
		tppPreset === 'coal_big'
			? [0, 42]
			: tppPreset === 'close'
				? [44, 48]
				: tppPreset === 'alp_surge'
					? [48, 100]
					: null
	);
	const onpRange = $derived<[number, number] | null>(
		onpPreset === 'low' ? [0, 17] : onpPreset === 'mid' ? [17, 24] : onpPreset === 'high' ? [24, 100] : null
	);

	const activeCount = $derived(
		Object.keys(locks).length + (tppPreset !== 'any' ? 1 : 0) + (onpPreset !== 'any' ? 1 : 0)
	);
	const conditioned = $derived(conditionSims(sims, { locks, tppRange, onpRange }, majority));

	function setLock(dIdx: number, code: string | null) {
		const next = { ...locks };
		if (code == null || next[dIdx] === code) delete next[dIdx];
		else next[dIdx] = code;
		onLocksChange?.(next);
	}

	function resetAll() {
		tppPreset = 'any';
		onpPreset = 'any';
		onLocksChange?.({});
	}

	const searchMatches = $derived.by(() => {
		const q = seatQuery.trim().toLowerCase();
		if (!q) return [];
		return sims.header.districts
			.map((name, idx) => ({ name, idx }))
			.filter((d) => d.name.toLowerCase().includes(q))
			.slice(0, 6);
	});
</script>

<section class="explorer card">
	<div class="top">
		<div>
			<p class="eyebrow">Interactive · {sims.header.n_sims.toLocaleString()} simulations in browser</p>
			<h3>Election-night "What-If" scenario explorer</h3>
			<p class="small muted">
				Lock outcomes in key seats or filter the statewide vote to condition all {sims.header.n_sims.toLocaleString()}
				simulations in real time.
			</p>
		</div>
		{#if activeCount > 0}
			<button type="button" class="reset" onclick={resetAll}>Reset scenario ({activeCount})</button>
		{/if}
	</div>

	<div class="filters">
		<div class="filter-group">
			<span class="small muted">Labor 2PP</span>
			<div class="pills" role="group" aria-label="Filter by Labor 2PP">
				<button type="button" aria-pressed={tppPreset === 'any'} onclick={() => (tppPreset = 'any')}>Any</button>
				<button type="button" aria-pressed={tppPreset === 'coal_big'} onclick={() => (tppPreset = 'coal_big')}>&lt; 42%</button>
				<button type="button" aria-pressed={tppPreset === 'close'} onclick={() => (tppPreset = 'close')}>44–48%</button>
				<button type="button" aria-pressed={tppPreset === 'alp_surge'} onclick={() => (tppPreset = 'alp_surge')}>&ge; 48%</button>
			</div>
		</div>
		{#if hasOnp}
			<div class="filter-group">
				<span class="small muted">One Nation primary</span>
				<div class="pills" role="group" aria-label="Filter by One Nation primary">
					<button type="button" aria-pressed={onpPreset === 'any'} onclick={() => (onpPreset = 'any')}>Any</button>
					<button type="button" aria-pressed={onpPreset === 'low'} onclick={() => (onpPreset = 'low')}>&lt; 17%</button>
					<button type="button" aria-pressed={onpPreset === 'mid'} onclick={() => (onpPreset = 'mid')}>17–24%</button>
					<button type="button" aria-pressed={onpPreset === 'high'} onclick={() => (onpPreset = 'high')}>&ge; 24%</button>
				</div>
			</div>
		{/if}
		<div class="filter-group seat-picker">
			<span class="small muted">Lock a seat</span>
			<input type="search" placeholder="Add seat (e.g. Hawthorn)" bind:value={seatQuery} aria-label="Lock a seat winner" />
			{#if searchMatches.length}
				<ul class="dropdown">
					{#each searchMatches as d (d.idx)}
						<li>
							<span>{d.name}</span>
							<span class="quick">
								{#each ['ALP', 'COAL', 'GRN', 'ONP', 'IND'] as c (c)}
									<button
										type="button"
										style:--c={partyColour(c)}
										onclick={() => {
											setLock(d.idx, c);
											seatQuery = '';
										}}
									>{c === 'COAL' ? coalShortLabel : party(c).short}</button>
								{/each}
							</span>
						</li>
					{/each}
				</ul>
			{/if}
		</div>
	</div>

	{#if Object.keys(locks).length}
		<div class="active-locks">
			{#each Object.entries(locks) as [dStr, code] (dStr)}
				{@const dIdx = Number(dStr)}
				<button type="button" class="lock-chip" onclick={() => setLock(dIdx, null)}>
					<i style:background={partyColour(code)}></i>
					<strong>{sims.header.districts[dIdx]}</strong>: {code === 'COAL' ? coalShortLabel : party(code).short}
					<span aria-hidden="true">✕</span>
				</button>
			{/each}
		</div>
	{/if}

	{#if conditioned.matched === 0}
		<p class="empty small">
			<strong>0 matching simulations.</strong> That combination never occurred in {sims.header.n_sims.toLocaleString()} runs—try relaxing a filter.
		</p>
	{:else}
		<div class="result">
			<p class="small muted match-line">
				Matching <strong class="num">{conditioned.matched.toLocaleString()}</strong> of
				{conditioned.total.toLocaleString()} simulations ({((100 * conditioned.matched) / conditioned.total).toFixed(1)}%) ·
				Labor 2PP median <strong class="num">{conditioned.tpp[1].toFixed(1)}%</strong> ({conditioned.tpp[0].toFixed(1)}–{conditioned.tpp[2].toFixed(1)}%)
			</p>
			<OutcomeBar
				alpMajority={conditioned.outcome.alp_majority}
				hung={conditioned.outcome.hung}
				coalMajority={conditioned.outcome.coal_majority}
				coal={coalShortLabel}
			/>
			<div class="seat-pills num">
				{#each [['COAL', coalLabel], ['ALP', 'Labor'], ['GRN', 'Greens'], ['ONP', 'One Nation'], ['IND', 'Ind.']] as [k, lbl] (k)}
					{@const q = conditioned.seats[k]}
					{#if q && (q[2] > 0 || k === 'ALP' || k === 'COAL')}
						<div class="sp">
							<span class="small muted"><i style:background={partyColour(k)}></i>{lbl}</span>
							<strong>{q[1]}</strong>
							<span class="small muted">({q[0]}–{q[2]})</span>
						</div>
					{/if}
				{/each}
			</div>
		</div>
	{/if}

	{#if bellwethers.length}
		<div class="bellwethers">
			<h4>Bellwether seats to watch</h4>
			<p class="small muted">
				Seats whose winner shifts majority odds most strongly across all simulations. Click a party pill to lock that seat above.
			</p>
			<div class="scroll-x">
				<table class="data">
					<thead>
						<tr>
							<th class="left">Seat</th>
							<th>{coalShortLabel} maj if {coalShortLabel} wins</th>
							<th>{coalShortLabel} maj if lost</th>
							<th>Lock</th>
						</tr>
					</thead>
					<tbody>
						{#each bellwethers as b (b.districtIndex)}
							<tr>
								<td class="left">
									{#if onSelectDistrict}
										<button type="button" class="link-btn" onclick={() => onSelectDistrict(b.district)}>{b.district}</button>
									{:else}
										{b.district}
									{/if}
								</td>
								<td>{Math.round(b.coalMajIfCoal * 100)}%</td>
								<td>{Math.round(b.coalMajIfNotCoal * 100)}%</td>
								<td>
									<button
										type="button"
										class="mini"
										class:active={locks[b.districtIndex] === 'ALP'}
										onclick={() => setLock(b.districtIndex, 'ALP')}
									>ALP</button>
									<button
										type="button"
										class="mini"
										class:active={locks[b.districtIndex] === 'COAL'}
										onclick={() => setLock(b.districtIndex, 'COAL')}
									>{coalShortLabel}</button>
								</td>
							</tr>
						{/each}
					</tbody>
				</table>
			</div>
		</div>
	{/if}
</section>

<style>
	.explorer {
		margin-top: 1.5rem;
		display: grid;
		gap: 1.1rem;
	}
	.top {
		display: flex;
		justify-content: space-between;
		align-items: flex-start;
		gap: 1rem;
		flex-wrap: wrap;
	}
	.top h3 {
		margin: 0.1rem 0 0.25rem;
	}
	.top p {
		margin: 0;
	}
	.reset {
		font: inherit;
		font-size: 0.82rem;
		font-weight: 600;
		padding: 0.35rem 0.75rem;
		border: 1px solid var(--rule-strong);
		border-radius: 999px;
		background: var(--bg);
		color: var(--fg);
		cursor: pointer;
	}
	.reset:hover {
		background: var(--rule);
	}
	.filters {
		display: flex;
		flex-wrap: wrap;
		gap: 0.9rem 1.5rem;
		align-items: flex-end;
	}
	.filter-group {
		display: flex;
		flex-direction: column;
		gap: 0.3rem;
		position: relative;
	}
	.pills {
		display: inline-flex;
		border: 1px solid var(--rule-strong);
		border-radius: var(--radius);
		overflow: hidden;
	}
	.pills button {
		font: inherit;
		font-size: 0.82rem;
		padding: 0.3rem 0.65rem;
		border: 0;
		background: var(--bg);
		color: var(--fg-2);
		cursor: pointer;
	}
	.pills button + button {
		border-left: 1px solid var(--rule-strong);
	}
	.pills button[aria-pressed='true'] {
		background: var(--fg);
		color: var(--bg);
	}
	.seat-picker input {
		font: inherit;
		font-size: 0.85rem;
		padding: 0.3rem 0.6rem;
		border: 1px solid var(--rule-strong);
		border-radius: var(--radius);
		background: var(--bg);
		color: var(--fg);
		width: 13.5rem;
	}
	.dropdown {
		position: absolute;
		top: 100%;
		left: 0;
		z-index: 15;
		list-style: none;
		margin: 0.25rem 0 0;
		padding: 0.3rem;
		background: var(--surface);
		border: 1px solid var(--rule-strong);
		border-radius: var(--radius);
		box-shadow: var(--shadow);
		min-width: 19rem;
		display: grid;
		gap: 0.25rem;
	}
	.dropdown li {
		display: flex;
		justify-content: space-between;
		align-items: center;
		gap: 0.5rem;
		font-size: 0.85rem;
		padding: 0.2rem 0.35rem;
	}
	.quick {
		display: flex;
		gap: 0.25rem;
	}
	.quick button {
		font: inherit;
		font-size: 0.72rem;
		padding: 0.15rem 0.4rem;
		border: 1px solid var(--c);
		border-radius: 4px;
		background: transparent;
		color: var(--fg);
		cursor: pointer;
	}
	.quick button:hover {
		background: var(--c);
		color: #fff;
	}
	.active-locks {
		display: flex;
		flex-wrap: wrap;
		gap: 0.45rem;
	}
	.lock-chip {
		display: inline-flex;
		align-items: center;
		gap: 0.4rem;
		font: inherit;
		font-size: 0.82rem;
		padding: 0.25rem 0.65rem;
		border-radius: 999px;
		border: 1px solid var(--rule-strong);
		background: var(--bg);
		color: var(--fg);
		cursor: pointer;
	}
	.lock-chip i,
	.sp i {
		display: inline-block;
		width: 0.55rem;
		height: 0.55rem;
		border-radius: 2px;
		margin-right: 0.25rem;
	}
	.match-line {
		margin: 0 0 0.6rem;
	}
	.seat-pills {
		display: flex;
		flex-wrap: wrap;
		gap: 0.6rem 1.25rem;
		margin-top: 0.9rem;
		padding-top: 0.75rem;
		border-top: 1px solid var(--rule);
	}
	.sp {
		display: inline-flex;
		align-items: baseline;
		gap: 0.35rem;
	}
	.empty {
		padding: 0.75rem 1rem;
		background: var(--bg);
		border-radius: var(--radius);
		margin: 0;
	}
	.bellwethers {
		border-top: 1px solid var(--rule);
		padding-top: 1rem;
	}
	.bellwethers h4 {
		margin: 0 0 0.2rem;
		font-size: 0.98rem;
	}
	.bellwethers p {
		margin: 0 0 0.6rem;
	}
	.link-btn {
		font: inherit;
		font-weight: 550;
		background: none;
		border: 0;
		padding: 0;
		color: inherit;
		text-decoration: underline;
		text-decoration-color: var(--rule-strong);
		cursor: pointer;
	}
	.mini {
		font: inherit;
		font-size: 0.74rem;
		padding: 0.15rem 0.45rem;
		border: 1px solid var(--rule-strong);
		border-radius: 4px;
		background: var(--bg);
		color: var(--fg-2);
		cursor: pointer;
		margin-left: 0.2rem;
	}
	.mini.active {
		background: var(--fg);
		color: var(--bg);
		border-color: var(--fg);
	}
</style>
