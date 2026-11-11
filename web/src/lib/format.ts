const dateFmt = new Intl.DateTimeFormat('en-AU', { day: 'numeric', month: 'short', year: 'numeric' });
const shortDateFmt = new Intl.DateTimeFormat('en-AU', { day: 'numeric', month: 'short' });

export const fmtDate = (iso: string) => dateFmt.format(new Date(iso));
export const fmtShortDate = (iso: string) => shortDateFmt.format(new Date(iso));
export const fmtInt = (n: number | null | undefined) => (n == null ? '–' : n.toLocaleString('en-AU'));
export const fmtPct = (n: number | null | undefined, digits = 1) =>
	n == null ? '–' : `${n.toFixed(digits)}%`;

/** "LASTNAME, First" -> "First Lastname" */
export function displayName(name: string | null | undefined): string {
	if (!name) return '';
	const [last, first] = name.split(',').map((s) => s.trim());
	if (!first) return name;
	const lastCased = last
		.toLowerCase()
		.replace(/(^|[\s'-])(\p{L})/gu, (_, sep: string, ch: string) => sep + ch.toUpperCase());
	return `${first} ${lastCased}`;
}

export function daysUntil(iso: string, from = new Date()): number {
	const ms = new Date(iso + 'T00:00:00+11:00').getTime() - from.getTime();
	return Math.ceil(ms / 86_400_000);
}

/** First letter upper-cased ("the LNP" -> "The LNP"). */
export const cap = (s: string) => s.charAt(0).toUpperCase() + s.slice(1);

/** "a" or "an" before a word or acronym, by sound: "an LNP", "a CLP", "a Liberal". */
export function article(word: string): string {
	const acronym = /^[A-Z]{2,}\b/.test(word);
	return (acronym ? /^[AEFHILMNORSX]/ : /^[aeiou]/i).test(word) ? 'an' : 'a';
}
