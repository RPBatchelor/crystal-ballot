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
	/** Elections with a published forecast. */
	forecastYears?: number[];
	hasPolls: boolean;
}

export const JURISDICTIONS: Jurisdiction[] = [
	{
		code: 'federal',
		name: 'Federal',
		short: 'Federal',
		kind: 'federal',
		chamber: 'House of Representatives',
		seats: 150,
		resultYears: [2022, 2025],
		hasPolls: true
	},
	{
		code: 'nsw',
		name: 'New South Wales',
		short: 'NSW',
		kind: 'state',
		chamber: 'Legislative Assembly',
		seats: 93,
		nextElection: '2027-03-27',
		resultYears: [],
		hasPolls: false
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
		hasPolls: true
	},
	{
		code: 'qld',
		name: 'Queensland',
		short: 'QLD',
		kind: 'state',
		chamber: 'Legislative Assembly',
		seats: 93,
		resultYears: [],
		hasPolls: false
	},
	{
		code: 'wa',
		name: 'Western Australia',
		short: 'WA',
		kind: 'state',
		chamber: 'Legislative Assembly',
		seats: 59,
		resultYears: [],
		hasPolls: false
	},
	{
		code: 'sa',
		name: 'South Australia',
		short: 'SA',
		kind: 'state',
		chamber: 'House of Assembly',
		seats: 47,
		resultYears: [],
		hasPolls: false
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

export function isActive(j: Jurisdiction): boolean {
	return j.hasPolls || j.resultYears.length > 0;
}
