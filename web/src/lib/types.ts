// Contract for files published by the pipeline (pipeline/src/prophecy/publish).

export interface Poll {
	pollster: string;
	client: string | null;
	field_start: string;
	field_end: string;
	sample_size: number | null;
	ALP: number | null;
	COAL: number | null;
	GRN: number | null;
	ONP: number | null;
	IND: number | null;
	OTH: number | null;
	tpp_alp_vs_coal: number | null;
	tpp_alp_vs_onp: number | null;
	cycle?: string;
}

export interface TrendPoint {
	date: string;
	ALP: number | null;
	COAL: number | null;
	GRN: number | null;
	ONP: number | null;
	tpp_alp_vs_coal: number | null;
}

export interface PollEvent {
	event_date: string | null;
	description: string;
}

export interface PollsFile {
	election_id: string;
	jurisdiction: string;
	election_date: string;
	generated_at: string;
	polls: Poll[];
	trend: TrendPoint[];
	trend_method: string;
	election_date_known?: boolean;
	cycles?: { election_id: string; date: string }[];
	results?: ({ year: number; date: string; ALP: number | null; COAL: number | null; GRN: number | null; ONP: number | null; tpp_alp_vs_coal: number | null } & Record<string, unknown>)[];
	house_effects?: { pollster: string; party: string; median: number; lo: number; hi: number }[];
	events: PollEvent[];
}

export interface CandidateResult {
	candidate: string;
	party: string;
	party_name: string | null;
	votes: number;
	pct: number;
}

export interface ByElection {
	date: string;
	elected: string;
	party: string;
	primary: CandidateResult[];
	tcp: CandidateResult[];
}

export interface SeatResult {
	name: string;
	slug: string;
	elected: string;
	party: string;
	enrolment: number;
	formal: number;
	informal: number;
	primary: CandidateResult[];
	tcp: CandidateResult[];
	margin: number;
	tcp_estimated?: boolean;
	runner_up_party: string;
	tpp_alp: number | null;
	tpp_method: string | null;
	classic: boolean;
	has_dop: boolean;
	by_election: ByElection | null;
}

export interface ResultsFile {
	election_id: string;
	jurisdiction: string;
	date: string;
	seats_total: number;
	majority: number;
	seat_counts: Record<string, number>;
	primary_share: Record<string, number>;
	/** First-preference share by party code (LIB and NAT separate). */
	party_share?: Record<string, number>;
	tpp_alp: number;
	seats: SeatResult[];
}

export interface PreferenceCount {
	count: number;
	excluded: string;
	excluded_party: string;
	votes: number;
	to: { candidate: string; party: string; votes: number; pct: number }[];
}

export type PreferencesFile = Record<string, PreferenceCount[]>;

export interface ForecastDistrict {
	district: string;
	slug: string;
	region: string;
	incumbent: string;
	probs: Record<string, number>;
	primary: Record<string, [number, number, number]>;
	leader: string;
	leader_prob: number;
	notes?: string[];
	/** Retrospective forecasts only: what actually happened in the seat. */
	actual_winner?: string;
	actual_primary?: Record<string, number>;
	p_actual?: number;
}

export interface ForecastFile {
	election_id: string;
	jurisdiction: string;
	election_date: string;
	generated_at: string;
	/** When the seat simulation ran (matches the `-sims` files it produced). */
	simulated_at?: string;
	model_version: string;
	validated: boolean;
	diagnostics: { max_rhat?: number; min_ess_bulk?: number; divergences?: number };
	n_sims: number;
	majority: number;
	outcome: {
		alp_majority: number;
		coal_majority: number;
		hung: number;
		alp_most_seats: number;
		coal_most_seats: number;
	};
	/** Quantiles [5, 25, 50, 75, 95] of seats won. */
	seats: Record<string, [number, number, number, number, number]>;
	seat_hist: Record<string, number[]>;
	statewide_primary: Record<string, [number, number, number]>;
	tpp_alp: [number, number, number];
	/** Coalition seats minus Labor seats: counts[i] simulations had a margin of min + i. */
	seat_margin?: { min: number; counts: number[] };
	/** [Labor seats, Coalition seats, simulations] for every combination that occurred. */
	seat_joint?: [number, number, number][];
	/** Labor two-party vote (%): counts[i] simulations fell in [min + i*step, min + (i+1)*step). */
	tpp_hist?: { min: number; step: number; counts: number[] };
	districts: ForecastDistrict[];
	/** 'retrospective': a blind backtest shown as the eve-of-election forecast. */
	mode?: 'live' | 'retrospective';
	actual?: {
		seat_counts: Record<string, number>;
		primary: Record<string, number | null>;
		tpp_alp: number;
	};
	scores?: {
		brier: number;
		log_loss: number;
		favourite_accuracy: number;
		status_quo_accuracy: number;
		calibration: { bin: string; n: number; mean_prob: number; hit_rate: number }[];
		seats: Record<string, { actual: number; median: number; p90: [number, number]; covered_90: boolean }>;
	};
}

/** One day's headline forecast (`forecast/{year}-history.json`, oldest first). */
export interface ForecastHistoryEntry {
	date: string;
	simulated_at: string | null;
	outcome: ForecastFile['outcome'];
	/** Seats won: [5th percentile, median, 95th percentile]. */
	seats: Record<string, [number, number, number]>;
	tpp_alp: [number, number, number];
	statewide_primary: Record<string, [number, number, number]>;
	/** Win probability by district and party. */
	probs: Record<string, Record<string, number>>;
}

/** Describes `forecast/{year}-sims.bin`: every simulation, little-endian. */
export interface SimsHeader {
	n_sims: number;
	simulated_at: string;
	districts: string[];
	/** `winners` values index this list. */
	parties: string[];
	/** Column order of `statewide`. */
	blocs: string[];
	byte_length: number;
	layout: {
		name: 'winners' | 'statewide' | 'tpp';
		dtype: 'uint8' | 'int16';
		shape: number[];
		offset: number;
		/** Divide stored values by this (int16 fields hold tenths of a percent). */
		scale: number;
	}[];
}

/** Decoded simulations: row-major, one row per simulation. */
export interface Sims {
	header: SimsHeader;
	/** n_sims x districts: index into header.parties. */
	winners: Uint8Array;
	/** n_sims x blocs, tenths of a percent. */
	statewide: Int16Array;
	/** n_sims, ALP v Coalition 2PP in tenths of a percent. */
	tpp: Int16Array;
}
