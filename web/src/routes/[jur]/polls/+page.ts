import { error } from '@sveltejs/kit';
import type { EntryGenerator, PageLoad } from './$types';
import { JURISDICTIONS, getJurisdiction } from '$lib/jurisdictions';
import { loadPolls } from '$lib/data';

export const entries: EntryGenerator = () =>
	JURISDICTIONS.filter((j) => j.hasPolls).map((j) => ({ jur: j.code }));

export const load: PageLoad = async ({ fetch, params }) => {
	const jurisdiction = getJurisdiction(params.jur);
	if (!jurisdiction?.hasPolls) error(404, 'No polling for this jurisdiction yet');
	return { jurisdiction, polls: await loadPolls(fetch, jurisdiction.code) };
};
