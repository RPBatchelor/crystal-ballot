"""Fetch CC/PD party leader portraits from Wikipedia/Wikimedia Commons into web/static/images/leaders/
and write web/static/data/leaders.json.
"""
from __future__ import annotations

import json
import os
import subprocess
import time
import urllib.parse
from pathlib import Path

try:
    from PIL import Image, ImageOps
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

ROOT = Path(__file__).resolve().parents[2]
IMG_DIR = ROOT / "web" / "static" / "images" / "leaders"
OUT_JSON = ROOT / "web" / "static" / "data" / "leaders.json"
USER_AGENT = os.environ.get(
    "PROPHECY_USER_AGENT",
    "CrystalBallot/2.0 (https://github.com/RPBatchelor/crystal-ballot; election forecast site)",
)

# Map leader slug -> Wikipedia article title for official portrait lookup.
WIKI_PAGES: dict[str, str] = {
    "ben-carroll": "Ben Carroll",
    "jess-wilson": "Jess Wilson",
    "ellen-sandell": "Ellen Sandell",
    "daniel-andrews": "Daniel Andrews",
    "matthew-guy": "Matthew Guy",
    "samantha-ratnam": "Samantha Ratnam",
    "denis-napthine": "Denis Napthine",
    "ted-baillieu": "Ted Baillieu",
    "john-brumby": "John Brumby",
    "steve-bracks": "Steve Bracks",
    "greg-barber": "Greg Barber (politician)",
    "mike-baird": "Mike Baird",
    "luke-foley": "Luke Foley",
    "barry-ofarrell": "Barry O'Farrell",
    "kristina-keneally": "Kristina Keneally",
    "anthony-albanese": "Anthony Albanese",
    "peter-dutton": "Peter Dutton",
    "adam-bandt": "Adam Bandt",
    "scott-morrison": "Scott Morrison",
    "bill-shorten": "Bill Shorten",
    "richard-di-natale": "Richard Di Natale",
    "chris-minns": "Chris Minns",
    "dominic-perrottet": "Dominic Perrottet",
    "gladys-berejiklian": "Gladys Berejiklian",
    "michael-daley": "Michael Daley",
    "david-crisafulli": "David Crisafulli",
    "steven-miles": "Steven Miles",
    "michael-berkman": "Michael Berkman",
    "annastacia-palaszczuk": "Annastacia Palaszczuk",
    "deb-frecklington": "Deb Frecklington",
    "roger-cook": "Roger Cook (politician)",
    "libby-mettam": "Libby Mettam",
    "brad-pettitt": "Brad Pettitt",
    "mark-mcgowan": "Mark McGowan",
    "zak-kirkup": "Zak Kirkup",
    "alison-xamon": "Alison Xamon",
    "peter-malinauskas": "Peter Malinauskas",
    "ashton-hurn": "Ashton Hurn",
    "cory-bernardi": "Cory Bernardi",
    "robert-simms": "Robert Simms (politician)",
    "steven-marshall": "Steven Marshall",
    "tammy-franks": "Tammy Franks",
    "lia-finocchiaro": "Lia Finocchiaro",
    "eva-lawler": "Eva Lawler",
    "michael-gunner": "Michael Gunner",
}

