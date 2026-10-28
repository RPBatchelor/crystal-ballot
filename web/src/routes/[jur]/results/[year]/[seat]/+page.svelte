<script lang="ts">
	import type { PageData } from './$types';
	import VoteBars from '$lib/components/charts/VoteBars.svelte';
	import { displayName, fmtDate, fmtInt, fmtPct } from '$lib/format';
	import { party, partyColour } from '$lib/parties';

	let { data }: { data: PageData } = $props();
	const s = $derived(data.seat);
	const j = $derived(data.jurisdiction);
	const base = $derived(`/${j.code}/results/${data.year}`);
	const [winner, loser] = $derived(s.tcp);
	const by = $derived(s.by_election);

	const sorted = $derived(data.results.seats.toSorted((a, b) => a.name.localeCompare(b.name)));
	const idx = $derived(sorted.findIndex((x) => x.slug === s.slug));
	const prev = $derived(sorted[(idx - 1 + sorted.length) % sorted.length]);
	const next = $derived(sorted[(idx + 1) % sorted.length]);

	const turnout = $derived(((s.formal + s.informal) / s.enrolment) * 100);
	const informal = $derived((s.informal / (s.formal + s.informal)) * 100);
</script>

<svelte:head>
	<title>{s.name} {data.year} · Prophecy</title>
</svelte:head>

<nav class="crumbs small">
	<a href={base + '/'}>← {data.year} results</a>
	<span class="pn">
		<a href="{base}/{prev.slug}/">‹ {prev.name}</a>
		<a href="{base}/{next.slug}/">{next.name} ›</a>
	</span>
</nav>

