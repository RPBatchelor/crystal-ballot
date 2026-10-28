import { error } from '@sveltejs/kit';
import type { EntryGenerator, PageLoad } from './$types';
import { loadPreferences, loadResults } from '$lib/data';
import { getJurisdiction } from '$lib/jurisdictions';

// Seat pages are discovered by the prerender crawler from links on the results page.
export const entries: EntryGenerator = () => [];

export const load: PageLoad = async ({ fetch, params }) => {
	const jurisdiction = getJurisdiction(params.jur);
	if (!jurisdiction) error(404, 'Unknown jurisdiction');
	const results = await loadResults(fetch, params.jur, params.year);
	const seat = results.seats.find((s) => s.slug === params.seat);
	if (!seat) error(404, 'Unknown seat');
	const preferences = seat.has_dop
		? ((await loadPreferences(fetch, params.jur, params.year))[seat.slug] ?? [])
		: [];
	return { jurisdiction, year: Number(params.year), results, seat, preferences };
};