ELECTIONS = {
    "vic-2026": {
        "head_title": "Premier",
        "head_before": {"name": "Ben Carroll", "party": "ALP"},
        "leaders": [
            {"bloc": "ALP", "party_label": "Labor", "name": "Ben Carroll", "slug": "ben-carroll", "seat": "Niddrie", "seat_slug": "niddrie"},
            {"bloc": "COAL", "party_label": "Coalition", "name": "Jess Wilson", "slug": "jess-wilson", "seat": "Kew", "seat_slug": "kew"},
            {"bloc": "GRN", "party_label": "Greens", "name": "Ellen Sandell", "slug": "ellen-sandell", "seat": "Melbourne", "seat_slug": "melbourne"},
            {"bloc": "ONP", "party_label": "One Nation", "name": "Warren Pickering", "slug": "warren-pickering", "seat": "Victorian leader", "seat_slug": None},
        ],
    },
    "vic-2022": {
        "head_title": "Premier",
        "head_before": {"name": "Daniel Andrews", "party": "ALP"},
        "head_after": {"name": "Daniel Andrews", "party": "ALP"},
        "leaders": [
            {"bloc": "ALP", "party_label": "Labor", "name": "Daniel Andrews", "slug": "daniel-andrews", "seat": "Mulgrave", "seat_slug": "mulgrave"},
            {"bloc": "COAL", "party_label": "Coalition", "name": "Matthew Guy", "slug": "matthew-guy", "seat": "Bulleen", "seat_slug": "bulleen"},
            {"bloc": "GRN", "party_label": "Greens", "name": "Samantha Ratnam", "slug": "samantha-ratnam", "seat": "MLC · Northern Metro", "seat_slug": None},
        ],
    },
    "vic-2018": {
        "head_title": "Premier",
        "head_before": {"name": "Daniel Andrews", "party": "ALP"},
        "head_after": {"name": "Daniel Andrews", "party": "ALP"},
        "leaders": [
            {"bloc": "ALP", "party_label": "Labor", "name": "Daniel Andrews", "slug": "daniel-andrews", "seat": "Mulgrave", "seat_slug": "mulgrave"},
            {"bloc": "COAL", "party_label": "Coalition", "name": "Matthew Guy", "slug": "matthew-guy", "seat": "Bulleen", "seat_slug": "bulleen"},
            {"bloc": "GRN", "party_label": "Greens", "name": "Samantha Ratnam", "slug": "samantha-ratnam", "seat": "MLC · Northern Metro", "seat_slug": None},
        ],
    },
    "vic-2014": {
        "head_title": "Premier",
        "head_before": {"name": "Denis Napthine", "party": "COAL"},
        "head_after": {"name": "Daniel Andrews", "party": "ALP"},
        "leaders": [
            {"bloc": "ALP", "party_label": "Labor", "name": "Daniel Andrews", "slug": "daniel-andrews", "seat": "Mulgrave", "seat_slug": "mulgrave"},
            {"bloc": "COAL", "party_label": "Coalition", "name": "Denis Napthine", "slug": "denis-napthine", "seat": "South-West Coast", "seat_slug": "south-west-coast"},
            {"bloc": "GRN", "party_label": "Greens", "name": "Greg Barber", "slug": "greg-barber", "seat": "MLC · Northern Metro", "seat_slug": None},
        ],
    },
    "vic-2010": {
        "head_title": "Premier",
        "head_before": {"name": "John Brumby", "party": "ALP"},
        "head_after": {"name": "Ted Baillieu", "party": "COAL"},
        "leaders": [
            {"bloc": "COAL", "party_label": "Coalition", "name": "Ted Baillieu", "slug": "ted-baillieu", "seat": "Hawthorn", "seat_slug": "hawthorn"},
            {"bloc": "ALP", "party_label": "Labor", "name": "John Brumby", "slug": "john-brumby", "seat": "Broadmeadows", "seat_slug": "broadmeadows"},
            {"bloc": "GRN", "party_label": "Greens", "name": "Greg Barber", "slug": "greg-barber", "seat": "MLC · Northern Metro", "seat_slug": None},
        ],
    },
    "vic-2006": {
        "head_title": "Premier",
        "head_before": {"name": "Steve Bracks", "party": "ALP"},
        "head_after": {"name": "Steve Bracks", "party": "ALP"},
        "leaders": [
            {"bloc": "ALP", "party_label": "Labor", "name": "Steve Bracks", "slug": "steve-bracks", "seat": "Williamstown", "seat_slug": "williamstown"},
            {"bloc": "COAL", "party_label": "Coalition", "name": "Ted Baillieu", "slug": "ted-baillieu", "seat": "Hawthorn", "seat_slug": "hawthorn"},
            {"bloc": "GRN", "party_label": "Greens", "name": "Greg Barber", "slug": "greg-barber", "seat": "MLC · Northern Metro", "seat_slug": None},
        ],
    },
    "federal-2025": {
        "head_title": "Prime Minister",
        "head_before": {"name": "Anthony Albanese", "party": "ALP"},
        "head_after": {"name": "Anthony Albanese", "party": "ALP"},
        "leaders": [
            {"bloc": "ALP", "party_label": "Labor", "name": "Anthony Albanese", "slug": "anthony-albanese", "seat": "Grayndler", "seat_slug": "grayndler"},
            {"bloc": "COAL", "party_label": "Coalition", "name": "Peter Dutton", "slug": "peter-dutton", "seat": "Dickson", "seat_slug": "dickson"},
            {"bloc": "GRN", "party_label": "Greens", "name": "Adam Bandt", "slug": "adam-bandt", "seat": "Melbourne", "seat_slug": "melbourne"},
        ],
    },
    "federal-2022": {
        "head_title": "Prime Minister",
        "head_before": {"name": "Scott Morrison", "party": "COAL"},
        "head_after": {"name": "Anthony Albanese", "party": "ALP"},
        "leaders": [
            {"bloc": "ALP", "party_label": "Labor", "name": "Anthony Albanese", "slug": "anthony-albanese", "seat": "Grayndler", "seat_slug": "grayndler"},
            {"bloc": "COAL", "party_label": "Coalition", "name": "Scott Morrison", "slug": "scott-morrison", "seat": "Cook", "seat_slug": "cook"},
            {"bloc": "GRN", "party_label": "Greens", "name": "Adam Bandt", "slug": "adam-bandt", "seat": "Melbourne", "seat_slug": "melbourne"},
        ],
    },
    "federal-2019": {
        "head_title": "Prime Minister",
        "head_before": {"name": "Scott Morrison", "party": "COAL"},
        "head_after": {"name": "Scott Morrison", "party": "COAL"},
        "leaders": [
            {"bloc": "COAL", "party_label": "Coalition", "name": "Scott Morrison", "slug": "scott-morrison", "seat": "Cook", "seat_slug": "cook"},
            {"bloc": "ALP", "party_label": "Labor", "name": "Bill Shorten", "slug": "bill-shorten", "seat": "Maribyrnong", "seat_slug": "maribyrnong"},
            {"bloc": "GRN", "party_label": "Greens", "name": "Richard Di Natale", "slug": "richard-di-natale", "seat": "Senator for Victoria", "seat_slug": None},
        ],
    },
    "nsw-2023": {
        "head_title": "Premier",
        "head_before": {"name": "Dominic Perrottet", "party": "COAL"},
        "head_after": {"name": "Chris Minns", "party": "ALP"},
        "leaders": [
            {"bloc": "ALP", "party_label": "Labor", "name": "Chris Minns", "slug": "chris-minns", "seat": "Kogarah", "seat_slug": "kogarah"},
            {"bloc": "COAL", "party_label": "Coalition", "name": "Dominic Perrottet", "slug": "dominic-perrottet", "seat": "Epping", "seat_slug": "epping"},
            {"bloc": "GRN", "party_label": "Greens", "name": "Greens NSW", "slug": "greens-nsw", "seat": "Collective leadership", "seat_slug": None},
        ],
    },
    "nsw-2019": {
        "head_title": "Premier",
        "head_before": {"name": "Gladys Berejiklian", "party": "COAL"},
        "head_after": {"name": "Gladys Berejiklian", "party": "COAL"},
        "leaders": [
            {"bloc": "COAL", "party_label": "Coalition", "name": "Gladys Berejiklian", "slug": "gladys-berejiklian", "seat": "Willoughby", "seat_slug": "willoughby"},
            {"bloc": "ALP", "party_label": "Labor", "name": "Michael Daley", "slug": "michael-daley", "seat": "Maroubra", "seat_slug": "maroubra"},
            {"bloc": "GRN", "party_label": "Greens", "name": "Greens NSW", "slug": "greens-nsw", "seat": "Collective leadership", "seat_slug": None},
        ],
    },
    "nsw-2015": {
        "head_title": "Premier",
        "head_before": {"name": "Mike Baird", "party": "COAL"},
        "head_after": {"name": "Mike Baird", "party": "COAL"},
        "leaders": [
            {"bloc": "COAL", "party_label": "Coalition", "name": "Mike Baird", "slug": "mike-baird", "seat": "Manly", "seat_slug": "manly"},
            {"bloc": "ALP", "party_label": "Labor", "name": "Luke Foley", "slug": "luke-foley", "seat": "Auburn", "seat_slug": "auburn"},
            {"bloc": "GRN", "party_label": "Greens", "name": "Greens NSW", "slug": "greens-nsw", "seat": "Collective leadership", "seat_slug": None},
        ],
    },
    "nsw-2011": {
        "head_title": "Premier",
        "head_before": {"name": "Kristina Keneally", "party": "ALP"},
        "head_after": {"name": "Barry O'Farrell", "party": "COAL"},
        "leaders": [
            {"bloc": "COAL", "party_label": "Coalition", "name": "Barry O'Farrell", "slug": "barry-ofarrell", "seat": "Ku-ring-gai", "seat_slug": "ku-ring-gai"},
            {"bloc": "ALP", "party_label": "Labor", "name": "Kristina Keneally", "slug": "kristina-keneally", "seat": "Heffron", "seat_slug": "heffron"},
            {"bloc": "GRN", "party_label": "Greens", "name": "Greens NSW", "slug": "greens-nsw", "seat": "Collective leadership", "seat_slug": None},
        ],
    },
    "qld-2024": {
        "head_title": "Premier",
        "head_before": {"name": "Steven Miles", "party": "ALP"},
        "head_after": {"name": "David Crisafulli", "party": "COAL"},
        "leaders": [
            {"bloc": "COAL", "party_label": "LNP", "name": "David Crisafulli", "slug": "david-crisafulli", "seat": "Broadwater", "seat_slug": "broadwater"},
            {"bloc": "ALP", "party_label": "Labor", "name": "Steven Miles", "slug": "steven-miles", "seat": "Murrumba", "seat_slug": "murrumba"},
            {"bloc": "GRN", "party_label": "Greens", "name": "Michael Berkman", "slug": "michael-berkman", "seat": "Maiwar", "seat_slug": "maiwar"},
        ],
    },
    "qld-2020": {
        "head_title": "Premier",
        "head_before": {"name": "Annastacia Palaszczuk", "party": "ALP"},
        "head_after": {"name": "Annastacia Palaszczuk", "party": "ALP"},
        "leaders": [
            {"bloc": "ALP", "party_label": "Labor", "name": "Annastacia Palaszczuk", "slug": "annastacia-palaszczuk", "seat": "Inala", "seat_slug": "inala"},
            {"bloc": "COAL", "party_label": "LNP", "name": "Deb Frecklington", "slug": "deb-frecklington", "seat": "Nanango", "seat_slug": "nanango"},
            {"bloc": "GRN", "party_label": "Greens", "name": "Michael Berkman", "slug": "michael-berkman", "seat": "Maiwar", "seat_slug": "maiwar"},
        ],
    },
    "wa-2025": {
        "head_title": "Premier",
        "head_before": {"name": "Roger Cook", "party": "ALP"},
        "head_after": {"name": "Roger Cook", "party": "ALP"},
        "leaders": [
            {"bloc": "ALP", "party_label": "Labor", "name": "Roger Cook", "slug": "roger-cook", "seat": "Kwinana", "seat_slug": "kwinana"},
            {"bloc": "COAL", "party_label": "Liberal & National", "name": "Libby Mettam", "slug": "libby-mettam", "seat": "Vasse", "seat_slug": "vasse"},
            {"bloc": "GRN", "party_label": "Greens", "name": "Brad Pettitt", "slug": "brad-pettitt", "seat": "MLC · South Metro", "seat_slug": None},
        ],
    },
    "wa-2021": {
        "head_title": "Premier",
        "head_before": {"name": "Mark McGowan", "party": "ALP"},
        "head_after": {"name": "Mark McGowan", "party": "ALP"},
        "leaders": [
            {"bloc": "ALP", "party_label": "Labor", "name": "Mark McGowan", "slug": "mark-mcgowan", "seat": "Rockingham", "seat_slug": "rockingham"},
            {"bloc": "COAL", "party_label": "Liberal & National", "name": "Zak Kirkup", "slug": "zak-kirkup", "seat": "Dawesville", "seat_slug": "dawesville"},
            {"bloc": "GRN", "party_label": "Greens", "name": "Alison Xamon", "slug": "alison-xamon", "seat": "MLC · North Metro", "seat_slug": None},
        ],
    },
    "sa-2026": {
        "head_title": "Premier",
        "head_before": {"name": "Peter Malinauskas", "party": "ALP"},
        "head_after": {"name": "Peter Malinauskas", "party": "ALP"},
        "leaders": [
            {"bloc": "ALP", "party_label": "Labor", "name": "Peter Malinauskas", "slug": "peter-malinauskas", "seat": "Croydon", "seat_slug": "croydon"},
            {"bloc": "COAL", "party_label": "Liberal", "name": "Ashton Hurn", "slug": "ashton-hurn", "seat": "Schubert", "seat_slug": "schubert"},
            {"bloc": "ONP", "party_label": "One Nation", "name": "Cory Bernardi", "slug": "cory-bernardi", "seat": "MLC · Legislative Council", "seat_slug": None},
            {"bloc": "GRN", "party_label": "Greens", "name": "Robert Simms", "slug": "robert-simms", "seat": "MLC · Legislative Council", "seat_slug": None},
        ],
    },
    "sa-2022": {
        "head_title": "Premier",
        "head_before": {"name": "Steven Marshall", "party": "COAL"},
        "head_after": {"name": "Peter Malinauskas", "party": "ALP"},
        "leaders": [
            {"bloc": "ALP", "party_label": "Labor", "name": "Peter Malinauskas", "slug": "peter-malinauskas", "seat": "Croydon", "seat_slug": "croydon"},
            {"bloc": "COAL", "party_label": "Liberal", "name": "Steven Marshall", "slug": "steven-marshall", "seat": "Dunstan", "seat_slug": "dunstan"},
            {"bloc": "GRN", "party_label": "Greens", "name": "Tammy Franks", "slug": "tammy-franks", "seat": "MLC · Legislative Council", "seat_slug": None},
        ],
    },
    "nt-2024": {
        "head_title": "Chief Minister",
        "head_before": {"name": "Eva Lawler", "party": "ALP"},
        "head_after": {"name": "Lia Finocchiaro", "party": "COAL"},
        "leaders": [
            {"bloc": "COAL", "party_label": "CLP", "name": "Lia Finocchiaro", "slug": "lia-finocchiaro", "seat": "Spillett", "seat_slug": "spillett"},
            {"bloc": "ALP", "party_label": "Labor", "name": "Eva Lawler", "slug": "eva-lawler", "seat": "Drysdale", "seat_slug": "drysdale"},
            {"bloc": "GRN", "party_label": "Greens", "name": "Kat McNamara", "slug": "kat-mcnamara", "seat": "Nightcliff", "seat_slug": "nightcliff"},
        ],
    },
    "nt-2020": {
        "head_title": "Chief Minister",
        "head_before": {"name": "Michael Gunner", "party": "ALP"},
        "head_after": {"name": "Michael Gunner", "party": "ALP"},
        "leaders": [
            {"bloc": "ALP", "party_label": "Labor", "name": "Michael Gunner", "slug": "michael-gunner", "seat": "Fannie Bay", "seat_slug": "fannie-bay"},
            {"bloc": "COAL", "party_label": "CLP", "name": "Lia Finocchiaro", "slug": "lia-finocchiaro", "seat": "Spillett", "seat_slug": "spillett"},
            {"bloc": "GRN", "party_label": "Greens", "name": "NT Greens", "slug": "nt-greens", "seat": "Territory-wide", "seat_slug": None},
        ],
    },
}


