import { interpolateLab } from 'd3-interpolate';
import { bloc, party, partyColour } from './parties';
import type { HemiSeat } from './components/charts/Hemicycle.svelte';

/** Boundary set (Vicmap layer) in force at each election. */
const BOUNDARIES: Record<string, Record<number, string>> = {
	vic: { 2014: 'assembly2013', 2018: 'assembly2013', 2022: 'assembly2022', 2026: 'assembly2022' }
};

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
	return i === -1 ? CHAMBER_ORDER.indexOf(bloc(code) === 'COAL' ? 'LIB' : 'OTH') : i;
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
