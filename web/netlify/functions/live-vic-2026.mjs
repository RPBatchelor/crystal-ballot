/**
 * Netlify Function: /.netlify/functions/live-vic-2026
 * Live election-night feed for the 2026 Victorian state election.
 *
 * Primary source: ABC Elections live results SSR payload
 *   https://www.abc.net.au/news/elections/vic/2026/results
 *   (includes all 88 electorates, live % counted, live 2CP swingDial, and ABC seat calls).
 * Fallback / override: curated static JSON at `/data/vic/live/2026.json`.
 * Cached 45s at Netlify CDN so concurrent viewers share one upstream fetch.
 */

const ABC_RESULTS_URL =
	process.env.ABC_LIVE_URL || 'https://www.abc.net.au/news/elections/vic/2026/results';

const HEADERS = {
	'Content-Type': 'application/json; charset=utf-8',
	'Cache-Control': 'public, s-maxage=45, max-age=30, stale-while-revalidate=60'
};

function slugify(name) {
	return (name || '')
		.toLowerCase()
		.replace(/[^a-z0-9]+/g, '-')
		.replace(/^-|-$/g, '');
}

function mapParty(raw) {
	const s = (raw || '').toUpperCase().trim();
	if (s === 'ALP' || s.includes('LABOR')) return 'ALP';
	if (s === 'NAT' || s.includes('NATIONAL')) return 'NAT';
	if (s === 'LIB' || s === 'L/NP' || s.includes('LIBERAL')) return 'LIB';
	if (s === 'GRN' || s.includes('GREEN')) return 'GRN';
	if (s === 'ONP' || s === 'PHON' || s.includes('ONE NATION')) return 'ONP';
	if (s === 'IND' || s.includes('INDEPENDENT')) return 'IND';
	return 'OTH';
}

function findElectoratesAndSummary(obj) {
	let electorates = null;
	let summary = null;
	const walk = (node) => {
		if (!node || typeof node !== 'object') return;
		if (Array.isArray(node)) {
			if (!electorates && node.length >= 80 && node.length <= 95 && node[0]?.name && 'counted' in node[0]) {
				electorates = node;
				return;
			}
			for (const item of node) walk(item);
			return;
		}
		if (!summary && Array.isArray(node.results) && 'inDoubt' in node && 'totalSeats' in node) {
			summary = node;
		}
		for (const val of Object.values(node)) walk(val);
	};
	walk(obj);
	return { electorates, summary };
}

