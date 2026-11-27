/**
 * Netlify Function: /.netlify/functions/live-vic-2026
 * Hybrid election-night feed:
 *   1. Reads curated/committed live JSON from `/data/vic/live/2026.json` on the same origin.
 *   2. Optionally fetches VEC's 2026 live results index (if VEC_LIVE_URL is set or once polls close)
 *      and merges any newly reported districts.
 *   3. Returns normalized LiveResultsFile JSON with a 45s CDN cache so concurrent viewers never
 *      hammer VEC.
 */

const DEFAULT_VEC_URL =
	process.env.VEC_LIVE_URL ||
	'https://www.vec.vic.gov.au/results/state-election-results/2026-state-election-results';

const HEADERS = {
	'Content-Type': 'application/json; charset=utf-8',
	'Cache-Control': 'public, s-maxage=45, max-age=30, stale-while-revalidate=60'
};

function slugify(name) {
	return name
		.toLowerCase()
		.replace(/[^a-z0-9]+/g, '-')
		.replace(/^-|-$/g, '');
}

function mapParty(raw) {
	const s = (raw || '').toUpperCase();
	if (s.includes('LABOR') || s === 'ALP') return 'ALP';
	if (s.includes('NATIONAL') || s === 'NAT') return 'NAT';
	if (s.includes('LIBERAL') || s === 'LIB') return 'LIB';
	if (s.includes('GREEN') || s === 'GRN') return 'GRN';
	if (s.includes('ONE NATION') || s === 'ONP' || s === 'PHON') return 'ONP';
	if (s.includes('INDEPENDENT') || s === 'IND') return 'IND';
	return 'OTH';
}

/**
 * Best-effort parser for VEC's summary table if published on election night.
 * Returns null if VEC hasn't opened the live tally room yet or HTML differs.
 */
function parseVecSummaryHtml(html) {
	// Look for standard VEC summary rows: District link + party + % counted / margin if present
	const rows = [];
	const trRe = /<tr[^>]*>([\s\S]*?)<\/tr>/gi;
	let m;
	while ((m = trRe.exec(html))) {
		const cells = [...m[1].matchAll(/<t[dh][^>]*>([\s\S]*?)<\/t[dh]>/gi)].map((c) =>
			c[1].replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ').trim()
		);
		if (cells.length < 3) continue;
		const linkMatch = m[1].match(/href="[^"]*\/([a-z0-9-]+)-district-results"/i);
		if (!linkMatch) continue;
		const slug = slugify(linkMatch[1]);
		const party = mapParty(cells[1] || cells[2]);
		const pctMatch = cells.join(' ').match(/(\d+(?:\.\d+)?)\s*%/);
		const pct = pctMatch ? Number(pctMatch[1]) : 0;
		const isElected = /elected|declared|won/i.test(cells.join(' '));
		rows.push({
			slug,
			status: isElected ? 'called' : pct > 0 ? 'counting' : 'uncounted',
			called_party: isElected ? party : null,
			leading_party: pct > 0 ? party : null,
			pct_counted: pct,
			source: 'vec'
		});
	}
	return rows.length >= 10 ? rows : null;
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

	// 1. Load static/curated live JSON (updated by prophecy live-poll or manual commits)
	try {
		const res = await fetch(`${origin}/data/vic/live/2026.json`, {
			headers: { 'Cache-Control': 'no-cache' }
		});
		if (res.ok) {
			const staticData = await res.json();
			base = { ...base, ...staticData };
		}
	} catch {
		// Continue with empty base
	}

	// 2. After polls close (2026-11-28 07:00 UTC = 6:00 PM AEDT), also poll VEC live summary
	const pollsClosed = Date.now() >= Date.parse('2026-11-28T07:00:00Z');
	if (pollsClosed && base.status !== 'final') {
		try {
			const vecRes = await fetch(DEFAULT_VEC_URL, {
				headers: { 'User-Agent': 'CrystalBallot/2.0 (election-night-tracker)' },
				signal: AbortSignal.timeout(8000)
			});
			if (vecRes.ok) {
				const html = await vecRes.text();
				const parsed = parseVecSummaryHtml(html);
				if (parsed) {
					const bySlug = new Map((base.districts || []).map((d) => [d.slug, d]));
					for (const row of parsed) {
						const existing = bySlug.get(row.slug);
						// Curated calls always take precedence over automated scrapes
						if (existing?.source === 'curated') continue;
						bySlug.set(row.slug, { ...(existing || {}), ...row });
					}
					const districts = [...bySlug.values()];
					const seatsCalled = districts.filter((d) => d.status === 'called').length;
					const seatsReporting = districts.filter((d) => (d.pct_counted || 0) > 0).length;
					const avgPct =
						districts.length > 0
							? districts.reduce((a, d) => a + (d.pct_counted || 0), 0) / districts.length
							: 0;
					base = {
						...base,
						updated_at: new Date().toISOString(),
						status: seatsCalled >= 88 ? 'final' : seatsReporting > 0 ? 'counting' : base.status,
						source: 'vec+curated',
						seats_called: seatsCalled,
						seats_reporting: seatsReporting,
						pct_counted: Number(avgPct.toFixed(1)),
						districts
					};
				}
			}
		} catch {
			// Fall back cleanly to static/curated JSON
		}
	}

	return {
		statusCode: 200,
		headers: HEADERS,
		body: JSON.stringify(base)
	};
};
