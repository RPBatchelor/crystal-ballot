import { error } from '@sveltejs/kit';
import type { EntryGenerator, PageLoad } from './$types';
import { JURISDICTIONS, allForecastYears, getJurisdiction } from '$lib/jurisdictions';
import { loadForecast, loadForecastHistory, loadGeo, loadResults } from '$lib/data';
import { boundarySet } from '$lib/maps';

export const entries: EntryGenerator = () =>
	JURISDICTIONS.flatMap((j) => allForecastYears(j).map((y) => ({ jur: j.code, year: String(y) })));

export const load: PageLoad = async ({ fetch, params }) => {
	const jurisdiction = getJurisdiction(params.jur);
	const year = Number(params.year);
	if (!jurisdiction || !allForecastYears(jurisdiction).includes(year)) error(404, 'No forecast for this election');
	// Seat links go to that election's results when it has happened, else the latest.
	const lastResults = jurisdiction.resultYears.includes(year) ? year : jurisdiction.resultYears.at(-1);
	const boundaries = boundarySet(params.jur, Number(params.year));
	const live = jurisdiction.forecastYears?.includes(year) ?? false;
	const [forecast, results, geo, history] = await Promise.all([
		loadForecast(fetch, params.jur, params.year),
		lastResults ? loadResults(fetch, params.jur, lastResults) : null,
		boundaries ? loadGeo(fetch, params.jur, boundaries) : null,
		live ? loadForecastHistory(fetch, params.jur, params.year) : null
	]);
	return { jurisdiction, year: Number(params.year), forecast, results, lastResults, geo, history };
};
