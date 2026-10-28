import type { PageLoad } from './$types';
import type { PollsFile } from '$lib/types';

export const load: PageLoad = async ({ fetch }) => {
	const res = await fetch('/data/vic/2026/polls.json');
	return { file: (await res.json()) as PollsFile };
};
