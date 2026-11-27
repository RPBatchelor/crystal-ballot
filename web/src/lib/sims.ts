import type { Sims } from './types';

const COAL_CODES = new Set(['LIB', 'NAT', 'LNP', 'CLP', 'COAL']);

export interface SimFilters {
	/** Locked seat winners: district index -> party code (e.g. 'ALP', 'COAL', 'LIB', 'GRN', 'ONP', 'IND'). */
	locks: Record<number, string>;
	/** Optional Labor 2PP range (%) [min, max]. */
	tppRange?: [number, number] | null;
	/** Optional One Nation statewide primary range (%) [min, max]. */
	onpRange?: [number, number] | null;
}

export interface ConditionedSummary {
	matched: number;
	total: number;
	outcome: {
		alp_majority: number;
		coal_majority: number;
		hung: number;
		alp_most_seats: number;
		coal_most_seats: number;
	};
	/** Median and 90% [p5, p50, p95] seats per bloc ('ALP', 'COAL', 'GRN', 'ONP', 'IND'). */
	seats: Record<string, [number, number, number]>;
	/** [p5, p50, p95] Labor 2PP (%). */
	tpp: [number, number, number];
}

export interface BellwetherRow {
	districtIndex: number;
	district: string;
	/** Seat win probabilities for ALP and COAL. */
	pAlp: number;
	pCoal: number;
	/** Coalition majority probability when Coalition wins vs loses this seat. */
	coalMajIfCoal: number;
	coalMajIfNotCoal: number;
	/** Labor majority probability when Labor wins vs loses this seat. */
	alpMajIfAlp: number;
	alpMajIfNotAlp: number;
	/** Overall leverage score (0-1). */
	leverage: number;
}

export interface SampledElection {
	simIndex: number;
	/** Winner party code per district index. */
	winners: string[];
	/** Seat counts by bloc ('ALP', 'COAL', 'LIB', 'NAT', 'GRN', 'ONP', 'IND', 'OTH'). */
	counts: Record<string, number>;
	tppAlp: number;
	statewide: Record<string, number>;
	outcome: 'alp_majority' | 'coal_majority' | 'hung';
}

function partyMatches(code: string, target: string): boolean {
	if (target === 'COAL') return COAL_CODES.has(code);
	return code === target;
}

function quantiles(arr: number[]): [number, number, number] {
	if (!arr.length) return [0, 0, 0];
	const sorted = arr.toSorted((a, b) => a - b);
	const q = (p: number) => sorted[Math.min(sorted.length - 1, Math.floor(p * (sorted.length - 1)))];
	return [q(0.05), q(0.5), q(0.95)];
}

/** Condition all S simulations on locked seats and optional statewide vote bounds. */
export function conditionSims(sims: Sims, filters: SimFilters, majority: number): ConditionedSummary {
	const { n_sims: S, districts, parties, blocs } = sims.header;
	const D = districts.length;
	const B = blocs.length;
	const winners = sims.winners;
	const tppArr = sims.tpp;
	const swArr = sims.statewide;

	const onpBlocIdx = blocs.indexOf('ONP');
	const lockEntries = Object.entries(filters.locks).map(([dStr, target]) => {
		const d = Number(dStr);
		const allowed = new Uint8Array(parties.length);
		parties.forEach((p, idx) => {
			if (partyMatches(p, target)) allowed[idx] = 1;
		});
		return { d, allowed };
	});

	const isAlp = new Uint8Array(parties.length);
	const isCoal = new Uint8Array(parties.length);
	const isGrn = new Uint8Array(parties.length);
	const isOnp = new Uint8Array(parties.length);
	const isInd = new Uint8Array(parties.length);
	parties.forEach((p, i) => {
		if (p === 'ALP') isAlp[i] = 1;
		else if (COAL_CODES.has(p)) isCoal[i] = 1;
		else if (p === 'GRN') isGrn[i] = 1;
		else if (p === 'ONP') isOnp[i] = 1;
		else if (p === 'IND') isInd[i] = 1;
	});

	const tppLo = filters.tppRange ? Math.round(filters.tppRange[0] * 10) : -Infinity;
	const tppHi = filters.tppRange ? Math.round(filters.tppRange[1] * 10) : Infinity;
	const onpLo = filters.onpRange ? Math.round(filters.onpRange[0] * 10) : -Infinity;
	const onpHi = filters.onpRange ? Math.round(filters.onpRange[1] * 10) : Infinity;

	const alpList: number[] = [];
	const coalList: number[] = [];
	const grnList: number[] = [];
	const onpList: number[] = [];
	const indList: number[] = [];
	const tppList: number[] = [];

	let alpMaj = 0;
	let coalMaj = 0;
	let hung = 0;
	let alpMost = 0;
	let coalMost = 0;

	for (let s = 0; s < S; s++) {
		const tppVal = tppArr[s];
		if (tppVal < tppLo || tppVal > tppHi) continue;
		if (onpBlocIdx >= 0 && filters.onpRange) {
			const onpVal = swArr[s * B + onpBlocIdx];
			if (onpVal < onpLo || onpVal > onpHi) continue;
		}
		const base = s * D;
		let ok = true;
		for (let i = 0; i < lockEntries.length; i++) {
			const lk = lockEntries[i];
			if (!lk.allowed[winners[base + lk.d]]) {
				ok = false;
				break;
			}
		}
		if (!ok) continue;

		let a = 0, c = 0, g = 0, o = 0, ind = 0;
		for (let d = 0; d < D; d++) {
			const w = winners[base + d];
			a += isAlp[w];
			c += isCoal[w];
			g += isGrn[w];
			o += isOnp[w];
			ind += isInd[w];
		}
		alpList.push(a);
		coalList.push(c);
		grnList.push(g);
		onpList.push(o);
		indList.push(ind);
		tppList.push(tppVal / 10);

		if (a >= majority) alpMaj++;
		else if (c >= majority) coalMaj++;
		else hung++;
		if (a > c) alpMost++;
		else if (c > a) coalMost++;
	}

	const m = alpList.length;
	const div = m || 1;
	return {
		matched: m,
		total: S,
		outcome: {
			alp_majority: alpMaj / div,
			coal_majority: coalMaj / div,
			hung: hung / div,
			alp_most_seats: alpMost / div,
			coal_most_seats: coalMost / div
		},
		seats: {
			ALP: quantiles(alpList),
			COAL: quantiles(coalList),
			GRN: quantiles(grnList),
			ONP: quantiles(onpList),
			IND: quantiles(indList)
		},
		tpp: quantiles(tppList)
	};
}