def _curl_bytes(url: str) -> bytes:
    res = subprocess.run(
        ["curl.exe", "-fsSL", "-A", USER_AGENT, "--max-time", "20", url],
        capture_output=True,
        check=True,
    )
    return res.stdout


def fetch_json(url: str) -> dict:
    return json.loads(_curl_bytes(url).decode("utf-8"))


def download_portrait(slug: str, title: str) -> tuple[str | None, str | None]:
    """Return (public_path, credit) or (None, None) if no free portrait exists."""
    params = urllib.parse.urlencode({
        "action": "query",
        "format": "json",
        "titles": title,
        "prop": "pageimages",
        "piprop": "thumbnail|name",
        "pilicense": "free",
        "pithumbsize": 320,
        "redirects": 1,
    })
    data = fetch_json(f"https://en.wikipedia.org/w/api.php?{params}")
    pages = data.get("query", {}).get("pages", {})
    page = next(iter(pages.values()), {})
    thumb = page.get("thumbnail", {}).get("source")
    img_name = page.get("pageimage")
    if not thumb or not img_name:
        return None, None
    # Skip SVG logos / placeholders
    if img_name.lower().endswith(".svg"):
        return None, None

    # Fetch license info from Commons
    credit = "Wikimedia Commons"
    try:
        lp = urllib.parse.urlencode({
            "action": "query",
            "format": "json",
            "titles": f"File:{img_name}",
            "prop": "imageinfo",
            "iiprop": "extmetadata",
        })
        ldata = fetch_json(f"https://commons.wikimedia.org/w/api.php?{lp}")
        lpages = ldata.get("query", {}).get("pages", {})
        lpage = next(iter(lpages.values()), {})
        meta = (lpage.get("imageinfo") or [{}])[0].get("extmetadata", {})
        lic = meta.get("LicenseShortName", {}).get("value")
        if lic:
            credit = f"Wikimedia Commons ({lic})"
    except Exception:
        pass

    raw = _curl_bytes(thumb)

    if HAS_PIL:
        from io import BytesIO
        im = Image.open(BytesIO(raw)).convert("RGB")
        # Crop to 4:5 portrait biased slightly toward the top (faces)
        im = ImageOps.fit(im, (240, 300), method=Image.Resampling.LANCZOS, centering=(0.5, 0.22))
        out = IMG_DIR / f"{slug}.webp"
        im.save(out, format="WEBP", quality=82)
        return f"/images/leaders/{slug}.webp", credit
    else:
        ext = ".png" if thumb.lower().endswith(".png") else ".jpg"
        out = IMG_DIR / f"{slug}{ext}"
        out.write_bytes(raw)
        return f"/images/leaders/{slug}{ext}", credit


