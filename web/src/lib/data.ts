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

/** A jurisdiction's single-member blind tests (oldest first), from its model.json. */
export interface BlindTest {
	year: number;
	seats: number;
	favourite: number; // share of seats the favourite won
	statusQuo: number; // share of seats kept by the party that held them
	brier: number;
}

export async function loadBlindTests(fetch: Fetch, jur: string): Promise<BlindTest[]> {
	const res = await fetch(`/data/${jur}/model.json`);
	if (!res.ok) return [];
	const m = (await res.json()) as {
		backtests?: { election_id: string; n_seats?: number; favourite_accuracy?: number; status_quo_accuracy?: number; brier?: number }[];
	};
	return (m.backtests ?? [])
		.filter((b) => b.favourite_accuracy != null && b.status_quo_accuracy != null && b.n_seats && b.brier != null)
		.map((b) => ({
			year: Number(b.election_id.slice(-4)),
			seats: b.n_seats!,
			favourite: b.favourite_accuracy!,
			statusQuo: b.status_quo_accuracy!,
			brier: b.brier!
		}))
		.sort((a, b) => a.year - b.year);
}

/** Daily headline history of a live forecast; null before the first stamped run. */
export async function loadForecastHistory(fetch: Fetch, jur: string, year: number | string) {
	const res = await fetch(`/data/${jur}/forecast/${year}-history.json`);
	return res.ok ? ((await res.json()) as import('./types').ForecastHistoryEntry[]) : null;
}

/** Every simulation behind a live forecast (about 2 MB): load after first paint. */
export async function loadSims(fetch: Fetch, jur: string, year: number | string) {
	const [h, b] = await Promise.all([
		fetch(`/data/${jur}/forecast/${year}-sims.json`),
		fetch(`/data/${jur}/forecast/${year}-sims.bin`)
	]);
	if (!h.ok || !b.ok) return null;
	const header = (await h.json()) as import('./types').SimsHeader;
	const buf = await b.arrayBuffer();
	if (buf.byteLength !== header.byte_length) return null; // header and file from different runs
	const view = (name: string) => {
		const f = header.layout.find((l) => l.name === name)!;
		const n = f.shape.reduce((a, c) => a * c, 1);
		return f.dtype === 'uint8' ? new Uint8Array(buf, f.offset, n) : new Int16Array(buf, f.offset, n);
	};
	return {
		header,
		winners: view('winners') as Uint8Array,
		statewide: view('statewide') as Int16Array,
		tpp: view('tpp') as Int16Array
	} satisfies import('./types').Sims;
}
