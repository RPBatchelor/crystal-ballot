<script lang="ts">
	import type { SeatResult } from '$lib/types';
	import { bloc, party, partyColour } from '$lib/parties';
	import { displayName, fmtPct } from '$lib/format';

	interface Props {
		seats: SeatResult[];
		base: string;
	}
	let { seats, base }: Props = $props();

	type Key = 'name' | 'party' | 'margin' | 'tpp_alp' | 'ALP' | 'COAL' | 'GRN';
	let sortKey = $state<Key>('margin');
	let asc = $state(true);
	let query = $state('');
	let filter = $state('all');

	const primaryOf = (s: SeatResult, b: string) =>
		s.primary.filter((c) => bloc(c.party) === b).reduce((acc, c) => acc + c.pct, 0);

	const sortValue = (s: SeatResult, k: Key): string | number => {
		if (k === 'name') return s.name;
		if (k === 'party') return party(s.party).short;
		if (k === 'margin') return s.margin;
		if (k === 'tpp_alp') return s.tpp_alp ?? -1;
		return primaryOf(s, k);
	};

	const rows = $derived(
		seats
			.filter((s) => filter === 'all' || bloc(s.party) === filter)
			.filter((s) => !query || s.name.toLowerCase().includes(query.toLowerCase()))
			.toSorted((a, b) => {
				const va = sortValue(a, sortKey);
				const vb = sortValue(b, sortKey);
				const cmp = typeof va === 'string' ? va.localeCompare(vb as string) : va - (vb as number);
				return asc ? cmp : -cmp;
			})
	);

	function sortBy(k: Key) {
		if (sortKey === k) asc = !asc;
		else {
			sortKey = k;
			asc = k === 'name' || k === 'margin';
		}
	}

	const columns: { key: Key; label: string; left?: boolean }[] = [
		{ key: 'name', label: 'Seat', left: true },
		{ key: 'party', label: 'Held by', left: true },
		{ key: 'margin', label: 'Margin' },
		{ key: 'tpp_alp', label: 'ALP 2PP' },
		{ key: 'ALP', label: 'ALP 1st' },
		{ key: 'COAL', label: 'L/NP 1st' },
		{ key: 'GRN', label: 'GRN 1st' }
	];
	const filters = [
		{ v: 'all', l: 'All seats' },
		{ v: 'ALP', l: 'Labor' },
		{ v: 'COAL', l: 'Coalition' },
		{ v: 'GRN', l: 'Greens' }
	];
</script>

<div class="controls">
	<label class="search">
		<span class="visually-hidden">Search seats</span>
		<input type="search" placeholder="Search seats" bind:value={query} />
	</label>
	<div class="filters" role="group" aria-label="Filter by party">
		{#each filters as f (f.v)}
			<button type="button" aria-pressed={filter === f.v} onclick={() => (filter = f.v)}>{f.l}</button>
		{/each}
	</div>
	<span class="muted small">{rows.length} seats</span>
</div>

<div class="scroll-x">
	<table class="data">
		<thead>
			<tr>
				{#each columns as c (c.key)}
					<th
						class:left={c.left}
						aria-sort={sortKey === c.key ? (asc ? 'ascending' : 'descending') : 'none'}
					>
						<button type="button" onclick={() => sortBy(c.key)}>
							{c.label}{sortKey === c.key ? (asc ? ' ↑' : ' ↓') : ''}
						</button>
					</th>
				{/each}
			</tr>
		</thead>
		<tbody>
			{#each rows as s (s.slug)}
				<tr>
					<td class="left"><a href="{base}/{s.slug}/">{s.name}</a></td>
					<td class="left">
						<span class="chip" style:--c={partyColour(s.party)}>{party(s.party).short}</span>
						<span class="member muted">{displayName(s.elected)}</span>
					</td>
					<td>
						{s.margin.toFixed(1)}
						{#if !s.classic}<span class="muted small">v {party(s.runner_up_party).code}</span>{/if}
					</td>
					<td>{fmtPct(s.tpp_alp)}</td>
					<td>{fmtPct(primaryOf(s, 'ALP'))}</td>
					<td>{fmtPct(primaryOf(s, 'COAL'))}</td>
					<td>{fmtPct(primaryOf(s, 'GRN'))}</td>
				</tr>
			{/each}
		</tbody>
	</table>
</div>

<style>
	.controls {
		display: flex;
		flex-wrap: wrap;
		gap: 0.75rem;
		align-items: center;
		margin-bottom: 0.75rem;
	}
	input[type='search'] {
		font: inherit;
		font-size: 0.9rem;
		padding: 0.4rem 0.65rem;
		border: 1px solid var(--rule-strong);
		border-radius: var(--radius);
		background: var(--surface);
		color: var(--fg);
		width: 12rem;
	}
	.filters {
		display: flex;
		border: 1px solid var(--rule-strong);
		border-radius: var(--radius);
		overflow: hidden;
	}
	.filters button {
		font: inherit;
		font-size: 0.85rem;
		padding: 0.35rem 0.7rem;
		border: 0;
		background: var(--surface);
		color: var(--fg-2);
		cursor: pointer;
	}
	.filters button + button {
		border-left: 1px solid var(--rule-strong);
	}
	.filters button[aria-pressed='true'] {
		background: var(--fg);
		color: var(--bg);
	}
	th button {
		font: inherit;
		background: none;
		border: 0;
		padding: 0;
		color: inherit;
		cursor: pointer;
	}
	.chip {
		display: inline-flex;
		align-items: center;
		gap: 0.35rem;
		font-weight: 550;
	}
	.chip::before {
		content: '';
		width: 0.6rem;
		height: 0.6rem;
		border-radius: 2px;
		background: var(--c);
	}
	.member {
		margin-left: 0.4rem;
		font-size: 0.85rem;
	}
</style>