def main() -> None:
    IMG_DIR.mkdir(parents=True, exist_ok=True)
    cache: dict[str, tuple[str | None, str | None]] = {}
    for slug, title in WIKI_PAGES.items():
        # Reuse existing file if already downloaded
        existing_webp = IMG_DIR / f"{slug}.webp"
        existing_jpg = IMG_DIR / f"{slug}.jpg"
        if existing_webp.exists():
            cache[slug] = (f"/images/leaders/{slug}.webp", "Wikimedia Commons")
            continue
        if existing_jpg.exists():
            cache[slug] = (f"/images/leaders/{slug}.jpg", "Wikimedia Commons")
            continue
        try:
            path, credit = download_portrait(slug, title)
            cache[slug] = (path, credit)
            print(f"{'OK  ' if path else 'MISS'} {slug:<22} -> {path or 'fallback'} ({credit or '-'})")
        except Exception as exc:
            cache[slug] = (None, None)
            print(f"ERR  {slug:<22} -> {exc}")
        time.sleep(0.15)

    out_data = {}
    for eid, spec in ELECTIONS.items():
        leaders_out = []
        for entry in spec["leaders"]:
            path, credit = cache.get(entry["slug"], (None, None))
            item = {
                "bloc": entry["bloc"],
                "party_label": entry["party_label"],
                "name": entry["name"],
                "seat": entry["seat"],
                "seat_slug": entry["seat_slug"],
                "portrait": path,
                "credit": credit,
            }
            leaders_out.append(item)
        out_data[eid] = {
            "head_title": spec["head_title"],
            "head_before": spec.get("head_before"),
            "head_after": spec.get("head_after"),
            "leaders": leaders_out,
        }

    OUT_JSON.write_text(json.dumps(out_data, indent=1) + "\n", encoding="utf-8")
    n_img = sum(1 for v in cache.values() if v[0])
    print(f"\nWrote {OUT_JSON} ({len(out_data)} elections, {n_img}/{len(WIKI_PAGES)} portraits, PIL={HAS_PIL})")


if __name__ == "__main__":
    main()
