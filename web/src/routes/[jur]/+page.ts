import { error } from '@sveltejs/kit';
import type { EntryGenerator, PageLoad } from './$types';
import { JURISDICTIONS, getJurisdiction } from '$lib/jurisdictions';
import { loadForecast, loadPolls, loadResults } from '$lib/data';

export const entries: EntryGenerator = () => JURISDICTIONS.map((j) => ({ jur: j.code }));

export const load: PageLoad = async ({ fetch, params }) => {
	const jurisdiction = getJurisdiction(params.jur);
	if (!jurisdiction) error(404, 'Unknown jurisdiction');
	const lastYear = jurisdiction.resultYears.at(-1);
	// With no live forecast, the hub leads with the latest retrospective one.
	const retroYear = jurisdiction.forecastYears?.length ? undefined : jurisdiction.retroYears?.at(-1);
	const [polls, results, retro] = await Promise.all([
		jurisdiction.hasPolls ? loadPolls(fetch, jurisdiction.code) : null,
		lastYear ? loadResults(fetch, jurisdiction.code, lastYear) : null,
		retroYear ? loadForecast(fetch, jurisdiction.code, retroYear) : null
	]);
	return { jurisdiction, polls, results, retro, retroYear };
};
