import { error } from '@sveltejs/kit';
import type { EntryGenerator, PageLoad } from './$types';
import { JURISDICTIONS, getJurisdiction } from '$lib/jurisdictions';
import { loadForecast, loadResults } from '$lib/data';

export const entries: EntryGenerator = () =>
	JURISDICTIONS.flatMap((j) => (j.forecastYears ?? []).map((y) => ({ jur: j.code, year: String(y) })));

export const load: PageLoad = async ({ fetch, params }) => {
	const jurisdiction = getJurisdiction(params.jur);
	if (!jurisdiction?.forecastYears?.includes(Number(params.year))) error(404, 'No forecast for this election');
	const lastResults = jurisdiction.resultYears.at(-1);
	const [forecast, results] = await Promise.all([
		loadForecast(fetch, params.jur, params.year),
		lastResults ? loadResults(fetch, params.jur, lastResults) : null
	]);
	return { jurisdiction, year: Number(params.year), forecast, results, lastResults };
};
