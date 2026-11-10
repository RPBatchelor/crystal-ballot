// Types of the model-evaluation data (static/data/<code>/model.json).

interface SeatRange {
	actual: number;
	median: number;
	p90: [number, number];
	covered_90: boolean;
}

interface Statewide {
	forecast: [number, number, number];
	actual: number | null;
}

/** A blind forecast of a single-member chamber, scored seat by seat. */
export interface Backtest {
	election_id: string;
	n_seats: number;
	brier: number;
	log_loss: number;
	favourite_accuracy: number;
	status_quo_accuracy: number;
	pendulum_accuracy?: number;
	seats: Record<string, SeatRange>;
	calibration: { bin: string; n: number; mean_prob: number; hit_rate: number }[];
	statewide: Record<string, Statewide>;
	outcome: { alp_majority: number; coal_majority: number; hung: number };
	misses: { district: string; won: string; favourite: string; p_fav: number; p_won: number }[];
}

/** A blind forecast of a Hare-Clark chamber (Tasmania, ACT), scored by seats per party. */
export interface HareClarkBacktest {
	election_id: string;
	n_divisions: number;
	seat_brier: number;
	seats: Record<string, SeatRange>;
	statewide: Record<string, Statewide>;
	outcome: { lib_majority: number; alp_majority: number; hung: number };
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
	backtests: (Backtest | HareClarkBacktest)[];
	poll_error: PollErrorRow[];
	poll_error_settings: { sd: Record<string, number>; bias: Record<string, number>; window_days: number } | null;
}

export const isHareClark = (b: Backtest | HareClarkBacktest): b is HareClarkBacktest => 'n_divisions' in b;
