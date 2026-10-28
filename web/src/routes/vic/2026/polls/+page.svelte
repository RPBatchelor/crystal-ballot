<script lang="ts">
	import type { PageData } from './$types';

	let { data }: { data: PageData } = $props();
	const file = $derived(data.file);

	const fmtDate = (iso: string) =>
		new Date(iso).toLocaleDateString('en-AU', { day: 'numeric', month: 'short', year: 'numeric' });
	const pct = (v: number | null) => (v === null ? '–' : `${v}`);
</script>

<svelte:head>
	<title>Victorian polls 2026 · Prophecy</title>
</svelte:head>

<h1>Victorian state voting intention</h1>
<p class="muted">
	{file.polls.length} polls since the 2022 election · election {fmtDate(file.election_date)} ·
	updated {fmtDate(file.generated_at)}
</p>

<div class="scroll">
	<table>
		<thead>
			<tr>
				<th class="left">Fieldwork end</th>
				<th class="left">Pollster</th>
				<th>n</th>
				<th class="alp">ALP</th>
				<th class="coal">L/NP</th>
				<th class="grn">GRN</th>
				<th class="onp">ONP</th>
				<th>IND</th>
				<th>OTH</th>
				<th>2PP ALP v L/NP</th>
				<th>2PP ALP v ONP</th>
			</tr>
		</thead>
		<tbody>
			{#each file.polls as p (p.pollster + p.field_end)}
				<tr>
					<td class="left">{fmtDate(p.field_end)}</td>
					<td class="left">{p.pollster}</td>
					<td>{p.sample_size?.toLocaleString() ?? '–'}</td>
					<td>{pct(p.ALP)}</td>
					<td>{pct(p.COAL)}</td>
					<td>{pct(p.GRN)}</td>
					<td>{pct(p.ONP)}</td>
					<td>{pct(p.IND)}</td>
					<td>{pct(p.OTH)}</td>
					<td>{pct(p.tpp_alp_vs_coal)}</td>
					<td>{pct(p.tpp_alp_vs_onp)}</td>
				</tr>
			{/each}
		</tbody>
	</table>
</div>

<p class="muted small">
	Source: pollster releases as compiled on Wikipedia; values are primary-vote %. ONP/IND blank
	means not reported separately (included in OTH).
</p>

<style>
	.muted {
		color: var(--muted);
	}
	.small {
		font-size: 0.85rem;
	}
	.scroll {
		overflow-x: auto;
	}
	table {
		border-collapse: collapse;
		font-variant-numeric: tabular-nums;
		font-size: 0.9rem;
		width: 100%;
	}
	th,
	td {
		padding: 0.35rem 0.6rem;
		text-align: right;
		border-bottom: 1px solid var(--rule);
		white-space: nowrap;
	}
	.left {
		text-align: left;
	}
	th.alp {
		color: var(--alp);
	}
	th.coal {
		color: var(--coal);
	}
	th.grn {
		color: var(--grn);
	}
	th.onp {
		color: var(--onp);
	}
</style>
