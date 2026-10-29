"""Canonical party codes.

Electoral commissions name parties inconsistently across elections ("Australian Labor
Party - Victorian Branch", "Labor", "ALP"...). Everything downstream uses short codes,
and the model groups codes into blocs (ALP, COAL, GRN, ONP, IND, OTH).
"""

from __future__ import annotations

import re

# (pattern, code). First match wins; patterns are matched case-insensitively.
_PATTERNS: list[tuple[str, str]] = [
    (r"labor|\balp\b|^a\.l\.p\.?$", "ALP"),
    (r"liberal national|\blnp\b", "LNP"),
    (r"liberal democrat", "LDP"),
    (r"\bclp\b|country liberal", "CLP"),
    (r"katter", "KAP"),
    (r"centre alliance", "CA"),
    (r"\bliberal\b", "LIB"),
    (r"national", "NAT"),
    (r"green", "GRN"),
    (r"one nation|hanson", "ONP"),
    (r"family first", "FFP"),
    (r"socialist", "VS"),
    (r"animal justice", "AJP"),
    (r"legalise cannabis", "LCP"),
    (r"reason|sex party", "REA"),
    (r"democratic labour|\bdlp\b", "DLP"),
    (r"shooters", "SFF"),
    (r"freedom party", "FPV"),
    (r"united australia|palmer", "UAP"),
    (r"sustainable australia", "SAP"),
    (r"justice party|derryn hinch", "DHJ"),
    (r"health australia", "HAP"),
    (r"new democrats", "ND"),
    (r"companions", "CPP"),
    (r"transport matters", "TMP"),
    (r"australian christians|christian", "CHR"),
    (r"angry victorians", "AVP"),
    (r"^\s*$|independent", "IND"),
]

BLOC = {
    "ALP": "ALP",
    "LIB": "COAL",
    "NAT": "COAL",
    "LNP": "COAL",
    "CLP": "COAL",
    "COAL": "COAL",
    # Minor parties holding seats as de facto independents (Kennedy, Mayo): grouping
    # them with Others would exclude them first in every simulated count.
    "KAP": "IND",
    "CA": "IND",
    "GRN": "GRN",
    "ONP": "ONP",
    "IND": "IND",
}


def party_code(name: str | None) -> str:
    """Map an electoral-commission party name to a short code ('IND' for blank)."""
    text = (name or "").strip()
    for pattern, code in _PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return code
    # Unknown minor party: stable code from initials so it is still distinguishable.
    initials = "".join(w[0] for w in re.findall(r"[A-Za-z]+", text) if w[0].isupper())
    return f"X_{initials or 'UNK'}"


def bloc(code: str) -> str:
    """Model bloc for a party code."""
    return BLOC.get(code, "OTH")
