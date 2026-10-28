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
