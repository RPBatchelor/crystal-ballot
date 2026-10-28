import { error } from '@sveltejs/kit';
import type { EntryGenerator, PageLoad } from './$types';
import { JURISDICTIONS, getJurisdiction } from '$lib/jurisdictions';
import { loadGeo, loadResults } from '$lib/data';
import { boundarySet, sameBoundaries } from '$lib/maps';

export const entries: EntryGenerator = () =>
	JURISDICTIONS.flatMap((j) => j.resultYears.map((y) => ({ jur: j.code, year: String(y) })));

export const load: PageLoad = async ({ fetch, params }) => {
	const jurisdiction = getJurisdiction(params.jur);
	const year = Number(params.year);
	if (!jurisdiction?.resultYears.includes(year)) error(404, 'No results for this election');
	const boundaries = boundarySet(params.jur, year);
	// Seat-level swing is only meaningful when boundaries are unchanged.
	const prevYear = jurisdiction.resultYears.filter((y) => y < year).at(-1);
	const [results, geo, previous] = await Promise.all([
		loadResults(fetch, params.jur, year),
		boundaries ? loadGeo(fetch, params.jur, boundaries) : null,
		prevYear && sameBoundaries(params.jur, year, prevYear) ? loadResults(fetch, params.jur, prevYear) : null
	]);
	return { jurisdiction, year, results, geo, previous, prevYear };
};