/** Rank the top bellwether / tipping-point seats by how strongly their outcome shifts majority odds. */
export function bellwetherSeats(sims: Sims, majority: number, topN = 10): BellwetherRow[] {
	const { n_sims: S, districts, parties } = sims.header;
	const D = districts.length;
	const winners = sims.winners;

	const isAlp = new Uint8Array(parties.length);
	const isCoal = new Uint8Array(parties.length);
	parties.forEach((p, i) => {
		if (p === 'ALP') isAlp[i] = 1;
		else if (COAL_CODES.has(p)) isCoal[i] = 1;
	});

	// Precompute chamber majority flags per simulation.
	const simAlpMaj = new Uint8Array(S);
	const simCoalMaj = new Uint8Array(S);
	for (let s = 0; s < S; s++) {
		const base = s * D;
		let a = 0, c = 0;
		for (let d = 0; d < D; d++) {
			const w = winners[base + d];
			a += isAlp[w];
			c += isCoal[w];
		}
		if (a >= majority) simAlpMaj[s] = 1;
		else if (c >= majority) simCoalMaj[s] = 1;
	}

	const rows: BellwetherRow[] = [];
	for (let d = 0; d < D; d++) {
		let nCoal = 0, nNotCoal = 0, cmGivenCoal = 0, cmGivenNotCoal = 0;
		let nAlp = 0, nNotAlp = 0, amGivenAlp = 0, amGivenNotAlp = 0;
		for (let s = 0; s < S; s++) {
			const w = winners[s * D + d];
			if (isCoal[w]) {
				nCoal++;
				cmGivenCoal += simCoalMaj[s];
			} else {
				nNotCoal++;
				cmGivenNotCoal += simCoalMaj[s];
			}
			if (isAlp[w]) {
				nAlp++;
				amGivenAlp += simAlpMaj[s];
			} else {
				nNotAlp++;
				amGivenNotAlp += simAlpMaj[s];
			}
		}
		const pCoal = nCoal / S;
		const pAlp = nAlp / S;
		// Skip near-certain seats where conditioning is noisy.
		if (Math.max(pCoal, pAlp) > 0.96 && Math.min(pCoal, pAlp) < 0.04) continue;
		const coalMajIfCoal = nCoal ? cmGivenCoal / nCoal : 0;
		const coalMajIfNotCoal = nNotCoal ? cmGivenNotCoal / nNotCoal : 0;
		const alpMajIfAlp = nAlp ? amGivenAlp / nAlp : 0;
		const alpMajIfNotAlp = nNotAlp ? amGivenNotAlp / nNotAlp : 0;
		// Expected shift in majority probability weighted by competitiveness.
		const coalSwing = Math.abs(coalMajIfCoal - coalMajIfNotCoal) * 4 * pCoal * (1 - pCoal);
		const alpSwing = Math.abs(alpMajIfAlp - alpMajIfNotAlp) * 4 * pAlp * (1 - pAlp);
		rows.push({
			districtIndex: d,
			district: districts[d],
			pAlp,
			pCoal,
			coalMajIfCoal,
			coalMajIfNotCoal,
			alpMajIfAlp,
			alpMajIfNotAlp,
			leverage: Math.max(coalSwing, alpSwing)
		});
	}
	return rows.sort((a, b) => b.leverage - a.leverage).slice(0, topN);
}

/** Extract one concrete simulated election night (Hypothetical Outcome Plot). */
export function sampleElection(sims: Sims, majority: number, simIndex?: number): SampledElection {
	const { n_sims: S, districts, parties, blocs } = sims.header;
	const D = districts.length;
	const B = blocs.length;
	const idx = simIndex ?? Math.floor(Math.random() * S);
	const base = idx * D;
	const winCodes: string[] = new Array(D);
	const counts: Record<string, number> = { ALP: 0, COAL: 0, LIB: 0, NAT: 0, GRN: 0, ONP: 0, IND: 0, OTH: 0 };
	for (let d = 0; d < D; d++) {
		const code = parties[sims.winners[base + d]];
		winCodes[d] = code;
		counts[code] = (counts[code] ?? 0) + 1;
		if (COAL_CODES.has(code) && code !== 'COAL') counts.COAL += 1;
	}
	const statewide: Record<string, number> = {};
	for (let b = 0; b < B; b++) {
		statewide[blocs[b]] = sims.statewide[idx * B + b] / 10;
	}
	const outcome =
		counts.ALP >= majority ? 'alp_majority' : counts.COAL >= majority ? 'coal_majority' : 'hung';
	return {
		simIndex: idx,
		winners: winCodes,
		counts,
		tppAlp: sims.tpp[idx] / 10,
		statewide,
		outcome
	};
}