function parseAbcResultsHtml(html) {
	const m = html.match(/<script id="__NEXT_DATA__"[^>]*>([\s\S]*?)<\/script>/);
	if (!m) return null;
	const nextData = JSON.parse(m[1]);
	const { electorates, summary } = findElectoratesAndSummary(nextData?.props?.pageProps);
	if (!electorates || electorates.length < 50) return null;

	let tppAlpSum = 0;
	let tppCoalSum = 0;
	const districts = [];

	for (const e of electorates) {
		const slug = slugify(e.name);
		const pctCounted = Number.parseFloat(e.counted) || 0;
		const dial = Array.isArray(e.swingDial) ? e.swingDial : [];

		// Extract leading party, margin, and Labor 2PP from swingDial
		let dialSorted = dial
			.map((c) => {
				const cp = c.predicted2CP || c.simple2CP || c.predicted || c.simple || {};
				const pct = Number.parseFloat(cp.pct);
				const votes = Number(cp.votes) || 0;
				return {
					party: mapParty(c.party?.code || c.party?.name),
					pct: Number.isFinite(pct) ? pct : null,
					votes
				};
			})
			.filter((c) => c.pct != null && c.pct > 0)
			.sort((a, b) => b.pct - a.pct);

		let leadingParty = e.leadingCandidate?.party?.code
			? mapParty(e.leadingCandidate.party.code)
			: dialSorted[0]?.party ?? null;

		let margin = null;
		if (dialSorted.length >= 2) {
			margin = Number((dialSorted[0].pct - 50).toFixed(1));
		}

		// Accumulate classic Labor v Coalition 2PP when both appear in swingDial
		let tppAlp = null;
		if (dialSorted.length === 2) {
			const alp = dialSorted.find((c) => c.party === 'ALP');
			const coal = dialSorted.find((c) => c.party === 'LIB' || c.party === 'NAT');
			if (alp && coal) {
				tppAlp = Number(alp.pct.toFixed(1));
				if (alp.votes > 0 && coal.votes > 0) {
					tppAlpSum += alp.votes;
					tppCoalSum += coal.votes;
				}
			}
		}

		// Determine status: ABC official call vs likely/projected vs counting vs uncounted
		const predStr = (e.predicted?.predictionString || '').toUpperCase();
		const isAbcCalled =
			Boolean(e.isFinalResult) ||
			(e.isDoubtful === false && Boolean(leadingParty)) ||
			(predStr.startsWith('SAFE') || predStr.includes('WON'));
		const isAbcLikely = !isAbcCalled && predStr.startsWith('LIKELY') && Boolean(leadingParty);

		let status = 'uncounted';
		let calledParty = null;
		if (isAbcCalled && leadingParty) {
			status = 'called';
			calledParty = leadingParty;
		} else if (isAbcLikely) {
			status = 'projected';
		} else if (pctCounted > 0 || leadingParty) {
			status = 'counting';
		}

		districts.push({
			slug,
			district: e.name,
			status,
			called_party: calledParty,
			leading_party: leadingParty,
			margin,
			pct_counted: Number(pctCounted.toFixed(1)),
			tpp_alp: tppAlp,
			called_at: status === 'called' ? e.updated || summary?.updated || null : null,
			source: status === 'called' ? 'abc' : status === 'projected' ? 'projected' : 'abc'
		});
	}

	const seatsCalled = districts.filter((d) => d.status === 'called').length;
	const seatsReporting = districts.filter((d) => d.pct_counted > 0 || d.status === 'called').length;
	const statewidePct = Number.parseFloat(summary?.counted) || 0;
	const swTpp =
		tppAlpSum + tppCoalSum > 0
			? Number(((100 * tppAlpSum) / (tppAlpSum + tppCoalSum)).toFixed(1))
			: null;

	return {
		election_id: 'vic-2026',
		updated_at: summary?.updated || new Date().toISOString(),
		status: seatsCalled >= 88 ? 'final' : seatsReporting > 0 ? 'counting' : 'pre_polls',
		source: 'abc',
		note: null,
		seats_called: seatsCalled,
		seats_reporting: seatsReporting,
		pct_counted: Number(statewidePct.toFixed(1)),
		statewide_primary: { ALP: null, COAL: null, GRN: null, ONP: null },
		tpp_alp: swTpp,
		districts
	};
}

export const handler = async (event) => {
	const origin = event.headers?.host
		? `https://${event.headers.host}`
		: 'https://crystalballot.netlify.app';

	let base = {
		election_id: 'vic-2026',
		updated_at: new Date().toISOString(),
		status: 'pre_polls',
		source: 'netlify-function',
		note: null,
		seats_called: 0,
		seats_reporting: 0,
		pct_counted: 0,
		statewide_primary: { ALP: null, COAL: null, GRN: null, ONP: null },
		tpp_alp: null,
		districts: []
	};

	// 1. Load static/curated overrides (if any)
	try {
		const res = await fetch(`${origin}/data/vic/live/2026.json`, {
			headers: { 'Cache-Control': 'no-cache' }
		});
		if (res.ok) {
			const staticData = await res.json();
			base = { ...base, ...staticData };
		}
	} catch {
		// Continue
	}

	// 2. Fetch live ABC Elections 2026 results
	try {
		const abcRes = await fetch(ABC_RESULTS_URL, {
			headers: {
				'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) CrystalBallot/2.0',
				Accept: 'text/html'
			},
			signal: AbortSignal.timeout(10000)
		});
		if (abcRes.ok) {
			const html = await abcRes.text();
			const live = parseAbcResultsHtml(html);
			if (live) {
				// Preserve any explicit curated calls from static JSON
				const curated = new Map(
					(base.districts || []).filter((d) => d.source === 'curated').map((d) => [d.slug, d])
				);
				const mergedDistricts = live.districts.map((d) =>
					curated.has(d.slug) ? { ...d, ...curated.get(d.slug) } : d
				);
				base = {
					...live,
					districts: mergedDistricts,
					seats_called: mergedDistricts.filter((d) => d.status === 'called').length
				};
			}
		}
	} catch {
		// Fall back cleanly to static/curated JSON
	}

	return {
		statusCode: 200,
		headers: HEADERS,
		body: JSON.stringify(base)
	};
};
