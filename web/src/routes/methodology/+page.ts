import type { PageLoad } from './$types';
import type { ModelFile } from './model';

// Site order: the live forecast first, then the states, territories and federal.
const SOURCES = ['vic', 'nsw', 'qld', 'wa', 'sa', 'tas', 'act', 'nt', 'federal'];

export const load: PageLoad = async ({ fetch }) => {
	const models = await Promise.all(
		SOURCES.map(async (code) => {
			const res = await fetch(`/data/${code}/model.json`);
			return [code, res.ok ? ((await res.json()) as ModelFile) : null] as const;
		})
	);
	return { models: Object.fromEntries(models) as Record<string, ModelFile | null> };
};
