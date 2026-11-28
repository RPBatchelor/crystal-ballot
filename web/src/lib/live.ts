/**
 * Real-time election-night scoring & Bayesian conditioning helpers.
 * Merges automated live counts, projected calls (>=75% counted & >=8% margin),
 * and interactive Call Desk manual calls against the frozen final forecast.
 */
import type {
	ForecastDistrict,
	ForecastFile,
	LiveDistrictResult,
	LiveResultsFile,
	LiveSeatStatus,
	Sims
} from './types';
import { conditionSims, type ConditionedSummary } from './sims';

const COAL_CODES = new Set(['LIB', 'NAT', 'LNP', 'CLP', 'COAL']);

export interface ManualCall {
	party: string;
	calledAt: string;
}

export interface MergedSeat {
	district: ForecastDistrict;
	live: LiveDistrictResult | null;
	effectiveStatus: LiveSeatStatus;
	/** Effective winner party code if called (or projected & includeProjected is true). */
	effectiveWinner: string | null;
	leadingParty: string | null;
	pctCounted: number;
	margin: number | null;
	tppAlp: number | null;
	primary: Record<string, number> | null;
	calledAt: string | null;
	source: 'manual' | 'vec' | 'abc' | 'curated' | 'projected' | null;
	/** Model's pre-election probability assigned to the actual/effective winner. */
	pActual: number | null;
	/** Whether the model's favourite won (null if not yet effectively called). */
	hit: boolean | null;
	/** Brier score contribution for this seat. */
	brier: number | null;
}

export interface LiveCalibrationBin {
	label: string;
	lo: number;
	hi: number;
	n: number;
	meanProb: number;
	hitRate: number;
}

export interface LiveModelScore {
	totalSeats: number;
	calledOfficial: number;
	calledProjected: number;
	calledManual: number;
	effectiveCalled: number;
	countingSeats: number;
	uncountedSeats: number;
	hits: number;
	expectedHits: number;
	statusQuoHits: number;
	brier: number | null;
	statusQuoBrier: number | null;
	logLoss: number | null;
	seatCounts: {
		called: Record<string, number>;
		leading: Record<string, number>;
	};
	calibration: LiveCalibrationBin[];
	upsets: MergedSeat[];
	recentCalls: MergedSeat[];
}

export function toBloc(code: string): string {
	return COAL_CODES.has(code) ? 'COAL' : code;
}

/** Return the model's probability for a specific party code (matching LIB/NAT/COAL cleanly). */
export function probForParty(probs: Record<string, number>, code: string): number {
	if (probs[code] != null) return probs[code];
	if (code === 'COAL') {
		return Object.entries(probs).reduce((a, [k, v]) => a + (COAL_CODES.has(k) ? v : 0), 0);
	}
	if (COAL_CODES.has(code) && probs.COAL != null) return probs.COAL;
	return 0;
}

/** Check whether two party codes represent the same winner (handling LIB/NAT/COAL equivalence when needed). */
export function sameWinner(a: string, b: string): boolean {
	if (a === b) return true;
	if ((a === 'COAL' && COAL_CODES.has(b)) || (b === 'COAL' && COAL_CODES.has(a))) return true;
	return false;
}

export const AUTO_PROJECT_PCT = 75;
export const AUTO_PROJECT_MARGIN = 8;

export function mergeLiveSeats(
	forecast: ForecastFile,
	feed: LiveResultsFile | null,
	manualCalls: Record<string, ManualCall>,
	includeProjected: boolean
): MergedSeat[] {
	const bySlug = new Map<string, LiveDistrictResult>((feed?.districts ?? []).map((d) => [d.slug, d]));

	return forecast.districts.map((d) => {
		const live = bySlug.get(d.slug) ?? null;
		const manual = manualCalls[d.slug] ?? null;

		let effectiveStatus: LiveSeatStatus = live?.status ?? 'uncounted';
		let effectiveWinner: string | null = null;
		let source: MergedSeat['source'] = null;
		let calledAt: string | null = live?.called_at ?? null;

		if (manual) {
			effectiveStatus = 'called';
			effectiveWinner = manual.party;
			source = 'manual';
			calledAt = manual.calledAt;
		} else if (live?.status === 'called' && live.called_party) {
			effectiveStatus = 'called';
			effectiveWinner = live.called_party;
			source = (live.source as MergedSeat['source']) ?? 'vec';
		} else if (
			live &&
			live.leading_party &&
			((live.status === 'projected') ||
				(live.pct_counted >= AUTO_PROJECT_PCT && (live.margin ?? 0) >= AUTO_PROJECT_MARGIN))
		) {
			effectiveStatus = 'projected';
			if (includeProjected) {
				effectiveWinner = live.leading_party;
				source = 'projected';
			}
		}

		const leadingParty = manual?.party ?? live?.called_party ?? live?.leading_party ?? null;
		let pActual: number | null = null;
		let hit: boolean | null = null;
		let brier: number | null = null;

		if (effectiveWinner) {
			pActual = probForParty(d.probs, effectiveWinner);
			hit = sameWinner(d.leader, effectiveWinner);
			// Multi-class Brier score: sum_p (prob_p - y_p)^2
			let sumSq = 0;
			let matchedAny = false;
			for (const [k, p] of Object.entries(d.probs)) {
				const isWin = sameWinner(k, effectiveWinner);
				if (isWin) matchedAny = true;
				const y = isWin ? 1 : 0;
				sumSq += (p - y) ** 2;
			}
			if (!matchedAny) sumSq += 1; // winner had 0 probability in forecast
			brier = sumSq;
		}

		return {
			district: d,
			live,
			effectiveStatus,
			effectiveWinner,
			leadingParty,
			pctCounted: live?.pct_counted ?? (manual ? 100 : 0),
			margin: live?.margin ?? null,
			tppAlp: live?.tpp_alp ?? null,
			primary: live?.primary ?? null,
			calledAt,
			source,
			pActual,
			hit,
			brier
		};
	});
}

