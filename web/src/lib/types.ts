// Contract for files published by the pipeline (pipeline/src/prophecy/publish).
// Phase 1 replaces these hand-written types with ones generated from JSON Schema.

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
	events: PollEvent[];
}
