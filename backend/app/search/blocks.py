"""Cutting a listing into the blocks it was actually written in.

Half of an advert is not prose. It is a heading, a bullet list and a column of
„Label: Wert" lines, and every reader in this package was written as if it were
one long sentence. Three failures follow from that, and all three are visible
in the recorded adverts:

* **A window reaches across a boundary.** The readers look 45 to 60 characters
  left of a match for the word that binds it. Across a line break that word
  belongs to another statement: „# Lagebeschreibung Thräna ist …" glues a
  heading to a subject, and the guards that stop it from mattering — the
  amenity nouns, the relation window — are each a patch on the same hole.
* **A number loses its label.** Advert 3464790207 writes „Grundstücksfläche:
  ca. 711 m²" as a pair; advert 3381469778 writes „bebaubare Fläche von ca.
  240 m²" as prose. Read as one string both are just numbers followed by m²,
  and only their order decides which one the search filters on.
* **A sentence about the development is read as one about the plot.** Advert
  3441433250 says „20 voll erschlossene Grundstücke zwischen 360 und 800 m²"
  and states 590 m² in its attribute list. The prose reader returns 360.

So the text is cut first, once, and the readers work inside a block. After that
„Bushaltestelle ‚Kitzen': ca. 300 m" is a label and a value, and nothing has to
understand German to see it.

The rules are the shapes the four recorded portals actually write, not a
grammar: a blank line ends a block, `#` marks a heading, a leading dash or star
marks a bullet, a short line without terminal punctuation is a heading, and a
`Label: Wert` line is a pair. Nothing here looks anything up.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# What a line can be. German, because these are the names the protocol and the
# notes use for them, and they are data about the document rather than code
# identifiers -- the same rule the API field names follow.
KINDS = ("ueberschrift", "paar", "punkt", "absatz")

# A heading is short and does not end like a sentence. Measured over the 16
# recorded adverts: „Eckdaten", „Besondere Merkmale:", „Willkommen in
# Eilenburg", „Anbieterauskunft:" all fit, and no paragraph of prose does.
MAX_HEADING_CHARS = 60

# A label is short too, and it is what stands in front of the colon. „Ort",
# „Grundstücksfläche", „Autobahnanschlussstelle A38 ‚Leipzig-Südwest'" are
# labels; a sentence that happens to contain a colon is not.
MAX_LABEL_CHARS = 60

_HEADING_MARK = re.compile(r"^\s{0,3}#{1,6}\s+")
_BULLET_MARK = re.compile(r"^\s{0,3}(?:[-–—*•‣·]|\d{1,2}[.)])\s+")
# The colon binds only when what stands in front of it is a label. Three
# measured conditions, and each one removes a shape the recordings contain:
#
# * **Whitespace after the colon.** „https://www.ohne-makler.net/…" is a line
#   in advert 3441433250 and was read as the pair „https" = „//www…".
# * **At most five words, and not beginning with an article.** The same advert
#   writes „Die Verkehrsanbindung ist hervorragend: Über den …" — a sentence
#   with a colon in it, read as a label for half a paragraph.
# * **No finite verb.** „Familien profitieren von der nahen Infrastruktur:" is
#   four words and starts with a noun; the verb is what says it is a clause.
_PAIR = re.compile(rf"^(?P<label>[^:\n]{{2,{MAX_LABEL_CHARS}}}?):(?:\s+(?P<value>\S.*))?$")
_SENTENCE_END = re.compile(r"[.!?]\s*$")

MAX_LABEL_WORDS = 5

# A label is a noun phrase. These begin a clause, and no label in the recorded
# adverts begins with one.
_NOT_A_LABEL_START = frozenset(
    "der die das den dem des ein eine einen einem einer unser unsere ihr ihre "
    "mein meine wir sie hier dort auch nur noch dieses diese dieser".split()
)

# A finite verb turns a noun phrase into a statement. Not a conjugation table --
# the handful that actually occur in advert prose.
_CLAUSE_VERBS = frozenset(
    "ist sind war waren wird werden hat haben hatte kann können sollen soll "
    "liegt liegen bietet bieten profitieren erreichen finden steht stehen "
    "befindet befinden erfolgt erfolgen gibt".split()
)


# A label never addresses the reader. „Stellen Sie sich vor:" is four words,
# starts with a noun-shaped word and carries no verb from the list above — the
# pronoun is what gives away that it is advertising copy, and German puts one
# in every imperative.
_ADDRESSES_THE_READER = frozenset("sie ihnen ihr ihre ihren uns euch dich".split())


def _reads_as_label(label: str) -> bool:
    words = label.replace("-", " ").split()
    if not words or len(words) > MAX_LABEL_WORDS:
        return False
    lowered = [word.strip("„“\"'()").casefold() for word in words]
    if lowered[0] in _NOT_A_LABEL_START:
        return False
    if any(word in _ADDRESSES_THE_READER for word in lowered[1:]):
        return False
    return not any(word in _CLAUSE_VERBS for word in lowered)


@dataclass(frozen=True, slots=True)
class Block:
    """One written unit of a listing, with where it sits in the original.

    ``text`` is the value for a pair and the whole line otherwise, always with
    the marker removed. ``start`` and ``end`` are offsets into the body that was
    split, so a reader that found something at a position can ask which block it
    was in and clamp its window to it.
    """

    kind: str
    text: str
    start: int
    end: int
    label: str | None = None

    @property
    def is_pair(self) -> bool:
        return self.kind == "paar"

    def contains(self, position: int) -> bool:
        return self.start <= position < self.end


def joined(*parts: str | None) -> str:
    """A listing's title and body as one string, with the join a block boundary.

    A blank line, not a space. „Ihr neues Wohngrundstück in Groitzsch" and „Zum
    Verkauf stehen zwei Baugrundstücke …" are two statements, and joining them
    with a space put the second one inside the first one's window.
    """

    return "\n\n".join(part.strip() for part in parts if part and part.strip())


def split_blocks(body: str | None) -> list[Block]:
    """Every block of a listing, in the order it was written.

    Line by line, because that is how these documents are written and because
    anything cleverer would need to know German. A run of prose lines with no
    blank line between them stays one paragraph -- advert 3441433250 writes
    three sentences on three lines and means one block.
    """

    if not body:
        return []

    out: list[Block] = []
    paragraph: list[tuple[str, int, int]] = []
    position = 0

    def flush() -> None:
        if not paragraph:
            return
        text = " ".join(line for line, _, _ in paragraph).strip()
        if text:
            out.append(
                Block(
                    kind="ueberschrift" if _reads_as_heading(text, len(paragraph)) else "absatz",
                    text=text,
                    start=paragraph[0][1],
                    end=paragraph[-1][2],
                )
            )
        paragraph.clear()

    for raw in body.split("\n"):
        start, end = position, position + len(raw)
        position = end + 1  # the newline that split() removed
        line = raw.strip()
        if not line:
            flush()
            continue

        heading = _HEADING_MARK.match(raw)
        if heading:
            flush()
            out.append(Block("ueberschrift", line[heading.end() - heading.start() :].strip(), start, end))
            continue

        bullet = _BULLET_MARK.match(raw)
        stripped = line[bullet.end() - bullet.start() :].strip() if bullet else line
        pair = _PAIR.match(stripped)
        if pair and pair.group("value") and _reads_as_label(pair.group("label")):
            flush()
            out.append(
                Block(
                    "paar",
                    pair.group("value").strip(),
                    start,
                    end,
                    label=pair.group("label").strip(),
                )
            )
            continue
        if bullet:
            flush()
            out.append(Block("punkt", stripped, start, end))
            continue

        paragraph.append((line, start, end))

    flush()
    return out


def _reads_as_heading(text: str, lines: int) -> bool:
    """Whether a paragraph of one line is a heading rather than a sentence.

    One line, short, and not ending like a sentence. „Besondere Merkmale:" ends
    in a colon and is a heading; „Eckdaten" ends in nothing and is one; the
    first sentence of an advert ends in a full stop and is not.
    """

    return lines == 1 and len(text) <= MAX_HEADING_CHARS and not _SENTENCE_END.search(text)


def block_at(blocks: list[Block], position: int) -> Block | None:
    """The block a position falls in, or nothing when it falls between two."""

    for block in blocks:
        if block.contains(position):
            return block
    return None


def bounds_at(blocks: list[Block], position: int, fallback: tuple[int, int]) -> tuple[int, int]:
    """How far a reader may look around a position without leaving its block.

    ``fallback`` is what to answer when the position is in no block at all --
    inside the whitespace between two, which a match never is but an excerpt's
    padding can be.
    """

    block = block_at(blocks, position)
    return (block.start, block.end) if block else fallback


def fold(text: str) -> str:
    """Lowercase, umlauts written out, spaces and hyphens gone.

    „Grundstücksfläche", „Grundstücks-Fläche" and „GRUNDSTUECKSFLAECHE" are one
    label, and a portal writes all three.
    """

    out = text.casefold()
    for source, target in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss")):
        out = out.replace(source, target)
    return re.sub(r"[\s\-.]", "", out)


def labelled(blocks: list[Block], *words: str) -> list[Block]:
    """The pairs whose label contains one of these words, folded."""

    needles = [fold(word) for word in words]
    return [
        block
        for block in blocks
        if block.is_pair
        and block.label
        and any(needle in fold(block.label) for needle in needles)
    ]


__all__ = [
    "Block",
    "fold",
    "joined",
    "KINDS",
    "MAX_HEADING_CHARS",
    "MAX_LABEL_WORDS",
    "block_at",
    "bounds_at",
    "labelled",
    "split_blocks",
]