export function scoreLiveSeats(seats: MergedSeat[]): LiveModelScore {
	const calledCounts: Record<string, number> = { ALP: 0, COAL: 0, LIB: 0, NAT: 0, GRN: 0, ONP: 0, IND: 0, OTH: 0 };
	const leadingCounts: Record<string, number> = { ALP: 0, COAL: 0, LIB: 0, NAT: 0, GRN: 0, ONP: 0, IND: 0, OTH: 0 };

	let calledOfficial = 0;
	let calledProjected = 0;
	let calledManual = 0;
	let countingSeats = 0;
	let uncountedSeats = 0;

	let hits = 0;
	let expectedHits = 0;
	let statusQuoHits = 0;
	let brierSum = 0;
	let sqBrierSum = 0;
	let logLossSum = 0;

	const calledList: MergedSeat[] = [];

	for (const s of seats) {
		if (s.source === 'manual') calledManual++;
		else if (s.source === 'vec' || s.source === 'abc' || s.source === 'curated') calledOfficial++;
		else if (s.source === 'projected') calledProjected++;

		if (s.effectiveWinner) {
			calledList.push(s);
			const w = s.effectiveWinner;
			calledCounts[w] = (calledCounts[w] ?? 0) + 1;
			if (COAL_CODES.has(w) && w !== 'COAL') calledCounts.COAL += 1;

			if (s.hit) hits++;
			expectedHits += s.district.leader_prob;
			const sqHit = sameWinner(s.district.incumbent, w);
			if (sqHit) statusQuoHits++;
			brierSum += s.brier ?? 0;
			sqBrierSum += sqHit ? 0 : 2;
			logLossSum += -Math.log(Math.max(s.pActual ?? 0, 1e-4));
		} else if (s.effectiveStatus === 'counting' || s.effectiveStatus === 'projected') {
			countingSeats++;
			if (s.leadingParty) {
				const l = s.leadingParty;
				leadingCounts[l] = (leadingCounts[l] ?? 0) + 1;
				if (COAL_CODES.has(l) && l !== 'COAL') leadingCounts.COAL += 1;
			}
		} else {
			uncountedSeats++;
		}
	}

	const n = calledList.length;

	// Running calibration bins across called seats (by favourite's pre-election probability)
	const binDefs: [string, number, number][] = [
		['<50% (multi-way)', 0, 0.5],
		['50–70%', 0.5, 0.7],
		['70–90%', 0.7, 0.9],
		['90–99%', 0.9, 0.99],
		['99%+', 0.99, 1.01]
	];
	const calibration: LiveCalibrationBin[] = binDefs.map(([label, lo, hi]) => {
		const inBin = calledList.filter((s) => s.district.leader_prob >= lo && s.district.leader_prob < hi);
		const bn = inBin.length;
		return {
			label,
			lo,
			hi,
			n: bn,
			meanProb: bn ? inBin.reduce((a, s) => a + s.district.leader_prob, 0) / bn : 0,
			hitRate: bn ? inBin.filter((s) => s.hit).length / bn : 0
		};
	});

	const upsets = calledList
		.filter((s) => s.hit === false)
		.toSorted((a, b) => (a.pActual ?? 0) - (b.pActual ?? 0));

	const recentCalls = calledList.toSorted((a, b) => {
		if (a.calledAt && b.calledAt) return b.calledAt.localeCompare(a.calledAt);
		if (a.calledAt) return -1;
		if (b.calledAt) return 1;
		return (a.pActual ?? 1) - (b.pActual ?? 1);
	});

	return {
		totalSeats: seats.length,
		calledOfficial,
		calledProjected,
		calledManual,
		effectiveCalled: n,
		countingSeats,
		uncountedSeats,
		hits,
		expectedHits,
		statusQuoHits,
		brier: n ? brierSum / n : null,
		statusQuoBrier: n ? sqBrierSum / n : null,
		logLoss: n ? logLossSum / n : null,
		seatCounts: {
			called: calledCounts,
			leading: leadingCounts
		},
		calibration,
		upsets,
		recentCalls
	};
}

/** Condition all 20,000 simulations on all effectively called seats. */
export function conditionLiveForecast(
	sims: Sims | null,
	seats: MergedSeat[],
	majority: number
): ConditionedSummary | null {
	if (!sims) return null;
	const locks: Record<number, string> = {};
	const idxByName = new Map<string, number>(sims.header.districts.map((name, i) => [name, i]));
	for (const s of seats) {
		if (!s.effectiveWinner) continue;
		const idx = idxByName.get(s.district.district);
		if (idx != null) locks[idx] = s.effectiveWinner;
	}
	return conditionSims(sims, { locks }, majority);
}
