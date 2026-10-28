import { error } from '@sveltejs/kit';
import type { EntryGenerator, PageLoad } from './$types';
import { JURISDICTIONS, getJurisdiction } from '$lib/jurisdictions';
import { loadResults } from '$lib/data';

export const entries: EntryGenerator = () =>
	JURISDICTIONS.flatMap((j) => j.resultYears.map((y) => ({ jur: j.code, year: String(y) })));

export const load: PageLoad = async ({ fetch, params }) => {
	const jurisdiction = getJurisdiction(params.jur);
	if (!jurisdiction?.resultYears.includes(Number(params.year))) error(404, 'No results for this election');
	return { jurisdiction, year: Number(params.year), results: await loadResults(fetch, params.jur, params.year) };
};
