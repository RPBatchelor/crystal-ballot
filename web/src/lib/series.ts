import { partyColour } from './parties';

/** Fixed series order for primary-vote charts: colour follows the party, never the rank. */
export const primarySeries = (coal = 'Coalition') =>
	PRIMARY_SERIES.map((s) => (s.key === 'COAL' ? { ...s, label: coal } : s));

export const PRIMARY_SERIES = [
	{ key: 'ALP', label: 'Labor', colour: partyColour('ALP') },
	{ key: 'COAL', label: 'Coalition', colour: partyColour('COAL') },
	{ key: 'GRN', label: 'Greens', colour: partyColour('GRN') },
	{ key: 'ONP', label: 'One Nation', colour: partyColour('ONP') }
];

export const TPP_SERIES = [{ key: 'tpp_alp_vs_coal', label: 'Labor 2PP', colour: partyColour('ALP') }];

/** Seat-count segments ordered left (Labor) to right (Coalition). */
export function seatSegments(counts: Record<string, number>) {
	const left = ['ALP', 'GRN', 'IND'];
	const right = ['NAT', 'LIB', 'LNP'];
	const pick = (codes: string[]) =>
		codes.filter((c) => counts[c]).map((code) => ({ code, seats: counts[code] }));
	// Any other parties sit on the crossbench, between the left bloc and the Coalition.
	const rest = Object.entries(counts)
		.filter(([c]) => !left.includes(c) && !right.includes(c))
		.map(([code, seats]) => ({ code, seats }));
	return [...pick(left), ...rest, ...pick(right)];
}
