import { error } from '@sveltejs/kit';
import type { EntryGenerator, PageLoad } from './$types';
import { JURISDICTIONS, getJurisdiction } from '$lib/jurisdictions';
import { loadForecast, loadGeo, loadResults } from '$lib/data';
import { boundarySet } from '$lib/maps';

export const entries: EntryGenerator = () =>
	JURISDICTIONS.flatMap((j) => (j.forecastYears ?? []).map((y) => ({ jur: j.code, year: String(y) })));

export const load: PageLoad = async ({ fetch, params }) => {
	const jurisdiction = getJurisdiction(params.jur);
	if (!jurisdiction?.forecastYears?.includes(Number(params.year))) error(404, 'No forecast for this election');
	const lastResults = jurisdiction.resultYears.at(-1);
	const boundaries = boundarySet(params.jur, Number(params.year));
	const [forecast, results, geo] = await Promise.all([
		loadForecast(fetch, params.jur, params.year),
		lastResults ? loadResults(fetch, params.jur, lastResults) : null,
		boundaries ? loadGeo(fetch, params.jur, boundaries) : null
	]);
	return { jurisdiction, year: Number(params.year), forecast, results, lastResults, geo };
};
