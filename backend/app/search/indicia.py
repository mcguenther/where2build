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

from ..gemarkung_index import GemarkungDirectory, GemarkungEntry, fold
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
    ("liegt_an", re.compile(r"(?:direkt\s+)?(?:an|am)\s+(?:der\s+|dem\s+)?", re.IGNORECASE)),
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

# „Großbothen, einem OT von Grimma" says two different things about two
# different places: Großbothen is where the plot is, and Grimma is the
# municipality Großbothen belongs to. Reading both as candidate cadastral
# districts is what made the reference listing look contested when it is not --
# and it is why the same text scores Grimma as often as Großbothen.
_MUNICIPALITY_RE = re.compile(
    r"(?:einem?\s+|ein\s+)?(?:OT|Ortsteil|Stadtteil|Gemeindeteil)\s+(?:von|der|des)\s+"
    r"([A-ZÄÖÜ][\wäöüßÄÖÜ\-]{2,}(?:[ -][A-ZÄÖÜ][\wäöüßÄÖÜ\-]+)?)",
)

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

    @property
    def exact(self) -> bool:
        """Whether the figure may be used as a hard filter.

        A bare number is exact; anything hedged or bounded is not.
        """

        return not self.wording and self.upper is None


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
                position = match.start()
                if best is None or position > best[0]:
                    best = (position, relation)
    return best[1] if best else None


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
    )


def _district_matches(
    directory: GemarkungDirectory, name: str
) -> list[GemarkungEntry]:
    """Directory entries whose name is exactly this word.

    Exactly, not "contains": a substring search over 5 339 names turns
    „Grimma“ into a match for „Grimmaischer“ and „Bad“ into a match for two
    dozen places. The folded comparison is what makes „Moelkau“ find „Mölkau“.
    """

    needle = fold(name)
    return [entry for entry in directory.entries if fold(entry.name) == needle]


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
        entries = _district_matches(directory, gemarkung) if directory else []
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

    # 4 · The body text: an explicit "Gemarkung X" first, then every directory
    #     name in the text, each with the relation that ties it to the plot.
    if body:
        found.extend(_from_body(body, counter, directory))

    # 5 · The location field, and last of all the pin.
    if adresse:
        found.append(
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
    return found


def _from_body(
    body: str, counter: list[int], directory: GemarkungDirectory | None
) -> list[Indiz]:
    """Parcel numbers, districts and streets read out of running text."""

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
    # reading of where the plot is -- it is the level above. Collected first so
    # the district scan below knows to weigh it down rather than treat it as a
    # competing cadastral district.
    municipalities: dict[str, tuple[int, int]] = {}
    for match in _MUNICIPALITY_RE.finditer(body):
        municipalities[fold(match.group(1))] = (match.start(1), match.end(1))
    for name_key, (start, end) in municipalities.items():
        out.append(
            _indiz(
                counter,
                art="gemeinde",
                wert=body[start:end],
                text=(
                    f"{body[start:end]} ist laut Text die Gemeinde, nicht der Ortsteil — "
                    "eine Ebene über der gesuchten Gemarkung"
                ),
                quelle="fliesstext",
                beleg=_excerpt(body, start, end),
                beziehung="liegt_in",
                sicherheit=0.5,
            )
        )

    named: set[str] = set()
    for match in _DISTRICT_RE.finditer(body):
        name = match.group(1).strip(" .:-")
        entries = _district_matches(directory, name) if directory else []
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
            if key in named or key not in index:
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
        if _in_authority_block(body, match.start()):
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
    "SOURCE_CONFIDENCE",
    "collect_indicia",
    "confidence",
    "german_number",
    "normalise_parcel_number",
    "parcel_label",
    "read_area",
]
