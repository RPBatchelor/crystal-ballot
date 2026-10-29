import { error } from '@sveltejs/kit';
import type { EntryGenerator, PageLoad } from './$types';
import { JURISDICTIONS, getJurisdiction } from '$lib/jurisdictions';
import { loadForecast, loadGeo } from '$lib/data';
import { boundarySet } from '$lib/maps';

export const entries: EntryGenerator = () =>
	JURISDICTIONS.flatMap((j) => (j.retroYears ?? []).map((y) => ({ jur: j.code, year: String(y) })));

export const load: PageLoad = async ({ fetch, params }) => {
	const jurisdiction = getJurisdiction(params.jur);
	const year = Number(params.year);
	if (!jurisdiction?.retroYears?.includes(year)) error(404, 'No retrospective forecast for this election');
	const boundaries = boundarySet(params.jur, year);
	const [forecast, geo] = await Promise.all([
		loadForecast(fetch, params.jur, year),
		boundaries ? loadGeo(fetch, params.jur, boundaries) : null
	]);
	if (!forecast.actual || !forecast.scores) error(404, 'No result to compare against');
	return { jurisdiction, year, forecast, geo };
};
