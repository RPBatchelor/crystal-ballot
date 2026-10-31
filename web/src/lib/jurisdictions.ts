export interface Jurisdiction {
	code: string; // url segment
	name: string;
	short: string;
	kind: 'federal' | 'state' | 'territory';
	chamber: string;
	seats: number;
	/** Next scheduled general election (ISO date) if known. */
	nextElection?: string;
	/** Past elections with published results on this site. */
	resultYears: number[];
	/** Elections with a published (live) forecast. */
	forecastYears?: number[];
	/** Past elections with a retrospective (blind backtest) forecast and its result. */
	retroYears?: number[];
	/** Who formed government after a hung parliament, where seat counts alone mislead. */
	minorityGovernments?: Record<number, string>;
	hasPolls: boolean;
	/** Electoral commission credited for results (short form). */
	commission?: string;
	/** Optional preferential voting: ballots can exhaust before the final count. */
	optionalPreferential?: boolean;
}

export const JURISDICTIONS: Jurisdiction[] = [
	{
		code: 'federal',
		name: 'Federal',
		short: 'Federal',
		kind: 'federal',
		chamber: 'House of Representatives',
		seats: 150,
		resultYears: [2007, 2010, 2013, 2016, 2019, 2022, 2025],
		retroYears: [2025],
		minorityGovernments: { 2010: 'ALP' },
		hasPolls: true,
		commission: 'AEC'
	},
	{
		code: 'nsw',
		name: 'New South Wales',
		short: 'NSW',
		kind: 'state',
		chamber: 'Legislative Assembly',
		seats: 93,
		nextElection: '2027-03-27',
		resultYears: [2015, 2019, 2023],
		retroYears: [2023],
		// 2023: Labor short of a majority (45 of 93), governing with crossbench support.
		minorityGovernments: { 2023: 'ALP' },
		hasPolls: true,
		commission: 'NSWEC',
		optionalPreferential: true
	},
	{
		code: 'vic',
		name: 'Victoria',
		short: 'VIC',
		kind: 'state',
		chamber: 'Legislative Assembly',
		seats: 88,
		nextElection: '2026-11-28',
		resultYears: [2014, 2018, 2022],
		forecastYears: [2026],
		retroYears: [2018],
		hasPolls: true,
		commission: 'VEC'
	},
	{
		code: 'qld',
		name: 'Queensland',
		short: 'QLD',
		kind: 'state',
		chamber: 'Legislative Assembly',
		seats: 93,
		nextElection: '2028-10-28',
		resultYears: [2012, 2015, 2017, 2020, 2024],
		retroYears: [2024],
		hasPolls: true,
		commission: 'ECQ'
	},
	{
		code: 'wa',
		name: 'Western Australia',
		short: 'WA',
		kind: 'state',
		chamber: 'Legislative Assembly',
		seats: 59,
		nextElection: '2029-03-10',
		resultYears: [2008, 2013, 2017, 2021, 2025],
		retroYears: [2025],
		hasPolls: true,
		commission: 'WAEC'
	},
	{
		code: 'sa',
		name: 'South Australia',
		short: 'SA',
		kind: 'state',
		chamber: 'House of Assembly',
		seats: 47,
		nextElection: '2030-03-16',
		resultYears: [2014, 2018, 2022, 2026],
		hasPolls: true,
		commission: 'ECSA'
	},
	{
		code: 'tas',
		name: 'Tasmania',
		short: 'TAS',
		kind: 'state',
		chamber: 'House of Assembly',
		seats: 35,
		resultYears: [],
		hasPolls: false
	},
	{
		code: 'act',
		name: 'Australian Capital Territory',
		short: 'ACT',
		kind: 'territory',
		chamber: 'Legislative Assembly',
		seats: 25,
		resultYears: [],
		hasPolls: false
	},
	{
		code: 'nt',
		name: 'Northern Territory',
		short: 'NT',
		kind: 'territory',
		chamber: 'Legislative Assembly',
		seats: 25,
		resultYears: [],
		hasPolls: false
	}
];

export function getJurisdiction(code: string): Jurisdiction | undefined {
	return JURISDICTIONS.find((j) => j.code === code);
}

/** All forecast pages (live and retrospective). */
export function allForecastYears(j: Jurisdiction): number[] {
	return [...(j.retroYears ?? []), ...(j.forecastYears ?? [])];
}

export function isActive(j: Jurisdiction): boolean {
	return j.hasPolls || j.resultYears.length > 0;
}
