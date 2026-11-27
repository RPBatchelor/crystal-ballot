import { error } from '@sveltejs/kit';
import type { EntryGenerator, PageLoad } from './$types';
import { JURISDICTIONS, getJurisdiction } from '$lib/jurisdictions';
import { loadForecast, loadGeo, loadLeaders, loadLiveResults, loadResults } from '$lib/data';
import { boundarySet } from '$lib/maps';

export const entries: EntryGenerator = () =>
	JURISDICTIONS.flatMap((j) => (j.forecastYears ?? []).map((y) => ({ jur: j.code, year: String(y) })));

export const load: PageLoad = async ({ fetch, params }) => {
	const jurisdiction = getJurisdiction(params.jur);
	const year = Number(params.year);
	if (!jurisdiction?.forecastYears?.includes(year)) error(404, 'No live tracker for this election');
	const baselineYear = jurisdiction.resultYears.filter((y) => y < year).at(-1);
	const boundaries = boundarySet(params.jur, year);
	const [forecast, prevResults, geo, allLeaders, initialLive] = await Promise.all([
		loadForecast(fetch, params.jur, year),
		baselineYear ? loadResults(fetch, params.jur, baselineYear) : null,
		boundaries ? loadGeo(fetch, params.jur, boundaries) : null,
		loadLeaders(fetch),
		loadLiveResults(fetch, params.jur, year)
	]);
	const leaders = allLeaders[`${params.jur}-${year}`] ?? null;
	return { jurisdiction, year, forecast, prevResults, baselineYear, geo, leaders, initialLive };
};
