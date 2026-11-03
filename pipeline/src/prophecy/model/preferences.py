"""Preference flows and the exclusion-count simulator.

Flow model (Luce choice): when a candidate of bloc i is excluded, each ballot goes to
remaining bloc j with probability w[i, j] / sum_{k in remaining} w[i, k]. The weights
are estimated from the VEC full distributions of preferences, which observe transfers
under many different sets of remaining candidates.

One Nation barely contested 2022, so flows *to* and *from* ONP are set to reproduce the
ALP-v-Coalition and ALP-v-ONP two-party-preferred figures reported by 2026 pollsters
(see ``ONP_FLOW_TARGETS``) and given wide uncertainty.

Optional preferential voting (NSW): a ballot with no further preference *exhausts*.
Exhaustion is one more Luce option, always available, with weight ``exhaust[i]`` on the
same scale as row i of the flow weights (which sum to 1 over all blocs). The fewer
candidates remain, the larger its share, as in real counts. ``exhaust=None`` is full
preferential voting.
"""

from __future__ import annotations

import numpy as np
import polars as pl

BLOCS = ["ALP", "COAL", "GRN", "ONP", "IND", "OTH"]
B = len(BLOCS)
IDX = {b: i for i, b in enumerate(BLOCS)}

# Share going to the *first* named party in a head-to-head between the two, for votes
# of the given origin. Derived from 2026 polls' reported 2PPs; see ``calibrate_onp``.
ONP_FLOW_TARGETS = {
    # origin: (to ALP share in ALP-v-ONP, to COAL share in COAL-v-ONP)
    "COAL": (0.50, None),
    "GRN": (0.88, 0.75),
    "IND": (0.55, 0.60),
    "OTH": (0.40, 0.55),
    # ONP's own preferences: share to ALP in ALP-v-COAL. Federal elections run ~35%;
    # 2026 Vic pollsters' 2PPs back out to 20-35% (RedBridge low, DemosAU high).
    "ONP": (0.30, None),
}


# Prior rows for blocs never excluded in the observed distributions (in 2022 Labor was
# always in the final two). Labor voters: Greens strongly over Coalition (~75/25,
# consistent with federal Labor preference flows), Coalition over One Nation (~75/25).
PRIOR_ROWS = {
    "ALP": {"COAL": 0.15, "GRN": 0.45, "ONP": 0.05, "IND": 0.20, "OTH": 0.15},
}


EXH = "EXH"  # to_bloc of exhausted ballots in DoP transfers


def estimate_weights(transfers: pl.DataFrame, iters: int = 200) -> np.ndarray:
    """MM estimation of Luce weights w[from, to] from DoP transfer events.

    ``transfers`` has one row per (district, count, from_bloc, to_bloc) with votes,
    including zero-vote receivers so the choice set is known.
    """
    return estimate_flows(transfers, iters)[0]


def estimate_flows(transfers: pl.DataFrame, iters: int = 200) -> tuple[np.ndarray, np.ndarray | None]:
    """Flow weights and, when the DoPs record exhausted ballots, exhaustion weights."""
    opv = EXH in set(transfers["to_bloc"].unique())
    K = B + 1 if opv else B  # exhaustion is column B
    col = {**IDX, EXH: B}
    w = np.ones((B, K))
    np.fill_diagonal(w, 0.0)
    events = []
    for (_, _, frm), g in transfers.group_by("district", "count", "from_bloc"):
        # Aggregate receivers by bloc (several minor parties can share a bloc).
        by = g.group_by("to_bloc").agg(pl.col("votes").sum())
        to = np.array([col[b] for b in by["to_bloc"]])
        v = by["votes"].to_numpy().astype(float)
        if v.sum() <= 0:
            continue
        # A bloc with several candidates remaining is counted once with summed votes;
        # multiplicity is ignored (minor-party blocs only).
        events.append((IDX[frm], to, v))
    for _ in range(iters):
        num = np.zeros((B, K))
        den = np.zeros((B, K))
        for i, to, v in events:
            total = v.sum()
            num[i, to] += v
            den[i, to] += total / w[i, to].sum()
        with np.errstate(divide="ignore", invalid="ignore"):
            new = np.where(den > 0, num / den, w)
        new[new <= 0] = 1e-4
        np.fill_diagonal(new, 0.0)
        w = new / new.sum(axis=1, keepdims=True)
    observed = {i for i, _, _ in events}
    exhaust = None
    if opv:
        # Rescale so flow weights sum to 1 over blocs; exhaustion on the same scale.
        exhaust = w[:, B] / w[:, :B].sum(axis=1)
        w = w[:, :B] / w[:, :B].sum(axis=1, keepdims=True)
        seen = [i for i in range(B) if i in observed]
        exhaust[[i for i in range(B) if i not in observed]] = np.median(exhaust[seen])
    for name, row in PRIOR_ROWS.items():
        if IDX[name] not in observed:
            w[IDX[name]] = [row.get(b, 0.0) for b in BLOCS]
    return w, exhaust


