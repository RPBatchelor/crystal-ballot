// What is different about the model in each jurisdiction, in plain English.
// Keep in step with the pipeline (README "New South Wales" ... "ACT and Northern Territory").

export interface JurisdictionNote {
	code: string;
	name: string;
	/** Chamber, size and voting system, as one short line. */
	system: string;
	/** Tags shown as chips: the voting system and anything else notable. */
	tags: string[];
	/** The differences from the general model. */
	points: string[];
	/** Shown in place of a backtest's caveat, e.g. why the latest election is not tested yet. */
	backtestNote?: string;
}

export const NOTES: JurisdictionNote[] = [
	{
		code: 'vic',
		name: 'Victoria',
		system: 'Legislative Assembly · 88 single-member seats · full preferential voting',
		tags: ['Live forecast', 'Full preferential'],
		points: [
			'This is the live forecast, for the election on 28 November 2026. The 2026 election uses the same boundaries as 2022, so every seat starts directly from its 2022 result, with no re-cutting needed.',
			'Seats move with their region as well as the state: the eight Legislative Council regions (such as Northern Metropolitan or Western Victoria) each get their own shared swing on top of the statewide one.',
			'Preference flows come from the Victorian Electoral Commission’s full distributions of preferences, published for 39 of the 88 seats in 2022, and are then tuned so that replaying 2022 reproduces the final two-candidate result in every seat.',
			'One Nation barely stood in 2022, so its 2022 state vote says nothing about where its voters are. Instead its vote is spread across seats in proportion to its 2025 federal vote, polling place by polling place, re-cut onto the state districts. Its preference flows are set to match the two-party figures published by 2026 pollsters, roughly 30% of One Nation preferences reaching Labor ahead of the Coalition, with wide uncertainty.',
			'Nominations closed on 9 November 2026, so the forecast uses the real ballot: a party with no candidate in a seat gets no vote there, retiring members and first-term members are known, and notable independents are given an expected vote of their own.',
			'By-elections since 2022 count: half of any swing in a by-election beyond what the statewide polls have moved is carried forward to that seat, where Labor, the Coalition and the Greens all stood both times.',
			'Victorian polls have tended to overstate the Greens (by about 1.6 points on average in the final month), so half of that lean is taken off, and the Greens get a wider allowance for polling error than elsewhere.'
		],
		backtestNote:
			'The latest blind test is of 2018. The 2022 election was held on new boundaries (the 2021 redistribution), and a fair test of 2022 needs the 2018 result re-cut onto those boundaries first, which has not been built yet. The 2018 test also uses the original hand-set seat settings, because there were too few earlier Victorian elections on matching boundaries to estimate them from.'
	},
	{
		code: 'nsw',
		name: 'New South Wales',
		system: 'Legislative Assembly · 93 single-member seats · optional preferential voting',
		tags: ['Optional preferential', 'Notional boundaries'],
		points: [
			'Voters only need to number one box, so many ballots “exhaust”: they stop counting before the final two candidates. The model treats exhausting as one more choice a ballot can make each time a candidate is excluded, estimated from the NSW Electoral Commission’s distributions, which record exhausted ballots at every count. As in real counts, the fewer candidates remain, the more ballots exhaust.',
			'NSW redrew its boundaries in 2021, so the 2019 result is first re-cut onto the 2023 seats. Each election-day polling place is assigned to the seat it served in 2023; pre-poll, postal and other votes follow the old seat’s polling places in proportion. This gives a “notional” 2019 result for each new seat, which is what the swing is applied to.',
			'The Shooters, Fishers and Farmers’ three members stood as independents in 2023, so their earlier vote is treated as personal (independent) vote. A member who left a major party to stand as an independent keeps half their old vote as a starting point.'
		]
	},
	{
		code: 'qld',
		name: 'Queensland',
		system: 'Legislative Assembly · 93 single-member seats · full preferential voting',
		tags: ['Full preferential'],
		points: [
			'Queensland returned to full preferential voting in 2016, so no ballots exhaust. The 2020 and 2024 elections were held on the same (2017) boundaries, so seats start directly from the previous result.',
			'The LNP is a single merged party, so there are no Liberal versus National contests to model.',
			'Katter’s Australian Party members are modelled like independents, because their vote is largely personal and tied to the member. A member who switched parties (Stephen Andrew, elected for One Nation in 2020, standing for Katter’s party in 2024) keeps half their old vote as a starting point.',
			'The Electoral Commission of Queensland only publishes a Labor versus LNP count where those two finished as the final pair (85 of 93 seats), so preference flows are tuned on those seats.'
		]
	},
	{
		code: 'wa',
		name: 'Western Australia',
		system: 'Legislative Assembly · 59 single-member seats · full preferential voting',
		tags: ['Full preferential', 'Notional boundaries'],
		points: [
			'The Liberals and Nationals are not in coalition in WA and often run against each other in country seats. The model treats them as one Coalition bloc for the statewide vote, and gives a seat to whichever of the two ran stronger there last time (or the only one standing).',
			'Boundaries are redrawn after every WA election, so the previous result is re-cut onto the new seats by polling place, as for NSW. Because the WA Electoral Commission publishes no Labor versus Coalition count by polling place, each old seat’s two-party result is carried across in proportion to its votes.',
			'WA polls have been volatile, most of all in Labor’s 2021 landslide, which the final polls understated. That history gives Labor a wider allowance for polling error in WA (about 3.9 points) than in any other state.'
		]
	},
	{
		code: 'sa',
		name: 'South Australia',
		system: 'House of Assembly · 47 single-member seats · full preferential voting',
		tags: ['Full preferential', 'Notional boundaries'],
		points: [
			'South Australia redraws its boundaries before every election, so the previous result is re-cut onto the new seats by polling place. The re-cut of 2022 onto the 2024 boundaries was checked against Antony Green’s published pendulum: the two differ by under one point on average across 41 seats.',
			'In 2022 about 40% of votes were not published by polling place, so those votes are spread in proportion to each old seat’s polling-place votes, which smooths over local differences.',
			'Before 2022 the Electoral Commission of South Australia published no full distributions of preferences, so for those elections preference flows are borrowed from the South Australian federal seats.'
		]
	},
	{
		code: 'tas',
		name: 'Tasmania',
		system: 'House of Assembly · 35 seats in five 7-member divisions · Hare-Clark proportional representation',
		tags: ['Hare-Clark', 'Proportional'],
		points: [
			'There are no single-member seats. Each of the five divisions elects seven members (five each, up to 2021) by proportional representation: a candidate with a quota (one-eighth of the vote, plus one) is elected, their surplus passes on, and the lowest candidates are excluded one by one. The model simulates this count directly.',
			'Because voters almost always stay within a party’s ticket while it has candidates left, each party is counted as one unit that can win several seats, and each independent as a unit that can win at most one.',
			'Under Hare-Clark every candidate’s own vote is counted, so an independent’s personal vote is observed directly and carried forward. A sitting member who leaves their party takes part of their old personal vote with them.',
			'New parties and first-time independents are drawn from how such newcomers have polled at earlier elections, so the model allows for an occasional breakthrough without predicting a particular one.',
			'Preference flows come from the full distributions in Tasmania’s five federal seats, which share the same boundaries. Statewide polls only: polls of single divisions are left out.'
		],
		backtestNote:
			'Hare-Clark has no two-party count, so this test is scored on seats won by each party rather than seat-by-seat winners.'
	},
	{
		code: 'act',
		name: 'Australian Capital Territory',
		system: 'Legislative Assembly · 25 seats in five 5-member electorates · Hare-Clark proportional representation',
		tags: ['Hare-Clark', 'Few or no polls'],
		points: [
			'The ACT uses the same Hare-Clark system as Tasmania, and the same count model, with preference flows from the ACT’s three federal seats (Bean, Canberra and Fenner).',
			'There was no public polling before the 2024 election. When a jurisdiction has fewer than three polls, the poll trend is replaced by the previous result plus a swing drawn from how much the ACT’s vote has moved between past elections.',
			'Elections ACT does not mark sitting members, so the previous election’s winners are treated as the sitting members. Groups that ran a party-style ticket (Independents for Canberra, Strong Independents) are modelled as small parties; one-candidate groups as independents.'
		],
		backtestNote:
			'With no polls at all, the 2024 test shows how far the model gets from past results and the history of swings alone. It is scored on seats per party, as for Tasmania.'
	},
	{
		code: 'nt',
		name: 'Northern Territory',
		system: 'Legislative Assembly · 25 single-member seats · full preferential voting',
		tags: ['Full preferential', 'Few or no polls'],
		points: [
			'The Country Liberal Party is the Coalition in the Territory. Seats are very small (around 6,000 voters), so personal votes matter and seats swing roughly twice as much as in the states; the model’s seat-by-seat uncertainty is wider to match.',
			'Only two public polls were published before the 2024 election, too few to fit a trend, so the forecast uses the previous result plus a swing drawn from the Territory’s own history of election-to-election changes.',
			'The NT Electoral Commission publishes no distributions of preferences in a form that can be read automatically, so flows come from the Territory’s federal seats (Lingiari and Solomon) and are tuned to the NT seats’ own Labor versus CLP results.',
			'The 2024 election was on new boundaries. The notional starting point for each seat is rebuilt from the published change in each party’s vote, which is approximate and lumps minor parties together.'
		]
	},
	{
		code: 'federal',
		name: 'Federal',
		system: 'House of Representatives · 150 single-member seats · full preferential voting',
		tags: ['Full preferential', 'Notional boundaries'],
		points: [
			'The federal model is the same single-member model, with each state acting as a region: seats in the same state swing together.',
			'Several states were redistributed before 2025, so seats start from the Australian Electoral Commission’s own notional results on the new boundaries.',
			'One Nation contested every seat at the previous federal election, so its own previous vote shows where its voters are.',
			'Preference flows come from the AEC’s full distributions of preferences, tuned so that replaying the previous election reproduces each seat’s result. The Liberals, Nationals, LNP and CLP are scored as one Coalition, and small-party members (Katter’s, Centre Alliance) as independents.'
		]
	}
];
