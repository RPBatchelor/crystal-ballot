import { error } from '@sveltejs/kit';
import type { PollsFile, PreferencesFile, ResultsFile } from './types';

type Fetch = typeof fetch;

async function getJSON<T>(fetch: Fetch, path: string): Promise<T> {
	const res = await fetch(path);
	if (!res.ok) error(404, `Data not found: ${path}`);
	return (await res.json()) as T;
}

export const loadPolls = (fetch: Fetch, jur: string) =>
	getJSON<PollsFile>(fetch, `/data/${jur}/polls.json`);

export const loadResults = (fetch: Fetch, jur: string, year: number | string) =>
	getJSON<ResultsFile>(fetch, `/data/${jur}/results/${year}.json`);

export const loadPreferences = (fetch: Fetch, jur: string, year: number | string) =>
	getJSON<PreferencesFile>(fetch, `/data/${jur}/results/${year}-preferences.json`);

export const loadForecast = (fetch: Fetch, jur: string, year: number | string) =>
	getJSON<import('./types').ForecastFile>(fetch, `/data/${jur}/forecast/${year}.json`);

export const loadGeo = (fetch: Fetch, jur: string, boundaries: string) =>
	getJSON<import('geojson').FeatureCollection<import('geojson').Geometry, import('./components/charts/SeatMap.svelte').SeatProps>>(
		fetch,
		`/data/${jur}/geo/${boundaries}.json`
	);
