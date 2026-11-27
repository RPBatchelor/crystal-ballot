import type { PageLoad } from './$types';
import { loadForecast } from '$lib/data';

export const load: PageLoad = async ({ fetch }) => {
	try {
		const liveVic = await loadForecast(fetch, 'vic', 2026);
		return { liveVic };
	} catch {
		return { liveVic: null };
	}
};