<p class="eyebrow">{j.name} · District of</p>
<h1>{s.name}</h1>
<p class="lede">
	<span class="chip" style:--c={partyColour(s.party)}>{party(s.party).short}</span>
	{displayName(s.elected)} won in {data.year} by a margin of
	<strong>{s.margin.toFixed(1)}%</strong> over {party(loser.party, loser.party_name ?? undefined).short}.
	{#if by}
		<br /><span class="by"
			>A {fmtDate(by.date)} by-election was won by {displayName(by.elected)} ({party(by.party).short}).</span
		>
	{/if}
</p>

<div class="split">
	<section>
		<h2>Two-candidate preferred</h2>
		<div class="tcp" role="img" aria-label="{winner.candidate} {winner.pct}%, {loser.candidate} {loser.pct}%">
			<span style:width="{winner.pct}%" style:background={partyColour(winner.party)}></span>
			<span style:width="{loser.pct}%" style:background={partyColour(loser.party)}></span>
			<i class="half" aria-hidden="true"></i>
		</div>
		<div class="tcp-labels">
			<span><strong class="num">{winner.pct.toFixed(1)}%</strong> {displayName(winner.candidate)}</span>
			<span><strong class="num">{loser.pct.toFixed(1)}%</strong> {displayName(loser.candidate)}</span>
		</div>
		{#if s.tpp_alp != null && !s.classic}
			<p class="muted small">Labor v Coalition two-party-preferred: {fmtPct(s.tpp_alp)} Labor.</p>
		{/if}
	</section>
	<section class="facts">
		<h2>The count</h2>
		<dl>
			<dt>Enrolled</dt><dd class="num">{fmtInt(s.enrolment)}</dd>
			<dt>Turnout</dt><dd class="num">{turnout.toFixed(1)}%</dd>
			<dt>Formal votes</dt><dd class="num">{fmtInt(s.formal)}</dd>
			<dt>Informal</dt><dd class="num">{informal.toFixed(1)}%</dd>
			<dt>Candidates</dt><dd class="num">{s.primary.length}</dd>
		</dl>
	</section>
</div>

<h2>First preferences</h2>
<VoteBars candidates={s.primary} winner={s.elected} />

{#if data.preferences.length}
	<h2>How preferences flowed</h2>
	<p class="muted small">
		The VEC's full distribution of preferences: at each count the lowest candidate is excluded and their
		ballots pass to the next preference still in the count.
	</p>
	<ol class="counts">
		{#each data.preferences as c (c.count)}
			<li>
				<div class="count-head">
					<span class="muted small num">Count {c.count}</span>
					<strong>{displayName(c.excluded)}</strong>
					<span class="muted small">{party(c.excluded_party).short} · {fmtInt(c.votes)} ballots</span>
				</div>
				<div class="flow" role="img" aria-label="Preferences of {c.excluded}">
					{#each c.to.filter((t) => t.votes > 0) as t (t.candidate)}
						<span
							style:width="{t.pct}%"
							style:background={partyColour(t.party)}
							title="{displayName(t.candidate)} {t.pct}%"
						></span>
					{/each}
				</div>
				<div class="flow-key small">
					{#each c.to.filter((t) => t.pct >= 5) as t (t.candidate)}
						<span><i style:background={partyColour(t.party)}></i>{displayName(t.candidate)} <strong class="num">{t.pct}%</strong></span>
					{/each}
				</div>
			</li>
		{/each}
	</ol>
{/if}

{#if by}
	<h2>{fmtDate(by.date)} by-election</h2>
	<VoteBars candidates={by.primary} winner={by.elected} />
{/if}

<style>
	.crumbs {
		display: flex;
		justify-content: space-between;
		gap: 1rem;
		margin-bottom: 1rem;
	}
	.pn {
		display: flex;
		gap: 1rem;
	}
	.chip {
		display: inline-flex;
		align-items: center;
		gap: 0.35rem;
		font-weight: 600;
		color: var(--fg);
	}
	.chip::before {
		content: '';
		width: 0.7rem;
		height: 0.7rem;
		border-radius: 2px;
		background: var(--c);
	}
	.by {
		font-size: 0.95rem;
	}
	.split {
		display: grid;
		grid-template-columns: 2fr 1fr;
		gap: 2rem;
	}
	@media (max-width: 720px) {
		.split {
			grid-template-columns: 1fr;
		}
	}
	.tcp {
		position: relative;
		display: flex;
		gap: 2px;
		height: 2.25rem;
		margin-top: 1rem;
	}
	.tcp span:first-child {
		border-radius: 4px 0 0 4px;
	}
	.tcp span:last-of-type {
		border-radius: 0 4px 4px 0;
	}
	.half {
		position: absolute;
		left: 50%;
		top: -0.35rem;
		bottom: -0.35rem;
		border-left: 2px dashed var(--fg);
	}
	.tcp-labels {
		display: flex;
		justify-content: space-between;
		gap: 1rem;
		margin-top: 0.5rem;
		font-size: 0.9rem;
	}
	.tcp-labels span:last-child {
		text-align: right;
	}
	dl {
		display: grid;
		grid-template-columns: auto 1fr;
		gap: 0.3rem 1rem;
		margin: 1rem 0 0;
		font-size: 0.92rem;
	}
	dt {
		color: var(--muted);
	}
	dd {
		margin: 0;
		text-align: right;
	}
	.counts {
		list-style: none;
		padding: 0;
		margin: 0;
		display: grid;
		gap: 1rem;
	}
	.count-head {
		display: flex;
		flex-wrap: wrap;
		gap: 0.25rem 0.6rem;
		align-items: baseline;
	}
	.flow {
		display: flex;
		gap: 2px;
		height: 0.85rem;
		margin: 0.35rem 0;
	}
	.flow span:first-child {
		border-radius: 3px 0 0 3px;
	}
	.flow span:last-child {
		border-radius: 0 3px 3px 0;
	}
	.flow-key {
		display: flex;
		flex-wrap: wrap;
		gap: 0.2rem 1rem;
		color: var(--fg-2);
	}
	.flow-key i {
		display: inline-block;
		width: 0.6rem;
		height: 0.6rem;
		border-radius: 2px;
		margin-right: 0.35rem;
	}
</style>