def calibrate_to_results(w: np.ndarray, primaries: np.ndarray, alp_tcp: np.ndarray,
                         origins: tuple[str, ...] = ("GRN", "OTH", "IND"),
                         outlier: float = 15.0,
                         exhaust: np.ndarray | None = None) -> tuple[np.ndarray, dict]:
    """Tilt each origin's ALP-v-COAL split so replayed counts match actual 2CPs.

    The DoPs cover only 39 seats and lump heterogeneous minor parties together; every
    seat's final ALP-v-Coalition result is an additional, direct constraint on flows.

    primaries: D x B seat primaries (fractions); alp_tcp: D actual ALP 2CP (%) for
    ALP-v-COAL seats, NaN elsewhere. Seats where the replay mispredicts the final pair
    by more than ``outlier`` points are excluded (a different count path, not a flow error).
    """
    from scipy.optimize import minimize

    a, c = IDX["ALP"], IDX["COAL"]
    rows = [IDX[o] for o in origins]
    mask = ~np.isnan(alp_tcp)

    def tilted(theta: np.ndarray) -> np.ndarray:
        t = w.copy()
        for i, th in zip(rows, theta):
            total = t[i, a] + t[i, c]
            ratio = t[i, a] / t[i, c] * np.exp(th)
            t[i, a], t[i, c] = total * ratio / (1 + ratio), total / (1 + ratio)
        return t

    def errors(theta: np.ndarray) -> np.ndarray:
        ex = None if exhaust is None else exhaust[None]
        _, final = count(primaries[None], tilted(theta)[None], ex)
        return final[0, :, a] * 100 - alp_tcp

    keep = mask & (np.abs(errors(np.zeros(len(rows)))) < outlier)
    res = minimize(lambda th: np.mean(errors(th)[keep] ** 2) + 0.5 * np.sum(th**2),
                   np.zeros(len(rows)), method="Nelder-Mead")
    err = errors(res.x)[keep]
    info = {"theta": dict(zip(origins, np.round(res.x, 3).tolist())),
            "bias": float(err.mean()), "sd": float(err.std()), "n": int(keep.sum())}
    return tilted(res.x), info


def apply_onp_targets(w: np.ndarray) -> np.ndarray:
    """Overwrite ONP-related weights so head-to-head splits match poll-implied targets."""
    w = w.copy()
    a, c, o = IDX["ALP"], IDX["COAL"], IDX["ONP"]
    for origin, (to_alp, to_coal) in ONP_FLOW_TARGETS.items():
        i = IDX[origin]
        if origin == "ONP":
            # ONP voters' split between ALP and COAL.
            total = w[i, a] + w[i, c]
            w[i, a], w[i, c] = to_alp * total, (1 - to_alp) * total
            continue
        # ONP weight implied by each head-to-head target; combine on the log scale.
        implied = [w[i, a] * (1 - to_alp) / to_alp]
        if to_coal is not None:
            implied.append(w[i, c] * (1 - to_coal) / to_coal)
        w[i, o] = float(np.exp(np.mean(np.log(implied))))
    np.fill_diagonal(w, 0.0)
    return w / w.sum(axis=1, keepdims=True)


def draw_weights(w: np.ndarray, n: int, rng: np.random.Generator,
                 concentration: np.ndarray | None = None) -> np.ndarray:
    """Dirichlet draws around the point estimate: n x B x B."""
    if concentration is None:
        concentration = np.full(B, 60.0)
        concentration[IDX["ONP"]] = 15.0  # ONP flows are poll-derived, far less certain
        concentration[IDX["IND"]] = 15.0
    out = np.zeros((n, B, B))
    for i in range(B):
        alpha = np.maximum(w[i] * concentration[i], 1e-3)
        alpha[i] = 1e-9
        draws = rng.dirichlet(alpha, size=n)
        draws[:, i] = 0.0
        out[:, i, :] = draws
    # ONP-receiving weights get extra spread since they are calibrated, not observed.
    onp = IDX["ONP"]
    out[:, :, onp] *= np.exp(rng.normal(0, 0.25, size=(n, B)))
    out[:, onp, onp] = 0.0
    return out


