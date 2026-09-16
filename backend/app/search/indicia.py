"""Reading a listing for statements about where the plot is.

Nothing here talks to a service. It turns text into *Indizien* -- one statement
each, with the sentence it came from and how far that source can be trusted --
and the search then decides which of them are worth a request.

Two measured rules shape the whole module:

* **Extract the relation, never the frequency.** Against the 5 339 names in the
  district directory, the reference listing scores Grimma 3x and Großbothen 3x,
  and Grimma is wrong -- it is named that often precisely because the plot is
  6 km away from it. So a place name is only worth something together with
  "Ortsteil von", "am Ortsrand von" or "6 km entfernt".
* **A garbled parcel number is worse than none.** Text recognition at 7 deg
  returned ``Flurstück 790717``: it found the word and corrupted the digits, and
  a plausible wrong number resolves to a real but foreign parcel. The AdV parcel
  key is 20 characters with five for the numerator and four for the denominator,
  so anything longer is structurally impossible and is rejected here rather than
  sent to the cadastre.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from ..gemarkung_index import GemarkungDirectory, GemarkungEntry, base_name, fold
from ..schemas import Indiz, IndizQuelle, Ortsbeziehung

# How far each source is trusted, and thereby which one wins a contradiction:
# an official extract outranks the platform's attribute list, which outranks
# the body text, which outranks the pin. The numbers only order; a conflict is
# always shown, never silently decided.
SOURCE_CONFIDENCE: dict[IndizQuelle, float] = {
    "nutzer": 1.00,
    "bild": 0.95,
    "attribut": 0.80,
    "fliesstext": 0.60,
    "modell": 0.45,
    "standortfeld": 0.35,
    # Measured at 6 235 m from the parcel actually offered. It may refute a
    # candidate; it may never narrow the search.
    "pin": 0.15,
}

# The AdV parcel key is 20 characters: six for the district, three for the
# Flur, five for the numerator, four for the denominator, two spare. Those two
# widths are the whole validity test a number can be given without asking the
# cadastre -- and they are exactly what catches a garbled reading.
MAX_ZAEHLER_DIGITS = 5
MAX_NENNER_DIGITS = 4

# „Flurstück 790/11“, „Flurstücksnummer: 85/1“, „Flst. 476“, „Flurstück 41/e“.
_PARCEL_RE = re.compile(
    r"(?:flurst(?:ü|ue)ck(?:s?nummer)?|flst\.?|flurstuecke?)\s*(?:nr\.?|nummer)?\s*[:.]?\s*"
    r"(\d{1,6})\s*(?:/\s*(\d{1,5}|[a-zA-Z]))?",
    re.IGNORECASE,
)

# „Gemarkung Großbothen“, „Gemarkung: Mölkau (144241)“.
_DISTRICT_RE = re.compile(
    r"gemarkung\s*[:.]?\s*([A-ZÄÖÜ][\wäöüßÄÖÜ.\-]*(?:[ -][A-ZÄÖÜ][\wäöüßÄÖÜ.\-]*)?)",
    re.IGNORECASE,
)

# „502 m²“, „ca. 1.104 qm“, „ab 450 m2“, „450–600 m²“.
_AREA_RE = re.compile(
    r"(?:(?P<wording>ca\.?|circa|rund|etwa|ungef(?:ä|ae)hr|ab|mind\.?|mindestens|gut|knapp)\s*)?"
    r"(?P<from>\d{1,3}(?:[.\s]\d{3})*(?:,\d+)?|\d+(?:,\d+)?)"
    r"(?:\s*(?:-|–|bis)\s*(?P<to>\d{1,3}(?:[.\s]\d{3})*(?:,\d+)?|\d+(?:,\d+)?))?"
    r"\s*(?:m²|m2|qm|quadratmeter)",
    re.IGNORECASE,
)

_STREET_RE = re.compile(
    r"\b([A-ZÄÖÜ][\wäöüßÄÖÜ.\-]{2,}(?:er)?[ -]?"
    r"(?:[Ss]tra(?:ß|ss)e|[Ww]eg|[Gg]asse|[Aa]llee|[Pp]latz|[Rr]ing|[Dd]amm|[Cc]haussee|[Ss]teig))\b"
)

# What ties a place name to the plot. Order matters: the first pattern that
# matches around a name decides, and "liegt_in" is checked before the weaker
# readings so „OT von Grimma“ is not mistaken for a mere mention.
_RELATION_PATTERNS: tuple[tuple[Ortsbeziehung, re.Pattern[str]], ...] = (
    (
        "liegt_in",
        re.compile(
            r"(?:ortsteil|OT|stadtteil|gemeindeteil)\s+(?:von\s+)?|"
            r"(?:am\s+)?ortsrand\s+von\s+|"
            r"(?:gelegen|liegt|befindet\s+sich)\s+(?:sich\s+)?in\s+|"
            r"\bin\s+(?:der\s+|dem\s+)?(?:ortslage\s+)?",
            re.IGNORECASE,
        ),
    ),
    (
        "liegt_an",
        # „Anbindung an Leipzig“ and „Nähe zu Leipzig“ are statements about how
        # well connected the plot is, not about what it borders — and Leipzig
        # holds parcels of every size, so reading them as location put two
        # false candidates next to the right one.
        re.compile(
            r"(?<!anbindung )(?<!verbindung )(?<!anschluss )(?<!nähe )(?<!naehe )"
            r"(?:direkt\s+)?(?:an|am)\s+(?:der\s+|dem\s+)?",
            re.IGNORECASE,
        ),
    ),
    (
        "entfernt_von",
        re.compile(
            r"(?:\d+[.,]?\d*\s*(?:km|kilometer|minuten|fahrminuten|gehminuten)\s*"
            r"(?:entfernte?n?|nach|bis|von|zur?|entfernung)?\s*"
            # „…entfernte Kreisstadt Grimma“: one noun may stand between the
            # distance and the name without breaking the statement.
            r"(?:[A-ZÄÖÜ][\wäöüß]+\s+)?)|"
            r"(?:entfernung\s+(?:nach|zu[rm]?)\s+)|(?:n(?:ä|ae)he\s+(?:von\s+)?)",
            re.IGNORECASE,
        ),
    ),
)

# How much of the sentence before a name is searched for a relation trigger.
_RELATION_WINDOW = 60

# Which relations make a named place worth a request. „erwaehnt“ deliberately
# does not: a place the text merely contains is not a statement about where the
# plot is, and in German -- where every noun is capitalised -- it is as likely
# to be the word „Wiesen“ as the Gemarkung of that name.
ANCHORING = ("liegt_in", "liegt_an", None)

# A place name, as German writes one.
_NAME = r"[A-ZÄÖÜ][\wäöüßÄÖÜ\-]{2,}(?:[ -][A-ZÄÖÜ][\wäöüßÄÖÜ\-]+)?"

# „Ortsteil Plagwitz von Machern“ says two different things about two different
# places, one level apart: Plagwitz is where the plot is, Machern is the
# municipality it belongs to. Reading both as candidate cadastral districts is
# what made the reference listing look contested when it is not.
#
# The two orderings both occur and neither is rare:
#
#     Ortsteil Plagwitz von Machern        district first
#     Ortsteil Lobstädt bei Neukieritzsch  district first
#     Ortsteil Plagwitz der Gemeinde Machern
#     Großbothen, einem OT von Grimma      district before the word
#
# Getting the *level* right is what makes the municipality usable, and the
# municipality is what separates the two Gemarkungen called Plagwitz — one in
# Machern, one in Leipzig.
_OT_NAMED_RE = re.compile(
    rf"(?:OT|Ortsteil|Stadtteil|Gemeindeteil)\s+(?P<district>{_NAME})\s+"
    rf"(?:von|bei|in|der\s+Gemeinde|der\s+Stadt|des\s+Marktes)\s+(?P<municipality>{_NAME})",
)
_OT_BEFORE_RE = re.compile(
    rf"(?P<district>{_NAME})\s*,\s*(?:einem?\s+|ein\s+)?"
    rf"(?:OT|Ortsteil|Stadtteil|Gemeindeteil)\s+(?:von|der|des)\s+(?P<municipality>{_NAME})",
)
_OT_PLAIN_RE = re.compile(
    rf"(?:einem?\s+|ein\s+)?(?:OT|Ortsteil|Stadtteil|Gemeindeteil)\s+(?:von|der|des)\s+"
    rf"(?P<municipality>{_NAME})",
)

# The platform's location field, read around its postcode. Five digits are the
# one unambiguous token in a German location line, and the three portals
# recorded put everything else in three different orders around them:
#
#     Burghausen-Rückmarsdorf, 04178 Leipzig, Sachsen   ImmoScout
#     04668 Sachsen – Grimma                            Kleinanzeigen
#     Maschinenhausstraße, 01587 Riesa, Sachsen         ohne-makler
#
# Behind the postcode stands the municipality — unless that slot holds the
# Bundesland, in which case the municipality is behind the dash. That is the
# cheapest way there is to tell two districts of the same name apart, and the
# field is reliable about it even though its coordinate is not: the pin sits
# 6 235 m out *because* it is the municipality's geocode, so the name it was
# geocoded from is exactly the part that holds.
#
# In front of the postcode stands the district the portal names, where it names
# one — ImmoScout puts its Ortsteil there. ohne-makler puts a street there
# instead, which is why the head only counts when the directory knows it.
_LOCALITY_RE = re.compile(
    rf"(?:(?P<district>{_NAME})\s*[,;]\s*)?"
    rf"(?<!\d)(?P<plz>\d{{5}})(?!\d)[\s,]*(?P<tail>{_NAME})?"
    rf"(?:\s*[-–—]\s*(?P<behind>{_NAME}))?"
)
# The same field without its postcode — „Sachsen - Machern“, which is the shape
# the recorded adverts carry. Then the municipality is simply the tail, and
# there is no slot a district could stand in.
_LOCALITY_TAIL_RE = re.compile(rf"(?:^|[-–—])\s*(?P<tail>{_NAME})\s*$")

# The same field names the *federal state*, and that is the one statement in a
# listing this tool can be certain it cannot serve. ALKIS is state-specific, so
# a plot in Sachsen-Anhalt has no Saxon Flurstück — and a Saxon namesake of the
# village it names is a real parcel a hundred kilometres away.
#
# Longest first, and matched as whole words: „Sachsen-Anhalt“ contains
# „Sachsen“, and reading it as Saxony is exactly the mistake this guards.
_FEDERAL_STATES = (
    "Baden-Württemberg",
    "Mecklenburg-Vorpommern",
    "Nordrhein-Westfalen",
    "Rheinland-Pfalz",
    "Schleswig-Holstein",
    "Sachsen-Anhalt",
    "Niedersachsen",
    "Brandenburg",
    "Thüringen",
    "Hamburg",
    "Saarland",
    "Sachsen",
    "Bayern",
    "Berlin",
    "Bremen",
    "Hessen",
)
_STATE_RE = re.compile(
    r"(?<![\wäöüßÄÖÜ-])(" + "|".join(re.escape(name) for name in _FEDERAL_STATES) + r")(?![\wäöüß-])"
)


def federal_state(adresse: str | None) -> str | None:
    """The Bundesland the platform's location field names, if it names one.

    „06796 Sachsen-Anhalt - Brehna“ is the whole answer to a listing this tool
    cannot serve, and it is free: no request, no model, no geometry. All five
    recorded adverts carry the state in this field, in this shape.
    """

    if not adresse:
        return None
    match = _STATE_RE.search(adresse)
    return match.group(1) if match else None


def outside_saxony(adresse: str | None) -> str | None:
    """The state named, when the listing places itself outside Saxony.

    ``None`` when the field says Sachsen, names no state at all, or is missing —
    absence is not evidence, and only a state actually named may stop a run.
    """

    state = federal_state(adresse)
    return None if state in (None, "Sachsen") else state

# A street name that begins with one of these is a sentence, not a street:
# „Ihr Platz zum Träumen“ is a headline and „einen befahrbaren Feldweg“ is a
# path through a field. German capitalises every noun, so the usual signal —
# a capital letter — says nothing here.
_NOT_A_STREET_PREFIX = (
    "ihr", "ihre", "der", "die", "das", "den", "dem", "ein", "eine", "einen",
    "einem", "mein", "unser", "unsere", "kein", "jeder", "dieser", "diese",
)
_NOT_A_STREET = ("feldweg", "wanderweg", "radweg", "waldweg", "fußweg", "gehweg", "kirchweg")

# The GeoSN prints its own address on every sheet it issues. A street read out
# of a map extract next to any of these is the authority signing its work, not
# a street near the plot.
_AUTHORITY_MARKERS = ("landesamt", "geobasisinformation", "olbrichtplatz", "geosn", "vermessung")

# How far around a street name the authority's own signature is looked for.
# The window is a *segment*, not a character count: on a short listing a fixed
# 120 characters reaches from the description into the footer and suppresses
# the one street that matters.
_SEGMENT_SPLIT = re.compile(r"[.;\n\r|]+")


def confidence(source: IndizQuelle) -> float:
    return SOURCE_CONFIDENCE.get(source, 0.3)


def normalise_parcel_number(raw: str) -> tuple[str, str | None] | None:
    """``"790/11"`` to ``("790", "11")``, or ``None`` when it cannot be one.

    The denominator may be a letter -- 41/e is a valid parcel number -- so it
    stays text. A numerator of more than five digits or a denominator of more
    than four is not a parcel number at all but a misread one, and returning
    ``None`` here is what keeps it from resolving to a real but foreign parcel.
    """

    text = raw.strip().replace(" ", "")
    match = re.fullmatch(r"(\d{1,9})(?:/(\w{1,6}))?", text)
    if not match:
        return None
    zaehler, nenner = match.group(1), match.group(2)
    if len(zaehler.lstrip("0") or "0") > MAX_ZAEHLER_DIGITS:
        return None
    if nenner is not None and len(nenner) > MAX_NENNER_DIGITS:
        return None
    return str(int(zaehler)), (nenner if nenner else None)


def parcel_label(zaehler: str, nenner: str | None) -> str:
    return f"{zaehler}/{nenner}" if nenner else zaehler


def german_number(raw: str) -> float | None:
    """``"1.104,5"`` to ``1104.5``. German thousands dots, German decimal comma."""

    text = raw.strip().replace(" ", "").replace(".", "").replace(",", ".")
    try:
        return float(text)
    except ValueError:
        return None


@dataclass(frozen=True, slots=True)
class AreaStatement:
    """A plot area as the listing writes it, wording included.

    The wording is not decoration either: „502 m²“ is exact and the search may
    filter on it, „ca. 500 m²“ is rounded and may only rank. Getting that wrong
    in the permissive direction produces an unhelpful list; getting it wrong in
    the strict direction deletes the right parcel.
    """

    value: float
    wording: str
    upper: float | None = None
    # The sentence saying this plot is a piece of something larger, if there is
    # one. Then the figure describes a *future* parcel and no existing one, so
    # it cannot be a hard filter however exactly it is written.
    part_of: str | None = None

    @property
    def exact(self) -> bool:
        """Whether the figure may be used as a hard filter.

        A bare number is exact; anything hedged or bounded is not — and neither
        is a figure for a plot that is still to be surveyed out of a bigger
        parcel, however precisely it is stated.
        """

        return not self.wording and self.upper is None and self.part_of is None


def read_area(text: str) -> AreaStatement | None:
    """The first plot area in a piece of text, with how it was written."""

    for match in _AREA_RE.finditer(text):
        value = german_number(match.group("from"))
        if value is None or value < 10 or value > 10_000_000:
            continue
        upper = german_number(match.group("to")) if match.group("to") else None
        wording = (match.group("wording") or "").strip().lower()
        return AreaStatement(value=value, wording=wording, upper=upper)
    return None


# A plot that is a piece of a bigger parcel, not a parcel. Measured on a real
# advert (2418686487): „eine noch zu vermessende Teilfläche, die im Rahmen des
# Verkaufsprozesses exakt abgegrenzt und im Grundbuch eingetragen wird“, with a
# stated 748,50 m². There is no Flurstück with that area, because the plot does
# not have one yet — so a hard filter on it finds *some other* parcel of that
# size and calls it confirmed, which is the one kind of wrong answer this
# search is built to refuse.
#
# Worded as pending on purpose: „die Vermessung ist erfolgt“ describes a plot
# that does have its own parcel.
_PART_AREA_RE = re.compile(
    r"[^.!?]*\b("
    r"teilfl(?:ä|ae)che"
    r"|noch\s+zu\s+vermessen(?:d\w*)?"
    r"|wird\s+(?:noch\s+)?(?:neu\s+)?vermessen"
    r"|nach\s+(?:der\s+)?(?:noch\s+ausstehenden\s+)?vermessung"
    r"|vermessung\s+steht\s+noch\s+aus"
    r"|noch\s+(?:zu\s+)?(?:heraus)?zu\s*teilen"
    r"|nach\s+(?:der\s+)?teilung"
    r"|herausgemessen"
    r")[^.!?]*",
    re.IGNORECASE,
)


def describes_part_area(text: str | None) -> str | None:
    """The sentence saying the plot is still to be surveyed out of a parcel.

    Returned rather than a boolean because it is the *Beleg*: a figure the
    search refuses to filter on has to say which sentence took the decision.
    """

    if not text:
        return None
    match = _PART_AREA_RE.search(text)
    return " ".join(match.group(0).split()) if match else None


def _excerpt(text: str, start: int, end: int, pad: int = 45) -> str:
    """The sentence around a match, for the user to look up."""

    left = max(0, start - pad)
    right = min(len(text), end + pad)
    snippet = " ".join(text[left:right].split())
    return f"{'…' if left else ''}{snippet}{'…' if right < len(text) else ''}"


def _relation_before(text: str, start: int) -> Ortsbeziehung | None:
    """Which relation the words just before a place name express, if any."""

    window = text[max(0, start - _RELATION_WINDOW) : start]
    best: tuple[int, Ortsbeziehung] | None = None
    for relation, pattern in _RELATION_PATTERNS:
        for match in pattern.finditer(window):
            # Only a trigger that runs up to the name itself binds to it;
            # anything further back belongs to another clause.
            if match.end() >= len(window) - 2:
                if relation == "liegt_in" and _names_an_amenity(window[: match.start()]):
                    continue
                position = match.start()
                if best is None or position > best[0]:
                    best = (position, relation)
    return best[1] if best else None


# What „in X“ is about when one of these stands in front of it. The same trap
# „Anbindung an Leipzig“ already guards, one preposition over: „weiterführende
# Schulen in Roitzsch“ says where the schools are, not where the plot is — and
# Roitzsch is a real Gemarkung near Wurzen, a hundred kilometres from the
# Brehna listing that sentence came from, holding a parcel of exactly the
# stated size. An amenity is somewhere to go, so it can never place the plot.
_AMENITY_NOUNS = (
    "schule", "schulen", "grundschule", "oberschule", "gymnasium", "gymnasien",
    "kita", "kitas", "kindergarten", "kindergärten", "kindertagesstätte",
    "einkauf", "einkaufen", "einkaufsmöglichkeit", "einkaufsmöglichkeiten",
    "supermarkt", "supermärkte", "geschäfte", "läden", "apotheke", "apotheken",
    "arzt", "ärzte", "praxen", "klinik", "kliniken", "krankenhaus",
    "universität", "hochschule", "arbeitsplätze", "arbeitgeber",
    "bahnhof", "bahnhöfe", "flughafen", "anschluss", "anschlüsse",
    "verbindung", "verbindungen", "anbindung", "haltestelle", "haltestellen",
)


def _names_an_amenity(before: str) -> bool:
    """Whether the words in front of an „in“ name somewhere to go rather than to be.

    Only the last two words are read: „weiterführende Schulen in …“ puts an
    adjective between the noun and the preposition, and anything further back
    belongs to another clause.
    """

    words = re.findall(r"[\wäöüßÄÖÜ]+", before.lower())
    return any(word in _AMENITY_NOUNS for word in words[-2:])


def _indiz(
    counter: list[int],
    *,
    art: str,
    wert: str,
    text: str,
    quelle: IndizQuelle,
    beleg: str | None = None,
    schluessel: str | None = None,
    beziehung: Ortsbeziehung | None = None,
    sicherheit: float | None = None,
    teil_von: str | None = None,
) -> Indiz:
    counter[0] += 1
    return Indiz(
        id=f"i{counter[0]}",
        art=art,  # type: ignore[arg-type]
        wert=wert,
        text=text,
        beleg=beleg,
        quelle=quelle,
        sicherheit=confidence(quelle) if sicherheit is None else sicherheit,
        schluessel=schluessel,
        beziehung=beziehung,
        teil_von=teil_von,
    )


def district_matches(
    directory: GemarkungDirectory, name: str
) -> list[GemarkungEntry]:
    """Directory entries whose name is exactly this word.

    Exactly, not "contains": a substring search over 5 339 names turns
    „Grimma“ into a match for „Grimmaischer“ and „Bad“ into a match for two
    dozen places. The folded comparison is what makes „Moelkau“ find „Mölkau“.
    """

    needle = fold(name)
    exact = [entry for entry in directory.entries if fold(entry.name) == needle]
    if exact:
        return exact
    # The Flur suffix, and only as a fallback: an entry that carries the name
    # outright is the better answer, and „Kitzen" must not also collect
    # „Kitzenhausen". Measured 16.09.2026: 248 of the directory's base names
    # exist *only* with the suffix -- Kitzen, Pehritzsch, Krostitz, Eilenburg
    # with 48 of them -- and five of six freshly recorded adverts named one.
    return [entry for entry in directory.entries if fold(base_name(entry.name)) == needle]


def _districts_in_compound(
    directory: GemarkungDirectory, name: str, municipality: str | None
) -> list[GemarkungEntry]:
    """The cadastral districts a compound place name is made of.

    A city's Ortsteil is often two former villages joined with a hyphen, and
    both halves are Gemarkungen while the compound is none: „Burghausen-
    Rückmarsdorf“ is Burghausen 145507 and Rückmarsdorf 145614, both in Stadt
    Leipzig. Reading the compound as one name finds nothing, which is how a
    listing whose district is stated outright ended up searched across the
    whole of Stadt Leipzig — 31 candidates where there is exactly one.

    The municipality is what makes splitting safe, and without it nothing is
    returned. A part is a *derived* reading, not a stated one, so it may only
    stand when its own municipality is the one the listing names: „Grünau-
    Siedlung“ splits to a Gemarkung Grünau that exists twice, in Großolbersdorf
    and Langenweißbach, 80 km from the Leipzig plot — and that is the trap this
    guard exists for. Measured against all 63 Leipzig Ortsteile: every compound
    resolves to its own Gemarkungen, every namesake elsewhere is dropped, and
    the five „Grünau-…“ names contribute nothing rather than anchoring wrong.
    """

    if not municipality or "-" not in name:
        return []
    needle = fold(municipality)
    out: list[GemarkungEntry] = []
    for part in name.split("-"):
        if len(part) < 3:
            continue
        for entry in district_matches(directory, part):
            if entry.gemeinde and needle in fold(entry.gemeinde):
                out.append(entry)
    return out


def _known_district_names(directory: GemarkungDirectory) -> dict[str, list[GemarkungEntry]]:
    index: dict[str, list[GemarkungEntry]] = {}
    for entry in directory.entries:
        index.setdefault(fold(entry.name), []).append(entry)
    return index


def _word_positions(text: str) -> list[tuple[str, int, int]]:
    """Capitalised words and two-word pairs, with where they sit.

    Place names are capitalised in German, which removes almost every word in
    a listing before a single directory lookup happens. Pairs are included so
    „Bad Lausick“ and „Klein Zschocher“ are found as themselves.
    """

    tokens = [
        (match.group(0), match.start(), match.end())
        for match in re.finditer(r"[A-ZÄÖÜ][\wäöüßÄÖÜ\-]{2,}", text)
    ]
    out: list[tuple[str, int, int]] = list(tokens)
    for first, second in zip(tokens, tokens[1:]):
        # Adjacent in the source, not merely consecutive matches.
        if second[1] - first[2] == 1:
            out.append((f"{first[0]} {second[0]}", first[1], second[2]))
    return out


def collect_indicia(
    *,
    text: str | None = None,
    titel: str | None = None,
    adresse: str | None = None,
    gemarkung: str | None = None,
    flurstuecksnummer: str | None = None,
    flaeche_m2: float | None = None,
    flaeche_text: str | None = None,
    lat: float | None = None,
    lon: float | None = None,
    directory: GemarkungDirectory | None = None,
    given: list[Indiz] | None = None,
) -> list[Indiz]:
    """Every statement a listing makes about where its plot is.

    The order is the order of trust, so the first Indiz of a kind is the one a
    conflict defaults to. Nothing is queried here and nothing is discarded --
    contradictions are kept and reported, because a contradiction the search
    resolves quietly is one the user can never check.
    """

    counter = [0]
    found: list[Indiz] = []
    body = " ".join(part for part in (titel, text) if part)

    # 1 · What the caller states outright. A district and a number typed by a
    #     person, or read off an official extract, are the strongest thing here.
    if gemarkung:
        entries = district_matches(directory, gemarkung) if directory else []
        key = entries[0].schluessel if len(entries) == 1 else None
        if key is None and gemarkung.strip().isdigit():
            key = gemarkung.strip()
        found.append(
            _indiz(
                counter,
                art="gemarkung",
                wert=gemarkung.strip(),
                text=f"Gemarkung {gemarkung.strip()}",
                quelle="nutzer",
                beleg="von Hand eingetragen",
                schluessel=key,
                beziehung="liegt_in",
            )
        )
    if flurstuecksnummer:
        parsed = normalise_parcel_number(flurstuecksnummer)
        if parsed:
            label = parcel_label(*parsed)
            found.append(
                _indiz(
                    counter,
                    art="flurstueck",
                    wert=label,
                    text=f"Flurstück {label}",
                    quelle="nutzer",
                    beleg="von Hand eingetragen",
                )
            )

    # 2 · Indicia the caller gathered elsewhere -- image text recognition above
    #     all. They keep their own source and confidence.
    for indiz in given or []:
        counter[0] += 1
        found.append(indiz.model_copy(update={"id": indiz.id or f"i{counter[0]}"}))

    # 3 · The attribute list: a plot area with a number is the second-strongest
    #     statement there is, because it is the one a hard filter can use.
    statement = read_area(flaeche_text) if flaeche_text else None
    if statement is None and flaeche_m2:
        statement = AreaStatement(value=flaeche_m2, wording="")
    if statement is None and body:
        statement = read_area(body)
    if statement is not None:
        written = (flaeche_text or "").strip() or f"{statement.value:g} m²"
        found.append(
            _indiz(
                counter,
                art="flaeche",
                wert=f"{statement.value:g}",
                text=(
                    f"Grundstücksfläche {written}"
                    + ("" if statement.exact else " — gerundet, kein harter Filter")
                ),
                quelle="attribut" if (flaeche_text or flaeche_m2) else "fliesstext",
                beleg=written,
                sicherheit=0.8 if statement.exact else 0.55,
            )
        )

    # 4 · The location field. The pin derived from it is useless — measured
    #     6 235 m out — but the *names* it was geocoded from are not: the
    #     municipality is what separates the Plagwitz in Machern from the one in
    #     Leipzig, and the district in front of the postcode is the portal's own
    #     Ortsteil field. Both cost nothing.
    #
    #     Read before the body, because the body scan needs to know which name
    #     is the municipality: „in Leipzig – Stadtteil Burghausen-Rückmarsdorf“
    #     names the city and the district in one sentence, and Gemarkung Leipzig
    #     is not a rival reading of the district — it is the level above.
    location: list[Indiz] = []
    if adresse:
        location.append(
            _indiz(
                counter,
                art="ort",
                wert=adresse.strip(),
                text=f"Standortfeld der Anzeige: {adresse.strip()}",
                quelle="standortfeld",
                beleg=adresse.strip(),
                beziehung="liegt_in",
            )
        )
        location.extend(_from_location_field(adresse.strip(), counter, directory))

    # 5 · The body text: an explicit "Gemarkung X" first, then every directory
    #     name in the text, each with the relation that ties it to the plot.
    municipality = next((i.wert for i in location if i.art == "gemeinde"), None)
    if body:
        found.extend(_from_body(body, counter, directory, municipality))
    found.extend(location)

    # A name the listing gives as the *municipality* is not a rival reading of
    # which Gemarkung the plot sits in — „in Leipzig – Stadtteil Burghausen-
    # Rückmarsdorf“ names the city and the district in one sentence, and
    # Gemarkung Leipzig holds parcels of every size. Demoted only when another
    # district is actually on the table: „Sachsen - Bad Lausick“ names one place
    # that is a Gemarkung as well as a Gemeinde, and demoting it there leaves
    # the run with no anchor at all.
    if municipality:
        needle = fold(municipality)
        elsewhere = any(
            i.art == "gemarkung" and i.beziehung in ANCHORING and fold(i.wert) != needle
            for i in found
        )
        if elsewhere:
            for indiz in found:
                if indiz.art == "gemarkung" and fold(indiz.wert) == needle:
                    indiz.beziehung = "erwaehnt"
                    indiz.sicherheit = min(indiz.sicherheit, 0.2)
                    indiz.text = (
                        f"{indiz.wert} ist laut Standortfeld die Gemeinde — eine Ebene "
                        "über der gesuchten Gemarkung"
                    )
    if lat is not None and lon is not None:
        found.append(
            _indiz(
                counter,
                art="pin",
                wert=f"{lat:.6f},{lon:.6f}",
                text="Kartenpunkt der Anzeige — meist der geokodierte Ortsname, nicht das Grundstück",
                quelle="pin",
                beleg=f"{lat:.5f}, {lon:.5f}",
            )
        )

    found.sort(key=lambda indiz: -indiz.sicherheit)

    # One Indiz per district. „Burghausen-Rückmarsdorf“ stands in the location
    # field and twice in the prose, and each occurrence names the same two
    # Gemarkungen -- five rows in the Verlauf for two claims. The strongest
    # reading survives, which is the sorted order above; the anchors were never
    # affected (they are keyed by Gemarkungsschlüssel), the list the user checks
    # was. Districts only: a municipality named both in the prose and in the
    # location field is two readings with two different Belege, and the field's
    # one is what says the pin's *name* holds even though its coordinate does
    # not -- dropping it would drop that.
    seen: set[str] = set()
    out: list[Indiz] = []
    compounds = {
        fold(i.wert): i.teil_von for i in found if i.art == "gemarkung" and i.teil_von
    }
    for indiz in found:
        if indiz.art == "gemarkung":
            key = indiz.schluessel or fold(indiz.wert)
            if key in seen:
                continue
            seen.add(key)
            # „in Rückmarsdorf“ in the title and „Stadtteil Burghausen-
            # Rückmarsdorf“ in the prose are the same place said two ways, and
            # the stronger of the two wins the dedupe above -- so the compound
            # has to survive on whichever reading is kept, or the two halves
            # would be put to the user as rival readings.
            if indiz.teil_von is None and fold(indiz.wert) in compounds:
                indiz.teil_von = compounds[fold(indiz.wert)]
        out.append(indiz)
    return out


def _from_location_field(
    adresse: str, counter: list[int], directory: GemarkungDirectory | None
) -> list[Indiz]:
    """The municipality and the district a platform's location field states.

    One string, read structurally rather than searched for names: the portals
    write it in three orders and the postcode is the only fixed point in all
    three. Reading it as one opaque line was what left a listing whose district
    stands in the field with no cadastral anchor at all.
    """

    out: list[Indiz] = []
    match = _LOCALITY_RE.search(adresse) or _LOCALITY_TAIL_RE.search(adresse)
    if not match:
        return out

    groups = match.groupdict()
    tail, behind = groups.get("tail"), groups.get("behind")
    # „04668 Sachsen – Grimma“: the state stands where the municipality would,
    # and the municipality is behind the dash.
    if tail and federal_state(tail) == tail:
        municipality = behind
    else:
        municipality = tail
    if municipality:
        out.append(
            _indiz(
                counter,
                art="gemeinde",
                wert=municipality,
                text=(
                    f"Gemeinde {municipality} laut Standortfeld — grenzt gleichnamige "
                    "Gemarkungen ein"
                ),
                quelle="standortfeld",
                beleg=adresse,
                beziehung="liegt_in",
            )
        )

    district = groups.get("district")
    if not district or directory is None:
        return out

    # The name itself, when the directory knows it. Every entry of that name is
    # offered, the way a name in the running text is — the municipality above
    # sorts out which one afterwards. A street stands in this slot on one of the
    # three portals, so a name the directory does not know contributes nothing.
    entries = district_matches(directory, district)
    derived = False
    if not entries:
        entries = _districts_in_compound(directory, district, municipality)
        derived = True
    for entry in entries if derived else entries[:1]:
        out.append(
            _indiz(
                counter,
                art="gemarkung",
                wert=entry.name if derived else district,
                text=(
                    f"{district} im Standortfeld ist keine Gemarkung — {entry.name} "
                    f"{entry.schluessel} ist ein Teil davon"
                    if derived
                    else f"Das Standortfeld nennt {district} als Ortsteil"
                ),
                quelle="standortfeld",
                beleg=adresse,
                schluessel=entry.schluessel if derived or len(entries) == 1 else None,
                beziehung="liegt_in",
                # A stated name outranks one taken out of a compound, and both
                # stay under an explicit „Gemarkung X“ in the text.
                sicherheit=0.5 if derived else 0.62,
                teil_von=district if derived else None,
            )
        )
    return out


def _from_body(
    body: str,
    counter: list[int],
    directory: GemarkungDirectory | None,
    municipality: str | None = None,
) -> list[Indiz]:
    """Parcel numbers, districts and streets read out of running text.

    ``municipality`` is the town the location field named. It is what makes a
    compound place name in the prose safe to take apart — see
    ``_districts_in_compound``.
    """

    out: list[Indiz] = []

    for match in _PARCEL_RE.finditer(body):
        parsed = normalise_parcel_number(
            f"{match.group(1)}/{match.group(2)}" if match.group(2) else match.group(1)
        )
        if not parsed:
            continue
        label = parcel_label(*parsed)
        if any(indiz.art == "flurstueck" and indiz.wert == label for indiz in out):
            continue
        out.append(
            _indiz(
                counter,
                art="flurstueck",
                wert=label,
                text=f"Flurstück {label} im Text",
                quelle="fliesstext",
                beleg=_excerpt(body, match.start(), match.end()),
            )
        )

    # A place named as the municipality an Ortsteil belongs to is not a rival
    # reading of where the plot is -- it is the level above, and it is what
    # tells two districts of the same name apart. Collected first so the
    # district scan below knows which names are already spoken for.
    municipalities: dict[str, tuple[int, int]] = {}
    stated_districts: dict[str, tuple[int, int]] = {}
    for pattern in (_OT_NAMED_RE, _OT_BEFORE_RE, _OT_PLAIN_RE):
        for match in pattern.finditer(body):
            groups = match.groupdict()
            name = groups["municipality"]
            municipalities.setdefault(fold(name), match.span("municipality"))
            if groups.get("district"):
                stated_districts.setdefault(
                    fold(groups["district"]), match.span("district")
                )

    for _, (start, end) in municipalities.items():
        name = body[start:end]
        out.append(
            _indiz(
                counter,
                art="gemeinde",
                wert=name,
                text=(
                    f"{name} ist laut Text die Gemeinde, nicht der Ortsteil — eine Ebene "
                    "über der gesuchten Gemarkung, und genau das, was gleichnamige "
                    "Gemarkungen auseinanderhält"
                ),
                quelle="fliesstext",
                beleg=_excerpt(body, start, end),
                beziehung="liegt_in",
                sicherheit=0.5,
            )
        )

    # „Ortsteil Plagwitz von Machern“ names the district outright. That is a
    # far stronger statement than a name the text merely contains, and it is
    # the one the search should anchor on.
    for _, (start, end) in stated_districts.items():
        name = body[start:end]
        out.append(
            _indiz(
                counter,
                art="gemarkung",
                wert=name,
                text=f"Der Text nennt {name} ausdrücklich als Ortsteil",
                quelle="fliesstext",
                beleg=_excerpt(body, start, end),
                beziehung="liegt_in",
                sicherheit=0.68,
            )
        )

    named: set[str] = set(stated_districts)
    for match in _DISTRICT_RE.finditer(body):
        name = match.group(1).strip(" .:-")
        entries = district_matches(directory, name) if directory else []
        named.add(fold(name))
        out.append(
            _indiz(
                counter,
                art="gemarkung",
                wert=name,
                text=f"Der Text nennt die Gemarkung {name}",
                quelle="fliesstext",
                beleg=_excerpt(body, match.start(), match.end()),
                schluessel=entries[0].schluessel if len(entries) == 1 else None,
                beziehung="liegt_in",
                # An explicit "Gemarkung X" is a cadastral statement, not a
                # place mention; it outranks a bare name in the same text.
                sicherheit=0.7,
            )
        )

    if directory is not None:
        index = _known_district_names(directory)
        for word, start, end in _word_positions(body):
            key = fold(word)
            if key in named:
                continue
            if key not in index:
                # A compound Ortsteil the directory does not carry, whose halves
                # it does: „Stadtteil Burghausen-Rückmarsdorf“ is Burghausen and
                # Rückmarsdorf, and reading it as one name finds neither. Only
                # where the text places the plot, only one word (the pair
                # „Stadtteil Burghausen-Rückmarsdorf“ is not a place name), and
                # only with the municipality's consent -- the guard is in the
                # helper.
                if " " in word or _relation_before(body, start) != "liegt_in":
                    continue
                named.add(key)
                for entry in _districts_in_compound(directory, word, municipality):
                    out.append(
                        _indiz(
                            counter,
                            art="gemarkung",
                            wert=entry.name,
                            text=(
                                f"{word} ist keine Gemarkung — {entry.name} "
                                f"{entry.schluessel} ist ein Teil davon"
                            ),
                            quelle="fliesstext",
                            beleg=_excerpt(body, start, end),
                            schluessel=entry.schluessel,
                            beziehung="liegt_in",
                            sicherheit=0.5,
                            teil_von=word,
                        )
                    )
                continue
            named.add(key)
            entries = index[key]
            relation = _relation_before(body, start)
            # Every occurrence, not the first: „Grimma" appears once as the
            # municipality Großbothen belongs to and once as „die ca. 6 km
            # entfernte Kreisstadt". Reading only the first turns a place the
            # text puts at a distance into the anchor.
            if _named_as_distant(body, key):
                relation = "entfernt_von"
            elif key in municipalities:
                relation = "erwaehnt"
            out.append(
                _indiz(
                    counter,
                    art="gemarkung",
                    wert=word,
                    text=_place_sentence(word, relation, len(entries)),
                    quelle="fliesstext",
                    beleg=_excerpt(body, start, end),
                    schluessel=entries[0].schluessel if len(entries) == 1 else None,
                    beziehung=relation or "erwaehnt",
                    # A place the text places the plot *in* is worth far more
                    # than one it merely names -- and one it names as being
                    # kilometres away is worth less than nothing as an anchor.
                    sicherheit={"liegt_in": 0.6, "liegt_an": 0.45}.get(relation or "", 0.2),
                )
            )

    for match in _STREET_RE.finditer(body):
        name = match.group(1).strip()
        if _in_authority_block(body, match.start()) or not _is_street_name(name):
            continue
        if any(indiz.art == "strasse" and indiz.wert == name for indiz in out):
            continue
        out.append(
            _indiz(
                counter,
                art="strasse",
                wert=name,
                text=f"Straße {name} — innerhalb einer Gemarkung nahezu eindeutig, allein wertlos",
                quelle="fliesstext",
                beleg=_excerpt(body, match.start(), match.end()),
                sicherheit=0.4,
            )
        )

    return out


def _named_as_distant(body: str, folded_name: str) -> bool:
    """Whether any occurrence of a name is preceded by a distance.

    One statement of distance outweighs any number of neutral mentions: „die
    ca. 6 km entfernte Kreisstadt Grimma" is the sentence that settles that the
    plot is not in Grimma, however often the name appears elsewhere.
    """

    _, pattern = _RELATION_PATTERNS[2]
    for word, start, _ in _word_positions(body):
        if fold(word) != folded_name:
            continue
        window = body[max(0, start - _RELATION_WINDOW) : start]
        if any(m.end() >= len(window) - 2 for m in pattern.finditer(window)):
            return True
    return False


def _is_street_name(name: str) -> bool:
    """Whether a match ending in -weg or -platz is plausibly a street.

    German capitalises every noun, so the capital letter that finds a street
    also finds „Ihr Platz zum Träumen“ and „einen befahrbaren Feldweg“. Two
    cheap rules remove both: a leading article or pronoun makes it a sentence,
    and a handful of generic paths are never addresses.
    """

    words = name.split()
    if words and words[0].lower() in _NOT_A_STREET_PREFIX:
        return False
    return name.lower() not in _NOT_A_STREET


def _in_authority_block(body: str, position: int) -> bool:
    """Whether a street sits inside the authority's own address block.

    Bounded by the sentence it stands in. A fixed character window reaches
    across the whole of a short listing, and then the GeoSN's footer suppresses
    the street the listing is actually about.
    """

    start = 0
    for match in _SEGMENT_SPLIT.finditer(body):
        if match.start() > position:
            break
        start = match.end()
    end = next(
        (m.start() for m in _SEGMENT_SPLIT.finditer(body, position)), len(body)
    )
    segment = body[start:end].lower()
    return any(marker in segment for marker in _AUTHORITY_MARKERS)


def _place_sentence(name: str, relation: Ortsbeziehung | None, count: int) -> str:
    """The German line under a place name. Composed, never written by a model."""

    ambiguous = "" if count <= 1 else f" — der Name kommt {count}-mal im Verzeichnis vor"
    if relation == "liegt_in":
        return f"Der Text setzt das Grundstück nach {name}{ambiguous}"
    if relation == "liegt_an":
        return f"Der Text nennt {name} als angrenzend{ambiguous}"
    if relation == "entfernt_von":
        return f"{name} wird als entfernt beschrieben — spricht gegen diesen Ort{ambiguous}"
    return f"{name} wird erwähnt, ohne zu sagen wie{ambiguous}"


__all__ = [
    "AreaStatement",
    "federal_state",
    "outside_saxony",
    "SOURCE_CONFIDENCE",
    "collect_indicia",
    "confidence",
    "german_number",
    "normalise_parcel_number",
    "parcel_label",
    "read_area",
]
