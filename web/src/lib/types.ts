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
