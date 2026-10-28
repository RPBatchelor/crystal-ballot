import { error } from '@sveltejs/kit';
import type { EntryGenerator, PageLoad } from './$types';
import { JURISDICTIONS, getJurisdiction } from '$lib/jurisdictions';
import { loadPolls, loadResults } from '$lib/data';

export const entries: EntryGenerator = () => JURISDICTIONS.map((j) => ({ jur: j.code }));

export const load: PageLoad = async ({ fetch, params }) => {
	const jurisdiction = getJurisdiction(params.jur);
	if (!jurisdiction) error(404, 'Unknown jurisdiction');
	const lastYear = jurisdiction.resultYears.at(-1);
	const [polls, results] = await Promise.all([
		jurisdiction.hasPolls ? loadPolls(fetch, jurisdiction.code) : null,
		lastYear ? loadResults(fetch, jurisdiction.code, lastYear) : null
	]);
	return { jurisdiction, polls, results };
};
