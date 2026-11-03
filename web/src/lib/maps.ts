import { interpolateLab } from 'd3-interpolate';
import { bloc, party, partyColour } from './parties';
import type { HemiSeat } from './components/charts/Hemicycle.svelte';

/** Boundary set (Vicmap layer; NSW redistribution) in force at each election. */
const BOUNDARIES: Record<string, Record<number, string>> = {
	vic: { 2014: 'assembly2013', 2018: 'assembly2013', 2022: 'assembly2022', 2026: 'assembly2022' },
	nsw: { 2015: 'nsw-2013', 2019: 'nsw-2013', 2023: 'nsw-2021', 2027: 'nsw-2021' },
	qld: { 2012: 'qld-2008', 2015: 'qld-2008', 2017: 'qld-2017', 2020: 'qld-2017', 2024: 'qld-2017' },
	sa: { 2014: 'sa-2012', 2018: 'sa-2016', 2022: 'sa-2020', 2026: 'sa-2024' }
};

/** Seat map layout: the state, its height/width, and an inset on the capital. */
export interface MapFrame {
	state: string;
	aspect: number;
	/** ``aspect``: inset height/width beside the main map (default 0.95). */
	inset: { label: string; west: number; south: number; east: number; north: number; aspect?: number };
}

const FRAMES: Record<string, MapFrame> = {
	vic: {
		state: 'Victoria',
		aspect: 0.64,
		inset: { label: 'Metropolitan Melbourne', west: 144.58, south: -38.12, east: 145.42, north: -37.58 }
	},
	nsw: {
		state: 'New South Wales',
		aspect: 0.86,
		inset: { label: 'Greater Sydney', west: 150.62, south: -34.12, east: 151.36, north: -33.56 }
	},
	qld: {
		state: 'Queensland',
		aspect: 1.3,
		inset: { label: 'South East Queensland', west: 152.6, south: -28.2, east: 153.58, north: -26.35, aspect: 1.75 }
	},
	sa: {
		state: 'South Australia',
		aspect: 1.15,
		inset: { label: 'Greater Adelaide', west: 138.45, south: -35.25, east: 138.85, north: -34.6, aspect: 1.5 }
	}
};

export const mapFrame = (jur: string): MapFrame => FRAMES[jur] ?? FRAMES.vic;

export function boundarySet(jur: string, year: number): string | undefined {
	return BOUNDARIES[jur]?.[year];
}

/** Elections sharing boundaries, so seat-level swings are like-for-like. */
export function sameBoundaries(jur: string, a: number, b: number): boolean {
	const x = boundarySet(jur, a);
	return x !== undefined && x === boundarySet(jur, b);
}

// Diverging Labor <-> Coalition scale with a neutral midpoint. Fixed hexes (fills on
// the map work in both themes); endpoints match the light-theme party colours.
const COAL_DARK = '#1f4e9e';
const COAL_LIGHT = '#c9d6ef';
const MID = '#e6e3dc';
const ALP_LIGHT = '#f2c6c3';
const ALP_DARK = '#c8202b';

function diverging(t: number): string {
	// t in [-1, 1]: -1 = Coalition extreme, +1 = Labor extreme.
	const c = Math.max(-1, Math.min(1, t));
	if (c >= 0) return c < 0.15 ? interpolateLab(MID, ALP_LIGHT)(c / 0.15) : interpolateLab(ALP_LIGHT, ALP_DARK)((c - 0.15) / 0.85);
	const d = -c;
	return d < 0.15 ? interpolateLab(MID, COAL_LIGHT)(d / 0.15) : interpolateLab(COAL_LIGHT, COAL_DARK)((d - 0.15) / 0.85);
}

/** Labor 2PP (%) -> colour; saturates at 50 +/- 25. */
export const tppColour = (alp: number) => diverging((alp - 50) / 25);
/** 2PP swing to Labor (points) -> colour; saturates at +/- 12. */
export const swingColour = (swing: number) => diverging(swing / 12);

export const TPP_GRADIENT = `linear-gradient(90deg, ${[-1, -0.5, -0.15, 0, 0.15, 0.5, 1].map(diverging).join(', ')})`;

/** Confidence tiers for forecast shading. */
export const TIERS = [
	{ min: 0.85, opacity: 1, label: 'Likely (85%+)' },
	{ min: 0.65, opacity: 0.6, label: 'Leaning (65–85%)' },
	{ min: 0, opacity: 0.28, label: 'Toss-up (under 65%)' }
];
export const tierOpacity = (p: number) => TIERS.find((t) => p >= t.min)!.opacity;

// Left-to-right order in the chamber diagram: government-side left bloc, crossbench,
// then the Coalition (Nationals before Liberals, as on most published diagrams).
const CHAMBER_ORDER = ['ALP', 'GRN', 'IND', 'OTH', 'ONP', 'NAT', 'LIB', 'LNP'];
const rank = (code: string) => {
	const i = CHAMBER_ORDER.indexOf(code);
	if (i !== -1) return i;
	const b = bloc(code);
	return CHAMBER_ORDER.indexOf(b === 'COAL' ? 'LIB' : b === 'IND' ? 'IND' : 'OTH');
};

/** Seats for the chamber diagram from per-seat winners. ``strength`` (0-1) orders seats
 * within a party so the safest sit on the outside and the closest near the centre. */
export function chamberSeats(
	rows: { slug: string; name: string; party: string; strength: number; detail?: string; href?: string; opacity?: number }[]
): HemiSeat[] {
	const leftSide = (code: string) => rank(code) < CHAMBER_ORDER.indexOf('ONP');
	return rows
		.toSorted((a, b) => {
			const r = rank(a.party) - rank(b.party);
			if (r) return r;
			// Left of centre: strongest first; right of centre: weakest first.
			return leftSide(a.party) ? b.strength - a.strength : a.strength - b.strength;
		})
		.map((s) => ({
			key: s.slug,
			colour: partyColour(s.party),
			opacity: s.opacity,
			label: `${s.name} · ${party(s.party).short}${s.detail ? ` · ${s.detail}` : ''}`,
			href: s.href
		}));
}
