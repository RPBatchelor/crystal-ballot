import type { PageLoad } from './$types';

export interface Backtest {
	election_id: string;
	n_seats: number;
	brier: number;
	log_loss: number;
	favourite_accuracy: number;
	status_quo_accuracy: number;
	seats: Record<string, { actual: number; median: number; p90: [number, number]; covered_90: boolean }>;
	calibration: { bin: string; n: number; mean_prob: number; hit_rate: number }[];
	statewide: Record<string, { forecast: [number, number, number]; actual: number }>;
	outcome: { alp_majority: number; coal_majority: number; hung: number };
	misses: { district: string; won: string; favourite: string; p_fav: number; p_won: number }[];
}

export interface PollErrorRow {
	year: number;
	n_polls: number;
	ALP_error: number | null;
	COAL_error: number | null;
	GRN_error: number | null;
	tpp_error: number | null;
	tpp_poll: number | null;
	tpp_result: number | null;
}

export interface ModelFile {
	backtests: Backtest[];
	poll_error: PollErrorRow[];
	poll_error_settings: { sd: Record<string, number>; bias: Record<string, number>; window_days: number } | null;
}

const SOURCES = [
	{ code: 'vic', name: 'Victoria' },
	{ code: 'nsw', name: 'New South Wales' },
	{ code: 'qld', name: 'Queensland' },
	{ code: 'sa', name: 'South Australia' },
	{ code: 'wa', name: 'Western Australia' },
	{ code: 'federal', name: 'Federal' }
];

export const load: PageLoad = async ({ fetch }) => {
	const models = await Promise.all(
		SOURCES.map(async ({ code, name }) => {
			const res = await fetch(`/data/${code}/model.json`);
			return { code, name, model: res.ok ? ((await res.json()) as ModelFile) : null };
		})
	);
	return { models: models.filter((m) => m.model) };
};
