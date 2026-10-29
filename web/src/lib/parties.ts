// Party display metadata. Codes match pipeline/src/prophecy/schema/parties.py.

export interface PartyMeta {
	code: string;
	short: string;
	name: string;
}

const PARTIES: Record<string, PartyMeta> = {
	ALP: { code: 'ALP', short: 'Labor', name: 'Australian Labor Party' },
	COAL: { code: 'COAL', short: 'Coalition', name: 'Liberal–National Coalition' },
	LIB: { code: 'LIB', short: 'Liberal', name: 'Liberal Party' },
	NAT: { code: 'NAT', short: 'Nationals', name: 'The Nationals' },
	LNP: { code: 'LNP', short: 'LNP', name: 'Liberal National Party' },
	CLP: { code: 'CLP', short: 'Country Liberal', name: 'Country Liberal Party' },
	KAP: { code: 'KAP', short: 'Katter (KAP)', name: "Katter's Australian Party" },
	CA: { code: 'CA', short: 'Centre Alliance', name: 'Centre Alliance' },
	GRN: { code: 'GRN', short: 'Greens', name: 'Australian Greens' },
	ONP: { code: 'ONP', short: 'One Nation', name: "Pauline Hanson's One Nation" },
	IND: { code: 'IND', short: 'Independent', name: 'Independent' },
	OTH: { code: 'OTH', short: 'Others', name: 'Other parties' }
};

const COLOURED = new Set(['ALP', 'COAL', 'LIB', 'NAT', 'LNP', 'GRN', 'ONP', 'IND']);

export function party(code: string, fallbackName?: string): PartyMeta {
	return PARTIES[code] ?? { code, short: fallbackName ?? code, name: fallbackName ?? code };
}

/** Readable party label: our short name for major parties, the official name for minor ones. */
export function partyLabel(code: string, officialName?: string | null): string {
	if (PARTIES[code] && code !== 'OTH') return PARTIES[code].short;
	return officialName?.trim() || 'Independent';
}

/** CSS colour for a party code; minor parties share the neutral "Others" grey. */
export function partyColour(code: string): string {
	if (code === 'LNP' || code === 'CLP') return 'var(--party-COAL)';
	// Minor parties holding seats as de facto independents.
	if (code === 'KAP' || code === 'CA') return 'var(--party-IND)';
	return COLOURED.has(code) ? `var(--party-${code})` : 'var(--party-OTH)';
}

/** Model bloc for a party code (mirrors schema.parties.bloc). */
export function bloc(code: string): string {
	if (['LIB', 'NAT', 'LNP', 'CLP', 'COAL'].includes(code)) return 'COAL';
	if (['KAP', 'CA'].includes(code)) return 'IND';
	return ['ALP', 'GRN', 'ONP', 'IND'].includes(code) ? code : 'OTH';
}