def draw_exhaust(exhaust: np.ndarray, n: int, rng: np.random.Generator,
                 sd: float = 0.2) -> np.ndarray:
    """Exhaustion weights per simulation (n x B), log-normal around the estimate."""
    return exhaust[None, :] * np.exp(rng.normal(0, sd, size=(n, B)))


def count(shares: np.ndarray, weights: np.ndarray,
          exhaust: np.ndarray | None = None) -> tuple[np.ndarray, np.ndarray]:
    """Run an exclusion count for every simulation and seat.

    shares:  S x D x B primary shares (0 where a bloc has no candidate)
    weights: S x B x B flow weights (one set per simulation)
    exhaust: S x B exhaustion weights (optional preferential voting), or None
    Returns (winner index S x D, final two-candidate shares S x D x B; under optional
    preferential voting these are shares of the ballots still in the count).
    """
    votes = shares.astype(float).copy()
    alive = votes > 0
    S = votes.shape[0]
    for _ in range(B - 2):
        n_alive = alive.sum(axis=2)
        active = n_alive > 2
        if not active.any():
            break
        masked = np.where(alive, votes, np.inf)
        # "Others" aggregates several minor candidates who are each excluded early in a
        # real count, so the bloc goes first rather than competing on its combined total.
        oth = IDX["OTH"]
        masked[..., oth] = np.where(alive[..., oth], -1.0, np.inf)
        loser = masked.argmin(axis=2)  # S x D
        loser_votes = np.take_along_axis(votes, loser[..., None], axis=2)[..., 0]
        # Flow weights from each seat's excluded bloc, restricted to survivors: S x D x B.
        w_from = weights[np.arange(S)[:, None], loser]
        survivors = alive.copy()
        np.put_along_axis(survivors, loser[..., None], False, axis=2)
        w_from = np.where(survivors, w_from, 0.0)
        tot = w_from.sum(axis=2, keepdims=True)
        if exhaust is not None:
            tot = tot + exhaust[np.arange(S)[:, None], loser][..., None]
        tot[tot == 0] = 1.0
        transfer = loser_votes[..., None] * w_from / tot
        votes = np.where(active[..., None], votes + transfer, votes)
        np.put_along_axis(votes, loser[..., None],
                          np.where(active, 0.0, loser_votes)[..., None], axis=2)
        alive = np.where(active[..., None], survivors, alive)
    winner = votes.argmax(axis=2)
    total = votes.sum(axis=2, keepdims=True)
    return winner, votes / np.where(total > 0, total, 1)


def two_party(primary: np.ndarray, weights: np.ndarray, a: str, b: str,
              exhaust: np.ndarray | None = None) -> np.ndarray:
    """Head-to-head share (%) for party ``a`` against ``b`` (S,).

    Runs a sequential count in which every other bloc is excluded, smallest first
    (Others first), so preferences pass through intermediate parties exactly as in a
    real count. Direct pairwise flows understate this (e.g. Others -> Greens -> Labor).
    With ``exhaust`` (S x B), exhausted ballots leave the count, as in NSW's 2PP.
    """
    ia, ib = IDX[a], IDX[b]
    votes = primary.astype(float).copy()
    alive = votes > 0
    alive[:, [ia, ib]] = True
    S = votes.shape[0]
    rows = np.arange(S)
    for _ in range(B - 2):
        candidates = alive.copy()
        candidates[:, [ia, ib]] = False
        if not candidates.any():
            break
        masked = np.where(candidates, votes, np.inf)
        masked[:, IDX["OTH"]] = np.where(candidates[:, IDX["OTH"]], -1.0, np.inf)
        loser = masked.argmin(axis=1)
        has = candidates[rows, loser]
        moving = np.where(has, votes[rows, loser], 0.0)
        alive[rows, loser] = np.where(has, False, alive[rows, loser])
        w_from = np.where(alive, weights[rows, loser], 0.0)
        tot = w_from.sum(axis=1, keepdims=True)
        if exhaust is not None:
            tot = tot + exhaust[rows, loser][:, None]
        votes += moving[:, None] * w_from / np.where(tot > 0, tot, 1)
        votes[rows, loser] = np.where(has, 0.0, votes[rows, loser])
    return 100 * votes[:, ia] / (votes[:, ia] + votes[:, ib])
